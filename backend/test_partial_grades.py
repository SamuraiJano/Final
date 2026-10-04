"""Check observed-area grading without changing the reconstructed surface."""

import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np

from algorithm import (FruitView, Settings, _grade, _grade_map,
                       build_surface_map)


class PartialGradeTests(unittest.TestCase):
    @staticmethod
    def _settings(**changes):
        return Settings(grade_partial_maps=True, **changes)

    @staticmethod
    def _known_partial_map(settings, all_defective=False, empty_defect_classes=False):
        # Perfect silhouette and supplied 25-degree motion isolate the grade
        # policy from detection, segmentation and photometric pose accuracy.
        size, radius = 100, 35
        y, x = np.mgrid[:size, :size]
        mask = (((x-49.5)**2 + (y-49.5)**2) < radius**2).astype(np.uint8)
        image = np.zeros((size, size, 3), np.uint8)
        image[mask > 0] = (35, 140, 235)
        defect = mask.copy() if all_defective else np.zeros_like(mask)
        views = [FruitView(image.copy(), mask.copy(),
                           {} if empty_defect_classes else {"spot": defect.copy()}, i)
                 for i in range(2)]
        angle = np.deg2rad(25.)
        rotation = np.array([[np.cos(angle), 0., np.sin(angle)],
                             [0., 1., 0.],
                             [-np.sin(angle), 0., np.cos(angle)]])
        with patch("algorithm.estimate_rotation", return_value=(rotation, .1)):
            return build_surface_map(views, settings)

    def test_default_remains_strict(self):
        self.assertFalse(Settings().grade_partial_maps)
        self.assertEqual(_grade(5., .2, Settings()),
                         (None, "insufficient_surface_coverage"))
        self.assertEqual(_grade_map(5., .8, 120., 50., 25.,
                                    Settings(minimum_longitude_coverage_deg=350.)),
                         (None, "insufficient_longitude_coverage"))

    def test_partial_boundary_grades_use_observed_percent(self):
        settings = self._settings()
        for percentage, expected in ((0., "Class 1"), (9.999, "Class 1"),
                                     (10., "Class 2"), (20., "Class 2"),
                                     (20.001, "Class 3"), (100., "Class 3")):
            with self.subTest(defect_pct=percentage):
                self.assertEqual(_grade(percentage, .2, settings),
                                 (expected, "graded_partial"))

    def test_complete_map_retains_regular_grade(self):
        settings = self._settings(minimum_longitude_coverage_deg=350.,
                                  minimum_rotation_coverage_deg=300.,
                                  maximum_pair_gap_deg=55.)
        self.assertEqual(_grade_map(15., .8, 360., 375., 25., settings),
                         ("Class 2", "graded"))

    def test_each_coverage_requirement_can_be_partial(self):
        settings = self._settings(minimum_longitude_coverage_deg=350.,
                                  minimum_rotation_coverage_deg=300.)
        for surface, longitude, rotation in ((.2, 360., 375.),
                                             (.8, 120., 375.),
                                             (.8, 360., 25.),
                                             (.2, 120., 25.)):
            with self.subTest(surface=surface, longitude=longitude, rotation=rotation):
                self.assertEqual(_grade_map(25., surface, longitude, rotation,
                                            25., settings),
                                 ("Class 3", "graded_partial"))

    def test_missing_segmentation_is_not_a_clean_grade(self):
        settings = self._settings(minimum_longitude_coverage_deg=350.)
        self.assertEqual(_grade(None, .2, settings),
                         (None, "missing_defect_masks"))
        self.assertEqual(_grade_map(None, .2, 120., 25., 25., settings),
                         (None, "missing_defect_masks"))

    def test_invalid_defect_percentage_never_gets_a_grade(self):
        for percentage in (float("nan"), float("inf"), -float("inf"), -1., 101.):
            for enabled in (False, True):
                with self.subTest(defect_pct=percentage, partial_grading=enabled):
                    settings = Settings(grade_partial_maps=enabled)
                    self.assertIsNone(_grade(percentage, .8, settings)[0])
                    self.assertIsNone(_grade_map(percentage, .8, 360., 375.,
                                                  25., settings)[0])

    def test_empty_or_invalid_observed_area_never_gets_a_grade(self):
        for coverage in (0., -1., float("nan"), float("inf"),
                         -float("inf"), 1.01):
            with self.subTest(coverage=coverage):
                self.assertIsNone(_grade(0., coverage, self._settings())[0])
                self.assertIsNone(_grade_map(0., coverage, 120., 25., 25.,
                                              self._settings())[0])

    def test_excessive_pair_gap_is_not_bypassed_by_partial_policy(self):
        settings = self._settings(maximum_pair_gap_deg=55.,
                                  minimum_longitude_coverage_deg=350.)
        self.assertEqual(_grade_map(0., .2, 120., 60., 60., settings),
                         (None, "insufficient_rotation_coverage"))

    def test_unknown_motion_or_longitude_never_gets_a_grade(self):
        for invalid in (float("nan"), float("inf"), -float("inf")):
            for position in range(3):
                values = [120., 25., 25.]
                values[position] = invalid
                with self.subTest(invalid=invalid, position=position):
                    self.assertIsNone(_grade_map(0., .2, *values,
                                                  self._settings())[0])

    def test_grade_policy_does_not_change_map_or_measured_area(self):
        strict = Settings(spheroid_type="sphere", rotation_axis="y",
                          minimum_longitude_coverage_deg=350.,
                          minimum_rotation_coverage_deg=300.,
                          maximum_pair_gap_deg=55.)
        original = self._known_partial_map(strict)
        partial = self._known_partial_map(replace(strict, grade_partial_maps=True))
        self.assertIsNone(original.grade)
        self.assertEqual((partial.grade, partial.status),
                         ("Class 1", "graded_partial"))
        self.assertTrue(partial.grade_provisional)
        self.assertFalse(partial.coverage_complete)
        self.assertLess(partial.observed_surface_pct, 65.)
        self.assertLess(partial.observed_longitude_deg, 350.)
        for field in ("bgr_map", "observed_mask", "longitude_deg", "latitude_deg"):
            np.testing.assert_array_equal(getattr(original, field), getattr(partial, field))
        for field in ("observed_surface_pct", "observed_longitude_deg",
                      "rotation_coverage_deg", "defect_pct_of_observed",
                      "defect_pct_of_full_surface", "pair_rotation_vectors_deg",
                      "pair_errors"):
            self.assertEqual(getattr(original, field), getattr(partial, field))
        np.testing.assert_array_equal(original.defect_maps["spot"],
                                      partial.defect_maps["spot"])

    def test_unobserved_surface_does_not_dilute_visible_defects(self):
        settings = self._settings(spheroid_type="sphere", rotation_axis="y",
                                  minimum_longitude_coverage_deg=350.,
                                  max_latitude_deg=10.)
        result = self._known_partial_map(settings, all_defective=True)
        self.assertAlmostEqual(result.defect_pct_of_observed, 100., places=6)
        # Using the whole fruit as the denominator would falsely produce
        # Class 1 here: only a narrow latitude band was observed.
        self.assertLess(result.defect_pct_of_full_surface, 10.)
        self.assertEqual((result.grade, result.status),
                         ("Class 3", "graded_partial"))

    def test_complete_inference_with_no_detected_defects_can_grade_partial(self):
        settings = self._settings(spheroid_type="sphere", rotation_axis="y",
                                  minimum_longitude_coverage_deg=350.,
                                  defect_observations_complete=True)
        result = self._known_partial_map(settings, empty_defect_classes=True)
        self.assertEqual(result.defect_pct_of_observed, 0.)
        self.assertEqual((result.grade, result.status),
                         ("Class 1", "graded_partial"))

    def test_map_without_defect_observations_stays_ungraded(self):
        settings = self._settings(spheroid_type="sphere", rotation_axis="y",
                                  minimum_longitude_coverage_deg=350.)
        result = self._known_partial_map(settings, empty_defect_classes=True)
        self.assertIsNone(result.defect_pct_of_observed)
        self.assertEqual((result.grade, result.status),
                         (None, "missing_defect_masks"))


if __name__ == "__main__":
    unittest.main()
