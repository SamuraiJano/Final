"""Tracking must retain entry/last-seen observations even when mapping cannot."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

from algorithm import MappingError, NaartjiePipeline
import main


class EntryTrackingTests(unittest.TestCase):
    @staticmethod
    def pipeline():
        segmenter = SimpleNamespace(names={0: 'spot'})
        return NaartjiePipeline(segmenter, defer_defect_segmentation=True)

    def test_partial_entry_and_exit_keep_identity_without_becoming_complete_map_views(self):
        pipeline = self.pipeline()
        frame = np.full((100, 100, 3), 70, np.uint8)
        with self.assertRaisesRegex(MappingError, 'cut off'):
            pipeline.add_tracked_detection(frame, 7, (25, 0, 65, 20), 0)
        pipeline.record_tracked_detection(frame, 7, (25, 20, 65, 60), 1)
        # A duplicate-frame capture skip must not stop observation bookkeeping.
        pipeline.record_tracked_detection(frame, 7, (25, 20, 65, 60), 1)
        with self.assertRaisesRegex(MappingError, 'cut off'):
            pipeline.add_tracked_detection(frame, 7, (25, 80, 65, 100), 2)
        self.assertEqual([row['frame'] for row in pipeline.tracking_history_by_id[7]], [0, 1, 2])
        self.assertEqual(pipeline.last_seen_frame[7], 2)
        self.assertEqual(pipeline.tracking_images_by_id[7]['entry'][0], 0)
        self.assertEqual(pipeline.tracking_images_by_id[7]['last_seen'][0], 2)
        self.assertNotIn(7, pipeline.views_by_id)

    def test_mapping_failure_still_saves_entry_and_last_seen_evidence_and_releases_track(self):
        pipeline = self.pipeline()
        frame = np.full((100, 100, 3), 70, np.uint8)
        pipeline.record_tracked_detection(frame, 7, (25, 0, 65, 20), 0)
        pipeline.record_tracked_detection(frame, 7, (25, 80, 65, 100), 5)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'example'
            root.mkdir()
            result = main._finish_track(pipeline, 7, root)
            self.assertEqual(result['first_seen_frame'], 0)
            self.assertEqual(result['last_seen_frame'], 5)
            self.assertEqual(result['tracked_frames'], 2)
            self.assertEqual(result['status'], 'mapping_failed')
            self.assertEqual(result['views'], 0)
            for view in result['tracking_evidence']:
                self.assertTrue((root / '7' / Path(view['crop']).name).is_file())
            saved = json.loads((root / '7/result.json').read_text())
            self.assertEqual(saved['tracking_history'], result['tracking_history'])
        self.assertNotIn(7, pipeline.tracking_history_by_id)
        self.assertNotIn(7, pipeline.tracking_images_by_id)
        self.assertNotIn(7, pipeline.last_seen_frame)


if __name__ == '__main__':
    unittest.main()
