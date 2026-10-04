"""Replay the exact original full-turn inputs with an explicitly frozen candidate."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import validate_full_turn_motion as full
from validate_native_prefilter import load_module
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--algorithm-source", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--input-directory", type=Path,
        default=ROOT / "diagnostics/algorithm-revision/full_turn_hybrid_20261002")
    parser.add_argument("--native-matching-cost", default="aligned_mad")
    parser.add_argument("--native-recheck-angle", type=float, default=20.)
    parser.add_argument("--transverse-angle", type=float, default=20.)
    parser.add_argument("--max-pair-angle", type=float, default=20.)
    args = parser.parse_args()
    output = ROOT / "diagnostics/algorithm-revision" / args.label
    output.mkdir(parents=True, exist_ok=False)
    origin = args.input_directory.resolve()
    original_report = json.loads((origin / "report.json").read_text())
    acceptance = original_report["acceptance"]
    assert acceptance["maximum_pose_error_deg"] == 5.
    assert acceptance["maximum_front_visible_landmark_rms_px"] == 5.
    assert acceptance["all_pairs_measured"] is True
    (output / "original_report.json").write_bytes((origin / "report.json").read_bytes())
    write_json(output / "acceptance_before_execution.json", acceptance)
    manifest = {}
    for name, reference in original_report["cases"].items():
        path = origin / f"{name}_inputs.npz"
        assert sha256(path) == reference["input_sha256"]
        (output / path.name).write_bytes(path.read_bytes())
        manifest[name] = {"input_file": path.name, "input_sha256": sha256(path)}
    write_json(output / "input_manifest.json", manifest)
    source = args.algorithm_source.resolve()
    assert sha256(source) == args.expected_sha256
    (output / "algorithm_snapshot.py").write_bytes(source.read_bytes())
    for name in (Path(__file__).name, "validate_full_turn_motion.py", "validate_extended_motion_controls.py",
                 "validate_motion_resolution.py", "validate_native_prefilter.py"):
        (output / name).write_bytes((ROOT / name).read_bytes())
    report = {"started_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
              "algorithm_sha256": args.expected_sha256, "validator_sha256": sha256(Path(__file__)),
              "original_input_directory": str(origin), "original_report_sha256": sha256(origin / "report.json"),
              "acceptance": acceptance,
              "scope": "Exact archived synthetic development inputs and declared limits. Actual matcher and mapping; no corrected or extrapolated poses. Not field/model accuracy.",
              "cases": {}}
    write_json(output / "report.json", report)
    module = load_module(output / "algorithm_snapshot.py", "frozen_full_turn_replay")
    full.OUTPUT = output
    previous_threads = cv2.getNumThreads()
    cv2.setNumThreads(1)
    try:
        for name, reference in manifest.items():
            with np.load(output / reference["input_file"]) as stored:
                inputs = {key: stored[key] for key in stored.files}
            inputs["case"] = name
            started = time.perf_counter()
            result = full.evaluate(module, inputs, hybrid=True, transverse_angle=args.transverse_angle,
                                   recheck_angle=args.native_recheck_angle, native_cost=args.native_matching_cost,
                                   max_pair_angle=args.max_pair_angle)
            summary = result["summary"]
            count = len(inputs["poses"])-1
            complete = summary["measured_pairs"] == count
            checks = {"all_pairs_measured": complete,
                "maximum_pose_within_5deg": complete and summary["maximum_pose_error_deg"] <= 5.,
                "maximum_front_visible_landmarks_within_5px": complete and summary["maximum_landmark_rms_px"] <= 5.,
                "known_clear_grade": result["mapping"].get("grade") == acceptance["clear_grade"]}
            report["cases"][name] = {**reference, "result": result, "checks": checks,
                                     "passed": all(checks.values()), "seconds": time.perf_counter()-started}
            write_json(output / "report.json", report)
            print(json.dumps({"case": name, **summary, "checks": checks}), flush=True)
    finally:
        cv2.setNumThreads(previous_threads)
    report["completed_at"] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    report["all_controls_passed"] = all(c["passed"] for c in report["cases"].values())
    write_json(output / "report.json", report)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for panels, (name, case) in zip(axes, report["cases"].items()):
        trace = case["result"]["trace"]
        for panel, key, title in zip(panels, ("pose_error_deg", "landmark_rms_px"),
                                    ("Pose error (degrees)", "Visible landmark RMS (pixels)")):
            panel.plot([r["true_angle_deg"] for r in trace], [r.get(key, np.nan) for r in trace], color="#286b55")
            panel.axhline(5., color="#b47136", ls="--", label="Predeclared 5-unit limit")
            panel.set(title=name.replace("_", " "), xlabel="Known rotation (degrees)", ylabel=title)
            panel.grid(alpha=.2)
            panel.legend(fontsize=8)
    fig.suptitle("Original full-turn control inputs: actual candidate outcomes")
    fig.savefig(output / "full_turn_accuracy.png", dpi=300)
    fig.savefig(output / "full_turn_accuracy.pdf")
    plt.close(fig)
    rows = []
    for name, case in report["cases"].items():
        summary = case["result"]["summary"]
        rows.append(f"| {name} | {summary['measured_pairs']}/{summary['input_pairs']} | {summary['maximum_pose_error_deg']:.6f} | {summary['maximum_landmark_rms_px']:.6f} | {'PASS' if case['passed'] else 'FAIL'} |")
    (output / "FULL_TURN_REPLAY.md").write_text(
        "# Exact original full-turn input replay\n\n" + report["scope"] + "\n\n"
        f"Source `{args.expected_sha256}`. Archived inputs copied byte-for-byte from `{origin.name}`; original hashes and 5°/5px/full-pair/class acceptance retained.\n\n"
        "| Case | Measured pairs | Maximum pose error (degrees) | Maximum visible landmark RMS (pixels) | Outcome |\n"
        "|---|---:|---:|---:|---|\n" + "\n".join(rows) + "\n\n"
        "Perfect sphere masks and known-clear defect masks isolate geometry and mapping execution. These controls do not establish real conveyor grading or neural-model accuracy.\n",
        encoding="utf-8")
    write_json(output / "sha256.json", {str(p.relative_to(output)): sha256(p) for p in output.rglob("*") if p.is_file()})
    print(json.dumps({"output": str(output), "all_controls_passed": report["all_controls_passed"]}), flush=True)


if __name__ == "__main__":
    main()
