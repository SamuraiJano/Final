"""Fairness, timing boundaries, raw-ID arithmetic and installed tracker integration."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np

import tracker_comparison as comparison
from tracker_comparison_metrics import DiagnosticSettings, RawTrackStatistics
from tracker_comparison_report import generate_report


def raw(track_id, x=10, score=.95):
    return [x, 10, x+20, 30, track_id, score, 0, 0]


class StatisticsTests(unittest.TestCase):
    def test_lifetime_consistency_uses_observed_interval_and_entire_video_denominator(self):
        stats = RawTrackStatistics('Test', 'full')
        for frame, rows in enumerate(([], [raw(91)], [], [raw(91, 12)], [])):
            stats.observe(frame, frame*.2, rows, .01)
        summary, tracks = stats.finish()
        track = tracks[0]
        self.assertEqual(track['track_id'], 91)
        self.assertEqual(track['first_frame'], 1)
        self.assertEqual(track['last_frame'], 3)
        self.assertEqual(track['observed_frames'], 2)
        self.assertEqual(track['possible_frames_between_first_and_last'], 3)
        self.assertAlmostEqual(track['lifetime_seconds'], .4)
        self.assertEqual(track['processed_video_frames_percent'], 40)
        self.assertAlmostEqual(track['consistency_percent'], 100*2/3)
        self.assertEqual(track['mean_box_width'], 20)
        self.assertEqual(summary['unique_raw_ids'], 1)
        self.assertEqual(summary['maximum_active_ids'], 1)
        self.assertEqual(summary['mean_active_ids'], .4)
        self.assertEqual(summary['final_active_ids'], 0)
        self.assertAlmostEqual(summary['processing_fps'], 100)
        self.assertEqual(summary['average_time_ms'], 10)

    def test_zero_lifetime_single_frame_and_short_thresholds_are_strict(self):
        stats = RawTrackStatistics('Test', 'cached')
        stats.observe(0, 0, [raw(1)], .01)
        stats.observe(1, .25, [raw(1), raw(2, 40)], .01)
        summary, tracks = stats.finish()
        self.assertEqual([t['lifetime_seconds'] for t in tracks], [.25, 0])
        self.assertEqual(summary['short_lived_ids'][0]['count'], 1)
        self.assertEqual(summary['short_lived_ids'][0]['percent'], 50)
        self.assertEqual(summary['mean_lifetime_seconds'], .125)
        self.assertEqual(summary['median_lifetime_seconds'], .125)
        self.assertEqual(summary['minimum_lifetime_seconds'], 0)
        self.assertEqual(summary['maximum_lifetime_seconds'], .25)
        self.assertEqual(sum(x['count'] for x in summary['lifetime_distribution']), 2)

    def test_substantial_persistence_has_explicit_observed_interval_definition(self):
        stats = RawTrackStatistics('Test', 'full')
        for frame in range(11):
            stats.observe(frame, frame*.1, [raw(1)], .01)
        summary, _ = stats.finish()
        self.assertEqual(summary['substantial_persistence_ids'], 1)
        self.assertEqual(summary['substantial_persistence_percent'], 100)
        self.assertEqual(summary['diagnostic_settings']['substantial_consistency_percent'], 90)

    def test_empty_frames_do_not_create_ids_or_claim_lifetime(self):
        stats = RawTrackStatistics('Test', 'cached')
        stats.observe(0, 0, [], .01)
        summary, tracks = stats.finish()
        self.assertEqual(tracks, [])
        self.assertIsNone(summary['mean_lifetime_seconds'])
        self.assertIsNone(summary['mean_consistency_percent'])
        self.assertEqual(summary['unique_raw_ids'], 0)
        self.assertEqual(summary['mean_active_ids'], 0)
        self.assertEqual(summary['short_lived_ids'][0]['count'], 0)
        self.assertIsNone(summary['short_lived_ids'][0]['percent'])

    def test_fragmentation_predicts_velocity_from_timestamps_without_merging_ids(self):
        stats = RawTrackStatistics('Test', 'cached')
        stats.observe(0, 0, [raw(81, 0)], .01)
        stats.observe(1, .1, [raw(81, 10)], .01)
        stats.observe(2, .3, [raw(909, 30)], .01)
        summary, tracks = stats.finish()
        self.assertEqual(summary['suspected_id_fragmentations'], 1)
        self.assertEqual([t['track_id'] for t in tracks], [81, 909])
        event = next(e for e in stats.events if e['event'] == 'Suspected ID Fragmentation')
        self.assertEqual(event['previous_track_id'], 81)
        self.assertEqual(event['track_id'], 909)
        self.assertAlmostEqual(event['predicted_x'], 40)
        self.assertAlmostEqual(event['gap_seconds'], .2)

    def test_fragmentation_window_is_seconds_not_frame_count(self):
        for timestamps, expected in (([0, .1, .2], 1), ([0, .1, .7], 0)):
            stats = RawTrackStatistics('Test', 'cached')
            for index, (timestamp, row) in enumerate(zip(timestamps, [raw(1), raw(1), raw(2)])):
                stats.observe(index, timestamp, [row], .01)
            self.assertEqual(stats.finish()[0]['suspected_id_fragmentations'], expected)

    def test_fragmentation_matches_one_pair_and_respects_class_and_size(self):
        stats = RawTrackStatistics('Test', 'cached')
        stats.observe(0, 0, [raw(1), raw(3)], .01)
        stats.observe(1, .1, [raw(2)], .01)
        self.assertEqual(stats.finish()[0]['suspected_id_fragmentations'], 1)
        other_class = raw(4)
        other_class[6] = 1
        stats.observe(2, .2, [other_class], .01)
        self.assertEqual(stats.finish()[0]['suspected_id_fragmentations'], 1)

    def test_duplicate_raw_ids_and_invalid_data_fail_clearly(self):
        for rows in ([raw(1), raw(1)], [raw(-1)], [[0]*8], [[float('nan')]*8], [[1]*7]):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    RawTrackStatistics('Test', 'full').observe(0, 0, rows, .01)

    def test_nonconsecutive_frames_backwards_time_and_nonpositive_timing_rejected(self):
        stats = RawTrackStatistics('Test', 'full')
        with self.assertRaises(ValueError):
            stats.observe(1, 0, [], .01)
        stats.observe(0, 1, [], .01)
        with self.assertRaises(ValueError):
            stats.observe(1, 0, [], .01)
        with self.assertRaises(ValueError):
            stats.observe(1, 2, [], 0)

    def test_invalid_diagnostic_settings_rejected(self):
        for args in (dict(fragmentation_window_seconds=0), dict(fragmentation_distance_box_diagonals=float('nan')),
                     dict(substantial_consistency_percent=101)):
            with self.assertRaises(ValueError):
                DiagnosticSettings(**args)


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.configurations = comparison.installed_trackers('cpu')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.video = self.root/'conveyor.avi'
        writer = cv2.VideoWriter(str(self.video), cv2.VideoWriter_fourcc(*'MJPG'), 10., (64, 64))
        self.assertTrue(writer.isOpened())
        for index in range(6):
            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            frame[10:30, 10+index:30+index] = 120
            writer.write(frame)
        writer.release()
        self.model = self.root/'best_stg1.pth'
        self.model.write_bytes(b'selected detector fixture')
        self.args = comparison.parser().parse_args(['--video', str(self.video), '--model', str(self.model),
                                                    '--device', 'cpu', '--output', str(self.root/'results')])

    def fake_detector(self, clock=None):
        class FakeDetector:
            kind = 'test detector'
            preprocessing = 'shared test preprocessing'
            names = {0: 'naartjie'}
            loader_metadata = None
            calls = []

            def __init__(self, checkpoint, device, confidence, iou, image_size):
                self.device = device
                self.settings = checkpoint, device, confidence, iou, image_size

            def predict(self, frame):
                self.calls.append((self.settings, hashlib.sha256(frame.tobytes()).hexdigest()))
                if clock is not None:
                    clock[0] += .005
                return np.array([[10, 10, 30, 30, .95, 0]], dtype=np.float32)

            def synchronize(self):
                pass
        return FakeDetector

    def test_all_six_installed_yaml_files_and_real_update_reset_interfaces(self):
        self.assertEqual(set(self.configurations), set(comparison.TRACKERS))
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        rows = np.array([[10, 10, 30, 30, .95, 0]], dtype=np.float32)
        for key, config in self.configurations.items():
            with self.subTest(key=key):
                self.assertEqual(config['filename'], key+'.yaml')
                self.assertEqual(comparison.sha256_file(Path(config['path'])), config['sha256'])
                tracker = comparison.fresh_tracker(key, self.configurations, 'cpu')
                output = comparison.update_tracker(tracker, rows, frame)
                self.assertGreater(len(output), 0)
                self.assertEqual(int(output[0, 4]), 1)
                tracker.reset()
                self.assertEqual(tracker.frame_id, 0)
                again = comparison.update_tracker(tracker, rows, frame)
                np.testing.assert_array_equal(output, again)

    def test_selected_yolo_checkpoint_records_effective_stride_aligned_size(self):
        import torch
        from ultralytics.engine.results import Boxes
        calls = []
        class LocalYOLO:
            task = 'detect'
            names = {0: 'naartjie'}
            model = SimpleNamespace(stride=torch.tensor([8., 16., 32.]))

            def __init__(self, checkpoint, task):
                calls.append(checkpoint)

            def predict(self, frame, **kwargs):
                calls.append(kwargs)
                return [SimpleNamespace(boxes=Boxes(torch.tensor([[10, 10, 30, 30, .95, 0]]), frame.shape[:2]))]

        checkpoint = self.root/'best.pt'
        checkpoint.write_bytes(b'local model fixture')
        with patch('ultralytics.YOLO', LocalYOLO):
            detector = comparison.Detector(checkpoint, 'cpu', .25, .7, 641)
            self.assertEqual(detector.input_size, [672, 672])
            rows = detector.predict(np.zeros((64, 64, 3), dtype=np.uint8))
        self.assertEqual(rows.shape, (1, 6))
        self.assertEqual(calls[-1]['imgsz'], [672, 672])
        self.assertEqual(calls[-1]['conf'], .25)
        self.assertEqual(calls[-1]['iou'], .7)
        self.assertFalse(calls[-1]['rect'])
        self.assertFalse(calls[-1]['half'])

    def test_both_modes_share_video_detector_settings_raw_ids_and_complete_frame_count(self):
        detector = self.fake_detector()
        folder = comparison.compare(self.args, detector)
        data = json.loads((folder/'comparison_summary.json').read_text())
        self.assertTrue(data['complete'])
        self.assertEqual(len(data['results']), 12)
        self.assertEqual({r['processed_frames'] for r in data['results']}, {6})
        self.assertEqual({r['warmup_frames_excluded'] for r in data['results']}, {3})
        self.assertTrue(all(r['fresh_state_verified'] and r['identical_video_frames_verified'] for r in data['results']))
        self.assertTrue(all(r['detection_matches_cache'] for r in data['results']))
        self.assertEqual(len({r['detection_sequence_sha256'] for r in data['results']}), 1)
        self.assertEqual(len({call[0] for call in detector.calls}), 1)
        self.assertEqual(detector.calls[0][0][2:], (.25, .7, 640))
        meta = data['metadata']
        self.assertEqual(meta['video']['frame_count'], 6)
        self.assertEqual(meta['video']['source_fps'], 10)
        self.assertTrue(meta['cached_detection_sequences_identical'])
        self.assertEqual(meta['detector_checkpoint_sha256'], comparison.sha256_file(self.model))
        for result in data['results']:
            path = Path(result['result_folder'])
            config = self.configurations[result['tracker_key']]
            self.assertEqual(comparison.sha256_file(path/config['filename']), config['sha256'])
            for name in ('tracks.csv', 'events.csv', 'frames.csv', 'observations.csv', 'summary.json', 'tracker_config.json'):
                self.assertTrue((path/name).is_file())
            with (path/'tracks.csv').open(newline='') as f:
                tracks = list(csv.DictReader(f))
            with (path/'observations.csv').open(newline='') as f:
                observations = list(csv.DictReader(f))
            raw_ids = {int(row['track_id']) for row in observations}
            self.assertEqual(raw_ids, {int(row['track_id']) for row in tracks})
            self.assertEqual(result['unique_raw_ids'], len(raw_ids))
            self.assertAlmostEqual(result['mean_lifetime_seconds'],
                                   sum(float(row['lifetime_seconds']) for row in tracks)/len(tracks))
            self.assertAlmostEqual(result['mean_consistency_percent'],
                                   sum(float(row['consistency_percent']) for row in tracks)/len(tracks))
        html = (folder/'report.html').read_text(encoding='utf-8')
        self.assertIn('Tracker-only processing FPS', html)
        self.assertNotIn('<script src=', html)
        self.assertNotIn('https://cdn', html)

    def test_timing_excludes_writes_annotation_encoding_and_decode(self):
        clock = [0.]
        original_update, original_csv = comparison.update_tracker, comparison.write_csv

        def update(*args):
            result = original_update(*args)
            clock[0] += .002
            return result

        def slow_csv(*args):
            clock[0] += 9.
            return original_csv(*args)

        def slow_annotate(frame, *args):
            clock[0] += 8.
            return frame.copy()

        def slow_hash(frame):
            clock[0] += 7.
            return hashlib.sha256(frame.tobytes()).hexdigest()

        actual_capture, actual_writer = cv2.VideoCapture, cv2.VideoWriter

        class SlowCapture:
            def __init__(self, *args):
                self.capture = actual_capture(*args)

            def read(self):
                clock[0] += 6.
                return self.capture.read()

            def __getattr__(self, name):
                return getattr(self.capture, name)

        class SlowEncoder:
            def __init__(self, *args):
                self.writer = actual_writer(*args)

            def write(self, image):
                clock[0] += 11.
                return self.writer.write(image)

            def __getattr__(self, name):
                return getattr(self.writer, name)

        self.args.trackers = ['bytetrack']
        self.args.annotated = True
        with patch.object(comparison, 'perf_counter', lambda: clock[0]), \
                patch.object(comparison, 'update_tracker', update), \
                patch.object(comparison, 'write_csv', slow_csv), \
                patch.object(comparison, 'annotate', slow_annotate), \
                patch.object(comparison, 'frame_hash', slow_hash), \
                patch.object(cv2, 'VideoCapture', SlowCapture), \
                patch.object(cv2, 'VideoWriter', SlowEncoder):
            folder = comparison.compare(self.args, self.fake_detector(clock))
        data = json.loads((folder/'comparison_summary.json').read_text())
        for result in data['results']:
            expected = .007 if result['mode'] == 'full' else .002
            self.assertAlmostEqual(result['average_time_ms'], expected*1000, places=7)
            self.assertAlmostEqual(result['processing_fps'], 1/expected, places=7)
            capture = cv2.VideoCapture(str(Path(result['result_folder'])/'annotated.mp4'))
            self.assertEqual(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 6)
            capture.release()

    def test_cuda_sync_precedes_start_and_stop(self):
        calls = []
        def sync():
            calls.append('sync')
        def clock():
            calls.append('clock')
            return len(calls)
        result, seconds = comparison.timed_call(lambda: calls.append('operation'), sync, clock)
        self.assertIsNone(result)
        self.assertGreater(seconds, 0)
        self.assertEqual(calls, ['sync', 'clock', 'operation', 'sync', 'clock'])

    def test_cache_is_not_mutated_by_tracker(self):
        rows = np.array([[10, 10, 30, 30, .95, 0]], dtype=np.float32)
        rows.flags.writeable = False
        before = rows.copy()
        class MutatingTracker:
            def update(self, boxes, frame):
                boxes.data[:] = 0
                return []
        comparison.update_tracker(MutatingTracker(), rows, np.zeros((64, 64, 3), dtype=np.uint8))
        np.testing.assert_array_equal(rows, before)

    def test_repeated_comparisons_do_not_overwrite_previous_run(self):
        self.args.trackers, self.args.mode = ['bytetrack'], 'cached'
        first = comparison.compare(self.args, self.fake_detector())
        before = comparison.sha256_file(first/'comparison_summary.json')
        second = comparison.compare(self.args, self.fake_detector())
        self.assertNotEqual(first, second)
        self.assertEqual(before, comparison.sha256_file(first/'comparison_summary.json'))

    def test_full_only_and_cached_only_modes_use_correct_timing_scope(self):
        self.args.trackers = ['bytetrack']
        for mode in ('full', 'cached'):
            self.args.mode = mode
            folder = comparison.compare(self.args, self.fake_detector())
            data = json.loads((folder/'comparison_summary.json').read_text())
            self.assertEqual(len(data['results']), 1)
            result = data['results'][0]
            self.assertEqual(result['timing_scope'], 'detector_plus_tracker' if mode == 'full' else 'tracker_only')
            self.assertEqual((folder/'detections.npz').exists(), mode == 'cached')
            self.assertIsNone(data['metadata']['cached_detection_sequences_identical'] if mode == 'full' else None)

    def test_missing_inputs_and_mixed_all_selection_fail_without_results(self):
        for change in (dict(video=str(self.root/'missing.mp4')), dict(trackers=['all', 'bytetrack']),
                       dict(conf=1.1), dict(iou=-1), dict(warmup=-1)):
            args = SimpleNamespace(**dict(vars(self.args), **change))
            with self.assertRaises((ValueError, FileNotFoundError)):
                comparison.compare(args, self.fake_detector())
        self.assertFalse((self.root/'results').exists())

    def test_failed_run_is_marked_failed_instead_of_fabricating_metrics(self):
        detector = self.fake_detector()
        def fail(frame):
            raise RuntimeError('deliberate detector failure')
        detector.predict = staticmethod(fail)
        with self.assertRaisesRegex(RuntimeError, 'deliberate detector failure'):
            comparison.compare(self.args, detector)
        folder = next((self.root/'results').iterdir())
        self.assertEqual(json.loads((folder/'status.json').read_text())['status'], 'failed')
        self.assertFalse((folder/'report.html').exists())

    def test_changed_frame_or_timestamp_rejected(self):
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        inputs = dict(timestamps=np.array([0.]), frame_hashes=[comparison.frame_hash(frame)])
        comparison.verify_frame(inputs, 0, 0, frame)
        for index, timestamp, image in ((1, 0, frame), (0, 1, frame), (0, 0, frame+1)):
            with self.assertRaises(ValueError):
                comparison.verify_frame(inputs, index, timestamp, image)

    def test_html_data_escapes_script_termination(self):
        path = self.root/'report.html'
        generate_report(path, {'filename': '</script><script>bad()</script>'}, [])
        html = path.read_text(encoding='utf-8')
        self.assertNotIn('</script><script>bad()', html)
        self.assertIn('\\u003c/script>', html)


if __name__ == '__main__':
    unittest.main()
