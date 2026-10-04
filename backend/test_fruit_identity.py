"""Known physical trajectories test identity recovery and map isolation."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from algorithm import FruitView, MapResult, NaartjiePipeline
from fruit_identity import FruitIdentityGuard
from conveyor_identity import ConveyorIdentitySettings
import main


def box(x=100, y=100):
    return [x, y, x+40, y+40]


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.guard = FruitIdentityGuard()

    def update(self, frame, ids, boxes):
        return self.guard.update(boxes, ids, frame, (600, 600))

    def seed(self):
        for frame in range(3):
            self.update(frame, [7], [box(y=100+5*frame)])

    def test_replacement_id_retains_one_capture(self):
        self.seed()
        decision = self.update(3, [93], [box(y=115)])[0]
        self.assertEqual(decision['capture_id'], 7)
        self.assertEqual(decision['reason'], 'recovered_tracker_id_change')
        self.assertEqual(self.guard.metadata[7]['source_tracker_ids'], [7, 93])
        self.assertEqual(self.update(4, [93], [box(y=120)])[0]['capture_id'], 7)

    def test_two_raw_ids_swapping_preserve_physical_paths_in_either_order(self):
        for reverse in (False, True):
            self.guard = FruitIdentityGuard()
            for frame in range(3):
                self.update(frame, [7, 8], [box(x=100, y=100+frame*5), box(x=200, y=100+frame*5)])
            ids, boxes = [8, 7], [box(x=100, y=115), box(x=200, y=115)]
            if reverse:
                ids.reverse(); boxes.reverse()
            decisions = self.update(3, ids, boxes)
            self.assertEqual([d['capture_id'] for d in decisions], [8, 7] if reverse else [7, 8])

    def test_new_id_without_motion_history_is_not_merged(self):
        self.update(0, [7], [box()])
        self.assertEqual(self.update(1, [8], [box(y=105)])[0]['capture_id'], 8)

    def test_gap_separates_same_raw_id_before_map_fitting(self):
        self.seed()
        self.update(3, [], [])
        decision = self.update(4, [7], [box(y=120)])[0]
        self.assertNotEqual(decision['capture_id'], 7)
        self.assertEqual(decision['reason'], 'observation_gap')
        self.assertTrue(all(m['identity_status'] == 'uncertain' for m in self.guard.metadata.values()))

    def test_same_id_teleport_does_not_contaminate_existing_capture(self):
        self.seed()
        decision = self.update(3, [7], [box(x=300)])[0]
        self.assertNotEqual(decision['capture_id'], 7)
        self.assertEqual(decision['reason'], 'motion_or_size_discontinuity')

    def test_shared_initial_motion_keeps_all_physical_fruit_ids(self):
        ids = list(range(1, 8))
        self.update(0, ids, [box(x=40+70*i) for i in range(7)])
        decisions = self.update(1, ids, [box(x=40+70*i, y=150) for i in range(7)])
        self.assertEqual([d['capture_id'] for d in decisions], ids)
        self.assertTrue(all(d['scene_motion_px'] == [0., 50.] for d in decisions))
        self.assertTrue(all(m['identity_status'] == 'motion_consistent' for m in self.guard.metadata.values()))

    def test_isolated_jump_is_rejected_amid_shared_motion(self):
        ids = list(range(1, 8))
        self.update(0, ids, [box(x=40+70*i) for i in range(7)])
        moved = [box(x=40+70*i, y=150) for i in range(7)]
        moved[-1] = box(x=450, y=350)
        decisions = self.update(1, ids, moved)
        self.assertEqual([d['capture_id'] for d in decisions[:-1]], ids[:-1])
        self.assertNotEqual(decisions[-1]['capture_id'], ids[-1])
        self.assertEqual(decisions[-1]['reason'], 'motion_or_size_discontinuity')

    def test_common_start_jump_does_not_bias_following_local_velocity(self):
        ids = list(range(1, 8))
        for frame, y in enumerate((100, 150, 155, 160, 165, 170)):
            decisions = self.update(frame, ids, [box(x=40+70*i, y=y) for i in range(7)])
            self.assertEqual([d['capture_id'] for d in decisions], ids)
        self.assertTrue(all('scene_motion_px' not in d for d in decisions))

    def test_incoherent_scene_does_not_supply_initial_motion(self):
        ids = list(range(1, 8))
        self.update(0, ids, [box(x=40+70*i) for i in range(7)])
        decisions = self.update(1, ids, [box(x=40+70*i, y=100+20*i) for i in range(7)])
        self.assertTrue(all('scene_motion_px' not in d for d in decisions))
        self.assertNotEqual(decisions[-1]['capture_id'], ids[-1])

    def test_two_similar_candidates_are_not_arbitrarily_merged(self):
        for frame in range(3):
            self.update(frame, [7, 8], [box(x=100, y=100+frame*5), box(x=120, y=100+frame*5)])
        decision = self.update(3, [90], [box(x=110, y=115)])[0]
        self.assertNotIn(decision['capture_id'], [7, 8])
        self.assertEqual(decision['reason'], 'ambiguous_association')

    def test_two_detections_cannot_both_take_one_capture(self):
        self.seed()
        decisions = self.update(3, [90, 91], [box(x=99, y=115), box(x=101, y=115)])
        self.assertEqual(len({d['capture_id'] for d in decisions}), 2)
        self.assertTrue(all(d['reason'] == 'ambiguous_association' for d in decisions))

    def test_edge_growth_does_not_split_trusted_raw_identity(self):
        for frame, bounds in enumerate(([100, 0, 120, 3], [90, 0, 130, 13],
                                       [90, 0, 130, 25], [90, 5, 130, 45])):
            self.assertEqual(self.update(frame, [7], [bounds])[0]['capture_id'], 7)

    def test_dropped_or_expired_id_never_reopens_old_capture(self):
        for drop in (False, True):
            self.guard = FruitIdentityGuard()
            self.seed()
            if drop:
                self.guard.drop(7)
            decision = self.update(50, [7], [box()])[0]
            self.assertNotEqual(decision['capture_id'], 7)
            self.assertEqual(decision['reason'], 'retired_tracker_id_reappeared')

    def test_capture_ids_cannot_collide_with_future_raw_ids(self):
        self.seed()
        new_id = self.update(3, [7], [box(x=300)])[0]['capture_id']
        decisions = self.update(4, [7, new_id], [box(x=300), box(x=450)])
        self.assertEqual(len({d['capture_id'] for d in decisions}), 2)
        json.dumps(self.guard.metadata)

    def test_legacy_pipeline_records_raw_ids_and_splits_before_capture(self):
        detector = SimpleNamespace(names={0: 'fruit'})
        pipeline = NaartjiePipeline(SimpleNamespace(names={0: 'spot'}), detector,
                                   identity_settings=ConveyorIdentitySettings(conveyor_identity_validation=False))
        image = np.zeros((600, 600, 3), np.uint8)
        def capture(frame, identity, bounds, index):
            pipeline.views_by_id.setdefault(identity, []).append(FruitView(image, frame_index=index))
            return True
        with patch.object(pipeline, 'add_tracked_detection', side_effect=capture):
            for frame, raw_id, bounds in [(0, 7, box()), (1, 7, box(y=105)),
                                          (2, 7, box(y=110)), (3, 93, box(y=115)),
                                          (4, 93, box(x=300))]:
                detector.track = lambda *a, **kw: [SimpleNamespace(boxes=SimpleNamespace(
                    xyxy=np.array([bounds]), id=np.array([raw_id]), cls=np.array([0])))]
                pipeline.process_frame(image, frame)
        self.assertEqual([v.frame_index for v in pipeline.views_by_id[7]], [0, 1, 2, 3])
        self.assertEqual(pipeline.tracking_history_by_id[7][-1]['raw_track_id'], 93)
        other = next(key for key in pipeline.views_by_id if key != 7)
        self.assertEqual([v.frame_index for v in pipeline.views_by_id[other]], [4])

    def test_uncertain_identity_cannot_receive_grade_even_with_complete_map(self):
        pipeline = NaartjiePipeline(SimpleNamespace(names={0: 'spot'}))
        pipeline.identity_guard.metadata[7] = {'identity_status': 'uncertain',
                                               'source_tracker_ids': [7]}
        image = np.zeros((8, 8, 3), np.uint8)
        pipeline.views_by_id[7] = [FruitView(image, np.ones((8, 8), np.uint8), frame_index=i)
                                   for i in range(2)]
        mapped = SimpleNamespace(status='graded', grade='Class 1', bgr_map=image,
            observed_mask=np.ones((8, 8), np.uint8), model_type='sphere', estimated_radii_px=[4, 4, 4],
            rotation_coverage_deg=360, map_longitude_span_deg=360, view_frames=[0, 1],
            discarded_view_frames=[], selection_diagnostics=[], observed_surface_pct=100,
            observed_longitude_deg=360, defect_pct_of_observed=0, pair_rotations_deg=[5],
            pair_rotation_vectors_deg=[], pair_errors=[0], defect_maps={})
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(pipeline, 'finish_track', return_value=mapped):
                row = main._finish_track(pipeline, 7, Path(directory))
            self.assertEqual(row['status'], 'identity_uncertain')
            self.assertIsNone(row['grade'])
            self.assertFalse(row['grade_provisional'])
            self.assertEqual(json.loads((Path(directory)/'7/result.json').read_text())['identity_status'], 'uncertain')
        self.assertNotIn(7, pipeline.identity_guard.metadata)

    def test_direct_pipeline_finish_also_withholds_uncertain_grade(self):
        pipeline = NaartjiePipeline(SimpleNamespace(names={0: 'spot'}))
        image = np.zeros((8, 8, 3), np.uint8)
        mask = np.ones((8, 8), np.uint8)
        pipeline.views_by_id[7] = [FruitView(image, mask, frame_index=i) for i in range(2)]
        pipeline.identity_guard.metadata[7] = {'identity_status': 'uncertain'}
        mapped = MapResult(image, mask, {}, np.zeros(8), np.zeros(8), [5], [], [0],
                           100, 0, 0, 'Class 1', 'graded', 'sphere', (4, 4, 4), 360)
        with patch('algorithm.build_surface_map', return_value=mapped) as build:
            result = pipeline.finish_track(7)
        self.assertEqual(result.status, 'identity_uncertain')
        self.assertIsNone(result.grade)
        self.assertEqual(mapped.grade, 'Class 1')
        self.assertEqual([v.frame_index for v in build.call_args.args[0]], [0, 1])


if __name__ == '__main__':
    unittest.main()
