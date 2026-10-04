"""Defect colours preserve source texture, geometry and unobserved regions."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from algorithm import Settings, _grade_map
from map_visualization import DEFECT_COLOURS, render_defect_overlay
import main


class MapVisualizationTests(unittest.TestCase):
    def test_only_observed_defects_are_tinted_and_original_arrays_are_preserved(self):
        image = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)
        observed = np.ones((4, 4), np.uint8)
        observed[0] = 0
        defect = np.zeros((4, 4), np.uint8)
        defect[:, 1] = 1
        original = image.copy()
        original_mask = defect.copy()
        overlay, legend = render_defect_overlay(image, observed, {'open_skin': defect})
        selected = (defect > 0) & (observed > 0)
        np.testing.assert_array_equal(overlay[~selected], original[~selected])
        self.assertTrue(np.all(np.any(overlay[selected] != original[selected], axis=1)))
        np.testing.assert_array_equal(image, original)
        np.testing.assert_array_equal(defect, original_mask)
        self.assertEqual(legend[0]['observed_pixels'], 3)

    def test_five_classes_have_distinct_colours_in_the_display_and_legend(self):
        image = np.full((5, 8, 3), 70, np.uint8)
        masks = {}
        for row, name in enumerate(sorted(DEFECT_COLOURS)):
            masks[name] = np.zeros((5, 8), np.uint8)
            masks[name][row] = 1
        overlay, legend = render_defect_overlay(image, np.ones((5, 8), np.uint8), masks)
        self.assertEqual(len({item['color'] for item in legend}), 5)
        self.assertEqual(len({tuple(pixel) for pixel in overlay[:, 0]}), 5)
        self.assertEqual({item['name'] for item in legend}, set(masks))

    def test_overlapping_labels_remain_visible_without_changing_their_masks(self):
        image = np.full((15, 15, 3), 70, np.uint8)
        masks = {name: np.ones((15, 15), np.uint8) for name in DEFECT_COLOURS}
        overlay, legend = render_defect_overlay(image, np.ones((15, 15), np.uint8), masks)
        self.assertEqual(len(np.unique(overlay.reshape(-1, 3), axis=0)), 5)
        self.assertTrue(all(item['observed_pixels'] == 225 for item in legend))
        self.assertTrue(all(np.all(mask == 1) for mask in masks.values()))

    def test_no_predictions_or_no_observed_surface_never_invents_defects(self):
        image = np.full((5, 5, 3), 80, np.uint8)
        overlay, legend = render_defect_overlay(image, np.ones((5, 5), np.uint8), {})
        np.testing.assert_array_equal(overlay, image)
        self.assertEqual(legend, [])
        overlay, legend = render_defect_overlay(image, np.zeros((5, 5), np.uint8),
                                               {'open_skin': np.ones((5, 5), np.uint8)})
        np.testing.assert_array_equal(overlay, image)
        self.assertEqual(legend[0]['observed_pixels'], 0)

    def test_invalid_shapes_are_rejected(self):
        image = np.zeros((5, 5, 3), np.uint8)
        with self.assertRaises(ValueError):
            render_defect_overlay(image, np.ones((4, 5)), {})
        with self.assertRaises(ValueError):
            render_defect_overlay(image, np.ones((5, 5)), {'open_skin': np.ones((4, 5))})

    def test_eighty_percent_is_the_regular_surface_grade_boundary(self):
        settings = Settings(minimum_surface_coverage=.8, grade_partial_maps=True,
                            minimum_longitude_coverage_deg=350.)
        self.assertEqual(_grade_map(15., .79999, 360., 360., 12., settings),
                         ('Class 2', 'graded_partial'))
        self.assertEqual(_grade_map(15., .8, 360., 360., 12., settings),
                         ('Class 2', 'graded'))
        self.assertEqual(_grade_map(15., .85, 120., 360., 12., settings),
                         ('Class 2', 'graded_partial'))

    def test_app_enables_eighty_percent_without_running_models(self):
        with patch.object(main, 'DfineSegmenter', return_value=SimpleNamespace(names={0: 'open_skin'})), \
                patch.object(main, 'DfineDetector', return_value=SimpleNamespace(names={0: 'fruit'})), \
                patch.object(main, 'inference_device', return_value='cpu'), \
                patch('pathlib.Path.is_file', return_value=True):
            pipeline, _, _ = main._make_pipeline(capture_stride_frames=1)
        self.assertEqual(pipeline.settings.minimum_surface_coverage, .8)
        self.assertTrue(pipeline.settings.grade_partial_maps)


if __name__ == '__main__':
    unittest.main()
