"""Stopping a video run must release the inference slot and skip its report."""

import io
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi import UploadFile

import main


class AnalysisCancelTests(unittest.TestCase):
    def setUp(self):
        self.results = tempfile.TemporaryDirectory()
        self.results_patch = patch.object(main, "RESULTS", Path(self.results.name))
        self.results_patch.start()

    def tearDown(self):
        with main.analysis_control_lock:
            main.pending_cancellations.clear()
            main.analysis_cancel_event.clear()
        self.results_patch.stop()
        self.results.cleanup()

    @staticmethod
    def video():
        return UploadFile(file=io.BytesIO(b"video"), filename="sample.mp4")

    def test_stop_before_upload_handler_starts(self):
        self.assertEqual(main.stop_analysis("early")["state"], "cancelling")
        with patch.object(main, "analyze_video") as analyze:
            result = main.analyze_upload(self.video(), "early")
        self.assertEqual(result["status"], "cancelled")
        analyze.assert_not_called()
        self.assertEqual(list(Path(self.results.name).iterdir()), [])
        self.assertFalse(main.analysis_lock.locked())

    def test_stop_during_processing(self):
        started = threading.Event()

        def wait_for_stop(_path, _output, _metrics, _progress):
            started.set()
            self.assertTrue(main.analysis_cancel_event.wait(3))
            raise main.AnalysisCancelled()

        with patch.object(main, "analyze_video", side_effect=wait_for_stop):
            with ThreadPoolExecutor(max_workers=1) as pool:
                run = pool.submit(main.analyze_upload, self.video(), "running")
                self.assertTrue(started.wait(3))
                self.assertEqual(main.stop_analysis("running")["state"], "cancelling")
                self.assertEqual(run.result(timeout=3)["status"], "cancelled")
        self.assertEqual(main.analysis_status()["state"], "cancelled")
        self.assertEqual(list(Path(self.results.name).iterdir()), [])
        self.assertFalse(main.analysis_lock.locked())

    def test_frame_loop_observes_stop_and_releases_video(self):
        class FakeVideo:
            released = False

            def isOpened(self):
                return True

            def get(self, _property):
                return 1

            def read(self):
                return True, np.zeros((24, 24, 3), np.uint8)

            def release(self):
                self.released = True

        class FakePipeline:
            last_seen_frame = {}

            def process_frame(self, *_args, **_kwargs):
                main.analysis_cancel_event.set()

        video = FakeVideo()
        with patch.object(main, "_make_pipeline", return_value=(FakePipeline(), object(), object())):
            with patch.object(main.cv2, "VideoCapture", return_value=video):
                with self.assertRaises(main.AnalysisCancelled):
                    main.analyze_video(Path("unused.mp4"), Path(self.results.name))
        self.assertTrue(video.released)


if __name__ == "__main__":
    unittest.main()
