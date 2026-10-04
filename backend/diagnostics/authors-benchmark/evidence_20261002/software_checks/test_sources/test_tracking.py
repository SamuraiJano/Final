"""Integration contract against the installed TrackTrack implementation."""
import unittest

import numpy as np
from ultralytics.engine.results import Boxes
from ultralytics.trackers.track_tracker import TRACKTRACK
from ultralytics.utils import YAML, IterableSimpleNamespace
from ultralytics.utils.checks import check_yaml


class TrackTrackTests(unittest.TestCase):
    def test_identity_survives_motion_and_one_missing_detection(self):
        args = IterableSimpleNamespace(**YAML.load(check_yaml('tracktrack.yaml')))
        args.gmc_method = 'none'
        tracker = TRACKTRACK(args)
        tracker.reset()
        ids = []
        for frame in range(8):
            rows = (np.empty((0, 6), np.float32) if frame == 5 else
                    np.array([[20+frame*2, 20, 60+frame*2, 60, .95, 0]], np.float32))
            tracked = tracker.update(Boxes(rows, (100, 100)), img=None)
            if len(tracked):
                self.assertEqual(tracked.shape[1], 8)
                adapted = Boxes(tracked[:, :7], (100, 100))
                ids.append(int(adapted.id[0]))
                self.assertEqual(int(adapted.cls[0]), 0)
                self.assertAlmostEqual(float(adapted.conf[0]), .95, places=5)
        self.assertGreaterEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 1)
        self.assertFalse(args.with_reid)


if __name__ == '__main__':
    unittest.main()
