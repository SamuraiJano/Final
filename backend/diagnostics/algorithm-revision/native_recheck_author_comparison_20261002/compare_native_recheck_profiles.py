"""Frozen same-label accuracy/availability audit for native recheck8 versus20."""
from pathlib import Path
import json
import numpy as np
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "diagnostics/authors-benchmark"
CASES = {
    "independent_pairs": ("correspondences", "runs/hybrid_wobble_profile_20261002", "runs/hybrid_refine20_profile_20261002"),
    "retained_segment": ("original_labels", "bridge_runs/hybrid_wobble_retained_20261002", "bridge_runs/hybrid_refine20_retained_20261002"),
}


def main():
    output = ROOT / "diagnostics/algorithm-revision/native_recheck_author_comparison_20261002"
    output.mkdir(parents=True, exist_ok=False)
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    report = {"method": "Match exact (group,object,line) labels and verify all source/target coordinates. Conditional paired RMS uses the same labels returned by BOTH settings; all497 labels remain in availability denominators. No new model/geometry estimates.", "comparisons": {}}
    for name, (rows_key, oldrel, newrel) in CASES.items():
        paths = [DATA / relative / "report.json" for relative in (oldrel, newrel)]
        old, new = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        identity = lambda row: (row["group"], row["object"], row["line"])
        a, b = [{identity(row): row for row in data[rows_key]} for data in (old, new)]
        assert len(a) == len(b) == 497 and set(a) == set(b)
        for key in a:
            assert all(a[key][field] == b[key][field] for field in ("source", "target", "source_xy", "target_xy"))
        common = [key for key in a if a[key]["status"] == b[key]["status"] == "ok"]
        changed = [b[key]["error_px"] - a[key]["error_px"] for key in common]
        row = {
            "baseline_report": str(paths[0]), "candidate_report": str(paths[1]),
            "baseline_report_sha256": sha256(paths[0]), "candidate_report_sha256": sha256(paths[1]),
            "algorithm_sha256": new["algorithm_sha256"], "same_algorithm_source": old["algorithm_sha256"] == new["algorithm_sha256"],
            "settings_changes": {key: {"before": old["settings"][key], "after": new["settings"][key]} for key in old["settings"] if old["settings"][key] != new["settings"][key]},
            "same_returned_labels": len(common),
            "native8_common_rms_px": float(np.sqrt(np.mean([a[key]["error_px"]**2 for key in common]))),
            "native20_common_rms_px": float(np.sqrt(np.mean([b[key]["error_px"]**2 for key in common]))),
            "improved": sum(value < -1e-8 for value in changed), "worsened": sum(value > 1e-8 for value in changed),
            "unchanged": sum(abs(value) <= 1e-8 for value in changed),
            "newly_returned_native20": sum(a[key]["status"] != "ok" and b[key]["status"] == "ok" for key in a),
            "lost_native20": sum(a[key]["status"] == "ok" and b[key]["status"] != "ok" for key in a),
            "labels": [{"group": key[0], "object": key[1], "line": key[2],
                        "native8_error_px": a[key]["error_px"], "native20_error_px": b[key]["error_px"]} for key in common],
        }
        assert row["same_algorithm_source"]
        assert row["settings_changes"] == {"minimum_view_rotation_deg": {"before": 8.0, "after": 20.0}}
        report["comparisons"][name] = row
    write_json(output / "report.json", report)
    rows = [f"| {name} | {row['same_returned_labels']} | {row['native8_common_rms_px']:.5f} | {row['native20_common_rms_px']:.5f} | {row['newly_returned_native20']} | {row['lost_native20']} |" for name, row in report["comparisons"].items()]
    (output / "NATIVE_RECHECK_COMPARISON.md").write_text(
        "# Native recheck trigger: same-label audit\n\n"
        "Only the native recheck trigger changes from8 to20degrees. Exact source951, transverse20, residual0.58 and all other settings stay fixed. Both sources score the same original497labels.\n\n"
        "| Evaluation | Common returned labels | Native8 RMS, px | Native20 RMS, px | Newly returned | Lost |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
        "Native20 independent availability drops462→416, within5 drops373→338; overall conditional RMS5.39868→5.37020 conceals the smaller returned subset. "
        "Retained availability drops368→287, within5 drops296→230 and conditional RMS5.60733→5.72502. "
        "Both common-label RMS comparisons worsen. Development data, not held-out or conveyor-grade accuracy. Failures remain counted.\n", encoding="utf-8")
    write_json(output / "sha256.json", {str(path.relative_to(output)): sha256(path) for path in output.rglob("*") if path.is_file() and path.name != "sha256.json"})
    print(json.dumps({name: {key: row[key] for key in ("same_returned_labels", "native8_common_rms_px", "native20_common_rms_px", "newly_returned_native20", "lost_native20")} for name, row in report["comparisons"].items()}))


if __name__ == "__main__":
    main()
