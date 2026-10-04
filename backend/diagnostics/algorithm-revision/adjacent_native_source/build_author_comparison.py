"""Draw measured author-label availability and coverage; no grade accuracy claim."""
from pathlib import Path
import json
import os

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[3]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT / "backend/diagnostics/plot-cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    diagnostic = PROJECT / "backend/diagnostics"
    baseline = json.loads((diagnostic / "authors-benchmark/runs/operational_profile_v1/report.json").read_text())
    revised = json.loads((diagnostic / "authors-benchmark/runs/adjacent_native_profile_20261002/report.json").read_text())
    old_retained = json.loads((diagnostic / "algorithm-audit/decision_20261002/author_bridge_baseline/report.json").read_text())
    new_retained = json.loads((diagnostic / "authors-benchmark/bridge_runs/adjacent_native_retained_20261002/report.json").read_text())
    figure, axes = plt.subplots(1,3,figsize=(12,5),layout="constrained")
    colors = ["#29764b","#cc963a","#b9c1c6"]
    for ax, title, values in [
        (axes[0],"Independent adjacent labels",[baseline["summary"]["all"],revised["summary"]["all"]]),
        (axes[1],"Labels on retained map poses",[old_retained["summary"]["original_published_labels"],
                                               new_retained["summary"]["original_published_labels"]])]:
        correct = [v["errors_px_conditional_on_prediction"]["within_5px"] for v in values]
        returned = [v["errors_px_conditional_on_prediction"]["count"] for v in values]
        bottom = [0,0]
        for label, counts, color in zip(["Within 5 px","Returned above 5 px","Unavailable"],
                                        [correct,[r-c for r,c in zip(returned,correct)],
                                         [497-r for r in returned]],colors):
            ax.bar([0,1],counts,bottom=bottom,color=color,label=label,width=.56)
            for i,(count,base) in enumerate(zip(counts,bottom)):
                if count:
                    ax.text(i,base+count/2,str(count),ha="center",va="center",fontsize=10)
            bottom = [b+c for b,c in zip(bottom,counts)]
        ax.set_title(title,fontsize=11)
        ax.set_xticks([0,1],["Baseline","Revised"])
        ax.set_ylim(0,530)
        ax.set_ylabel("Author correspondences (497 total)")
        ax.spines[["top","right"]].set_visible(False)
    axes[0].legend(loc="upper center",bbox_to_anchor=(.5,-.09),fontsize=8,frameon=False)
    status = []
    for report in [baseline,revised]:
        produced = [t["map"] for t in report["tracks"] if t["map"]["status"] == "produced"]
        eligible = sum(m["result_status"] == "missing_defect_masks" for m in produced)
        status.append([eligible,len(produced)-eligible,36-len(produced)])
    bottom = [0,0]
    for j,(label,color) in enumerate(zip(["Coverage eligible; no defect truth","Partial map","Mapping failed"],colors)):
        counts = [v[j] for v in status]
        axes[2].bar([0,1],counts,bottom=bottom,color=color,label=label,width=.56)
        for i,(count,base) in enumerate(zip(counts,bottom)):
            if count:
                axes[2].text(i,base+count/2,str(count),ha="center",va="center",fontsize=10)
        bottom = [b+c for b,c in zip(bottom,counts)]
    axes[2].set(title="Map availability and coverage",ylabel="Author sequences (36 total)",ylim=(0,38))
    axes[2].set_xticks([0,1],["Baseline","Revised"])
    axes[2].spines[["top","right"]].set_visible(False)
    axes[2].legend(loc="upper center",bbox_to_anchor=(.5,-.09),fontsize=8,frameon=False)
    figure.suptitle("Conservative adjacent-motion revision: accuracy and availability remain separate\n"
                    "578 author images; development evidence, not held-out evaluation or grade accuracy",fontsize=13)
    figure.savefig(HERE / "author_accuracy_availability.png",dpi=300)
    figure.savefig(HERE / "author_accuracy_availability.pdf")


if __name__ == "__main__":
    main()
