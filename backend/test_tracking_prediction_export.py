"""Replay provenance and original-frame alignment controls."""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from export_tracking_test_predictions import load_cached_detections


class TrackingPredictionExportTests(unittest.TestCase):
    def test_cache_preserves_original_order_and_explicit_empty_frames(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'report.json').write_text(json.dumps({'input_sha256': {'video': 'a'*64}}))
            row0 = np.array([[1, 2, 20, 22, .9, 0]], np.float32)
            row2 = np.array([[5, 6, 24, 26, .8, 0]], np.float32)
            np.savez(root/'cache.npz', frame_00002=row2, frame_00000=row0,
                     frame_00001=np.empty((0, 6), np.float32))
            rows, provenance = load_cached_detections(root/'cache.npz', 'a'*64, 3)
            np.testing.assert_array_equal(rows[0], row0)
            self.assertEqual(rows[1].shape, (0, 6))
            np.testing.assert_array_equal(rows[2], row2)
            self.assertEqual(provenance['input_sha256']['video'], 'a'*64)

    def test_missing_original_frame_and_wrong_video_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'report.json').write_text(json.dumps({'input_sha256': {'video': 'a'*64}}))
            np.savez(root/'cache.npz', frame_00001=np.empty((0, 6), np.float32))
            with self.assertRaisesRegex(ValueError, 'lack original frames'):
                load_cached_detections(root/'cache.npz', 'a'*64, 2)
            with self.assertRaisesRegex(ValueError, 'does not match'):
                load_cached_detections(root/'cache.npz', 'b'*64, 1)

    def test_unproven_or_invalid_detections_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            np.savez(root/'cache.npz', frame_00000=np.array([[1, 2, 20, 22, .9, 0]], np.float32))
            with self.assertRaisesRegex(ValueError, 'report.json'):
                load_cached_detections(root/'cache.npz', 'a'*64, 1)
            (root/'report.json').write_text(json.dumps({'input_sha256': {'video': 'a'*64}}))
            np.savez(root/'cache.npz', frame_00000=np.array([[1, 2, 0, 22, .9, 0]], np.float32))
            with self.assertRaisesRegex(ValueError, 'invalid boxes'):
                load_cached_detections(root/'cache.npz', 'a'*64, 1)


if __name__ == '__main__':
    unittest.main()
