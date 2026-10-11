"""Independent motion/area controls, async evidence gates and bounded resources."""
from dataclasses import replace
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import patch
import threading
import unittest

import cv2
import numpy as np

import algorithm as a
from fast_rotation import estimate_feature_rotation
from inference_scheduler import InferenceScheduler
from realtime_pipeline import RealtimePipeline, OnlineTrack, OnlineSegment
from test_dense_mapping import render, settings, rotation_x


class ClearSegmenter:
    names = {0: 'defect'}
    def predict_batch(self, images, **kwargs):
        return [SimpleNamespace(masks=None, boxes=None) for image in images]


class RealtimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cv2.setNumThreads(1)

    def test_feature_rotation_and_measured_chain_seed(self):
        for angle in (4., 12., 20., 30.):
            views = render([0, angle])
            config = replace(settings(), min_pair_angle_deg=.25, native_point_preblur_sigma=0.)
            model = a.fit_spheroid(views, config)
            # A deliberately imperfect seed represents measured intervening frames.
            seed = rotation_x(angle - 1.)
            diagnostics = {}
            rotation, _ = estimate_feature_rotation(*views, model, 0, config, diagnostics, seed)
            difference = np.rad2deg(np.linalg.norm(cv2.Rodrigues(rotation @ rotation_x(angle).T)[0]))
            self.assertLess(difference, .25)
            self.assertTrue(diagnostics['feature_rotation_verified'])

    def test_flat_and_stationary_skin_supply_no_rotation(self):
        for flat in (False, True):
            views = render([0., 0.])
            if flat:
                for view in views:
                    view.image[view.object_mask > 0] = [20, 100, 200]
            config = replace(settings(), min_pair_angle_deg=.25, native_point_preblur_sigma=0.)
            with self.assertRaises(a.MappingError):
                estimate_feature_rotation(*views, a.fit_spheroid(views, config), 0, config)

    def test_vectorised_fusion_matches_original_pixels_masks_and_area(self):
        for oblate in (False, True):
            views = render(range(0, 441, 20), oblate=oblate)
            for view in views:
                yy, xx = np.indices(view.object_mask.shape)
                view.defect_masks = {'first': ((xx > 90) & (xx < 105)).astype(np.uint8),
                                     'second': ((yy > 90) & (yy < 105)).astype(np.uint8)}
            config = replace(settings(), select_rotating_views=False, adaptive_keyframes=False,
                             defect_observations_complete=True, grade_partial_maps=True)
            with patch.object(a, 'estimate_rotation', return_value=(rotation_x(20), .1)):
                scalar = a.build_surface_map(views, config)
                vector = a.build_surface_map(views, replace(config, vectorized_fusion=True))
            np.testing.assert_array_equal(scalar.observed_mask, vector.observed_mask)
            np.testing.assert_array_equal(scalar.bgr_map, vector.bgr_map)
            for name in scalar.defect_maps:
                np.testing.assert_array_equal(scalar.defect_maps[name], vector.defect_maps[name])
            self.assertAlmostEqual(scalar.observed_surface_pct, vector.observed_surface_pct, places=8)
            self.assertAlmostEqual(scalar.defect_pct_of_observed, vector.defect_pct_of_observed, places=8)

    def test_online_full_turn_reaches_coverage_without_reconstruction_at_exit(self):
        pipeline = RealtimePipeline(ClearSegmenter(), settings=replace(settings(),
            keyframe_minimum_rotation_deg=15., maximum_keyframe_index_gap=8,
            minimum_view_rotation_deg=20., grade_partial_maps=True, native_point_preblur_sigma=0.),
            defer_defect_segmentation=True, recovery_searches=0)
        views = render(range(0, 365, 4))
        try:
            with patch.object(a, '_grabcut', side_effect=lambda image, iterations, bbox: views[index].object_mask):
                for index, view in enumerate(views):
                    pipeline.add_tracked_detection(view.image, 1, [20, 20, 190, 190], index)
                    pipeline._submit()
                    pipeline._poll()
            pipeline.flush()
            with patch.object(a, 'build_surface_map', side_effect=AssertionError('Exit must not rebuild maps')):
                result = pipeline.finish_track(1)
            self.assertGreaterEqual(result.observed_surface_pct, 80)
            self.assertGreaterEqual(result.observed_longitude_deg, 350)
            self.assertTrue(result.coverage_complete)
            self.assertEqual(result.grade, 'Class 1')
            self.assertLessEqual(len(pipeline.views_by_id[1]), 40)
            pipeline.identity_guard.metadata[1] = {'identity_status': 'uncertain'}
            self.assertIsNone(pipeline.finish_track(1).grade)
        finally:
            pipeline.close()

    def test_missing_capture_frames_are_never_stitched(self):
        pipeline = RealtimePipeline(ClearSegmenter(), settings=replace(settings(),
            keyframe_minimum_rotation_deg=15., maximum_keyframe_index_gap=8),
            defer_defect_segmentation=True, recovery_searches=0)
        views = render([0, 4])
        try:
            for index, view in enumerate(views):
                with patch.object(a, '_grabcut', return_value=view.object_mask):
                    pipeline.add_tracked_detection(view.image, 1, [20, 20, 190, 190], index * 10)
            with self.assertRaises(a.MappingError):
                pipeline.finish_track(1)
            self.assertEqual(pipeline.counters['segment_splits'], 1)
        finally:
            pipeline.close()

    def test_gpu_scheduler_prioritises_detection_and_propagates_errors(self):
        scheduler = InferenceScheduler(capacity=4)
        started, release = threading.Event(), threading.Event()
        order = []
        def blocker():
            started.set()
            self.assertTrue(release.wait(3))
        try:
            first = scheduler.submit(blocker)
            self.assertTrue(started.wait(3))
            segment = scheduler.submit(lambda: order.append('segment'), priority=1)
            detect = scheduler.submit(lambda: order.append('detect'), priority=0)
            release.set()
            first.result(timeout=3); detect.result(timeout=3); segment.result(timeout=3)
            self.assertEqual(order, ['detect', 'segment'])
            failed = scheduler.submit(lambda: (_ for _ in ()).throw(ValueError('model failed')))
            with self.assertRaisesRegex(ValueError, 'model failed'):
                failed.result(timeout=3)
        finally:
            release.set()
            scheduler.close()

    def test_pending_defect_masks_never_produce_an_all_clear_grade(self):
        from inference_scheduler import ScheduledSegmenter
        scheduler = InferenceScheduler()
        started, release = threading.Event(), threading.Event()
        def blocker():
            started.set()
            self.assertTrue(release.wait(3))
        pipeline = RealtimePipeline(ScheduledSegmenter(ClearSegmenter(), scheduler),
            settings=replace(settings(), grade_partial_maps=True), defer_defect_segmentation=True)
        views = render([0, 20])
        model = a.fit_spheroid(views, pipeline.settings)
        axes, radii, longitude, direction, positions = a._map_trajectory(model, [rotation_x(20)], pipeline.settings)
        segment = OnlineSegment(model, views, axes, list(positions), radii, longitude[0], direction,
                                [rotation_x(20)], [.1])
        pipeline.online[1] = OnlineTrack(segments=[segment])
        try:
            first = scheduler.submit(blocker)
            self.assertTrue(started.wait(3))
            pipeline.requests.extend((1, view) for view in views)
            pipeline._submit()
            self.assertFalse(pipeline.track_ready(1))
            with self.assertRaisesRegex(a.MappingError, 'still pending'):
                pipeline.finish_track(1)
            self.assertEqual(segment.fused, 0)
            release.set()
            first.result(timeout=3)
            pipeline._poll(wait=True)
            self.assertTrue(pipeline.track_ready(1))
            self.assertEqual(pipeline.finish_track(1).grade, 'Class 1')
        finally:
            release.set()
            pipeline.close()
        self.assertFalse(scheduler.thread.is_alive())
        self.assertEqual(len(pipeline.batches), 0)

    def test_reference_batches_only_selected_views_and_preserves_source_evidence(self):
        batches = []
        class RecordingSegmenter(ClearSegmenter):
            def predict_batch(self, images, **kwargs):
                batches.append(len(images))
                return super().predict_batch(images, **kwargs)
        pipeline = a.NaartjiePipeline(RecordingSegmenter(), settings=replace(settings(),
            vectorized_fusion=True, grade_partial_maps=True), defer_defect_segmentation=True)
        views = render(range(0, 201, 20))
        pipeline.views_by_id[1] = views
        def select(prepared, model, config):
            chosen = list(range(0, 11, 2))
            return [prepared[index] for index in chosen], a._subset_spheroid(model, chosen), \
                [rotation_x(40)] * 5, [.1] * 5, []
        with patch.object(a, '_select_rotating_views', side_effect=select):
            result = pipeline.finish_track(1)
        self.assertEqual(batches, [4, 2])
        self.assertEqual(result.view_frames, [0, 2, 4, 6, 8, 10])
        self.assertEqual([view.frame_index for view in views if view.defect_masks], result.view_frames)

    def test_scheduler_overload_is_explicit_and_shutdown_drains_accepted_work(self):
        scheduler = InferenceScheduler(capacity=1)
        started, release = threading.Event(), threading.Event()
        def blocker():
            started.set()
            self.assertTrue(release.wait(3))
        try:
            first = scheduler.submit(blocker)
            self.assertTrue(started.wait(3))
            queued = scheduler.submit(lambda: 'finished')
            with self.assertRaisesRegex(RuntimeError, 'queue is full'):
                scheduler.submit(lambda: None)
            release.set()
            scheduler.close()
            first.result(timeout=3)
            self.assertEqual(queued.result(timeout=3), 'finished')
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                scheduler.submit(lambda: None)
        finally:
            release.set()
            scheduler.close()

    def test_camera_ring_preserves_source_sequence_when_frames_overrun(self):
        from main import CameraFeed
        camera = CameraFeed()
        image = np.zeros((8, 8, 3), np.uint8)
        for sequence in range(1, 7):
            camera.frames.append((sequence, image, float(sequence)))
        camera.sequence = 6
        stop = threading.Event()
        self.assertEqual(camera.next_frame(1, stop)[0], 3)
        self.assertEqual(camera.next_frame(3, stop)[0], 4)
        stop.set()
        self.assertIsNone(camera.next_frame(4, stop))

    def test_batch_adapter_keeps_640_and_variable_crop_coordinates(self):
        from dfine_segmenter import DfineSegmenter
        segmenter = DfineSegmenter.__new__(DfineSegmenter)
        shapes = []
        class Model:
            def _preprocess(self, image, bgr):
                return np.zeros((3, 640, 640), np.uint8)
            def _predict(self, inputs):
                shapes.append(tuple(inputs.shape))
                return inputs
            def _postprocess(self, raw, processed, original):
                self.original = original
                return [{'labels': [], 'masks': None} for _ in original]
        segmenter.model = Model()
        segmenter.names = {0: 'defect'}
        segmenter.device, segmenter.mixed_precision = 'cpu', False
        segmenter.input_size = (640, 640)
        segmenter.inference_calls = segmenter.batch_calls = segmenter.maximum_batch_size = 0
        segmenter.total_latency_ms = segmenter.total_predictions = segmenter.total_confidence = 0.
        images = [np.zeros((90, 120, 3), np.uint8), np.zeros((140, 80, 3), np.uint8)]
        self.assertEqual(len(segmenter.predict_batch(images)), 2)
        self.assertEqual(shapes, [(2, 3, 640, 640)])
        self.assertEqual(segmenter.model.original, [(90, 120), (140, 80)])
        self.assertEqual(segmenter.inference_calls, 2)


if __name__ == '__main__':
    unittest.main()
