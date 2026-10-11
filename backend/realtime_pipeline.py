"""Bounded online reconstruction with measured motion and asynchronous defects.

Every frame is detected/tracked. Optical-flow steps only seed a directly checked
anchor/keyframe measurement; they never enter the surface atlas on their own.
Disconnected segments, unsegmented views and uncertain identities stay explicit.
"""
from collections import deque, Counter
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
import time
import threading

import cv2
import numpy as np

import algorithm as a
from fast_rotation import _track_fit, estimate_feature_rotation
from surface_atlas import SurfaceAtlas


@dataclass
class OnlineSegment:
    model: object
    views: list
    axes: list
    positions: list
    radii: np.ndarray
    longitude_start: float
    direction: float
    rotations: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    atlas: object = None
    fused: int = 0

    def advance(self, settings):
        if self.atlas is None:
            self.atlas = SurfaceAtlas(self.model, settings, self.longitude_start, self.direction, self.radii)
        while self.fused < len(self.views):
            view = self.views[self.fused]
            if not view.defect_masks:
                break
            self.atlas.append(view, self.axes[self.fused], a._ellipse(view.object_mask).center,
                              self.positions[self.fused])
            self.fused += 1

    def result(self, diagnostics, captured):
        if self.fused < 2:
            return None
        return self.atlas.result(self.rotations[:self.fused - 1], self.errors[:self.fused - 1],
                [view.frame_index for view in self.views[:self.fused]], diagnostics, captured)


@dataclass
class OnlineTrack:
    recent: deque = field(default_factory=lambda: deque(maxlen=8))
    anchor: object = None
    previous: object = None
    chain: np.ndarray = field(default_factory=lambda: np.eye(3))
    chain_valid: bool = True
    segments: list = field(default_factory=list)
    current: object = None
    diagnostics: deque = field(default_factory=lambda: deque(maxlen=120))
    captured_frames: deque = field(default_factory=lambda: deque(maxlen=120))
    captures: int = 0
    recoveries: int = 0
    ending: bool = False
    ellipses: dict = field(default_factory=dict)


class RealtimePipeline(a.NaartjiePipeline):
    inspection_profile = 'realtime'

    def __init__(self, *args, segmentation_batch_size=4, maximum_keyframes=32,
                 recovery_searches=1, motion_workers=4, **kwargs):
        super().__init__(*args, **kwargs)
        if not 1 <= segmentation_batch_size <= 8 or not 2 <= maximum_keyframes <= 120:
            raise ValueError('Invalid realtime batch or keyframe buffer size')
        if recovery_searches < 0 or motion_workers < 1:
            raise ValueError('Recovery searches must be nonnegative and motion workers positive')
        self.batch_size = segmentation_batch_size
        self.maximum_keyframes = maximum_keyframes
        self.recovery_searches = recovery_searches
        self.motion_workers = motion_workers
        self.motion_pool = ThreadPoolExecutor(max_workers=motion_workers, thread_name_prefix='fruit-motion')
        self.capture_futures = []
        self.parallel_capture = False
        self.stats_lock = threading.Lock()
        self.online = {}
        self.requests = []
        self.batches = deque()
        self.counters = Counter()
        self.seconds = Counter()
        self.frame_times = deque(maxlen=600)
        self.defect_latencies = deque(maxlen=600)
        self.capture_origin = None
        self.closed = False

    def _count(self, name, increment=1):
        with self.stats_lock:
            self.counters[name] += increment

    def _split(self, state, view, reason):
        state.diagnostics.append(dict(method='online_segment', status='split',
                target_frame=view.frame_index, reason=reason))
        state.anchor = state.previous = view
        state.chain = np.eye(3)
        state.chain_valid = True
        state.current = None
        # Retain the most supported previous segment and the new active segment.
        if len(state.segments) > 1:
            state.segments = [max(state.segments, key=lambda item: item.positions[-1])]
        self._count('segment_splits')

    def _model(self, state, view):
        candidates = {item.frame_index: item for item in state.recent}
        candidates[state.anchor.frame_index] = state.anchor
        candidates[view.frame_index] = view
        views = [candidates[index] for index in sorted(candidates)]
        state.ellipses = {index: state.ellipses.get(index) for index in candidates}
        for item in views:
            if state.ellipses[item.frame_index] is None:
                state.ellipses[item.frame_index] = a._ellipse(item.object_mask)
        model = a.fit_spheroid(views, self.settings,
                              ellipses=[state.ellipses[item.frame_index] for item in views])
        return model, {item.frame_index: index for index, item in enumerate(views)}

    def _keyframe(self, track_id, state, view, model, lookup, force=False):
        gap = view.frame_index - state.anchor.frame_index
        if gap <= 0:
            return
        record = dict(method='online_keyframe', source_frame=state.anchor.frame_index,
                      target_frame=view.frame_index, source_frame_gap=gap)
        pair = a._subset_spheroid(model, [lookup[state.anchor.frame_index], lookup[view.frame_index]])
        minimum = 3. if force else self.settings.keyframe_minimum_rotation_deg
        settings = replace(self.settings, min_pair_angle_deg=.25, feature_rotation_fallback=False)
        try:
            rotation, error = estimate_feature_rotation(state.anchor, view, pair, 0, settings, record,
                              initial_rotation=state.chain if state.chain_valid else None)
        except a.MappingError as failure:
            self._count('feature_rejections')
            if state.recoveries >= self.recovery_searches:
                record.update(status='rejected', reason=str(failure))
                state.diagnostics.append(record)
                return
            state.recoveries += 1
            self._count('recovery_searches')
            try:
                legacy = replace(settings, rotation_estimator='search')
                rotation, error = a.estimate_rotation(state.anchor, view, pair, 0, legacy, record)
                a._verify_keyframe_rotation(state.anchor, view, pair, rotation, legacy, record)
                record['recovery_search'] = True
            except a.MappingError as recovery_failure:
                record.update(status='rejected', reason=str(recovery_failure))
                state.diagnostics.append(record)
                return
        vector = np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel()
        axis = 0 if self.settings.rotation_axis == 'x' else 1
        if abs(vector[axis]) < minimum:
            record.update(status='skipped', reason='Measured turn below keyframe spacing',
                          rotation_vector_deg=vector.tolist())
            state.diagnostics.append(record)
            return
        if state.current is None:
            axes, radii, longitudes, direction, positions = a._map_trajectory(pair, [rotation], self.settings)
            if direction == 0 or not .25 <= np.rad2deg(positions[-1]) <= self.settings.max_pair_angle_deg + 12:
                state.diagnostics.append({**record, 'status': 'rejected', 'reason': 'Unordered fruit longitude'})
                return
            segment = OnlineSegment(pair, [state.anchor, view], list(axes), list(positions),
                                    radii, longitudes[0], direction, [rotation], [error])
            state.current = segment
            state.segments.append(segment)
            self.requests.extend([(track_id, state.anchor), (track_id, view)])
        else:
            segment = state.current
            if len(segment.views) >= self.maximum_keyframes:
                self._split(state, view, 'Bounded keyframe buffer reached; no pose bridge assumed')
                return
            if max(abs(pair.A / segment.model.A - 1), abs(pair.B / segment.model.B - 1)) > .05:
                self._split(state, view, 'Shape changed by more than 5%; fixed atlas geometry no longer supported')
                return
            axes = rotation @ segment.axes[-1]
            ray = axes.T @ np.array([0., 0., 1.])
            longitude = np.arctan2(ray[2] / segment.radii[2], ray[0] / segment.radii[0])
            previous_ray = segment.axes[-1].T @ np.array([0., 0., 1.])
            previous_longitude = np.arctan2(previous_ray[2] / segment.radii[2], previous_ray[0] / segment.radii[0])
            increment = segment.direction * np.arctan2(np.sin(longitude - previous_longitude),
                                                        np.cos(longitude - previous_longitude))
            if not .25 <= np.rad2deg(increment) <= self.settings.max_pair_angle_deg + 12:
                self._split(state, view, 'Unordered fruit longitude; disconnected segments remain separate')
                return
            segment.views.append(view)
            segment.axes.append(axes)
            segment.positions.append(segment.positions[-1] + increment)
            segment.rotations.append(rotation)
            segment.errors.append(error)
            self.requests.append((track_id, view))
        record.update(status='accepted', rotation_vector_deg=vector.tolist(), error=error)
        state.diagnostics.append(record)
        state.anchor = view
        state.chain = np.eye(3)
        state.chain_valid = True
        self._count('accepted_keyframes')

    def _advance(self, track_id, state, view):
        state.recent.append(view)
        state.captured_frames.append(view.frame_index)
        state.captures += 1
        if state.anchor is None:
            state.anchor = state.previous = view
            return
        gap = view.frame_index - state.anchor.frame_index
        if view.frame_index - state.previous.frame_index > self.settings.maximum_view_index_gap:
            self._split(state, view, 'Missing original capture frames')
            return
        if gap > self.settings.maximum_keyframe_index_gap:
            self._split(state, view, 'Direct anchor measurement window exceeded')
            return
        try:
            model, lookup = self._model(state, view)
        except a.MappingError:
            self._split(state, view, 'Silhouettes cannot support a local spheroid')
            return
        try:
            pair = a._subset_spheroid(model, [lookup[state.previous.frame_index], lookup[view.frame_index]])
            forward, _ = _track_fit(state.previous, view, pair, 0, self.settings, maximum_features=40)
            reverse_pair = a._subset_spheroid(pair, [1, 0])
            backward, _ = _track_fit(view, state.previous, reverse_pair, 0,
                         replace(self.settings, rotation_direction=-self.settings.rotation_direction),
                         maximum_features=40, initial_rotation=forward.T)
            disagreement = float(np.rad2deg(np.linalg.norm(cv2.Rodrigues(backward @ forward)[0])))
            if disagreement > self.settings.keyframe_inverse_tolerance_deg:
                raise a.MappingError('Consecutive peel estimates disagree')
            if state.chain_valid:
                state.chain = forward @ state.chain
            self._count('flow_steps')
        except a.MappingError as failure:
            state.chain_valid = False
            self._count('flow_rejections')
            state.diagnostics.append(dict(method='online_flow', status='rejected', target_frame=view.frame_index,
                                          reason=str(failure)))
        state.previous = view
        axis = 0 if self.settings.rotation_axis == 'x' else 1
        measured = abs(np.rad2deg(cv2.Rodrigues(state.chain)[0])[axis, 0])
        if measured >= self.settings.keyframe_minimum_rotation_deg or gap == self.settings.maximum_keyframe_index_gap:
            self._keyframe(track_id, state, view, model, lookup,
                           force=gap == self.settings.maximum_keyframe_index_gap)
        if gap == self.settings.maximum_keyframe_index_gap and state.anchor is not view:
            self._split(state, view, 'Anchor window exhausted without a verified keyframe')

    def add_tracked_detection(self, frame, track_id, bbox_xyxy, frame_index):
        if self.parallel_capture:
            future = self.motion_pool.submit(self._capture, frame, track_id, bbox_xyxy, frame_index)
            self.capture_futures.append((track_id, future))
            return True
        return self._capture(frame, track_id, bbox_xyxy, frame_index)

    def _capture(self, frame, track_id, bbox_xyxy, frame_index):
        started = time.perf_counter()
        captured = super().add_tracked_detection(frame, track_id, bbox_xyxy, frame_index)
        with self.stats_lock:
            self.seconds['silhouettes'] += time.perf_counter() - started
        if not captured:
            return False
        state = self.online.setdefault(track_id, OnlineTrack())
        view = self.views_by_id[track_id][-1]
        view.capture_monotonic = self.capture_origin
        started = time.perf_counter()
        self._advance(track_id, state, view)
        with self.stats_lock:
            self.seconds['motion'] += time.perf_counter() - started
        retained = {item.frame_index: item for segment in state.segments for item in segment.views}
        for item in state.recent:
            retained.setdefault(item.frame_index, item)
        self.views_by_id[track_id] = [retained[index] for index in sorted(retained)]
        return True

    def _submit(self):
        while self.requests:
            requests, self.requests = self.requests[:self.batch_size], self.requests[self.batch_size:]
            images = [cv2.bitwise_and(view.image, view.image, mask=view.object_mask) for _, view in requests]
            if hasattr(self.segmenter, 'predict_batch_async'):
                future = self.segmenter.predict_batch_async(images, conf=self.segmentation_conf)
            else:
                future = Future()
                try:
                    if hasattr(self.segmenter, 'predict_batch'):
                        results = self.segmenter.predict_batch(images, conf=self.segmentation_conf)
                    else:
                        results = [self.segmenter.predict(image, conf=self.segmentation_conf)[0] for image in images]
                    future.set_result(results)
                except BaseException as failure:
                    future.set_exception(failure)
            self.batches.append((future, requests))
            self.counters['segmentation_batches'] += 1
            self.counters['segmented_views_submitted'] += len(requests)
            self.counters['maximum_pending_batches'] = max(self.counters['maximum_pending_batches'], len(self.batches))

    def _poll(self, wait=False):
        touched = set()
        while self.batches and (wait or self.batches[0][0].done()):
            future, requests = self.batches.popleft()
            results = future.result()
            if len(results) != len(requests):
                raise a.MappingError('Segmentation batch result count does not match selected views')
            for (track_id, view), result in zip(requests, results):
                view.defect_masks = self._defects_from_result(result, view.object_mask)
                self.counters['segmented_views_completed'] += 1
                if getattr(view, 'capture_monotonic', None) is not None:
                    self.defect_latencies.append(time.monotonic() - view.capture_monotonic)
                touched.add(track_id)
        started = time.perf_counter()
        for track_id in touched:
            state = self.online.get(track_id)
            if state:
                for segment in state.segments:
                    segment.advance(self.settings)
        self.seconds['fusion'] += time.perf_counter() - started

    def process_frame(self, *args, **kwargs):
        started = time.perf_counter()
        self.capture_origin = kwargs.pop('capture_monotonic', time.monotonic())
        self._poll()
        self.parallel_capture = True
        try:
            super().process_frame(*args, **kwargs)
        finally:
            self.parallel_capture = False
        captured = []
        for track_id, future in self.capture_futures:
            try:
                if future.result():
                    captured.append(track_id)
            except a.MappingError as failure:
                counts = self.rejected_views_by_id.setdefault(track_id, {})
                counts[str(failure)] = counts.get(str(failure), 0) + 1
        self.capture_futures.clear()
        self._submit()
        self._poll()
        elapsed = time.perf_counter() - started
        self.frame_times.append(elapsed)
        self.seconds['frames'] += elapsed
        self.counters['frames'] += 1
        return captured

    def flush(self):
        for track_id in list(self.online):
            self.end_track(track_id)
        self._submit()
        self._poll(wait=True)

    def end_track(self, track_id):
        state = self.online.get(track_id)
        if state is None or state.ending:
            return
        state.ending = True
        if state.previous is not None and state.previous is not state.anchor:
            try:
                model, lookup = self._model(state, state.previous)
                self._keyframe(track_id, state, state.previous, model, lookup, force=True)
            except a.MappingError:
                pass
        self._submit()

    def track_ready(self, track_id):
        self._poll()
        return all(view.defect_masks for segment in self.online.get(track_id, OnlineTrack()).segments
                   for view in segment.views)

    def finish_track(self, track_id):
        state = self.online.get(track_id)
        if not state:
            raise a.MappingError('No online motion evidence')
        if not self.track_ready(track_id):
            raise a.MappingError('Selected defect observations are still pending')
        results = [segment.result(state.diagnostics, state.captured_frames) for segment in state.segments]
        results = [result for result in results if result is not None]
        if not results:
            raise a.MappingError('No verified online rotating segment', list(state.diagnostics))
        result = max(results, key=lambda item: item.observed_surface_pct)
        if self.identity_guard.metadata.get(track_id, {}).get('identity_status') == 'uncertain':
            result = replace(result, grade=None, status='identity_uncertain', grade_provisional=False)
        return result

    def detach_track(self, track_id):
        """Freeze a finished fruit for background file writing; no GPU calls remain."""
        try:
            result, failure = self.finish_track(track_id), None
        except a.MappingError as error:
            result, failure = None, error
        identity = dict(self.identity_guard.metadata.get(track_id, {}))
        frozen = SimpleNamespace(settings=self.settings,
            views_by_id={track_id: list(self.views_by_id.get(track_id, []))},
            rejected_views_by_id={track_id: dict(self.rejected_views_by_id.get(track_id, {}))},
            tracking_history_by_id={track_id: list(self.tracking_history_by_id.get(track_id, []))},
            tracking_images_by_id={track_id: dict(self.tracking_images_by_id.get(track_id, {}))},
            identity_guard=SimpleNamespace(metadata={track_id: identity}))
        def finish(_track_id):
            if failure is not None:
                raise failure
            return result
        frozen.finish_track = finish
        frozen.drop_track = lambda _track_id: None
        self.drop_track(track_id)
        return frozen

    def drop_track(self, track_id):
        self.online.pop(int(track_id), None)
        super().drop_track(track_id)

    def runtime_metrics(self):
        frames = self.counters['frames']
        return dict(profile='realtime', model_input_size=[640, 640],
            counters=dict(self.counters), stage_seconds=dict(self.seconds),
            processing_fps=frames / self.seconds['frames'] if self.seconds['frames'] else 0.,
            frame_p95_ms=float(np.percentile(self.frame_times, 95) * 1000) if self.frame_times else None,
            defect_update_p95_ms=float(np.percentile(self.defect_latencies, 95) * 1000) if self.defect_latencies else None,
            segmentation_batch_size=self.batch_size, maximum_keyframes=self.maximum_keyframes,
            motion_workers=self.motion_workers,
            recovery_search_limit=self.recovery_searches,
            pending_batches=len(self.batches), active_fruit=len(self.online),
            inference_queue_maximum=getattr(getattr(self.segmenter, 'scheduler', None), 'maximum_pending', 0))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.motion_pool.shutdown(wait=True, cancel_futures=True)
        scheduler = getattr(self.segmenter, 'scheduler', None)
        if scheduler:
            scheduler.close()
        self.batches.clear()
        self.requests.clear()
        self.capture_futures.clear()
