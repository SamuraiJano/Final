"""Independent camera-fixed illumination controls, without production edits/models.

Prepare all known-answer inputs before loading an estimator. Replay the same
NPZs for each frozen source; preserve failed/unavailable results without fitting
or extrapolating poses to the truth.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
import argparse
import json
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import validate_extended_motion_controls as short
import validate_full_turn_motion as full
from validate_native_prefilter import load_module
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "diagnostics/algorithm-revision/camera_shading_inputs_20261002"
SOURCE = ROOT / "diagnostics/algorithm-revision/hybrid_photometric_source/algorithm_snapshot.py"
LIGHT = np.array([.45, -.35, 1.0])
LIGHT /= np.linalg.norm(LIGHT)


def illumination(camera, pattern, pose, mode):
    # Body texture moves with the known body pose. The illumination field stays
    # at fixed camera coordinates; it never follows a feature or an estimate.
    reflectance = .75 * short.body_texture(camera @ pose, pattern) + 20.
    if mode == "linear_additive":
        return reflectance + .30 * camera[:, :, 0] + .20 * camera[:, :, 1]
    diffuse = np.maximum((camera / 55.) @ LIGHT, 0.)
    return reflectance * (.55 + .45 * diffuse)


def render(pattern, mode, kind):
    if kind == "full_turn_x12":
        inputs = full.render([12.] * 30, pattern, axis="x")
        poses = inputs["poses"]
    else:
        inputs = short.render(pattern, kind == "stationary_120")
        poses = inputs["truth_poses"]
    yy, xx = np.mgrid[:150, :150]
    x, y = xx - 74.5, yy - 74.5
    z = np.sqrt(np.maximum(55.**2 - x*x - y*y, 0.))
    camera = np.stack((x, y, z), axis=-1)
    mask = inputs["mask"].astype(bool)
    seed = (1301 if pattern == "a" else 1923) + (0 if mode == "linear_additive" else 10000)
    rng = np.random.default_rng(seed)
    images = []
    extrema = []
    for pose in poses:
        values = illumination(camera, pattern, pose, mode)
        if kind == "stationary_120":
            values += rng.normal(0., 2., (150, 150))
        extrema.append((float(values[mask].min()), float(values[mask].max())))
        assert np.all((values[mask] > 0.) & (values[mask] < 255.)), "No illuminated fruit pixel may saturate"
        channel = np.uint8(values)
        channel[~mask] = 0
        images.append(np.repeat(channel[:, :, None], 3, axis=2))
    inputs["images"] = np.array(images)
    return inputs, {"kind": kind, "texture": pattern, "illumination": mode,
                    "stationary_noise_sigma_gray": 2. if kind == "stationary_120" else 0.,
                    "noise_seed": seed if kind == "stationary_120" else None,
                    "fruit_float_min": min(value[0] for value in extrema),
                    "fruit_float_max": max(value[1] for value in extrema), "saturated_pixels": 0}


def prepare_inputs():
    INPUT.mkdir(parents=True, exist_ok=False)
    for name in (Path(__file__).name, "validate_extended_motion_controls.py", "validate_full_turn_motion.py"):
        (INPUT / name).write_bytes((ROOT / name).read_bytes())
    manifest = {
        "prepared_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
        "renderer_sha256": sha256(Path(__file__)),
        "method": "Radius55 sphere, camera center74.5/74.5, independent body textures and analytical body-to-camera rotations. Texture reflectance .75*body_texture+20. Lighting is defined in fixed camera coordinates, not by estimated correspondences.",
        "illumination_equations": {"linear_additive": "I=reflectance+0.30*camera_x+0.20*camera_y",
            "lambertian_multiplicative": "I=reflectance*(0.55+0.45*max(camera_normal dot normalized([0.45,-0.35,1]),0))"},
        "acceptance": {"full_turn": {"all_30_pairs_measured": True, "max_pose_error_deg": 5., "max_front_visible_landmark_rms_px": 5.},
            "short_xy": {"all_10_pairs_measured": True, "endpoint_pose_error_deg": 1., "max_landmark_rms_px": 1.},
            "stationary_120": {"all_119_pairs_unavailable": True, "no_extrapolated_endpoint": True, "no_map_or_grade": True}},
        "scope": "Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.",
        "cases": {},
    }
    previews = []
    for kind in ("full_turn_x12", "short_xy", "stationary_120"):
        for mode in ("linear_additive", "lambertian_multiplicative"):
            for pattern in ("a", "b"):
                name = f"{kind}_{mode}_texture_{pattern}"
                inputs, row = render(pattern, mode, kind)
                path = INPUT / f"{name}.npz"
                np.savez_compressed(path, **inputs)
                row["input_sha256"] = sha256(path)
                row["frames"] = len(inputs["images"])
                manifest["cases"][name] = row
                previews.append((name, inputs["images"]))
    # The limits and every input are saved before any estimator is loaded.
    write_json(INPUT / "inputs.json", manifest)
    fig, axes = plt.subplots(6, 3, figsize=(10, 17))
    for panels, (name, images) in zip(axes, previews[:4] + previews[4:6]):
        for panel, index in zip(panels, (0, min(1, len(images)-1), min(15, len(images)-1))):
            panel.imshow(images[index][:, :, ::-1]); panel.axis("off")
            panel.set_title(f"Frame {index}", fontsize=9)
        panels[0].text(0., -0.10, name.replace("_", " "), transform=panels[0].transAxes, fontsize=8)
    fig.suptitle("Known camera-fixed lighting, moving body texture")
    fig.tight_layout(); fig.savefig(INPUT / "rendered_inputs.png", dpi=300)
    fig.savefig(INPUT / "rendered_inputs.pdf"); plt.close(fig)
    write_json(INPUT / "sha256.json", {str(path.relative_to(INPUT)): sha256(path) for path in INPUT.rglob("*") if path.is_file() and path.name != "sha256.json"})
    print(json.dumps({"prepared_inputs": str(INPUT), "scenes": len(manifest["cases"]), "limits_saved_before_estimation": True}), flush=True)


def short_settings(module):
    return module.Settings(spheroid_type="sphere", rotation_axis="y", rotation_direction=1,
        native_matching_cost="green_mad", minimum_view_rotation_deg=20., transverse_angle_deg=20.,
        bidirectional_matching=True, min_pair_angle_deg=.25, maximum_view_index_gap=1,
        select_rotating_views=True, minimum_longitude_coverage_deg=350., defect_observations_complete=False)


def stationary_checks(result):
    summary = result["summary"]
    return {"all_119_unavailable": summary["input_pairs"] == 119 and summary["measured_pairs"] == 0,
            "endpoint_unavailable": summary["endpoint_pose_error_deg"] is None and summary["endpoint_landmark_rms_px"] is None,
            "no_map_or_grade": result["mapping"]["status"] == "mapping_failed" and result["mapping"]["grade"] is None}


def run(args):
    if args.expected_sha256 and sha256(args.algorithm_source) != args.expected_sha256:
        raise ValueError("Frozen source hash differs")
    output = ROOT / "diagnostics/algorithm-revision" / args.label
    output.mkdir(parents=True, exist_ok=False)
    source = output / "algorithm_snapshot.py"
    source.write_bytes(args.algorithm_source.read_bytes())
    helper_names = (Path(__file__).name, "validate_extended_motion_controls.py", "validate_full_turn_motion.py",
                    "validate_native_prefilter.py", "validate_motion_resolution.py")
    for filename in helper_names:
        (output / filename).write_bytes((ROOT / filename).read_bytes())
    manifest = json.loads((INPUT / "inputs.json").read_text(encoding="utf-8"))
    report = {"started_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
              "algorithm_sha256": sha256(source), "validator_sha256": sha256(Path(__file__)),
              "helper_sha256": {filename: sha256(output / filename) for filename in helper_names},
              "input_manifest_sha256": sha256(INPUT / "inputs.json"), "input_directory": str(INPUT),
              "acceptance": manifest["acceptance"], "scope": manifest["scope"], "cases": {}}
    write_json(output / "report.json", report)
    module = load_module(source, "camera_shading_candidate")
    full.OUTPUT = output
    saved_threads = cv2.getNumThreads(); cv2.setNumThreads(1)
    try:
        for name, reference in manifest["cases"].items():
            path = INPUT / f"{name}.npz"
            assert sha256(path) == reference["input_sha256"]
            with np.load(path) as stored:
                inputs = {key: stored[key] for key in stored.files}
            inputs["case"] = name
            if reference["kind"] == "full_turn_x12":
                result = full.evaluate(module, inputs, hybrid=True, transverse_angle=20., recheck_angle=20.)
                complete = result["summary"]["measured_pairs"] == 30
                checks = {"all_30_pairs_measured": complete,
                    "maximum_pose_within_5deg": complete and result["summary"]["maximum_pose_error_deg"] <= 5.,
                    "maximum_front_visible_landmarks_within_5px": complete and result["summary"]["maximum_landmark_rms_px"] <= 5.}
            else:
                result = short.evaluate(module, inputs, short_settings(module))
                if reference["kind"] == "stationary_120":
                    checks = stationary_checks(result)
                else:
                    summary = result["summary"]
                    checks = {"all_10_pairs_measured": summary["measured_pairs"] == 10,
                        "endpoint_within_1deg": summary["endpoint_pose_error_deg"] is not None and summary["endpoint_pose_error_deg"] <= 1.,
                        "maximum_landmarks_within_1px": summary["measured_pairs"] == 10 and summary["maximum_landmark_rms_px"] <= 1.}
            report["cases"][name] = {**reference, "result": result, "checks": checks, "passed": all(checks.values())}
            write_json(output / "report.json", report)
            print(json.dumps({"case": name, **result["summary"], "checks": checks}), flush=True)
    finally:
        cv2.setNumThreads(saved_threads)
    report["completed_at"] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    report["all_controls_passed"] = all(row["passed"] for row in report["cases"].values())
    rows = []
    for name, row in report["cases"].items():
        summary = row["result"]["summary"]
        unavailable = row["kind"] == "stationary_120" and summary["endpoint_pose_error_deg"] is None
        pose = "unavailable" if unavailable else summary["maximum_pose_error_deg"]
        rms = "unavailable" if unavailable else summary["maximum_landmark_rms_px"]
        rows.append(f"| {name} | {summary['measured_pairs']}/{summary['input_pairs']} | {pose} | {rms} | {'PASS' if row['passed'] else 'FAIL'} |")
    (output / "CAMERA_SHADING_CONTROLS.md").write_text(
        "# Camera-fixed illumination: independent motion controls\n\n"
        f"Source SHA256 `{report['algorithm_sha256']}`. Exact input manifest SHA256 `{report['input_manifest_sha256']}`.\n\n"
        "All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run "
        "with quarter-resolution paper MAD, native green rechecks below 20 degrees, transverse bound 20 degrees, unchanged 0.58 residual and 3-degree consensus gates. No models or production edits.\n\n"
        "| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |\n"
        "| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
        "Full turns require all 30 measurements and 5-degree/5-pixel errors. Short x/y chains require all 10 measurements, "
        "endpoint 1-degree and maximum 1-pixel landmark errors. Stationary controls require all 119 pairs unavailable, "
        "null endpoints and no map/grade. Helper stationary zero maxima include only frame 0 scaffolding and are not scored zero motion.\n\n"
        + manifest["scope"] + "\n", encoding="utf-8")
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    for panel, kind in zip(axes, ("full_turn_x12", "short_xy", "stationary_120")):
        selected = [(name, row) for name, row in report["cases"].items() if row["kind"] == kind]
        values = [row["result"]["summary"]["measured_pairs"] if kind == "stationary_120" else
                  row["result"]["summary"]["endpoint_pose_error_deg"] if kind == "short_xy" else
                  row["result"]["summary"]["maximum_pose_error_deg"] for _, row in selected]
        values = [np.nan if value is None else value for value in values]
        panel.bar(range(len(values)), values, color=["#267a4e" if row["passed"] else "#a64f36" for _, row in selected])
        panel.set(xticks=range(len(values)), xticklabels=[f"{row['texture'].upper()}\n{'Plane' if row['illumination']=='linear_additive' else 'Lambert'}" for _, row in selected],
                  title=kind.replace("_", " "), ylabel="Returned false turns" if kind == "stationary_120" else
                  "Endpoint pose error (degrees)" if kind == "short_xy" else "Maximum pose error (degrees)")
        panel.grid(axis="y", alpha=.2)
        if kind != "stationary_120":
            panel.axhline(5. if kind == "full_turn_x12" else 1., linestyle="--", color="#777")
    fig.suptitle("Camera-fixed illumination: actual control outcomes")
    fig.tight_layout(); fig.savefig(output / "camera_shading_outcomes.png", dpi=300)
    fig.savefig(output / "camera_shading_outcomes.pdf"); plt.close(fig)
    write_json(output / "report.json", report)
    write_json(output / "sha256.json", {str(path.relative_to(output)): sha256(path) for path in output.rglob("*") if path.is_file() and path.name != "sha256.json"})
    print(json.dumps({"completed": str(output), "all_controls_passed": report["all_controls_passed"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-inputs", action="store_true")
    parser.add_argument("--label", default="camera_shading_baseline_20261002")
    parser.add_argument("--algorithm-source", type=Path, default=SOURCE)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    if args.prepare_inputs:
        prepare_inputs()
    else:
        run(args)


if __name__ == "__main__":
    main()
