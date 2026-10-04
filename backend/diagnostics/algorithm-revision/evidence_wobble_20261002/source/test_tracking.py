"""Integration contract against the installed TrackTrack implementation."""
import unittest

import numpy as np
from ultralytics.engine.results import Boxes
from ultralytics.trackers.track_tracker import TRACKTRACK
from ultralytics.utils import YAML, IterableSimpleNamespace
from ultralytics.utils.checks import check_yaml
from dfine_segmenter import make_fruit_tracker, associate_fruit_detections, suppress_duplicate_detections


class TrackTrackTests(unittest.TestCase):
    def test_duplicate_queries_do_not_create_two_ids_for_one_fruit(self):
        tracker=make_fruit_tracker('cpu');tracker.reset()
        frame=np.zeros((160,160,3),np.uint8)
        size=None
        for offset in (0,3,6):
            rows=np.array([[20,20+offset,60,60+offset,.95,0],
                           [20.5,20+offset,60.5,60+offset,.4,0],
                           [100,20+offset,140,60+offset,.9,0]],np.float32)
            tracked,size=associate_fruit_detections(tracker,rows,frame,size)
            self.assertEqual(len(tracked),2)
            self.assertEqual(set(np.round(tracked[:,5],2)),{np.float32(.95),np.float32(.9)})
        # Nearby separate fruit survive, as do identical boxes of different classes.
        rows=np.array([[20,20,60,60,.95,0],[20,20,60,60,.4,1]],np.float32)
        self.assertEqual(len(suppress_duplicate_detections(rows)),2)

    def test_thin_low_confidence_entry_keeps_identity_as_visible_box_grows(self):
        # A radius-20 fruit moves down about 10 pixels per frame. These bounds
        # follow its visible circular cap until the entire fruit is in frame.
        for preset in (None, np.array([40., 40.]), np.array([80., 80.])):
            with self.subTest(typical_size=preset):
                tracker = make_fruit_tracker('cpu', .25)
                tracker.reset()
                frame = np.zeros((160, 160, 3), np.uint8)
                size, ids = preset, []
                for visible_box in ([69.5, 0, 90.5, 3], [61, 0, 99, 13], [60, 0, 100, 25],
                                    [60, 0, 100, 35], [60, 5, 100, 45]):
                    rows = np.array([[*visible_box, .38, 0]], np.float32)
                    tracked, size = associate_fruit_detections(tracker, rows, frame, size)
                    self.assertEqual(len(tracked), 1)
                    np.testing.assert_allclose(tracked[0,:4], visible_box)
                    ids.append(int(tracked[0,4]))
                self.assertEqual(len(set(ids)), 1)

    def test_low_confidence_interior_box_does_not_create_an_unseen_fruit(self):
        tracker=make_fruit_tracker('cpu');tracker.reset()
        frame=np.zeros((160,160,3),np.uint8)
        rows=np.array([[60,60,100,100,.38,0]],np.float32)
        tracked,_=associate_fruit_detections(tracker,rows,frame)
        self.assertEqual(len(tracked),0)

    def test_nearby_edge_fruit_keep_separate_ids_across_full_visibility(self):
        for confidence in (.38, .95):
            with self.subTest(interior_confidence=confidence):
                tracker=make_fruit_tracker('cpu');tracker.reset()
                frame=np.zeros((160,160,3),np.uint8)
                size=np.array([80.,80.])
                identities=[]
                for index, (left, right, bottom) in enumerate(((34.5,55.5,3),(26,64,13),
                                                              (25,65,25),(25,65,35),(25,65,45))):
                    top=5 if index==4 else 0
                    score=.38 if index==0 else confidence
                    rows=np.array([[left,top,right,bottom,score,0],
                                   [left+70,top,right+70,bottom,score,0]],np.float32)
                    tracked,size=associate_fruit_detections(tracker,rows,frame,size)
                    self.assertEqual(len(tracked),2)
                    tracked=tracked[np.argsort(tracked[:,0])]
                    identities.append(tuple(tracked[:,4].astype(int)))
                    np.testing.assert_allclose(tracked[:,:4],rows[:,:4])
                self.assertEqual(len(set(identities)),1)
                self.assertNotEqual(*identities[0])

    def test_entering_fruit_is_published_on_first_accepted_detection(self):
        tracker = make_fruit_tracker('cpu')
        tracker.args.gmc_method = 'none'
        tracker.reset()
        empty = Boxes(np.empty((0, 6), np.float32), (100, 100))
        for _ in range(3):
            self.assertEqual(len(tracker.update(empty, img=None)), 0)
        identifiers = []
        for x in (0, 2, 4):
            rows = np.array([[x, 15, x+30, 55, .95, 0]], np.float32)
            tracked = tracker.update(Boxes(rows, (100, 100)), img=None)
            self.assertEqual(len(tracked), 1)
            identifiers.append(int(tracked[0, 4]))
        self.assertEqual(len(set(identifiers)), 1)
        self.assertEqual(tracker.min_track_len, 1)

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
