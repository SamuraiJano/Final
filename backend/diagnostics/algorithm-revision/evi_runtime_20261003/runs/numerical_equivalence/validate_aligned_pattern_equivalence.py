"""Numerical checks for the isolated nine-sample neighborhood candidate."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import warnings

import cv2
import numpy as np

from test_algorithm import AlgorithmTests
from validate_native_prefilter import load_module
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
BASE = ROOT / "diagnostics/algorithm-revision/aligned_contrast_source/algorithm_snapshot.py"
SOURCE = ROOT / "diagnostics/algorithm-revision/aligned_pattern_source/algorithm_snapshot.py"
SOURCE_SHA = "9a5a3e13c8b9200958c678110640153022dbe8e59d4e3559ea1743ef579b5067"
INPUT = ROOT / "diagnostics/algorithm-revision/camera_shading_inputs_20261002/full_turn_x12_lambertian_multiplicative_texture_a.npz"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="aligned_pattern_equivalence_20261002")
    parser.add_argument("--algorithm-source", type=Path, default=SOURCE)
    parser.add_argument("--expected-sha256", default=SOURCE_SHA)
    parser.add_argument("--local-gradient", action="store_true")
    parser.add_argument("--log-green", action="store_true")
    parser.add_argument("--unblurred", action="store_true")
    args = parser.parse_args()
    candidate = args.algorithm_source.resolve()
    assert sha256(candidate) == args.expected_sha256
    output = ROOT / "diagnostics/algorithm-revision" / args.label
    output.mkdir(parents=True, exist_ok=False)
    for name, path in [("algorithm_snapshot.py", candidate), ("baseline_algorithm.py", BASE),
                       (INPUT.name, INPUT), (Path(__file__).name, Path(__file__))]:
        (output / name).write_bytes(path.read_bytes())
    for name in ("test_algorithm.py", "validate_native_prefilter.py", "validate_motion_resolution.py"):
        (output / name).write_bytes((ROOT / name).read_bytes())
    module = load_module(candidate, "aligned_pattern_check")
    baseline = load_module(BASE, "aligned_scalar_check")
    with np.load(INPUT) as stored:
        images, mask = stored["images"][:2], stored["mask"]
    settings = module.Settings(spheroid_type="sphere", rotation_axis="x", image_downsample=1,
                               highpass_sigma=5., matching_cost="aligned_mad",
                               min_pair_angle_deg=.25, max_pair_angle_deg=20.)
    views = [module.FruitView(image, mask, frame_index=i) for i, image in enumerate(images)]
    model = module.fit_spheroid(views, settings)
    points, _, _ = module._relevant(views[0], model, 0, settings)
    patches = module._surface_patches(points, model.matrices[0], settings.highpass_sigma)
    greens = [image[:, :, 1].astype(np.float32) / 255. for image in images]
    if args.log_green:
        greens = [np.log(np.maximum(green, 1./255.)) for green in greens]
    if not args.unblurred:
        greens = [cv2.GaussianBlur(green, (0, 0), 2.) for green in greens]
    responses, source_valid = module._patch_response(greens[0], patches[None], model.ellipses[0].center,
                                                     mask, model.matrices[0])
    good = source_valid[0]
    points, patches, responses = points[good], patches[good], responses[0, good]
    assert len(points) >= settings.min_pair_points
    assert responses.shape == (len(points), 9)
    vectors = np.deg2rad([[0., 0., 0.], [12., 0., 0.], [10., -2., 0.], [179., 0., 0.]])
    np.savez_compressed(output / "actual_patch_fixture.npz", source_image=images[0], target_image=images[1],
                        mask=mask, points=points, source_patches=patches, source_responses=responses,
                        source_green=greens[0], target_green=greens[1], vectors=vectors,
                        center=model.ellipses[1].center, target_matrix=model.matrices[1])
    report = {"recorded_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
              "algorithm_sha256": args.expected_sha256, "baseline_sha256": sha256(BASE),
              "input_sha256": sha256(INPUT), "settings": asdict(settings),
              "scope": "Numerical cost consistency, invariance and legacy preservation; not motion/grade accuracy.",
              "actual_source_neighborhoods": len(points), "pattern_checks": [], "legacy_checks": []}
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        for normalized in (False, True):
            for masked in (False, True):
                target_mask = np.zeros_like(mask) if masked else mask
                arguments = (points, responses, greens[1], target_mask, views[1], model.ellipses[1].center,
                             settings.min_pair_points, model.matrices[1])
                batch = module._cost_many(vectors, *arguments, normalize=normalized,
                                          compensate_brightness=True, source_patches=patches)
                scalar = np.array([module._cost(v, *arguments, normalize=normalized,
                                                compensate_brightness=True, source_patches=patches) for v in vectors])
                np.testing.assert_array_equal(np.isfinite(batch), np.isfinite(scalar))
                finite = np.isfinite(batch)
                np.testing.assert_allclose(batch[finite], scalar[finite], atol=1e-12, rtol=1e-12)
                assert not np.isnan(batch).any() and not np.isnan(scalar).any()
                assert np.isinf(batch[-1]), "Back-facing neighborhoods must be unavailable."
                assert (not finite.any()) if masked else finite[:3].all()
                if normalized:
                    assert ((batch[finite] >= 0.) & (batch[finite] <= 1. + 1e-12)).all()
                report["pattern_checks"].append({"normalized": normalized, "all_masked": masked,
                    "hypotheses": len(vectors), "finite_hypotheses": int(finite.sum()),
                    "batch": [float(v) if np.isfinite(v) else None for v in batch],
                    "maximum_scalar_batch_difference": float(np.max(np.abs(batch[finite]-scalar[finite]))) if finite.any() else None,
                    "passed": True})
        weights = np.array([1., 2., 1., 2., 4., 2., 1., 2., 1.]) / 16.
        np.testing.assert_allclose(responses @ weights, 0., atol=1e-12)
        gained, gained_valid = module._patch_response(greens[0] * 1.15 + .04, patches[None],
            model.ellipses[0].center, mask, model.matrices[0])
        contrast_above_floor = (responses**2 @ weights) > .999
        assert contrast_above_floor.any()
        np.testing.assert_allclose(gained[0, contrast_above_floor], responses[contrast_above_floor], atol=3e-5, rtol=3e-5)
        assert gained_valid.all()
        invariance_key = "log_descriptor_field_invariance" if args.log_green else "brightness_invariance"
        report[invariance_key] = {"gain": 1.15, "offset": .04,
            "neighborhoods_above_contrast_floor": int(contrast_above_floor.sum()),
            "maximum_difference": float(np.max(np.abs(gained[0, contrast_above_floor]-responses[contrast_above_floor]))),
            "scope": "Affine change to descriptor field; for log mode this is not an original-green exposure-offset invariance claim.",
            "passed": True}
        if args.local_gradient:
            x, y = np.tile([-1., 0., 1.], 3), np.repeat([-1., 0., 1.], 3)
            np.testing.assert_allclose(responses @ (weights*x), 0., atol=1e-12)
            np.testing.assert_allclose(responses @ (weights*y), 0., atol=1e-12)
            yy, xx = np.mgrid[:greens[0].shape[0], :greens[0].shape[1]]
            gradient_green = greens[0]*1.15 + .04 + .0011*(xx-74.5) - .0018*(yy-74.5)
            affine, affine_valid = module._patch_response(gradient_green.astype(np.float32), patches[None],
                model.ellipses[0].center, mask, model.matrices[0])
            assert affine_valid.all()
            np.testing.assert_allclose(affine[0, contrast_above_floor], responses[contrast_above_floor],
                                       atol=3e-5, rtol=3e-5)
            report["local_affine_gradient_invariance"] = {"gain": 1.15, "offset": .04,
                "image_plane_slope_x_per_pixel": .0011, "image_plane_slope_y_per_pixel": -.0018,
                "maximum_difference": float(np.max(np.abs(affine[0, contrast_above_floor]-responses[contrast_above_floor]))),
                "scope": "Affine image-plane gradient applied to unrotated descriptor field; log-mode field differs from original green. Not exposure-offset or curved-light motion accuracy.",
                "passed": True}
        if args.log_green and args.unblurred:
            raw = images[0][:, :, 1].astype(np.float32) / 255.
            gained_log = np.log(np.maximum(raw*1.1, 1./255.))
            gain_response, gain_valid = module._patch_response(gained_log, patches[None],
                model.ellipses[0].center, mask, model.matrices[0])
            assert gain_valid.all()
            np.testing.assert_allclose(gain_response[0, contrast_above_floor], responses[contrast_above_floor],
                                       atol=3e-5, rtol=3e-5)
            report["original_green_multiplicative_gain"] = {"gain": 1.1,
                "maximum_difference": float(np.max(np.abs(gain_response[0, contrast_above_floor]-responses[contrast_above_floor]))),
                "scope": "Unrotated visible source neighborhoods above channel/contrast floors; additive green offsets are not invariant.",
                "passed": True}
        fixture = AlgorithmTests._photometric_fixture()
        for normalized in (False, True):
            for compensate in (False, True):
                for masked in (False, True):
                    arguments = fixture if not masked else (*fixture[:3], np.zeros_like(fixture[3]), *fixture[4:])
                    old = baseline._cost_many(vectors, *arguments, normalize=normalized, compensate_brightness=compensate)
                    new = module._cost_many(vectors, *arguments, normalize=normalized, compensate_brightness=compensate)
                    np.testing.assert_array_equal(old, new)
                    old_scalar = np.array([baseline._cost(v, *arguments, normalize=normalized, compensate_brightness=compensate) for v in vectors])
                    new_scalar = np.array([module._cost(v, *arguments, normalize=normalized, compensate_brightness=compensate) for v in vectors])
                    np.testing.assert_array_equal(old_scalar, new_scalar)
                    report["legacy_checks"].append({"normalized": normalized, "compensate_brightness": compensate,
                        "all_masked": masked, "hypotheses": len(vectors), "exact_equality": True})
    report["all_checks_passed"] = True
    report["completed_at"] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    write_json(output / "report.json", report)
    write_json(output / "sha256.json", {str(p.relative_to(output)): sha256(p) for p in output.rglob("*") if p.is_file()})
    print(json.dumps({"all_checks_passed": True, "source_sha256": args.expected_sha256, "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
