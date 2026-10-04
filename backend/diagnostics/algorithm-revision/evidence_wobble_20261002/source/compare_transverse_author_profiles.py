"""Compare the same published labels between frozen 10/20-degree profiles."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import benchmark_authors as benchmark
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
DIAGNOSTICS = ROOT / "diagnostics"
PAIRS = {
    "independent_pairs": ("authors-benchmark/runs/hybrid_photometric_profile_20261002", "authors-benchmark/runs/hybrid_wobble_profile_20261002", "correspondences"),
    "retained_segment": ("authors-benchmark/bridge_runs/hybrid_photometric_retained_20261002", "authors-benchmark/bridge_runs/hybrid_wobble_retained_20261002", "original_labels"),
}


def identity(row):
    return row["group"], row["object"], int(row["line"])


def main():
    output = DIAGNOSTICS / "algorithm-revision/transverse_author_comparison_20261002"
    output.mkdir(parents=True, exist_ok=False)
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    report = {"recorded_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
              "method": "Match every label by (fruit class, object ID, annotation line); assert identical source/target frame and pixel coordinates. Paired accuracy uses only labels returned by BOTH frozen profiles; availability is separately counted over all 497 labels. No model or rotation estimator is run.",
              "scope": "Development author images used during tuning, not held-out evaluation. Common-label accuracy and newly available predictions must both be reported; a larger returned subset alone does not show improved accuracy.",
              "comparisons": {}}
    worst_images = []
    for name, (before_path, after_path, rows_key) in PAIRS.items():
        paths = [DIAGNOSTICS / relative / "report.json" for relative in (before_path, after_path)]
        before, after = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        old = {identity(row): row for row in before[rows_key]}
        new = {identity(row): row for row in after[rows_key]}
        assert len(old) == len(new) == 497 and set(old) == set(new)
        common, new_only, old_only, neither = [], [], [], []
        for key in sorted(old):
            a, b = old[key], new[key]
            assert all(a[field] == b[field] for field in ("source", "target", "source_xy", "target_xy"))
            returned_before, returned_after = a["status"] == "ok", b["status"] == "ok"
            row = {"group": key[0], "object": key[1], "line": key[2],
                   "source": b["source"], "target": b["target"],
                   "source_xy": b["source_xy"], "target_xy": b["target_xy"],
                   "alpha10_error_px": a.get("error_px"), "alpha20_error_px": b.get("error_px"),
                   "alpha10_status": a["status"], "alpha20_status": b["status"]}
            if returned_before and returned_after:
                row["error_change_px"] = b["error_px"] - a["error_px"]
                common.append(row)
            elif returned_after:
                new_only.append(row)
            elif returned_before:
                old_only.append(row)
            else:
                neither.append(row)
        settings_changes = {key: {"before": before["settings"][key], "after": after["settings"][key]}
                            for key in after["settings"] if before["settings"][key] != after["settings"][key]}
        worst = max((row for row in after[rows_key] if row["status"] == "ok"), key=lambda row: row["error_px"])
        result = {
            "baseline_report": before_path + "/report.json", "candidate_report": after_path + "/report.json",
            "baseline_report_sha256": sha256(paths[0]), "candidate_report_sha256": sha256(paths[1]),
            "same_algorithm_source": before["algorithm_sha256"] == after["algorithm_sha256"],
            "algorithm_sha256": after["algorithm_sha256"], "settings_changes": settings_changes,
            "total_identical_labels": 497,
            "availability": {"both_returned": len(common), "newly_returned_alpha20": len(new_only),
                             "lost_alpha20": len(old_only), "both_unavailable": len(neither)},
            "same_returned_labels_alpha10": benchmark.stats([row["alpha10_error_px"] for row in common]),
            "same_returned_labels_alpha20": benchmark.stats([row["alpha20_error_px"] for row in common]),
            "common_improved": sum(row["error_change_px"] < -1e-8 for row in common),
            "common_worsened": sum(row["error_change_px"] > 1e-8 for row in common),
            "common_unchanged": sum(abs(row["error_change_px"]) <= 1e-8 for row in common),
            "newly_returned_alpha20_errors": benchmark.stats([row["alpha20_error_px"] for row in new_only]),
            "lost_alpha20_errors": benchmark.stats([row["alpha10_error_px"] for row in old_only]),
            "worst_alpha20_prediction": worst,
            "common_labels": common, "newly_returned_labels": new_only, "lost_labels": old_only,
        }
        report["comparisons"][name] = result
        print(json.dumps({"comparison": name, "availability": result["availability"],
                          "same_labels_alpha10": result["same_returned_labels_alpha10"],
                          "same_labels_alpha20": result["same_returned_labels_alpha20"],
                          "common_improved": result["common_improved"], "common_worsened": result["common_worsened"],
                          "worst": {key: worst[key] for key in ("group", "object", "line", "error_px")}}), flush=True)
        views = benchmark.load_views(benchmark.DATA / "rotation/data" / worst["group"] / worst["object"], 0)
        picture = output / f"{name}_worst_alpha20.png"
        benchmark.save_correspondence_view(picture, views, worst, np.asarray(worst["prediction"]))
        worst_images.append(picture.name)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for panel, (name, result) in zip(axes, report["comparisons"].items()):
        rows = result["common_labels"]
        panel.scatter([row["alpha10_error_px"] for row in rows], [row["alpha20_error_px"] for row in rows], s=10, alpha=.55, color="#267a4e")
        upper = max(max(row["alpha10_error_px"], row["alpha20_error_px"]) for row in rows) * 1.05
        panel.plot([0, upper], [0, upper], "--", color="#777", label="Same error")
        panel.set(title=name.replace("_", " "), xlabel="Alpha 10 error (pixels)", ylabel="Alpha 20 error (pixels)")
        panel.grid(alpha=.2); panel.legend(fontsize=8)
    fig.suptitle("Author accuracy on exactly the same returned labels")
    fig.tight_layout(); fig.savefig(output / "same_label_accuracy.png", dpi=300)
    fig.savefig(output / "same_label_accuracy.pdf"); plt.close(fig)
    write_json(output / "report.json", report)
    rows = []
    for name, row in report["comparisons"].items():
        a, b, availability = row["same_returned_labels_alpha10"], row["same_returned_labels_alpha20"], row["availability"]
        rows.append(f"| {name} | {availability['both_returned']} | {a['rms']:.5f} | {b['rms']:.5f} | {availability['newly_returned_alpha20']} | {availability['lost_alpha20']} | {row['common_improved']} / {row['common_worsened']} / {row['common_unchanged']} |")
    (output / "SAME_LABEL_COMPARISON.md").write_text(
        "# Same-label comparison of transverse bounds\n\n" + report["method"] + "\n\n"
        "| Evaluation | Common returned labels | Alpha 10 RMS, px | Alpha 20 RMS, px | Newly returned | Lost | Improved / worsened / unchanged |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
        "The alpha 20 independent and retained subsets both include a returned 39.55996-pixel error. "
        "Worst-case actual image evidence is included below. These outcomes are retained; more available predictions are not a general accuracy claim.\n\n"
        + report["scope"] + "\n\n![Matched-label accuracy](same_label_accuracy.png)\n\n"
        + "\n\n".join(f"![Returned worst-case author error]({name})" for name in worst_images) + "\n", encoding="utf-8")
    write_json(output / "sha256.json", {str(path.relative_to(output)): sha256(path) for path in output.rglob("*") if path.is_file() and path.name != "sha256.json"})


if __name__ == "__main__":
    main()
