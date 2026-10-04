"""Isolated control-flow and geometry checks; not production grading accuracy."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import cv2
import numpy as np


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("adjacent_candidate", HERE / "algorithm_snapshot.py")
candidate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = candidate
spec.loader.exec_module(candidate)


class AdjacentCandidateTests(unittest.TestCase):
    def inputs(self, frames):
        size = 150
        y, x = np.mgrid[:size, :size]
        mask = (((x-74.5)**2+(y-74.5)**2) < 55**2).astype(np.uint8)
        views = [candidate.FruitView(np.zeros((size,size,3),np.uint8), mask, frame_index=i)
                 for i in frames]
        settings = candidate.Settings(spheroid_type="sphere", rotation_axis="y",
                                      select_rotating_views=True, maximum_view_index_gap=1)
        return views, candidate.fit_spheroid(views, settings), settings

    @staticmethod
    def rotation(vector):
        return cv2.Rodrigues(np.deg2rad(np.asarray(vector,dtype=float)))[0]

    def test_valid_small_adjacent_motion_is_retained(self):
        views, model, settings = self.inputs(range(6))
        calls = []
        def estimate(source, target, *_):
            calls.append((source.frame_index,target.frame_index))
            return self.rotation([0,2,0]), .1
        with patch.object(candidate, "estimate_rotation", side_effect=estimate):
            selected, _, rotations, _, _ = candidate._select_rotating_views(views,model,settings)
        self.assertEqual(calls, [(0,1),(1,2),(2,3),(3,4),(4,5)])
        self.assertEqual([v.frame_index for v in selected], list(range(6)))
        self.assertEqual(len(rotations),5)

    def test_failed_pair_never_creates_a_later_replacement_bridge(self):
        views, model, settings = self.inputs(range(7))
        calls = []
        def estimate(source, target, *_):
            pair = (source.frame_index,target.frame_index)
            calls.append(pair)
            if pair == (1,2):
                raise candidate.MappingError("unmeasured")
            return self.rotation([0,10,0]), .1
        with patch.object(candidate, "estimate_rotation", side_effect=estimate):
            selected, _, _, _, _ = candidate._select_rotating_views(views,model,settings)
        self.assertTrue(all(b-a == 1 for a,b in calls))
        self.assertEqual([v.frame_index for v in selected], [2,3,4,5,6])

    def test_missing_original_frame_splits_adjacent_list_positions(self):
        views, model, settings = self.inputs([0,1,3,4,5,6])
        calls = []
        def estimate(source, target, *_):
            calls.append((source.frame_index,target.frame_index))
            return self.rotation([0,10,0]), .1
        with patch.object(candidate, "estimate_rotation", side_effect=estimate):
            selected, _, _, _, records = candidate._select_rotating_views(views,model,settings)
        self.assertNotIn((1,3),calls)
        self.assertEqual([v.frame_index for v in selected], [3,4,5,6])
        self.assertTrue(any(r.get("source_frame_gap") == 2 and r["status"] == "split" for r in records))

    def test_nearly_stationary_positive_jitter_does_not_accumulate_coverage(self):
        views, model, settings = self.inputs(range(100))
        with patch.object(candidate, "estimate_rotation", return_value=(self.rotation([0,.2,0]),.05)):
            with self.assertRaisesRegex(candidate.MappingError,"No reliable rotating sequence"):
                candidate._select_rotating_views(views,model,settings)

    def test_trajectory_uses_ordered_matrix_product_and_original_map_equations(self):
        views, model, settings = self.inputs(range(4))
        rotations = [self.rotation([0,10,0]),self.rotation([2,8,0]),self.rotation([-1,12,0])]
        axes, radii, longitude, direction, progress = candidate._map_trajectory(model,rotations,settings)
        poses = [np.eye(3)]
        for rotation in rotations:
            poses.append(rotation @ poses[-1])
        basis, expected_radii = candidate._map_frame(model,settings)
        reference = poses[model.reference_index].T @ basis
        expected_axes = [pose @ reference for pose in poses]
        expected_longitude = np.unwrap([
            np.arctan2((q.T @ np.array([0.,0.,1.]))[2]/expected_radii[2],
                       (q.T @ np.array([0.,0.,1.]))[0]/expected_radii[0]) for q in expected_axes])
        np.testing.assert_allclose(axes,expected_axes)
        np.testing.assert_allclose(radii,expected_radii)
        np.testing.assert_allclose(longitude,expected_longitude)
        np.testing.assert_allclose(progress,direction*(expected_longitude-expected_longitude[0]))
        self.assertGreater(np.linalg.norm(rotations[1] @ rotations[0] - rotations[0] @ rotations[1]), .001)

    def test_backwards_longitude_splits_before_fusion(self):
        views, _, settings = self.inputs(range(7))
        settings.rotation_axis = "x"
        # Stay away from the exactly 45-degree map-basis selection tie.
        pole_angle = np.deg2rad(40.)
        pole = np.array([np.cos(pole_angle),np.sin(pole_angle),0.])
        major = np.array([pole[1],-pole[0],0.])
        basis = np.column_stack((major,pole,np.cross(major,pole)))
        ellipse = candidate.Ellipse(np.array([75.,75.]),55.,40.,major[:2],pole[:2])
        matrix = np.eye(3)/55**2+(1/40**2-1/55**2)*np.outer(pole,pole)
        model = candidate.Spheroid(55.,40.,[ellipse]*7,[matrix]*7,basis,0,[pole]*7)
        def estimate(source, target, *_):
            vector = [3.,-5.,0.] if source.frame_index == 2 else [10.,0.,0.]
            return self.rotation(vector), .1
        with patch.object(candidate, "estimate_rotation", side_effect=estimate):
            selected, selected_model, rotations, _, records = candidate._select_rotating_views(views,model,settings)
        self.assertEqual([v.frame_index for v in selected], [3,4,5,6])
        _, _, _, _, progress = candidate._map_trajectory(selected_model,rotations,settings)
        self.assertTrue(np.all(np.rad2deg(np.diff(progress)) >= .25))
        self.assertTrue(any(r["method"] == "map_trajectory_check" and r["source_frame"] == 2
                            and r["longitude_delta_deg"] < 0 for r in records))


if __name__ == "__main__":
    unittest.main(verbosity=2)
