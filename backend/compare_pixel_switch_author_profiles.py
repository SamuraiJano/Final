"""Compare every author label across the final and two archived profiles."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import benchmark_authors as benchmark
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "diagnostics/authors-benchmark/runs"
FINAL = "pixel_switch_trace_author_profile_20261002"
BASELINES = ("operational_profile_v1", "hybrid_wobble_profile_20261002")
EXPECTED = "50bdd78eafcc5581d0368353c9996c2f95823c69f734dac6f778dc82f22c815d"


def identity(row):
    return row["group"], row["object"], int(row["line"])


def index(report):
    result = {identity(row): row for row in report["correspondences"]}
    assert len(result) == len(report["correspondences"]) == 497
    assert len(report["tracks"]) == 36
    return result


def compare(old, new, group=None):
    common, gained, lost, neither = [], [], [], []
    for key in sorted(old):
        if group and key[0] != group:
            continue
        a, b = old[key], new[key]
        assert all(a[k] == b[k] for k in ("source", "target", "source_xy", "target_xy", "split"))
        row = {"group": key[0], "object": key[1], "line": key[2],
            "source": a["source"], "target": a["target"], "source_xy": a["source_xy"], "target_xy": a["target_xy"],
            "baseline_status": a["status"], "candidate_status": b["status"],
            "baseline_error_px": a.get("error_px"), "candidate_error_px": b.get("error_px"),
            "baseline_reason": a.get("reason"), "candidate_reason": b.get("reason")}
        before, after = a["status"] == "ok", b["status"] == "ok"
        if before and after:
            row["error_change_px"] = b["error_px"]-a["error_px"]
            common.append(row)
        elif after:
            gained.append(row)
        elif before:
            lost.append(row)
        else:
            neither.append(row)
    return {"total_labels": len(common)+len(gained)+len(lost)+len(neither),
        "availability": {"both_returned": len(common), "newly_returned": len(gained),
                         "lost": len(lost), "both_unavailable": len(neither)},
        "baseline_same_returned_labels": benchmark.stats([r["baseline_error_px"] for r in common]),
        "candidate_same_returned_labels": benchmark.stats([r["candidate_error_px"] for r in common]),
        "common_improved": sum(r["error_change_px"] < -1e-8 for r in common),
        "common_worsened": sum(r["error_change_px"] > 1e-8 for r in common),
        "common_unchanged": sum(abs(r["error_change_px"]) <= 1e-8 for r in common),
        "newly_returned_errors": benchmark.stats([r["candidate_error_px"] for r in gained]),
        "lost_baseline_errors": benchmark.stats([r["baseline_error_px"] for r in lost]),
        "common_labels": common, "newly_returned_labels": gained,
        "lost_labels": lost, "both_unavailable_labels": neither}


def main():
    output = ROOT / "diagnostics/algorithm-revision/pixel_switch_author_comparison_20261002"
    output.mkdir(parents=True, exist_ok=False)
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    report_path = RUNS / FINAL / "report.json"
    final = json.loads(report_path.read_text())
    assert final["algorithm_sha256"] == EXPECTED
    new = index(final)
    sources = output / "frozen_reports"
    sources.mkdir()
    (sources / f"{FINAL}.json").write_bytes(report_path.read_bytes())
    report = {"recorded_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
        "algorithm_sha256": EXPECTED, "builder_sha256": sha256(Path(__file__)),
        "method": "Match all497author labels by fruit group, object and annotation line; require identical source/target frames, pixel coordinates and split. Separate common-label errors from availability changes. Report every gained/lost/unavailable label and all three fruit groups. No estimator/model is run here.",
        "scope": "Development data repeatedly inspected during algorithm work, not held-out evaluation. Settings and source differ, so this is a profile comparison, not an isolated causal comparison. Publication Table4 used a different label subset; this is not a reproduction or comparison on an identical published subset. Conditional RMS uses only returned predictions; counts over all497labels remain visible.",
        "candidate_report_sha256": sha256(report_path), "candidate_settings": final["settings"],
        "candidate_all_labels_summary": final["summary"]["all"], "comparisons": {}}
    for name in BASELINES:
        path = RUNS / name / "report.json"
        baseline = json.loads(path.read_text())
        assert baseline["source_repositories"] == final["source_repositories"]
        old = index(baseline)
        assert set(old) == set(new)
        (sources / f"{name}.json").write_bytes(path.read_bytes())
        result = compare(old, new)
        result.update(baseline_report=str(path), baseline_report_sha256=sha256(path),
            baseline_algorithm_sha256=baseline["algorithm_sha256"],
            baseline_all_labels_summary=baseline["summary"]["all"],
            settings_changes={k: {"baseline": baseline["settings"].get(k), "candidate": v}
                              for k,v in final["settings"].items() if baseline["settings"].get(k) != v},
            groups={group: compare(old,new,group) for group in sorted({k[0] for k in new})})
        report["comparisons"][name] = result
        print(json.dumps({"baseline": name, "availability": result["availability"],
            "same_labels_baseline": result["baseline_same_returned_labels"],
            "same_labels_candidate": result["candidate_same_returned_labels"],
            "improved_worsened_unchanged": [result[k] for k in ("common_improved","common_worsened","common_unchanged")]}), flush=True)
    returned = [r for r in final["correspondences"] if r["status"] == "ok"]
    worst = max(returned,key=lambda r:r["error_px"])
    report["worst_candidate_prediction"] = worst
    views = benchmark.load_views(benchmark.DATA / "rotation/data" / worst["group"] / worst["object"], 0)
    benchmark.save_correspondence_view(output / "worst_candidate_author_error.png", views, worst,
                                       np.asarray(worst["prediction"]))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for panel, (name,result) in zip(axes,report["comparisons"].items()):
        rows = result["common_labels"]
        panel.scatter([r["baseline_error_px"] for r in rows], [r["candidate_error_px"] for r in rows],
                      s=11,alpha=.55,color="#286b55")
        upper = max(max(r["baseline_error_px"],r["candidate_error_px"]) for r in rows)*1.05
        panel.plot([0,upper],[0,upper],"--",color="#777",label="Equal error")
        panel.set(title=name.replace("_"," "),xlabel="Archived profile error (pixels)",
                  ylabel="Final profile error (pixels)",xlim=(0,upper),ylim=(0,upper))
        panel.grid(alpha=.2)
        panel.legend(fontsize=8)
    fig.suptitle("Author labels returned by both profiles: every paired result")
    fig.savefig(output / "same_label_accuracy.png",dpi=300)
    fig.savefig(output / "same_label_accuracy.pdf")
    plt.close(fig)
    rows=[]
    for name,result in report["comparisons"].items():
        a,b=result["baseline_same_returned_labels"],result["candidate_same_returned_labels"]
        v=result["availability"]
        rows.append(f"| {name} | {v['both_returned']} | {a['rms']:.6f} | {b['rms']:.6f} | {v['newly_returned']} | {v['lost']} | {v['both_unavailable']} | {result['common_improved']} / {result['common_worsened']} / {result['common_unchanged']} |")
    text = ("# Final author profile: same-label comparison\n\n"+report["method"]+"\n\n"+report["scope"]+"\n\n"
        "Final profile predicts457/497labels: conditional RMS5.224579pixels,372labels within5pixels (74.849% of all497). More within5 does not establish a general accuracy improvement.\n\n"
        "| Archived profile | Common returned | Archived RMS (px) | Final RMS (px) | Newly returned | Lost | Both unavailable | Improved / worsened / unchanged |\n"
        "|---|---:|---:|---:|---:|---:|---:|---|\n"+"\n".join(rows)+"\n\n"
        f"Worst final returned error: {worst['error_px']:.6f}pixels, {worst['group']}/{worst['object']}, annotation line{worst['line']}. This result is retained and shown below. JSON includes per-group comparisons, every individual label and all source/settings/report hashes.\n\n"
        "![All common labels](same_label_accuracy.png)\n\n![Worst final author prediction](worst_candidate_author_error.png)\n")
    (output / "SAME_LABEL_COMPARISON.md").write_text(text,encoding="utf-8")
    report["completed_at"] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    write_json(output / "report.json",report)
    write_json(output / "sha256.json",{str(p.relative_to(output)):sha256(p) for p in output.rglob("*") if p.is_file()})
    print(json.dumps({"output":str(output),"worst_error_px":worst["error_px"]}),flush=True)


if __name__ == "__main__":
    main()
