"""Acquisition, fusion, deadlines, shared identity and hot-switch controls."""
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import json
import time
import unittest

import numpy as np

from algorithm import NaartjiePipeline
from inspection_config import InspectionConfiguration, InspectionSettings, NineViewSettings
from inspection_pipeline import InspectionPipeline
from nine_view import NineViewEngine, fuse_view, progress_at, select_crop, View


class Clock:
    now = 100.
    def __call__(self): return self.now


class Segmenter:
    names = {0: 'dark_marking', 1: 'open_skin'}
    def __init__(self): self.futures, self.images = [], []
    def predict_batch_async(self, images, **kwargs):
        future = Future()
        self.futures.append(future); self.images.append(images)
        return future


def clear():
    return SimpleNamespace(masks=None, boxes=None)


def defects(shape, severity=.35, confidence=.9, overlapping=False):
    mask = np.zeros(shape, np.uint8)
    mask[:int(shape[0] * severity)] = 1
    masks = np.stack([mask, mask]) if overlapping else mask[None]
    return SimpleNamespace(masks=SimpleNamespace(data=masks), boxes=SimpleNamespace(
        cls=np.arange(len(masks)), conf=np.full(len(masks), confidence)))


def image():
    rng = np.random.default_rng(891)
    green = rng.integers(70, 180, (1000, 180), dtype=np.uint8)
    return np.stack((green // 3, green, np.full_like(green, 220)), axis=-1)


def box(progress):
    center = 50 + 900 * progress
    return [60, center - 16, 92, center + 16]


def snapshot(**changes):
    return InspectionSettings(algorithm='nine_view', nine_view=NineViewSettings(region=(0, .05, 1, .95), **changes))


class NineViewTests(unittest.TestCase):
    def test_actual_numpy_detector_coordinates_produce_json_safe_quality(self):
        bounds = np.array(box(.45), np.float32)
        neighbour = bounds + np.array([27, 0, 27, 0], np.float32)
        view, error = select_crop(image(), bounds, 0, 0., 100., 4, .45,
                                 snapshot().nine_view, [bounds, neighbour])
        self.assertIsNone(error)
        json.dumps(view.quality, allow_nan=False)

    def setUp(self):
        self.clock, self.segmenter = Clock(), Segmenter()
        self.engine = NineViewEngine(self.segmenter, clock=self.clock, start_worker=False,
            mask_provider=lambda view: np.ones(view.image.shape[:2], np.uint8))
        self.frame = image()
        self.addCleanup(self.engine.close)

    def open(self, key='run:1', **changes):
        self.assertTrue(self.engine.open(key, 1, snapshot(**changes), 0., self.clock.now))
        return self.engine.fruit[key]

    def observe(self, key='run:1', bins=range(9), duplicates=False):
        for frame, index in enumerate(bins):
            self.engine.observe(key, self.frame, box((index + .5) / 9), frame,
                                frame / 30, self.clock.now)
            if duplicates:
                self.engine.observe(key, self.frame, box((index + .5) / 9), frame,
                                    frame / 30, self.clock.now)
        self.engine.end(key, 'region_exit')

    def drain(self):
        while self.engine.pending_depth():
            self.engine.dispatch()
            future = self.segmenter.futures[-1]
            future.set_result([clear() for _ in self.segmenter.images[-1]])
        self.engine.expire()

    def test_exact_nine_distinct_frames_and_deterministic_ties(self):
        state = self.open()
        self.observe(duplicates=True)
        self.drain()
        self.assertTrue(state.result['evidence_complete'])
        self.assertEqual(state.result['processed_crops'], 9)
        self.assertEqual(state.result['grade'], 'Class 1')
        self.assertTrue(state.result['grade_provisional'])
        self.assertIsNone(state.result['observed_surface_pct'])
        self.assertEqual(state.result['view_frames'], list(range(9)))
        self.assertEqual(len(set(state.result['view_frames'])), 9)
        self.assertEqual(self.engine.counts['terminal_results'], 1)
        self.engine.expire(); self.assertEqual(self.engine.counts['terminal_results'], 1)

    def test_progressive_inference_before_nine_is_available(self):
        self.open()
        for index in range(3):
            self.engine.observe('run:1', self.frame, box((index + .5) / 9), index, index / 30, self.clock.now)
        self.engine.dispatch()
        self.assertEqual(len(self.segmenter.images[-1]), 2)
        self.assertFalse(self.engine.ready('run:1'))

    def test_equal_quality_candidates_in_one_bin_keep_earlier_distinct_frame(self):
        state = self.open()
        for index in (0, 1):
            self.engine.observe('run:1', self.frame, box(.05), index, index / 30, self.clock.now)
        self.assertEqual(state.slots[0].frame, 0)
        self.assertEqual(sum(view is not None for view in state.slots), 1)

    def test_missing_bins_grade_available_views_without_padding(self):
        state = self.open(expected_dwell_seconds=.1)
        self.observe(bins=(0, 1, 3, 5, 8))
        self.drain()
        self.assertFalse(state.result['evidence_complete'])
        self.assertEqual(state.result['selected_crops'], 5)
        self.assertEqual(state.result['missing_bins'], [2, 4, 6, 7])
        self.assertEqual(state.result['grade'], 'Class 1')
        self.assertEqual(state.result['processed_crops'], 5)
        self.assertFalse(state.result['configured_dwell_can_supply_nine'])

    def test_poor_crops_are_rejected(self):
        state = self.open()
        flat = np.full_like(self.frame, 255)
        self.engine.observe('run:1', flat, box(.05), 0, 0., self.clock.now)
        self.engine.observe('run:1', self.frame, [0, 80, 40, 112], 1, .1, self.clock.now)
        self.engine.observe('run:1', self.frame, [60, 100, 65, 105], 2, .2, self.clock.now)
        self.engine.end('run:1'); self.drain()
        self.assertIsNone(state.result['grade'])
        self.assertTrue(state.rejection_counts['blurred_crop'])
        self.assertTrue(state.rejection_counts['clipped_crop'])
        self.assertTrue(state.rejection_counts['crop_too_small'])

    def test_best_candidate_tie_keeps_earliest_frame_and_no_extra_slot(self):
        state = self.open()
        self.engine.observe('run:1', self.frame, box(.05), 0, 0., self.clock.now)
        self.engine.observe('run:1', self.frame, box(.05), 1, .1, self.clock.now)
        self.assertEqual(state.slots[0].frame, 0)
        self.assertEqual(sum(view is not None for view in state.slots), 1)

    def test_out_of_order_completion_and_one_supported_severe_view(self):
        state = self.open()
        self.observe()
        self.engine.dispatch(); self.engine.dispatch()
        second = [clear() for _ in self.segmenter.images[1]]
        second[0] = defects(self.segmenter.images[1][0].shape[:2], overlapping=True)
        self.segmenter.futures[1].set_result(second)
        self.assertFalse(self.engine.ready('run:1'))
        self.segmenter.futures[0].set_result([clear() for _ in self.segmenter.images[0]])
        self.drain()
        self.assertEqual(state.result['grade'], 'Class 3')
        self.assertEqual(state.result['worst_view_frame'], 4)
        self.assertLess(state.result['worst_view_defect_pct'], 40)  # duplicate masks are unioned

    def test_low_confidence_artifact_does_not_create_severe_grade(self):
        self.open(); self.observe(); self.engine.dispatch()
        results = [defects(image.shape[:2], confidence=.1) for image in self.segmenter.images[0]]
        self.segmenter.futures[0].set_result(results)
        self.drain()
        self.assertEqual(self.engine.fruit['run:1'].result['grade'], 'Class 1')

    def test_failed_batch_uses_successful_views_and_late_completion_is_ignored(self):
        state = self.open(); self.observe(); self.engine.dispatch()
        self.segmenter.futures[0].set_exception(RuntimeError('model failed'))
        self.drain()
        self.assertEqual(state.result['grade'], 'Class 1')
        self.assertFalse(state.result['evidence_complete'])
        self.engine.complete(1, self.segmenter.futures[0], time.perf_counter())
        self.assertEqual(self.engine.counts['terminal_results'], 1)

    def test_deadline_stationary_track_loss_and_entry_truncation(self):
        state = self.open(track_loss_seconds=10.)
        self.engine.observe('run:1', self.frame, box(.05), 0, 0., self.clock.now)
        self.clock.now += 5.
        self.engine.expire()
        self.assertIsNone(state.result['grade'])
        self.assertTrue(state.result['deadline_missed'])
        self.assertEqual(state.result['reason'], 'decision_deadline')
        state = self.open('run:2')
        self.clock.now += 1.1; self.engine.expire()
        self.assertEqual(state.result['end_reason'] if 'end_reason' in state.result else state.end_reason, 'track_loss')
        state = self.open('run:3')
        self.observe('run:3', bins=(4, 5, 6, 7, 8)); self.drain()
        self.assertEqual(state.result['missing_bins'], [0, 1, 2, 3])

    def test_overload_and_state_bounds_are_explicit(self):
        engine = NineViewEngine(self.segmenter, clock=self.clock, start_worker=False, maximum_active=1,
            maximum_pending=2, mask_provider=lambda v: np.ones(v.image.shape[:2], np.uint8))
        self.addCleanup(engine.close)
        self.assertTrue(engine.open('a', 1, snapshot(), 0., 100.))
        self.assertFalse(engine.open('b', 2, snapshot(), 0., 100.))
        for i in range(9):
            engine.observe('a', self.frame, box((i + .5) / 9), i, i / 30, 100.)
        engine.end('a')
        self.assertLessEqual(engine.pending_depth(), 2)
        self.assertGreater(engine.counts['dropped_accepted_views'], 0)
        self.assertEqual(len(engine.fruit['a'].slots), 9)

    def test_all_four_directions_and_unconfigured_region(self):
        for direction in ('top_to_bottom', 'bottom_to_top', 'left_to_right', 'right_to_left'):
            config = NineViewSettings(region=(0, 0, 1, 1), direction=direction)
            value, across = progress_at([40, 40, 60, 60], (100, 100), config)
            self.assertAlmostEqual(value, .5); self.assertTrue(across)
        config = InspectionSettings(algorithm='nine_view')
        self.engine.open('unset', 2, config, 0., 100.)
        self.assertTrue(self.engine.ready('unset'))
        self.assertEqual(self.engine.fruit['unset'].result['reason'], 'inspection_region_not_configured')

    def test_glare_overlap_and_mask_failures_remain_incomplete(self):
        state = self.open(minimum_blur_variance=0.)
        white = np.full_like(self.frame, 255)
        self.engine.observe('run:1', white, box(.05), 0, 0., self.clock.now)
        neighbour = np.array(box(.05)) + [2, 0, 2, 0]
        self.engine.observe('run:1', self.frame, box(.05), 1, .1, self.clock.now, [neighbour])
        self.assertEqual(state.rejection_counts['excessive_glare'], 1)
        self.assertEqual(state.rejection_counts['overlapping_fruit'], 1)
        self.observe()
        self.engine.mask_provider = lambda view: np.zeros(view.image.shape[:2], np.uint8)
        while self.engine.pending_depth(): self.engine.dispatch()
        self.engine.expire()
        self.assertIsNone(state.result['grade'])
        self.assertFalse(state.result['evidence_complete'])

    def test_dispatch_is_fair_across_fruit_and_bounds_inflight(self):
        self.open('a'); self.open('b')
        self.observe('a'); self.observe('b')
        self.engine.dispatch()
        self.assertEqual([key for key, _, _ in self.engine.inflight[1]], ['a', 'b', 'a', 'b'])
        self.engine.dispatch(); self.engine.dispatch()
        self.assertEqual(len(self.engine.inflight), 2)

    def test_stationary_dwell_grades_available_view_and_uncertain_identity_withholds_grade(self):
        state = self.open(decision_deadline_seconds=20., maximum_dwell_seconds=.5, track_loss_seconds=10.)
        self.engine.observe('run:1', self.frame, box(.05), 0, 0., self.clock.now)
        self.clock.now += .6; self.engine.expire(); self.drain()
        self.assertEqual(state.end_reason, 'stationary_or_dwell_timeout')
        self.assertEqual(state.result['grade'], 'Class 1')
        state = self.open('uncertain'); state.identity_uncertain = True
        self.observe('uncertain'); self.drain()
        self.assertTrue(state.result['evidence_complete'])
        self.assertIsNone(state.result['grade'])

    def test_late_inference_after_detach_cannot_grade_a_reused_identity(self):
        state = self.open(); self.observe(); self.engine.dispatch()
        old_future = self.segmenter.futures[0]
        self.clock.now += 6.; self.engine.expire()
        self.engine.detach('run:1')
        fresh = self.open('run:2')
        old_future.set_result([clear() for _ in self.segmenter.images[0]])
        self.assertIsNone(fresh.result)
        self.assertEqual(self.engine.counts['late_completions_ignored'], 4)


class SwitchingTests(unittest.TestCase):
    def test_active_overload_has_complete_failure_metadata_and_releases_images(self):
        config = InspectionConfiguration()
        config.update({'algorithm': 'nine_view', 'nine_view': {'region': (0, .05, 1, .95)}})
        surface = NaartjiePipeline(Segmenter(), SimpleNamespace(names={0: 'fruit'}), defer_defect_segmentation=True)
        router = InspectionPipeline(surface, config.snapshot, start_worker=False, maximum_active=1)
        self.addCleanup(router.close)
        router._record(image(), 1, box(.2), 0)
        router._record(image(), 2, box(.2), 0)
        result = router.detach_track(2).nine_view_result
        self.assertEqual(result['status'], 'nine_view_overloaded')
        self.assertFalse(result['evidence_complete'])
        self.assertIsNone(result['grade'])
        self.assertEqual(result['missing_bins'], list(range(9)))
        self.assertEqual(result['decision_deadline_monotonic'] - result['entry_capture_monotonic'], 5)
        self.assertNotIn(2, router.tracking_images_by_id)
        self.assertEqual(len(router.nine.fruit), 1)
        router.drop_track(1); router.drop_track(2)
        self.assertEqual(router.routes, {})
        self.assertEqual(router.nine.fruit, {})

    def test_shared_tracking_continues_after_publication_without_reconstruction(self):
        class Detector:
            names = {0: 'fruit'}
            calls = 0
            def track(self, frame, **kwargs):
                self.calls += 1
                return [SimpleNamespace(boxes=SimpleNamespace(id=np.array([7]),
                    cls=np.array([0]), xyxy=np.array([box(.45)])))]
        detector, segmenter, clock = Detector(), Segmenter(), Clock()
        config = InspectionConfiguration()
        config.update({'algorithm': 'nine_view', 'nine_view': {'region': (0, .05, 1, .95)}})
        from conveyor_identity import ConveyorIdentitySettings
        surface = NaartjiePipeline(segmenter, detector, defer_defect_segmentation=True,
            identity_settings=ConveyorIdentitySettings(reference_speed_px_s=30.))
        router = InspectionPipeline(surface, config.snapshot, run_id='stream', clock=clock, start_worker=False)
        self.addCleanup(router.close)
        with patch('algorithm.fit_spheroid', side_effect=AssertionError('Nine-view must bypass fitting')), \
                patch('algorithm.build_surface_map', side_effect=AssertionError('Nine-view must bypass mapping')):
            router.process_frame(image(), 0, timestamp=0., capture_monotonic=clock.now)
            fruit_id = next(iter(router.routes))
            clock.now += 6.; router.nine.expire()
            result = router.detach_track(fruit_id).nine_view_result
            self.assertEqual(result['status'], 'nine_view_timeout')
            config.update({'algorithm': 'surface_mapping'})
            for index in range(1, 5):
                router.process_frame(image(), index, timestamp=index / 30, capture_monotonic=clock.now)
            self.assertEqual(detector.calls, 5)
            self.assertEqual(router.routes[fruit_id]['snapshot'].algorithm, 'nine_view')
            self.assertEqual(router.counters['entered_fruit'], 1)
            self.assertEqual(len(router.tracking_history_by_id[fruit_id]), 1)
            self.assertEqual(router.ready_tracks(), [])

    def test_assignment_waits_until_region_entry(self):
        config = InspectionConfiguration()
        config.update({'nine_view': {'region': (0, .25, 1, .75)}})
        surface = NaartjiePipeline(Segmenter(), SimpleNamespace(names={0: 'fruit'}), defer_defect_segmentation=True)
        router = InspectionPipeline(surface, config.snapshot, start_worker=False)
        self.addCleanup(router.close)
        router._record(image(), 1, box(.1), 0)
        self.assertNotIn(1, router.routes)
        config.update({'algorithm': 'nine_view'})
        router._record(image(), 1, box(.4), 1)
        self.assertEqual(router.routes[1]['snapshot'].algorithm, 'nine_view')
        self.assertEqual(router.routes[1]['snapshot'].version, 3)

    def test_detached_surface_fixture_preserves_existing_map_and_frozen_settings(self):
        import algorithm as a
        from test_dense_mapping import render, rotation_x
        segmenter = Segmenter()
        settings = a.Settings(spheroid_type='sphere', rotation_axis='x',
            minimum_surface_coverage=.1, grade_partial_maps=True)
        views = render([0, 20, 40, 60])
        for view in views:
            mask = np.zeros(view.object_mask.shape, np.uint8)
            mask[65:90, 85:110] = view.object_mask[65:90, 85:110]
            view.defect_masks = {'open_skin': mask}
        config = InspectionConfiguration()
        surface = NaartjiePipeline(segmenter, settings=settings)
        router = InspectionPipeline(surface, config.snapshot, start_worker=False)
        self.addCleanup(router.close)
        router._record(image(), 1, box(.2), 0)
        surface.views_by_id[1] = views
        frozen = router.detach_track(1)
        surface.settings.minimum_surface_coverage = .99
        config.update({'algorithm': 'nine_view'})
        with patch('algorithm.estimate_rotation', return_value=(rotation_x(20), .1)):
            expected = a.build_surface_map(views, settings=frozen.settings)
            actual = frozen.finish_track(1)
        self.assertEqual(actual.grade, expected.grade)
        self.assertEqual(actual.status, expected.status)
        self.assertAlmostEqual(actual.defect_pct_of_observed, expected.defect_pct_of_observed)
        np.testing.assert_array_equal(actual.bgr_map, expected.bgr_map)
        np.testing.assert_array_equal(actual.observed_mask, expected.observed_mask)
        self.assertEqual(frozen.settings.minimum_surface_coverage, .1)

    def test_writer_publishes_once_without_reattaching_stationary_fruit(self):
        import main
        config = InspectionConfiguration()
        config.update({'algorithm': 'nine_view', 'nine_view': {'region': (0, .05, 1, .95)}})
        class Immediate(Segmenter):
            def predict_batch(self, images, **kwargs): return [clear() for _ in images]
        segmenter = Immediate()
        surface = NaartjiePipeline(segmenter, SimpleNamespace(names={0: 'fruit'}), defer_defect_segmentation=True)
        router = InspectionPipeline(surface, config.snapshot, run_id='writer', start_worker=False,
            mask_provider=lambda view: np.ones(view.image.shape[:2], np.uint8))
        self.addCleanup(router.close)
        frame = image()
        router.captured_at = time.monotonic()
        for index in range(9):
            router.timestamp = index / 30
            router._record(frame, 1, box((index + .5) / 9), index)
        router.nine.end('writer:1', 'region_exit')
        while router.nine.pending_depth():
            router.nine.dispatch()
            if segmenter.futures:
                segmenter.futures[-1].set_result([clear() for _ in segmenter.images[-1]])
        with tempfile.TemporaryDirectory() as directory:
            writer = main.TrackWriter(Path(directory))
            try:
                writer.finish(router, 1); writer.collect(wait=True)
                self.assertEqual(len(writer.results), 1)
                self.assertTrue(writer.results[0]['evidence_complete'])
                self.assertTrue((Path(directory) / '1/contact_sheet.png').is_file())
                router._record(frame, 1, box(.95), 10)
                self.assertEqual(router.ready_tracks(), [])
                self.assertEqual(router.counters['published_fruit'], 1)
                writer.finish(router, 1)
                self.assertEqual(len(writer.results), 1)
                self.assertEqual(len(router.routes), 0)
            finally: writer.close()

    def test_switches_both_ways_keep_entry_snapshot_and_resources(self):
        config = InspectionConfiguration()
        segmenter = Segmenter()
        detector = SimpleNamespace(names={0: 'fruit'})
        surface = NaartjiePipeline(segmenter, detector, defer_defect_segmentation=True)
        router = InspectionPipeline(surface, config.snapshot, run_id='test', start_worker=False)
        self.addCleanup(router.close)
        frame = image()
        with patch.object(router, '_original_capture', return_value=True) as capture:
            router._record(frame, 1, box(.1), 0)
            old = router.routes[1]['snapshot']
            config.update({'algorithm': 'nine_view', 'nine_view': {'region': (0, .05, 1, .95)}})
            router._record(frame, 2, box(.1), 1)
            config.update({'algorithm': 'surface_mapping'})
            router._record(frame, 3, box(.1), 2)
            for _ in range(10):
                config.update({'algorithm': 'nine_view'})
                config.update({'algorithm': 'surface_mapping'})
            self.assertEqual(router.routes[1]['snapshot'], old)
            self.assertEqual([router.routes[i]['snapshot'].algorithm for i in (1, 2, 3)],
                             ['surface_mapping', 'nine_view', 'surface_mapping'])
            router._capture(frame, 1, box(.1), 3)
            router._capture(frame, 2, box(.1), 3)
            router._capture(frame, 3, box(.1), 3)
            self.assertEqual(capture.call_count, 2)
            self.assertIs(router.segmenter, segmenter)
            self.assertIs(router.surface.detector.model, detector)
            self.assertEqual(router.nine.fruit['test:2'].snapshot.version, 2)

    def test_tracker_supported_recovery_and_reused_raw_id_keep_distinct_fruit(self):
        from conveyor_identity import ConveyorIdentityManager, ConveyorIdentitySettings
        guard = ConveyorIdentityManager(ConveyorIdentitySettings(reference_speed_px_s=30.))
        shape = (1000, 1000, 3)
        first = guard.update([[200, 100, 300, 200]], [7], 0, shape, 0.)[0]['fruit_id']
        recovered = guard.update([[200, 103, 300, 203]], [8], 3, shape, .1)[0]['fruit_id']
        self.assertEqual(first, recovered)
        guard.drop(first)
        reused = guard.update([[500, 500, 600, 600]], [7], 60, shape, 2.)[0]['fruit_id']
        self.assertNotEqual(reused, first)

    def test_configuration_persistence_legacy_default_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text('{}')
            config = InspectionConfiguration(path)
            self.assertEqual(config.snapshot().algorithm, 'surface_mapping')
            retained = config.snapshot()
            config.update({'algorithm': 'nine_view'})
            self.assertEqual(retained.algorithm, 'surface_mapping')
            self.assertEqual(InspectionConfiguration(path).snapshot().version, 2)
            with self.assertRaises(ValueError): config.update({'expected_version': 1})
            with self.assertRaises(ValueError): config.update({'nine_view': {'class_1_max_defect_pct': 40}})
            with self.assertRaises(ValueError): config.update({'nine_view': {'calibration_status': 'validated'}})
            for name in ('decision_deadline_seconds', 'maximum_dwell_seconds', 'track_loss_seconds'):
                with self.assertRaises(ValueError): config.update({'nine_view': {name: None}})

    def test_api_switch_is_allowed_while_inspection_is_active(self):
        import main
        from fastapi.testclient import TestClient
        with patch.object(main, 'inspection_configuration', InspectionConfiguration()):
            self.assertTrue(main.analysis_lock.acquire(blocking=False))
            try:
                client = TestClient(main.app)
                self.assertEqual(client.post('/api/inspection/config', json={'algorithm': 'nine_view'}).status_code, 200)
                self.assertEqual(client.get('/api/inspection/config').json()['config']['algorithm'], 'nine_view')
                self.assertEqual(client.post('/api/inspection/config', json={'algorithm': 'wrong'}).status_code, 422)
            finally: main.analysis_lock.release()


if __name__ == '__main__':
    unittest.main()
