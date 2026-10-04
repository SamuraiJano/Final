"""Synthetic regression checks for the surface reconstruction geometry."""

import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import cv2

from algorithm import (Ellipse, FruitView, MappingError, NaartjiePipeline, Settings,
                       _grade, _height, _oblate_poles, _sample_view,
                       _validate_capture_mask, _select_rotating_views,
                       _cost, _cost_many, build_surface_map, estimate_rotation, fit_spheroid)


class AlgorithmTests(unittest.TestCase):
    @staticmethod
    def _rotation(axis: str, degrees: float) -> np.ndarray:
        angle = np.deg2rad(degrees)
        c, s = np.cos(angle), np.sin(angle)
        if axis == "y":
            return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])

    @staticmethod
    def _silhouette(pole: np.ndarray, A: float = 55, B: float = 40,
                    size: int = 150) -> np.ndarray:
        y, x = np.mgrid[:size, :size]
        xy = np.stack((x-(size-1)/2, y-(size-1)/2), axis=-1)
        projected = A*A*np.eye(2) + (B*B-A*A)*np.outer(pole[:2], pole[:2])
        return (np.einsum("...i,ij,...j->...", xy,
                          np.linalg.inv(projected), xy) <= 1).astype(np.uint8)

    def test_grade_boundaries_are_percentages(self) -> None:
        settings = Settings()
        for percentage, expected in ((0, "Class 1"), (5, "Class 1"),
                                     (10, "Class 2"), (20, "Class 2"),
                                     (25, "Class 3")):
            with self.subTest(percentage=percentage):
                self.assertEqual(_grade(percentage, .8, settings),
                                 (expected, "graded"))
        self.assertEqual(_grade(5, .5, settings),
                         (None, "insufficient_surface_coverage"))

    def test_oblate_pole_follows_rotation_through_turning_point(self) -> None:
        for axis in ("x", "y"):
            for direction in (-1, 1):
                with self.subTest(axis=axis, direction=direction):
                    pole0 = np.array([.55, .75, .36]) if axis == "y" else np.array([.75, .55, .36])
                    pole0 /= np.linalg.norm(pole0)
                    truth = [self._rotation(axis, direction*k*25) @ pole0
                             for k in range(10)]
                    views = [FruitView(np.zeros((150, 150, 3), np.uint8),
                                       self._silhouette(pole)) for pole in truth]
                    fitted = fit_spheroid(views, Settings(rotation_axis=axis,
                                                          rotation_direction=direction))
                    self.assertGreater(min(abs(float(a @ b)) for a, b in
                                           zip(fitted.pole_axes, truth)), .98)

    def test_axis_aligned_oblate_pole_has_constant_silhouette(self) -> None:
        pole = np.array([0., 1., 0.])
        mask = self._silhouette(pole)
        views = [FruitView(np.zeros((150, 150, 3), np.uint8), mask)
                 for _ in range(5)]
        fitted = fit_spheroid(views, Settings())
        self.assertTrue(all(abs(float(p @ pole)) > .99
                            for p in fitted.pole_axes))

    def test_small_silhouette_noise_does_not_become_a_full_turn(self) -> None:
        ellipses = []
        for degrees, minor in [(0, 40), (.2, 40.02), (-.2, 40.01), (.1, 40.03)]:
            angle = np.deg2rad(degrees)
            ellipses.append(Ellipse(np.array([75., 75.]), 55., minor,
                                    np.array([np.cos(angle), -np.sin(angle)]),
                                    np.array([np.sin(angle), np.cos(angle)])))
        for axis in ('x', 'y'):
            with self.subTest(axis=axis):
                poles = _oblate_poles(ellipses, 55., 40., Settings(rotation_axis=axis))
                self.assertTrue(all(abs(p[1]) > .99 for p in poles))

    def test_tilted_spheroid_visibility_uses_surface_normal(self) -> None:
        pole = np.array([.6, 0., .8])
        matrix = np.eye(3)/55**2 + (1/25**2-1/55**2)*np.outer(pole, pole)
        x = np.linspace(-49, 49, 1000)
        front = _height(matrix, x, np.zeros_like(x))
        visible_index = np.flatnonzero(np.isfinite(front) & (front < 0))[0]
        back = -2*matrix[0, 2]*x/matrix[2, 2] - front
        hidden_index = np.flatnonzero(np.isfinite(back) & (back > 0))[0]
        points = np.array([[x[visible_index]+60, 60., front[visible_index]],
                           [x[hidden_index]+60, 60., back[hidden_index]]])
        view = FruitView(np.full((120, 120, 3), 200, np.uint8),
                         np.ones((120, 120), np.uint8))
        _, valid, _ = _sample_view(view, points, [], matrix, np.array([60., 60.]))
        self.assertEqual(valid.tolist(), [True, False])

    def test_collapsed_and_occluded_masks_are_rejected(self) -> None:
        mask = np.zeros((100, 100), np.uint8)
        mask[45:55, 45:55] = 1
        with self.assertRaisesRegex(MappingError, 'too little'):
            _validate_capture_mask(mask, (10, 10, 90, 90), Settings())
        mask[10:90, 10:90] = 1
        mask[30:70, 50:90] = 0
        with self.assertRaisesRegex(MappingError, 'occluded'):
            _validate_capture_mask(mask, (10, 10, 90, 90), Settings())

    def test_auto_model_uses_sphere_for_near_circular_views(self) -> None:
        y, x = np.mgrid[:128, :128]
        mask = (((x-63.5)**2 + (y-63.5)**2) < 48**2).astype(np.uint8)
        views = [FruitView(np.zeros((128, 128, 3), np.uint8), mask)
                 for _ in range(3)]
        fitted = fit_spheroid(views, Settings(spheroid_type="auto"))
        self.assertEqual(fitted.A, fitted.B)

    def test_failed_motion_ends_sequence_without_a_replacement_bridge(self) -> None:
        mask = self._silhouette(np.array([0., 1., 0.]))
        views = [FruitView(np.zeros((150,150,3), np.uint8), mask, frame_index=i)
                 for i in range(6)]
        settings = Settings(select_rotating_views=True)
        model = fit_spheroid(views, settings)
        measured = {(0,1):0., (1,2):25., (3,4):25., (4,5):25., (1,4):50.}
        calls = []
        def estimate(source, target, *args):
            pair = (source.frame_index, target.frame_index)
            calls.append(pair)
            if pair not in measured:
                raise MappingError('bad target texture')
            return self._rotation('y', measured[pair]), .2
        with patch('algorithm.estimate_rotation', side_effect=estimate):
            selected, _, rotations, _, _ = _select_rotating_views(views, model, settings)
        self.assertEqual([v.frame_index for v in selected], [3,4,5])
        self.assertEqual(len(rotations), 2)
        self.assertEqual(calls, [(0,1),(1,2),(2,3),(3,4),(4,5)])

    def test_small_measured_turns_are_retained(self) -> None:
        mask = self._silhouette(np.array([0., 1., 0.]))
        views = [FruitView(np.zeros((150,150,3), np.uint8), mask, frame_index=i)
                 for i in range(6)]
        settings = Settings(select_rotating_views=True)
        model = fit_spheroid(views, settings)
        with patch('algorithm.estimate_rotation', return_value=(self._rotation('y', .6), .05)):
            selected, _, rotations, _, _ = _select_rotating_views(views, model, settings)
        self.assertEqual([v.frame_index for v in selected], list(range(6)))
        self.assertAlmostEqual(sum(np.rad2deg(cv2.Rodrigues(r)[0][1,0]) for r in rotations), 3.)

    def test_original_frame_gap_splits_even_when_crop_list_is_consecutive(self) -> None:
        mask = self._silhouette(np.array([0., 1., 0.]))
        views = [FruitView(np.zeros((150,150,3), np.uint8), mask, frame_index=i)
                 for i in (10,11,18,19)]
        settings = Settings(select_rotating_views=True)
        model = fit_spheroid(views, settings)
        calls = []
        def estimate(source, target, *args):
            calls.append((source.frame_index, target.frame_index))
            return self._rotation('y',25.), .2
        with patch('algorithm.estimate_rotation', side_effect=estimate):
            selected, _, _, _, _ = _select_rotating_views(views, model, settings)
        self.assertEqual(calls, [(10,11),(18,19)])
        self.assertEqual(len(selected), 2)

    def test_small_positive_jitter_cannot_build_a_full_turn(self) -> None:
        mask = self._silhouette(np.array([0., 1., 0.]))
        views = [FruitView(np.zeros((150,150,3), np.uint8), mask, frame_index=i)
                 for i in range(100)]
        settings = Settings(select_rotating_views=True)
        model = fit_spheroid(views, settings)
        with patch('algorithm.estimate_rotation', return_value=(self._rotation('y', .2), .05)):
            with self.assertRaisesRegex(MappingError, 'No reliable rotating sequence') as caught:
                _select_rotating_views(views, model, settings)
        self.assertEqual(len(caught.exception.diagnostics), 99)

    def test_small_motion_uses_native_pixels_before_minimum_angle_gate(self) -> None:
        view = FruitView(np.zeros((150,150,3), np.uint8))
        details = {}
        with patch('algorithm._search_rotation', side_effect=[
            (self._rotation('y', .2), .1), (self._rotation('y', 1.1), .08)
        ]) as search:
            rotation, _ = estimate_rotation(view, view, None, 0, Settings(), details)
        self.assertAlmostEqual(np.rad2deg(cv2.Rodrigues(rotation)[0][1,0]), 1.1)
        self.assertEqual([call.args[-1].image_downsample for call in search.call_args_list], [4,1])
        self.assertEqual(search.call_args_list[1].args[-1].highpass_sigma, 5.)
        self.assertEqual(details['image_downsample'], 1)

    def test_failed_match_is_not_rescued_at_another_resolution(self) -> None:
        view = FruitView(np.zeros((150,150,3), np.uint8))
        with patch('algorithm._search_rotation', side_effect=MappingError('bad texture')) as search:
            with self.assertRaisesRegex(MappingError, 'bad texture'):
                estimate_rotation(view, view, None, 0, Settings())
        self.assertEqual(search.call_count, 1)

    def test_failed_native_recheck_cannot_reuse_coarse_motion(self) -> None:
        view = FruitView(np.zeros((150,150,3), np.uint8))
        with patch('algorithm._search_rotation', side_effect=[
            (self._rotation('y', 2.), .1), MappingError('native match failed')
        ]):
            with self.assertRaisesRegex(MappingError, 'native match failed'):
                estimate_rotation(view, view, None, 0, Settings())

    @staticmethod
    def _photometric_fixture():
        """Known visible points and a linear image; no image matcher is mocked."""
        yy, xx = np.mgrid[:32, :32]
        green = (.2+.003*xx+.005*yy).astype(np.float32)
        xy = np.array([[x, y] for y in (-2., 0., 2.) for x in (-4., -2., 0., 2., 4.)])
        points = np.column_stack((xy, np.sqrt(100.-np.sum(xy**2, axis=1))))
        center = np.array([16., 16.])
        pixels = (xy+center).astype(int)
        # The independent identity-pose MAD is exactly .012 before rounding.
        source = green[pixels[:, 1], pixels[:, 0]]+np.tile([-.02, -.01, 0., .01, .02], 3)
        view = FruitView(np.zeros((32, 32, 3), np.uint8), np.ones((32, 32), np.uint8))
        return points, source, green, view.object_mask, view, center, 12, np.eye(3)/100.

    def test_green_mad_preserves_nonzero_residual_under_brightness_offset(self) -> None:
        arguments = self._photometric_fixture()
        shifted = (*arguments[:2], arguments[2]+.05, *arguments[3:])
        for normalized in (False, True):
            with self.subTest(normalized=normalized):
                baseline = _cost(np.zeros(3), *arguments, normalize=normalized, compensate_brightness=True)
                offset = _cost(np.zeros(3), *shifted, normalize=normalized, compensate_brightness=True)
                self.assertAlmostEqual(baseline, offset, places=6)
                self.assertGreater(baseline, 0.)
                if not normalized:
                    self.assertAlmostEqual(baseline, .012, places=6)
        raw_offset = _cost(np.zeros(3), *shifted, normalize=False, compensate_brightness=False)
        self.assertGreater(raw_offset, .04)

    def test_scalar_and_batch_costs_agree_for_visible_and_hidden_hypotheses(self) -> None:
        arguments = self._photometric_fixture()
        vectors = np.deg2rad([[0., 0., 0.], [.3, 1.3, 0.], [-1., 6., 0.], [0., 179., 0.]])
        for normalized in (False, True):
            for brightness in (False, True):
                with self.subTest(normalized=normalized, brightness=brightness):
                    scalar = np.array([_cost(vector, *arguments, normalize=normalized,
                                            compensate_brightness=brightness) for vector in vectors])
                    batch = _cost_many(vectors, *arguments, normalize=normalized,
                                       compensate_brightness=brightness)
                    np.testing.assert_allclose(batch, scalar, rtol=1.e-6, atol=1.e-7)
                    self.assertTrue(np.isinf(batch[-1]))
                    self.assertTrue(np.isfinite(batch[:-1]).all())

    def test_all_invalid_green_hypotheses_are_unavailable_without_nan_warning(self) -> None:
        arguments = self._photometric_fixture()
        hidden = (*arguments[:3], np.zeros_like(arguments[3]), *arguments[4:])
        with warnings.catch_warnings():
            warnings.simplefilter('error', RuntimeWarning)
            costs = _cost_many(np.zeros((3, 3)), *hidden, normalize=True, compensate_brightness=True)
        self.assertTrue(np.isinf(costs).all())

    def test_native_green_recheck_keeps_paper_coarse_match_and_filter_width(self) -> None:
        view = FruitView(np.zeros((150, 150, 3), np.uint8))
        settings = Settings(native_matching_cost='green_mad', minimum_view_rotation_deg=8.)
        details = {}
        with patch('algorithm._search_rotation', side_effect=[
            (self._rotation('y', 5.), .1), (self._rotation('y', 6.), .08)
        ]) as search:
            rotation, _ = estimate_rotation(view, view, None, 0, settings, details)
        coarse, native = [call.args[-1] for call in search.call_args_list]
        self.assertEqual((coarse.image_downsample, coarse.matching_cost), (4, 'mad'))
        self.assertEqual((native.image_downsample, native.highpass_sigma, native.matching_cost), (1, 5., 'green_mad'))
        self.assertAlmostEqual(np.rad2deg(cv2.Rodrigues(rotation)[0][1, 0]), 6.)
        self.assertEqual(details['native_matching_cost'], 'green_mad')

    def test_native_green_disagreement_is_rejected_without_coarse_fallback(self) -> None:
        view = FruitView(np.zeros((150, 150, 3), np.uint8))
        settings = Settings(native_matching_cost='green_mad', minimum_view_rotation_deg=8.)
        with patch('algorithm._search_rotation', side_effect=[
            (self._rotation('y', 1.), .1), (self._rotation('y', 6.), .08)
        ]) as search:
            with self.assertRaisesRegex(MappingError, 'disagrees'):
                estimate_rotation(view, view, None, 0, settings)
        self.assertEqual(search.call_count, 2)

    def test_native_green_threshold_leaves_large_motion_with_paper_matcher(self) -> None:
        view = FruitView(np.zeros((150, 150, 3), np.uint8))
        settings = Settings(native_matching_cost='green_mad', minimum_view_rotation_deg=8.)
        # Rodrigues conversion can recover a nominal 8 degrees just below 8
        # through floating-point rounding. These are clearly above the gate.
        for angle in (8.01, 20.):
            with self.subTest(angle=angle):
                with patch('algorithm._search_rotation', return_value=(self._rotation('y', angle), .1)) as search:
                    rotation, _ = estimate_rotation(view, view, None, 0, settings)
                self.assertEqual(search.call_count, 1)
                self.assertEqual(search.call_args.args[-1].matching_cost, 'mad')
                self.assertAlmostEqual(np.rad2deg(cv2.Rodrigues(rotation)[0][1, 0]), angle)

    def test_unobservable_rolling_is_rejected_after_native_recheck(self) -> None:
        view = FruitView(np.zeros((150,150,3), np.uint8))
        with patch('algorithm._search_rotation', side_effect=[
            (self._rotation('y', .05), .04), (self._rotation('y', .13), .03)
        ]):
            with self.assertRaisesRegex(MappingError, 'too small'):
                estimate_rotation(view, view, None, 0, Settings(min_pair_angle_deg=.25))

    def test_stationary_fruit_cannot_acquire_rotation_coverage(self) -> None:
        mask = self._silhouette(np.array([0., 1., 0.]))
        views = [FruitView(np.zeros((150,150,3), np.uint8), mask, frame_index=i)
                 for i in range(6)]
        settings = Settings(select_rotating_views=True)
        model = fit_spheroid(views, settings)
        with patch('algorithm.estimate_rotation', return_value=(np.eye(3), .05)):
            with self.assertRaisesRegex(MappingError, 'No reliable rotating sequence'):
                _select_rotating_views(views, model, settings)

    def test_view_selection_does_not_join_across_unmeasured_gaps(self) -> None:
        mask = self._silhouette(np.array([0., 1., 0.]))
        views = [FruitView(np.zeros((150,150,3), np.uint8), mask, frame_index=i)
                 for i in range(6)]
        settings = Settings(select_rotating_views=True, maximum_view_index_gap=1)
        model = fit_spheroid(views, settings)
        def estimate(source, target, *args):
            if source.frame_index == 1:
                raise MappingError('no matched transition')
            return self._rotation('y',25.), .2
        with patch('algorithm.estimate_rotation', side_effect=estimate):
            selected, _, rotations, _, _ = _select_rotating_views(views, model, settings)
        self.assertEqual([v.frame_index for v in selected], [2,3,4,5])
        self.assertEqual(len(rotations), 3)

    def test_deferred_segmentation_runs_on_retained_views_and_preserves_area(self) -> None:
        class Segmenter:
            names = {0:'spot'}
            calls = 0
            def predict(self, image, **kwargs):
                self.calls += 1
                return [SimpleNamespace(
                    masks=SimpleNamespace(data=np.ones((1,*image.shape[:2]),np.uint8)),
                    boxes=SimpleNamespace(cls=np.array([0])))]
        segmenter=Segmenter()
        settings=Settings(spheroid_type='sphere',rotation_axis='y',select_rotating_views=True,
                          minimum_rotation_coverage_deg=350,defect_observations_complete=True)
        pipeline=NaartjiePipeline(segmenter,settings=settings,defer_defect_segmentation=True)
        y,x=np.mgrid[:150,:150]
        mask=(((x-74.5)**2+(y-74.5)**2)<55**2).astype(np.uint8)
        frame=np.zeros((150,150,3),np.uint8);frame[mask>0]=(45,150,230)
        self.assertTrue(pipeline.add_tracked_detection(frame,7,(19,19,130,130),0))
        self.assertEqual(segmenter.calls,0)
        # Known motion isolates lazy inference from texture matching. Frame 1
        # repeats frame 0; the other 15 transitions total exactly 375 degrees.
        pipeline.views_by_id[7]=[FruitView(frame,mask,frame_index=i) for i in range(17)]
        def estimate(source,target,*args):
            angle=0. if target.frame_index==1 else 25.
            return self._rotation('y',angle),.1
        with patch('algorithm.estimate_rotation',side_effect=estimate):
            result=pipeline.finish_track(7)
        self.assertEqual(segmenter.calls,16)
        self.assertEqual(result.discarded_view_frames,[0])
        self.assertAlmostEqual(result.defect_pct_of_observed,100.,places=6)
        self.assertEqual(result.grade,'Class 3')

    def test_detector_uses_tracktrack_and_grabcut_crop(self) -> None:
        class Detector:
            names = {0: "object"}

            def track(self, frame, **kwargs):
                self.tracker_name = kwargs["tracker"]
                boxes = SimpleNamespace(
                    id=np.array([7]), cls=np.array([0]),
                    xyxy=np.array([[32, 32, 112, 112]], np.float32),
                )
                return [SimpleNamespace(boxes=boxes)]

        class Segmenter:
            names = {0: "spot"}

            def predict(self, crop, **kwargs):
                return [SimpleNamespace(masks=None, boxes=None)]

        detector = Detector()
        pipeline = NaartjiePipeline(Segmenter(), detector,
                                    max_views_per_track=2)
        y, x = np.mgrid[:144, :144]
        frame = np.zeros((144, 144, 3), np.uint8)
        frame[(x-72)**2 + (y-72)**2 < 40**2] = (45, 150, 230)
        self.assertEqual(pipeline.process_frame(frame, 1), [7])
        self.assertEqual(detector.tracker_name, "tracktrack.yaml")
        self.assertEqual(pipeline.last_seen_frame[7], 1)
        self.assertGreater(int(pipeline.views_by_id[7][0].object_mask.sum()), 100)
        self.assertEqual(pipeline.process_frame(frame, 2, capture_views=False), [])
        self.assertEqual(pipeline.last_seen_frame[7], 2)
        self.assertEqual(len(pipeline.views_by_id[7]), 1)
        with self.assertRaisesRegex(MappingError, 'cut off'):
            pipeline.add_tracked_detection(frame, 8, (0, 32, 80, 112), 3)

    def test_textured_oblate_track_builds_map(self) -> None:
        size, A, B = 150, 55., 40.
        y, x = np.mgrid[:size, :size]
        X, Y = x-(size-1)/2, y-(size-1)/2
        pole0 = np.array([.55, .75, .36])
        pole0 /= np.linalg.norm(pole0)
        views = []
        for k in range(16):
            rotation = self._rotation("y", k*25)
            pole = rotation @ pole0
            matrix = np.eye(3)/A**2 + (1/B**2-1/A**2)*np.outer(pole, pole)
            Z = _height(matrix, X, Y)
            visible = np.isfinite(Z) & (Z > 0)
            camera = np.stack((X, Y, np.nan_to_num(Z)), axis=-1)
            fruit = camera @ rotation
            fx, fy, fz = fruit[:, :, 0], fruit[:, :, 1], fruit[:, :, 2]
            intensity = (.5 + .17*np.sin(.31*fx+.14*fy) +
                         .13*np.cos(.29*fz-.11*fy) + .1*np.sin(.23*fx+.26*fz))
            channel = np.uint8(np.clip(intensity, 0, 1)*255)
            image = np.repeat(channel[:, :, None], 3, axis=2)
            image[~visible] = 0
            defect = visible & (fx > 15) & (fx < 25) & (fy > -8) & (fy < 8) & (fz > 35)
            views.append(FruitView(image, visible.astype(np.uint8),
                                   {"spot": defect.astype(np.uint8)}, k))
        result = build_surface_map(views, Settings(search_step_deg=3,
                                                   transverse_angle_deg=3,
                                                   min_texture=.002,
                                                   minimum_rotation_coverage_deg=350,
                                                   maximum_pair_gap_deg=55))
        self.assertTrue(all(abs(angle-25) < 2 for angle in result.pair_rotations_deg))
        self.assertGreater(result.observed_surface_pct, 65)
        self.assertGreaterEqual(result.rotation_coverage_deg, 350)
        self.assertEqual((result.grade, result.status), ("Class 1", "graded"))
        self.assertGreater(result.defect_pct_of_observed, 0)


if __name__ == "__main__":
    unittest.main()
