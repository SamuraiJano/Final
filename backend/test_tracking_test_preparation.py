"""Controls for frame alignment and prediction-free test preparation."""
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from prepare_tracking_test import prediction_rows, prepare, sha256_file


class PreparationTests(unittest.TestCase):
    def test_preserves_empty_frames_edge_bounds_and_local_frame_number(self):
        cache = [{"frame": 7, "tracks": [[-1, 2, 20, 30, 41, .7, 0]]},
                 {"frame": 8, "tracks": []},
                 {"frame": 9, "tracks": [[8, 9, 24, 31, 42, .8, 0]]}]
        rows = prediction_rows(cache, 7, 9)
        self.assertEqual([row[0] for row in rows], [1, 3])
        self.assertEqual(rows[0][:7], [1, 41, -1, 2, 21, 28, .7])

    def test_missing_frames_duplicate_ids_and_invalid_boxes_rejected(self):
        for cache, start, end in [
            ([{"frame": 0, "tracks": []}], 0, 1),
            ([{"frame": 0, "tracks": []}, {"frame": 0, "tracks": []}], 0, 0),
            ([{"frame": 0, "tracks": [[0, 0, 10, 10, 1, .9, 0]] * 2}], 0, 0),
            ([{"frame": 0, "tracks": [[0, 0, 0, 10, 1, .9, 0]]}], 0, 0),
            ([{"frame": 0, "tracks": [[0, 0, 10, 10, 1.2, .9, 0]]}], 0, 0),
            ([{"frame": 0, "tracks": [[0, 0, float("nan"), 10, 1, .9, 0]]}], 0, 0),
        ]:
            with self.subTest(cache=cache), self.assertRaises(ValueError):
                prediction_rows(cache, start, end)

    def test_real_decode_and_blind_annotation_start_empty(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            video = root / "input.avi"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
            self.assertTrue(writer.isOpened())
            for level in (20, 70, 120, 170):
                writer.write(np.full((48, 64, 3), level, np.uint8))
            writer.release()
            cache = root / "cache.json"
            cache.write_text(json.dumps([{"frame": index, "tracks": [[4, 5, 14, 15, 777, .9, 0]]}
                                         for index in range(4)]))
            output = root / "test"
            manifest = prepare(video, cache, output, 1, 2)
            self.assertEqual(manifest["frames"], [1, 2])
            self.assertEqual(manifest["source_start_frame"], 1)
            self.assertEqual(manifest["reviewed_frames"], [])
            self.assertFalse(manifest["annotation_complete"])
            self.assertEqual((output / "ground_truth.csv").read_text(), "")
            self.assertAlmostEqual(cv2.imread(str(output / "frames/000001.jpg")).mean(), 70, delta=3)
            self.assertAlmostEqual(cv2.imread(str(output / "frames/000002.jpg")).mean(), 120, delta=3)
            html = (output / "annotate.html").read_text(encoding="utf-8")
            self.assertNotIn("__DATASET_JSON__", html)
            self.assertNotIn("777", html)
            self.assertNotIn("predictions.csv", html)
            self.assertEqual(manifest["source_sha256"], sha256_file(video))
            self.assertTrue((output / "physical_cohorts.csv").is_file())
            with self.assertRaises(FileExistsError):
                prepare(video, cache, output, 1, 2)

    def test_mismatched_video_provenance_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            video = root / "input.avi"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
            self.assertTrue(writer.isOpened())
            writer.write(np.zeros((48, 64, 3), np.uint8)); writer.release()
            cache = root / "cache.json"
            cache.write_text('[{"frame":0,"tracks":[]}]')
            (root / "report.json").write_text(json.dumps({"input_sha256": {"video": "0" * 64}}))
            with self.assertRaisesRegex(ValueError, "different source video"):
                prepare(video, cache, root / "test", 0, 0)
            self.assertFalse((root / "test").exists())


if __name__ == "__main__":
    unittest.main()
