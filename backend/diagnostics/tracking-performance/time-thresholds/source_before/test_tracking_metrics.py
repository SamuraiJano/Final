"""Checkpoint mathematics, censoring and passive pipeline/API integration."""
import csv
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from algorithm import NaartjiePipeline
from tracking_metrics import TrackingConfig, TrackingMetrics, EXPORTS, replay_journal
import main


def box(position, x=500):
    y = 100+8*position
    return [x-40, y-40, x+40, y+40]


class CheckpointTests(unittest.TestCase):
    def metrics(self, **kwargs):
        return TrackingMetrics(TrackingConfig(region=(.1, .1, .9, .9),
                               lost_buffer_frames=2, fragment_gap_frames=3, **kwargs))

    def observe(self, metrics, frame, positions, seconds=.02):
        metrics.observe(frame, frame*.1, (1000, 1000), list(positions),
                        [box(p) for p in positions.values()], seconds)

    def test_complete_crossings_are_interpolated_and_fps_is_measured(self):
        m = self.metrics()
        self.observe(m, 0, {17: -10})
        self.observe(m, 1, {17: 110})
        data = m.finish()
        self.assertEqual(len(m.crossings), 101)
        self.assertAlmostEqual(m.crossings[50][17]['crossing_frame'], .5)
        self.assertAlmostEqual(m.crossings[50][17]['crossing_time'], .05)
        np.testing.assert_allclose(m.crossings[50][17]['crossing_position'], [500, 500])
        for key in ('id_continuity_percent', 'mean_regional_continuity_percent', 'regional_pass_rate_percent'):
            self.assertEqual(data['summary'][key], 100)
        self.assertEqual(data['summary']['processing_fps'], 50)
        self.assertEqual(data['summary']['average_processing_time_ms'], 20)
        self.assertEqual(data['tracks'][0]['region_coverage_percent'], 100)

    def test_stop_does_not_age_active_or_recently_missing_tracks_into_losses(self):
        m = self.metrics()
        self.observe(m, 0, {1: -1})
        self.observe(m, 1, {1: 50})
        self.observe(m, 2, {})
        self.observe(m, 3, {})
        data = m.finish()
        self.assertEqual(data['summary']['lost_tracks'], 0)
        self.assertEqual(data['summary']['unfinished_entering_tracks'], 1)
        self.assertEqual(data['summary']['id_continuity_percent'], 0)
        self.assertIsNone(data['regions'][50]['continuity_percent'])
        self.assertEqual(data['regions'][50]['pending_ids'], [1])

    def test_confirmed_loss_is_counted_and_regional_drop_is_localised(self):
        m = self.metrics()
        self.observe(m, 0, {1: -1})
        self.observe(m, 1, {1: 50})
        for frame in (2, 3, 4):
            self.observe(m, frame, {})
        data = m.finish()
        self.assertEqual(data['summary']['lost_tracks'], 1)
        self.assertEqual(data['summary']['minimum_regional_continuity_percent'], 0)
        self.assertEqual(data['summary']['worst_region_start_percent'], 50)
        self.assertEqual(data['regions'][50]['lost_ids'], [1])
        self.assertEqual(data['tracks'][0]['status'], 'lost')

    def test_suspected_fragment_keeps_distinct_raw_ids(self):
        m = self.metrics()
        self.observe(m, 0, {17: -1})
        self.observe(m, 1, {17: 10})
        self.observe(m, 2, {17: 20})
        self.observe(m, 3, {31: 30})
        data = m.finish()
        self.assertEqual(data['summary']['id_fragmentations'], 1)
        self.assertEqual(data['summary']['mid_region_new_ids'], 1)
        event = next(e for e in data['events'] if e['event_type'] == 'id_fragmentation')
        self.assertEqual(event['IDs'], [17, 31])
        self.assertEqual(event['frame'], 3)
        self.assertEqual(event['position_percent'], 30)
        self.assertEqual(data['summary']['completed_tracks'], 0)
        self.assertEqual(data['summary']['valid_entering_tracks'], 1)

    def test_already_present_ids_are_left_censored(self):
        m = self.metrics()
        self.observe(m, 0, {2: 40})
        self.observe(m, 1, {2: 70})
        data = m.finish()
        self.assertEqual(data['summary']['mid_region_new_ids'], 0)
        self.assertEqual(data['summary']['valid_entering_tracks'], 0)
        self.assertIsNone(data['summary']['id_continuity_percent'])

    def test_fragment_near_entry_is_not_mislabelled_as_mid_region_new_id(self):
        m = self.metrics()
        for frame, positions in enumerate(({17:-.5}, {17:.5}, {17:1}, {31:2})):
            self.observe(m, frame, positions)
        summary = m.finish()['summary']
        self.assertEqual(summary['id_fragmentations'], 1)
        self.assertEqual(summary['mid_region_new_ids'], 0)

    def test_ambiguous_fragment_candidates_do_not_assert_a_match(self):
        m = self.metrics()
        self.observe(m, 0, {1: 20, 2: 20})
        self.observe(m, 1, {3: 20})
        self.assertEqual(m.finish()['summary']['id_fragmentations'], 0)

    def test_order_reversal_is_possible_swap_and_fails_region(self):
        m = self.metrics()
        self.observe(m, 0, {12: 39.8, 18: 39.6})
        self.observe(m, 1, {12: 40.4, 18: 40.9})
        self.observe(m, 2, {12: 41.7, 18: 41.1})
        data = m.finish()
        region = data['regions'][40]
        self.assertEqual(region['continuity_percent'], 100)
        self.assertFalse(region['region_pass'])
        self.assertEqual(region['possible_swap_count'], 1)
        self.assertEqual(region['order_consistency_percent'], 0)
        self.assertEqual(data['summary']['order_inversions'], 1)

    def test_missing_observation_is_not_interpolated_into_complete_track(self):
        m = self.metrics()
        self.observe(m, 0, {1: -1})
        self.observe(m, 1, {1: 10})
        self.observe(m, 2, {})
        self.observe(m, 3, {1: 90})
        self.observe(m, 4, {1: 101})
        data = m.finish()
        self.assertNotIn(1, m.crossings[50])
        self.assertEqual(data['summary']['completed_tracks'], 0)
        self.assertEqual(data['tracks'][0]['region_coverage_percent'], 20)

    def test_large_live_time_gap_is_not_interpolated(self):
        m = self.metrics()
        m.observe(0, 0, (1000, 1000), [1], [box(-1)], .02)
        m.observe(1, 2, (1000, 1000), [1], [box(101)], .02)
        self.assertFalse(m.crossings[0])

    def test_reverse_jitter_does_not_record_duplicate_crossings(self):
        m = self.metrics()
        for frame, p in enumerate((-1, 50, 49, 51, 101)):
            self.observe(m, frame, {1: p})
        self.assertEqual(len(m.crossings[50]), 1)
        self.assertEqual(m.finish()['summary']['completed_tracks'], 1)

    def test_region_and_direction_are_used_for_all_four_orientations(self):
        for direction in ('top_to_bottom', 'bottom_to_top', 'left_to_right', 'right_to_left'):
            with self.subTest(direction=direction):
                m = self.metrics(direction=direction)
                positions = (-10, 110) if direction in ('top_to_bottom', 'left_to_right') else (110, -10)
                for frame, p in enumerate(positions):
                    bounds = box(p)
                    if direction in ('left_to_right', 'right_to_left'):
                        bounds = [bounds[1], bounds[0], bounds[3], bounds[2]]
                    m.observe(frame, frame*.1, (1000, 1000), [1], [bounds], .02)
                self.assertEqual(m.finish()['summary']['id_continuity_percent'], 100)
        m = self.metrics()
        for frame, p in enumerate((-10, 110)):
            m.observe(frame, frame*.1, (1000, 1000), [1], [box(p, x=20)], .02)
        self.assertEqual(m.finish()['summary']['valid_entering_tracks'], 0)

    def test_no_region_retains_timing_without_fabricated_spatial_metrics(self):
        m = TrackingMetrics()
        self.observe(m, 0, {1: 10})
        self.observe(m, 1, {1: 90})
        data = m.finish()
        self.assertFalse(data['summary']['region_configured'])
        self.assertEqual(data['summary']['processing_fps'], 50)
        self.assertIsNone(data['summary']['mean_regional_continuity_percent'])

    def test_new_instance_resets_all_history(self):
        a, b = self.metrics(), self.metrics()
        self.observe(a, 0, {1: -1}); self.observe(a, 1, {1: 101})
        data = b.finish()
        self.assertEqual(data['summary']['total_unique_track_ids'], 0)
        self.assertEqual(data['summary']['frames_processed'], 0)
        self.assertEqual(data['events'], [])

    def test_exports_and_journal_replay_preserve_measured_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            m = TrackingMetrics(self.metrics().config, folder, 'run')
            self.observe(m, 0, {1: -10}); self.observe(m, 1, {1: 110})
            original = m.finish()
            for filename in EXPORTS:
                self.assertTrue((folder/filename).is_file())
            with (folder/'checkpoint_crossings.csv').open(newline='', encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 101)
            np.testing.assert_allclose(json.loads(rows[50]['crossing_position']), [500, 500])
            replayed = replay_journal(folder/'tracking_observations.jsonl', m.config, 'run').snapshot()
            self.assertEqual(original, replayed)


class PassiveIntegrationTests(unittest.TestCase):
    def test_one_existing_detector_call_per_frame_and_guard_gets_same_boxes(self):
        class Detector:
            names = {0: 'fruit'}
            calls = 0
            def track(self, *args, **kwargs):
                self.calls += 1
                return [SimpleNamespace(boxes=SimpleNamespace(xyxy=np.array([box(20)]),
                    cls=np.array([0]), id=np.array([17])))]
        detector = Detector()
        pipeline = NaartjiePipeline(SimpleNamespace(names={0: 'defect'}), detector)
        pipeline.tracking_metrics = TrackingMetrics(TrackingConfig(region=(.1,.1,.9,.9)))
        frame = np.zeros((1000, 1000, 3), np.uint8)
        with patch.object(pipeline.identity_guard, 'update', wraps=pipeline.identity_guard.update) as guard:
            result = pipeline.process_frame(frame, 0, capture_views=False, timestamp=0)
        self.assertEqual(result, [])
        self.assertEqual(detector.calls, 1)
        self.assertEqual(pipeline.tracking_metrics.snapshot()['tracks'][0]['track_id'], 17)
        self.assertEqual(pipeline.tracking_metrics.snapshot()['summary']['timed_frames'], 1)
        np.testing.assert_array_equal(guard.call_args.args[0], [box(20)])
        self.assertEqual(list(guard.call_args.args[1]), [17])

    def test_empty_frames_are_timed_and_observed(self):
        detector = SimpleNamespace(names={0: 'fruit'}, track=lambda *a, **k: [SimpleNamespace(boxes=None)])
        pipeline = NaartjiePipeline(SimpleNamespace(names={0: 'defect'}), detector)
        pipeline.tracking_metrics = TrackingMetrics()
        self.assertEqual(pipeline.process_frame(np.zeros((40,40,3), np.uint8), 0, capture_views=False), [])
        self.assertEqual(pipeline.tracking_metrics.snapshot()['summary']['timed_frames'], 1)

    def test_api_config_exports_replay_and_run_isolation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(main, 'RESULTS', root), patch.object(main, 'tracking_config_path', root/'config.json'), patch.object(main, 'tracking_current', None):
                client = TestClient(main.app)
                config = TrackingConfig(region=(.1,.1,.9,.9))
                self.assertEqual(client.post('/api/tracking/config', json=asdict(config)).status_code, 200)
                self.assertEqual(client.post('/api/tracking/config', json={'region': [1,0,0,1]}).status_code, 422)
                a = main._begin_tracking(root/'a')
                a.observe(0, 0, (1000,1000), [1], [box(-10)], .02)
                a.observe(1, .1, (1000,1000), [1], [box(110)], .02)
                a.finish()
                for filename in EXPORTS:
                    response = client.get(f'/api/tracking/runs/a/exports/{filename}')
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(filename, response.headers['content-disposition'])
                response = client.post('/api/tracking/runs/a/recalculate', json=asdict(config))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['summary']['completed_tracks'], 1)
                b = main._begin_tracking(root/'b')
                self.assertEqual(client.get('/api/tracking/status').json()['job_id'], 'b')
                self.assertEqual(client.get('/api/tracking/runs/b').json()['summary']['total_unique_track_ids'], 0)
                self.assertEqual(client.get('/api/tracking/runs/a').json()['summary']['completed_tracks'], 1)
                self.assertEqual(client.get('/api/tracking/runs/a/exports/other.csv').status_code, 404)
                self.assertEqual(client.post('/api/tracking/runs/b/recalculate', json=asdict(config)).status_code, 200)
                b.finish()

    def test_model_load_failure_closes_tracking_journal(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch.object(main, 'tracking_current', None), patch.object(main, '_make_pipeline', side_effect=RuntimeError('model fixture failed')):
                with self.assertRaisesRegex(RuntimeError, 'model fixture failed'):
                    main.analyze_video(Path('unused.mp4'), folder)
                self.assertEqual(main.tracking_current.state, 'error')
                self.assertIsNone(main.tracking_current._journal)

    def test_active_run_keeps_its_region_and_recalculation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(main, 'RESULTS', root), patch.object(main, 'tracking_config_path', root/'config.json'), patch.object(main, 'tracking_current', None):
                client = TestClient(main.app)
                initial = TrackingConfig(region=(.1,.1,.9,.9))
                changed = TrackingConfig(region=(.2,.2,.8,.8))
                client.post('/api/tracking/config', json=asdict(initial))
                a = main._begin_tracking(root/'a')
                self.assertTrue(main.analysis_lock.acquire(blocking=False))
                try:
                    client.post('/api/tracking/config', json=asdict(changed))
                    self.assertEqual(a.config.region, initial.region)
                    self.assertEqual(client.post('/api/tracking/runs/a/recalculate', json=asdict(changed)).status_code, 409)
                finally:
                    main.analysis_lock.release()
                a.finish()
                b = main._begin_tracking(root/'b')
                self.assertEqual(b.config.region, changed.region)
                b.finish()

    def test_live_runner_collects_and_saves_its_own_metrics(self):
        inspector = main.LiveInspector()
        class Detector:
            names = {0: 'fruit'}
            inference_calls = 0
            total_predictions = 0
            total_latency_ms = 0
            total_confidence = 0
            def track(self, *args, **kwargs):
                self.inference_calls += 1
                if self.inference_calls == 3:
                    inspector.stop_event.set()
                p = [-1, 50, 101][self.inference_calls-1]
                return [SimpleNamespace(boxes=SimpleNamespace(xyxy=np.array([box(p)]),
                    cls=np.array([0]), id=np.array([17])))]
        detector = Detector()
        segmenter = SimpleNamespace(names={0:'defect'}, inference_calls=0, total_predictions=0,
                                    total_latency_ms=0, total_confidence=0)
        pipeline = NaartjiePipeline(segmenter, detector)
        class Camera:
            sequence = 0
            raw_frame = np.zeros((1000,1000,3),np.uint8)
            raw_timestamp = 0
        camera = Camera()
        class Condition:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def wait_for(self, *args, **kwargs):
                camera.sequence += 1
                camera.raw_timestamp = (camera.sequence-1)*.1
        camera.condition = Condition()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(main, 'RESULTS', root), patch.object(main, 'camera', camera), \
                    patch.object(main, 'tracking_current', None), \
                    patch.object(main, '_tracking_config', return_value=TrackingConfig(region=(.1,.1,.9,.9))), \
                    patch.object(main, '_make_pipeline', return_value=(pipeline,detector,segmenter)), \
                    patch.object(pipeline, 'add_tracked_detection', return_value=False), \
                    patch.object(main, '_finish_track', side_effect=lambda p,i,o: p.drop_track(i)):
                self.assertTrue(main.analysis_lock.acquire(blocking=False))
                inspector._run('live-fixture')
                self.assertFalse(main.analysis_lock.locked())
                self.assertEqual(inspector.state, 'stopped')
                report = json.loads((root/'live-fixture/report.json').read_text(encoding='utf-8'))
                self.assertEqual(report['metrics']['tracking']['completed_tracks'], 1)
                self.assertEqual(report['metrics']['tracking']['timed_frames'], 3)
                self.assertEqual(detector.inference_calls, 3)
                self.assertEqual(segmenter.inference_calls, 0)
                for filename in EXPORTS:
                    self.assertTrue((root/'live-fixture'/filename).is_file())

    def test_video_runner_collects_even_when_duplicate_content_skips_capture(self):
        class Detector:
            names = {0:'fruit'}
            inference_calls = 0
            total_predictions = 0
            total_latency_ms = 0
            total_confidence = 0
            tracker = SimpleNamespace(args=SimpleNamespace(with_reid=True), min_track_len=1)
            def track(self, *args, **kwargs):
                p = [-1,50,101][self.inference_calls]
                self.inference_calls += 1
                return [SimpleNamespace(boxes=SimpleNamespace(xyxy=np.array([box(p)]),
                    cls=np.array([0]), id=np.array([17])))]
        class Video:
            index = 0
            released = False
            def isOpened(self): return True
            def get(self, prop):
                if prop == main.cv2.CAP_PROP_FPS: return 30
                if prop == main.cv2.CAP_PROP_FRAME_COUNT: return 3
                return (self.index-1)*1000/30
            def read(self):
                self.index += 1
                return (True,np.zeros((1000,1000,3),np.uint8)) if self.index <= 3 else (False,None)
            def release(self): self.released = True
        detector, video = Detector(), Video()
        segmenter = SimpleNamespace(names={0:'defect'}, inference_calls=0, total_predictions=0,
                                    total_latency_ms=0, total_confidence=0)
        pipeline = NaartjiePipeline(segmenter, detector)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(main, 'tracking_current', None), \
                    patch.object(main, '_tracking_config', return_value=TrackingConfig(region=(.1,.1,.9,.9))), \
                    patch.object(main, '_make_pipeline', return_value=(pipeline,detector,segmenter)), \
                    patch.object(main.cv2, 'VideoCapture', return_value=video), \
                    patch.object(pipeline, 'add_tracked_detection', return_value=False) as capture, \
                    patch.object(main, '_finish_track', side_effect=lambda p,i,o: p.drop_track(i)):
                metrics = {}
                main.analyze_video(Path('video-fixture.mp4'),root,metrics)
                self.assertEqual(metrics['tracking']['completed_tracks'],1)
                self.assertEqual(metrics['tracking']['timed_frames'],3)
                self.assertEqual(metrics['duplicate_frames'],2)
                self.assertEqual(detector.inference_calls,3)
                self.assertEqual(capture.call_count,1)
                self.assertTrue(video.released)
                self.assertTrue((root/'tracking_metrics.json').is_file())


if __name__ == '__main__':
    unittest.main()
