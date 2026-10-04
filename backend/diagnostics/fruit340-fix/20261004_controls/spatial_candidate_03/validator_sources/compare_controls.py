"""Compare frozen estimators on pre-existing independent known-motion pixels.

No production edits and no truth-driven pose correction. Failed chains stay
unavailable. Absolute acceptance and change from baseline are reported separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

import cv2
import numpy as np
import validate_camera_shading as shading
import validate_extended_motion_controls as short
import validate_full_turn_motion as full
import validate_motion_resolution as resolution


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def input_cases(stress_only=False, spatial_only=False):
    stress = Path(__file__).resolve().parent / "stress_inputs"
    if spatial_only:
        stress = Path(__file__).resolve().parent / "spatial_inputs"
        stress_only = True
    if stress_only:
        manifest = json.loads((stress / "inputs.json").read_text(encoding="utf-8"))
        for name, reference in manifest["cases"].items():
            yield name, stress / f"{name}.npz", reference
        return
    manifest = json.loads((shading.INPUT / "inputs.json").read_text(encoding="utf-8"))
    for name, reference in manifest["cases"].items():
        yield name, shading.INPUT / f"{name}.npz", reference
    extended = BACKEND / "diagnostics/algorithm-revision/extended_motion_controls_20261002"
    for name in ("variable_xy_texture_a", "variable_xy_texture_b", "stationary_120_texture_a", "stationary_120_texture_b"):
        yield name, extended / f"{name}_inputs.npz", {"kind": "stationary_120" if name.startswith("stationary") else "short_xy", "illumination": "unlit_body_texture"}
    inputs = BACKEND / "diagnostics/algorithm-revision/motion_resolution_20261002"
    for name in ("variable_small_motion", "stationary_pixel_noise", "uniform_stationary"):
        yield name, inputs / f"{name}_inputs.npz", {"kind": "resolution", "stationary": name != "variable_small_motion"}


def inspect_searches(module):
    counts = Counter()
    original = module._search_rotation
    def search(source, target, model, index, settings, **search_options):
        kind = f"d{settings.image_downsample}/{settings.matching_cost}/{'bidirectional' if settings.bidirectional_matching else 'single'}"
        if search_options.get("inplane_angle_deg", 0.):
            kind += f"/zbound{search_options['inplane_angle_deg']:g}"
        counts[kind + "/attempted"] += 1
        try:
            result = original(source, target, model, index, settings, **search_options)
        except module.MappingError:
            counts[kind + "/unavailable"] += 1
            raise
        counts[kind + "/measured"] += 1
        return result
    module._search_rotation = search
    return counts


def pair_truth(inputs, index):
    if "truth_poses" in inputs:
        poses = inputs["truth_poses"]
    elif "poses" in inputs:
        poses = inputs["poses"]
    else:
        poses = np.array([resolution.rotation_y(angle) for angle in inputs["angles_deg"]])
    return poses[index + 1] @ poses[index].T


def pair_accuracy(result, inputs):
    for index, row in enumerate(result["pairs"]):
        if row["status"] == "measured":
            vector = row.get("rotation_vector_deg", row.get("vector_deg"))
            estimated = cv2.Rodrigues(np.deg2rad(vector))[0]
            row["independent_increment_pose_error_deg"] = short.angle_error_deg(estimated, pair_truth(inputs, index))


def absolute_checks(result, reference):
    summary = result["summary"]
    stationary = reference["kind"].startswith("stationary") or reference.get("stationary", False)
    if stationary:
        mapping = result["mapping"]
        return {
            "all_pairs_unavailable": summary["measured_pairs"] == 0,
            "endpoint_unavailable": summary.get("endpoint_pose_error_deg", summary.get("final_pose_error_deg")) is None,
            "no_map_or_grade": mapping["status"] == "mapping_failed" and mapping["grade"] is None,
        }
    if reference["kind"] == "full_turn_x12":
        return {
            "all_pairs_measured": summary["measured_pairs"] == summary["input_pairs"],
            "maximum_pose_within_5deg": summary["measured_pairs"] == summary["input_pairs"] and summary["maximum_pose_error_deg"] <= 5.,
            "maximum_landmarks_within_5px": summary["measured_pairs"] == summary["input_pairs"] and summary["maximum_landmark_rms_px"] <= 5.,
        }
    return {
        "all_pairs_measured": summary["measured_pairs"] == summary["input_pairs"],
        "endpoint_within_1deg": summary.get("endpoint_pose_error_deg", summary.get("final_pose_error_deg")) is not None and summary.get("endpoint_pose_error_deg", summary.get("final_pose_error_deg")) <= 1.,
        "maximum_landmarks_within_1px": summary["measured_pairs"] == summary["input_pairs"] and summary.get("maximum_landmark_rms_px", summary.get("max_landmark_rms_px")) <= 1.,
    }


def evaluate(module, inputs, reference, folder):
    counts = inspect_searches(module)
    try:
        if reference["kind"] == "full_turn_x12":
            full.OUTPUT = folder
            result = full.evaluate(module, inputs, hybrid=True, transverse_angle=20., recheck_angle=20., native_cost="aligned_mad", max_pair_angle=20.)
        else:
            settings = shading.short_settings(module, "aligned_mad", 20.)
            settings.rotation_axis = reference.get("rotation_axis", "y")
            result = resolution.evaluate(module, inputs, settings) if reference["kind"] == "resolution" else short.evaluate(module, inputs, settings)
    finally:
        # This module is loaded per case, so restoration is unnecessary.
        pass
    pair_accuracy(result, inputs)
    result["search_call_counts"] = dict(counts)
    result["absolute_checks"] = absolute_checks(result, reference)
    result["absolute_passed"] = all(result["absolute_checks"].values())
    return result


def compare(baseline, candidate):
    changed = []
    regressions = []
    newly_measured = []
    for old, new in zip(baseline["pairs"], candidate["pairs"]):
        pair = {"source_frame": old["source_frame"], "target_frame": old["target_frame"], "baseline_status": old["status"], "candidate_status": new["status"]}
        if old["status"] == new["status"] == "measured":
            old_vector = np.array(old.get("rotation_vector_deg", old.get("vector_deg")))
            new_vector = np.array(new.get("rotation_vector_deg", new.get("vector_deg")))
            matrix_error = short.angle_error_deg(cv2.Rodrigues(np.deg2rad(old_vector))[0], cv2.Rodrigues(np.deg2rad(new_vector))[0])
            if matrix_error > 1e-5 or abs(old["residual"] - new["residual"]) > 1e-8:
                changed.append({**pair, "returned_pose_change_deg": matrix_error, "baseline_truth_error_deg": old["independent_increment_pose_error_deg"], "candidate_truth_error_deg": new["independent_increment_pose_error_deg"]})
                if new["independent_increment_pose_error_deg"] > old["independent_increment_pose_error_deg"] + .05:
                    regressions.append(changed[-1])
        elif old["status"] != new["status"]:
            changed.append(pair)
            if new["status"] == "measured":
                newly_measured.append({**pair, "baseline_reason": old.get("reason"), "candidate_truth_error_deg": new["independent_increment_pose_error_deg"], "candidate_residual": new["residual"]})
            else:
                regressions.append(pair)
    return {"changed_pairs": changed, "newly_measured_pairs": newly_measured, "existing_measured_regressions": regressions,
            "existing_measured_outputs_preserved": not regressions and not any(row["baseline_status"] == "measured" for row in changed),
            "baseline_absolute_passed": baseline["absolute_passed"], "candidate_absolute_passed": candidate["absolute_passed"],
            "previously_passing_control_preserved": not baseline["absolute_passed"] or candidate["absolute_passed"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--stress-only", action="store_true")
    parser.add_argument("--spatial-only", action="store_true")
    parser.add_argument("--baseline-report", type=Path, help="Reuse explicitly documented, hash-verified baseline results on identical inputs; candidate always reruns")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = {}
    for name, source in (("baseline", args.baseline), ("candidate", args.candidate)):
        folder = args.output / name
        folder.mkdir()
        frozen = folder / "algorithm.py"
        frozen.write_bytes(source.read_bytes())
        sources[name] = frozen
    helpers = [Path(__file__), *(BACKEND / name for name in ("validate_camera_shading.py", "validate_extended_motion_controls.py", "validate_full_turn_motion.py", "validate_motion_resolution.py"))]
    helpers_folder = args.output / "validator_sources"
    helpers_folder.mkdir()
    for source in helpers:
        (helpers_folder / source.name).write_bytes(source.read_bytes())
    baseline_reference = None
    if args.baseline_report:
        baseline_reference = json.loads(args.baseline_report.read_text(encoding="utf-8"))
        if baseline_reference["algorithm_sha256"]["baseline"] != digest(sources["baseline"]):
            raise ValueError("Cached baseline source differs")
        for source in helpers[1:]:
            if baseline_reference["validator_sha256"][source.name] != digest(source):
                raise ValueError(f"Cached baseline analytical validator differs: {source.name}")
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "algorithm_sha256": {name: digest(path) for name, path in sources.items()},
        "validator_sha256": {path.name: digest(path) for path in helpers},
        "method": "Replay pre-existing frozen images, exact masks and independent analytical pose/landmark truth through both frozen estimator sources. Native aligned_mad, quarter-resolution coarse search, bidirectional matching and rolling/transverse bounds 20 degrees. Existing helper acceptance thresholds remain fixed. Failed chains are never interpolated; per-pair truth errors are additionally scored independently after chain failure.",
        "scope": "Synthetic development software controls only: perfect sphere masks and known orthographic projection, no real fruit ground truth, no detector or defect segmentation inference, no occlusion or glare. Full-turn maps have explicitly known all-clear labels to test map execution. A pass does not establish real fruit pose, surface or grading accuracy.",
        "baseline_reference_report": str(args.baseline_report) if args.baseline_report else None,
        "baseline_reference_sha256": digest(args.baseline_report) if args.baseline_report else None,
        "cases": {},
    }
    write(args.output / "report.json", report)
    cv2.setNumThreads(1)
    started = time.perf_counter()
    for name, path, reference in input_cases(args.stress_only, args.spatial_only):
        if args.cases and name not in args.cases:
            continue
        observed_hash = digest(path)
        if reference.get("input_sha256") and reference["input_sha256"] != observed_hash:
            raise ValueError(f"Frozen input hash differs: {path}")
        with np.load(path) as stored:
            inputs = {key: stored[key] for key in stored.files}
        inputs["case"] = name
        row = {"input_file": str(path), "input_sha256": observed_hash, "reference": reference, "variants": {}}
        report["cases"][name] = row
        for variant, source in sources.items():
            cached = baseline_reference and baseline_reference["cases"].get(name)
            if variant == "baseline" and cached:
                if cached["input_sha256"] != observed_hash or cached["reference"] != reference:
                    raise ValueError(f"Cached baseline input or acceptance reference differs: {name}")
                result = cached["variants"]["baseline"]
                row["baseline_reused_from_verified_report"] = True
            else:
                module = load_module(source, f"fruit340_controls_{variant}_{name}")
                result = evaluate(module, inputs, reference, args.output / variant)
            row["variants"][variant] = result
            write(args.output / "report.json", report)
            print(json.dumps({"case": name, "variant": variant, "summary": result["summary"], "absolute_checks": result["absolute_checks"]}), flush=True)
        row["comparison"] = compare(row["variants"]["baseline"], row["variants"]["candidate"])
        write(args.output / "report.json", report)
    report["seconds"] = time.perf_counter() - started
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["all_previously_passing_controls_preserved"] = all(row["comparison"]["previously_passing_control_preserved"] for row in report["cases"].values())
    report["all_existing_measured_outputs_preserved"] = all(row["comparison"]["existing_measured_outputs_preserved"] for row in report["cases"].values())
    report["candidate_all_absolute_controls_passed"] = all(row["variants"]["candidate"]["absolute_passed"] for row in report["cases"].values())
    write(args.output / "report.json", report)
    lines = ["# Fruit 340 correction: independent motion controls", "", report["method"], "", report["scope"], "", "| Known scene | Baseline measured | Candidate measured | Baseline control | Candidate control | Changed pairs |", "| --- | --- | --- | --- | --- | --- |"]
    if args.baseline_report:
        lines[4:4] = [f"Baseline measurements reused from `{args.baseline_report}` after verifying the exact source, analytical validators, pixels and acceptance references. Candidate measurements rerun for every listed case.", ""]
    for name, row in report["cases"].items():
        old, new = row["variants"]["baseline"], row["variants"]["candidate"]
        lines.append(f"| {name} | {old['summary']['measured_pairs']}/{old['summary']['input_pairs']} | {new['summary']['measured_pairs']}/{new['summary']['input_pairs']} | {'PASS' if old['absolute_passed'] else 'FAIL'} | {'PASS' if new['absolute_passed'] else 'FAIL'} | {len(row['comparison']['changed_pairs'])} |")
    (args.output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write(args.output / "sha256.json", {str(path.relative_to(args.output)): digest(path) for path in args.output.rglob("*") if path.is_file() and path.name != "sha256.json"})
    print(json.dumps({"completed": str(args.output), "cases": len(report["cases"]), "seconds": report["seconds"], "previously_passing_controls_preserved": report["all_previously_passing_controls_preserved"], "existing_measured_outputs_preserved": report["all_existing_measured_outputs_preserved"], "candidate_all_absolute_controls_passed": report["candidate_all_absolute_controls_passed"]}), flush=True)


if __name__ == "__main__":
    main()
