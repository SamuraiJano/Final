"""Failed mapping/video runs must release crops without hiding their error."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from algorithm import FruitView, MappingError, NaartjiePipeline
import main


TRACK_STATE = (
    'views_by_id', 'last_capture_frame', 'last_seen_frame',
    'rejected_views_by_id', 'tracking_history_by_id', 'tracking_images_by_id',
)


class AnalysisCleanupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.output = Path(self.directory.name)
        self.pipeline = NaartjiePipeline(SimpleNamespace(names={0: 'spot'}),
                                        defer_defect_segmentation=True)
        self.add_track(7)
        self.add_track(8)

    def tearDown(self):
        self.directory.cleanup()

    def add_track(self, identity):
        self.pipeline.drop_track(identity)
        frame = np.full((40, 40, 3), 70, np.uint8)
        for index in (0, 1):
            self.pipeline.record_tracked_detection(frame, identity, (8, 8, 24, 24), index)
        image = frame[8:24, 8:24].copy()
        mask = np.ones(image.shape[:2], np.uint8)
        self.pipeline.views_by_id[identity] = [
            FruitView(image.copy(), mask.copy(), frame_index=index) for index in (0, 1)
        ]
        self.pipeline.last_capture_frame[identity] = 1
        self.pipeline.rejected_views_by_id[identity] = {'earlier unusable crop': 1}

    def assert_released(self, identity):
        for name in TRACK_STATE:
            self.assertNotIn(identity, getattr(self.pipeline, name), name)

    def fake_video(self, opened=True):
        video = Mock()
        video.isOpened.return_value = opened
        video.get.return_value = 1
        video.read.side_effect = [
            (True, np.zeros((40, 40, 3), np.uint8)), (False, None),
        ]
        return video

    def analyze(self, video):
        with patch.object(main, '_make_pipeline',
                          return_value=(self.pipeline, object(), object())):
            with patch.object(main.cv2, 'VideoCapture', return_value=video):
                return main.analyze_video(Path('unused.mp4'), self.output)

    def test_unexpected_track_errors_propagate_and_release_only_that_track(self):
        for error in (RuntimeError('unexpected matcher failure'), MemoryError('allocation failed')):
            with self.subTest(error=type(error).__name__):
                self.add_track(7)
                with patch.object(self.pipeline, 'finish_track', side_effect=error):
                    with self.assertRaises(type(error)) as raised:
                        main._finish_track(self.pipeline, 7, self.output)
                self.assertIs(raised.exception, error)
                self.assert_released(7)
                for name in TRACK_STATE:
                    self.assertIn(8, getattr(self.pipeline, name), name)
                # Entry evidence precedes matching; no successful result is invented.
                self.assertTrue((self.output / '7/tracking_entry_frame_00000.png').is_file())
                self.assertFalse((self.output / '7/result.json').exists())

    def test_mapping_failure_keeps_views_until_evidence_is_written(self):
        save_evidence = main._save_view_evidence

        def save_while_retained(views, folder, url):
            self.assertIs(views, self.pipeline.views_by_id[7])
            self.assertIn(7, self.pipeline.tracking_images_by_id)
            return save_evidence(views, folder, url)

        with patch.object(self.pipeline, 'finish_track', side_effect=MappingError('no motion')):
            with patch.object(main, '_save_view_evidence', side_effect=save_while_retained):
                result = main._finish_track(self.pipeline, 7, self.output)
        self.assertEqual(result['status'], 'mapping_failed')
        self.assertIsNone(result['grade'])
        self.assertEqual(len(result['view_evidence']), 2)
        self.assertTrue((self.output / '7/result.json').is_file())
        self.assert_released(7)

    def test_frame_processing_error_releases_video_and_all_remaining_tracks(self):
        for error in (RuntimeError('detector failed'), MemoryError('allocation failed')):
            with self.subTest(error=type(error).__name__):
                self.add_track(7)
                self.add_track(8)
                video = self.fake_video()
                with patch.object(self.pipeline, 'process_frame', side_effect=error):
                    with self.assertRaises(type(error)) as raised:
                        self.analyze(video)
                self.assertIs(raised.exception, error)
                video.release.assert_called_once()
                self.assert_released(7)
                self.assert_released(8)

    def test_end_of_video_mapping_error_releases_other_pending_tracks(self):
        video = self.fake_video()
        error = MemoryError('allocation failed during mapping')
        with patch.object(self.pipeline, 'process_frame'):
            with patch.object(self.pipeline, 'finish_track', side_effect=error):
                with self.assertRaises(MemoryError) as raised:
                    self.analyze(video)
        self.assertIs(raised.exception, error)
        video.release.assert_called_once()
        self.assert_released(7)
        self.assert_released(8)

    def test_unopened_video_releases_capture_and_pending_tracks(self):
        video = self.fake_video(opened=False)
        with self.assertRaisesRegex(ValueError, 'Could not open'):
            self.analyze(video)
        video.release.assert_called_once()
        self.assert_released(7)
        self.assert_released(8)

    def test_cancel_after_pipeline_creation_releases_tracks_without_opening_video(self):
        with patch.object(main, '_check_analysis_cancelled',
                          side_effect=[None, main.AnalysisCancelled()]):
            with patch.object(main, '_make_pipeline',
                              return_value=(self.pipeline, object(), object())):
                with patch.object(main.cv2, 'VideoCapture') as capture:
                    with self.assertRaises(main.AnalysisCancelled):
                        main.analyze_video(Path('unused.mp4'), self.output)
        capture.assert_not_called()
        self.assert_released(7)
        self.assert_released(8)

    def test_completed_run_saves_review_evidence_and_releases_tracks(self):
        video = self.fake_video()
        with patch.object(self.pipeline, 'process_frame'):
            with patch.object(self.pipeline, 'finish_track', side_effect=MappingError('no motion')):
                rows = self.analyze(video)
        self.assertEqual([row['track_id'] for row in rows], [7, 8])
        self.assertTrue(all(row['status'] == 'mapping_failed' and row['grade'] is None for row in rows))
        self.assertTrue(all(row['view_evidence'] for row in rows))
        video.release.assert_called_once()
        self.assert_released(7)
        self.assert_released(8)


if __name__ == '__main__':
    unittest.main()
