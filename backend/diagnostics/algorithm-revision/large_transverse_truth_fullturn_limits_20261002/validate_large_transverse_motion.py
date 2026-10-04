"""Isolated large-transverse known-truth probe; no neural models or production edits."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import json
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import validate_extended_motion_controls as controls
from validate_native_prefilter import load_module
from validate_photometric_motion_controls import settings_for
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "diagnostics/algorithm-revision/hybrid_photometric_source/algorithm_snapshot.py"
LABEL = "large_transverse_truth_20261002"
EXPECTED = "951b55a4912d3147d349282846e2e02d20159a410b6bb2e8fdd4ab4dd3abea2d"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default=LABEL)
    parser.add_argument("--input-dir", type=Path, help="Replay exact NPZs from a prior probe instead of rendering again")
    parser.add_argument("--full-turn-limits", action="store_true", help="Use the existing full-turn 5-degree/5-pixel criteria; preserve the prior strict report")
    args = parser.parse_args()
    pose_limit = 5.0 if args.full_turn_limits else 1.0
    landmark_limit = 5.0 if args.full_turn_limits else 1.0
    assert sha256(SOURCE) == EXPECTED
    output = ROOT / "diagnostics/algorithm-revision" / args.label
    output.mkdir(parents=True, exist_ok=False)
    source = output / "algorithm_snapshot.py"
    source.write_bytes(SOURCE.read_bytes())
    for name in (Path(__file__).name, "validate_extended_motion_controls.py", "validate_photometric_motion_controls.py"):
        (output / name).write_bytes((ROOT / name).read_bytes())
    module = load_module(source, "large_transverse_candidate")
    reference = json.loads((ROOT / "diagnostics/algorithm-revision/extended_motion_controls_20261002/report.json").read_text(encoding="utf-8"))
    report = {
        "started_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
        "algorithm_sha256": EXPECTED,
        "validator_sha256": sha256(Path(__file__)),
        "method": "Four independently rendered two-frame sphere scenes. Both texture patterns and both signs of a 13-degree transverse plus 11-degree rolling axis-angle vector. Analytical pose and projected landmarks score the actual estimator, never initialize it. The same scenes are compared at transverse bounds 10 and 20 with unchanged residual .58 and all other settings.",
        "acceptance": {"pair_measured": True, "pose_error_max_deg": pose_limit, "landmark_rms_max_px": landmark_limit},
        "acceptance_profile": "Existing full-turn 5-degree/5-pixel criteria" if args.full_turn_limits else "Strict pair 1-degree/1-pixel diagnostic criteria",
        "prior_input_directory": str(args.input_dir.resolve()) if args.input_dir else None,
        "prior_strict_report_sha256": sha256(args.input_dir / "report.json") if args.input_dir else None,
        "acceptance_provenance": "The strict first-run result is preserved. This separate replay uses the 5-degree/5-pixel tolerance requested by the parent to align with the previously established full-turn controls. It does not overwrite or change the first-run 1-degree/1-pixel failure." if args.full_turn_limits else "Limits declared in this source before the first run.",
        "scope": "A new diagnostic probe for larger transverse motion. Ideal sphere, perfect masks, no exposure change. Does not establish field accuracy or change the prior accepted controls.",
        "cases": {},
    }
    write_json(output / "report.json", report)
    saved_threads = cv2.getNumThreads()
    cv2.setNumThreads(1)
    try:
        for pattern in ("a", "b"):
            for sign in (-1, 1):
                name = f"texture_{pattern}_transverse_{sign * 13:+d}"
                path = output / f"{name}_inputs.npz"
                if args.input_dir:
                    previous = args.input_dir / path.name
                    path.write_bytes(previous.read_bytes())
                    with np.load(path) as stored:
                        inputs = {key: stored[key] for key in stored.files}
                else:
                    controls.X_STEPS = [float(sign * 13)]
                    controls.Y_STEPS = [11.0]
                    inputs = controls.render(pattern, False)
                    np.savez_compressed(path, **inputs)
                row = {"input_sha256": sha256(path), "true_axis_angle_vector_deg": [float(sign * 13), 11.0, 0.0], "bounds": {}}
                for bound in (10.0, 20.0):
                    settings = settings_for(module, reference["cases"][f"variable_xy_texture_{pattern}"], "hybrid")
                    settings.transverse_angle_deg = bound
                    result = controls.evaluate(module, inputs, settings)
                    summary = result["summary"]
                    checks = {
                        "pair_measured": summary["measured_pairs"] == 1,
                        "known_pose_within_declared_limit": summary["endpoint_pose_error_deg"] is not None and summary["endpoint_pose_error_deg"] <= pose_limit,
                        "known_landmarks_within_declared_limit": summary["endpoint_landmark_rms_px"] is not None and summary["endpoint_landmark_rms_px"] <= landmark_limit,
                    }
                    row["bounds"][str(int(bound))] = {"result": result, "control_results": checks, "passed": all(checks.values())}
                    print(json.dumps({"case": name, "bound": bound, **summary, "controls": checks}), flush=True)
                report["cases"][name] = row
                write_json(output / "report.json", report)
    finally:
        cv2.setNumThreads(saved_threads)
    report["completed_at"] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    report["twenty_degree_controls_passed"] = all(row["bounds"]["20"]["passed"] for row in report["cases"].values())
    write_json(output / "report.json", report)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    names = list(report["cases"])
    for panel, key, ylabel, limit in zip(axes, ("endpoint_pose_error_deg", "endpoint_landmark_rms_px"), ("3D pose error (degrees)", "Projected landmark RMS (pixels)"), (pose_limit, landmark_limit)):
        for offset, bound, color in ((-.18, "10", "#a64f36"), (.18, "20", "#267a4e")):
            values = [report["cases"][name]["bounds"][bound]["result"]["summary"][key] for name in names]
            panel.bar(np.arange(len(names)) + offset, [np.nan if value is None else value for value in values], width=.35, color=color, label=f"Bound {bound} degrees")
            for index, value in enumerate(values):
                if value is None:
                    panel.text(index + offset, .05, "Unavailable", rotation=90, ha="center", va="bottom", fontsize=7)
        panel.axhline(limit, linestyle="--", color="#555", label="Declared replay limit")
        panel.set(ylabel=ylabel, xticks=np.arange(len(names)), xticklabels=["A −13", "A +13", "B −13", "B +13"])
        panel.grid(axis="y", alpha=.2)
        panel.legend(fontsize=8)
    fig.suptitle("Known 13-degree transverse plus 11-degree rolling motion")
    fig.tight_layout()
    fig.savefig(output / "large_transverse_truth.png", dpi=300)
    fig.savefig(output / "large_transverse_truth.pdf")
    plt.close(fig)
    rows = []
    for name, row in report["cases"].items():
        for bound, variant in row["bounds"].items():
            result = variant["result"]
            summary = result["summary"]
            pose = summary["endpoint_pose_error_deg"]
            rms = summary["endpoint_landmark_rms_px"]
            rows.append(f"| {name} | {bound} | {summary['measured_pairs']}/1 | {pose if pose is not None else 'unavailable'} | {rms if rms is not None else 'unavailable'} | {'PASS' if variant['passed'] else 'FAIL'} |")
    (output / "LARGE_TRANSVERSE_TRUTH.md").write_text(
        "# Large transverse motion: independent geometry probe\n\n" + report["method"] + "\n\n"
        f"Criteria recorded before this replay: returned measurement, at most {pose_limit:g} degrees pose error and {landmark_limit:g} pixels projected landmark RMS. "
        "A rejected measurement remains unavailable, rather than being assigned zero error.\n\n"
        + report["acceptance_provenance"] + "\n\n"
        "| Scene | Bound, deg | Returned pair | Pose error, deg | Landmark RMS, px | Control |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
        + report["scope"] + "\n\n![Independent geometry errors](large_transverse_truth.png)\n", encoding="utf-8")
    write_json(output / "sha256.json", {str(path.relative_to(output)): sha256(path) for path in output.rglob("*") if path.is_file() and path.name != "sha256.json"})
    print(json.dumps({"completed": str(output), "twenty_degree_controls_passed": report["twenty_degree_controls_passed"]}), flush=True)


if __name__ == "__main__":
    main()
