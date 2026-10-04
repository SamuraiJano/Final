"""Compare the frozen 10- and 20-degree short-motion controls without editing scores."""
from pathlib import Path
import hashlib
import json


HERE = Path(__file__).resolve().parent
BASELINE = HERE.parent / "hybrid_motion_controls_20261002"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    prior = json.loads((BASELINE / "report.json").read_text(encoding="utf-8"))
    current = json.loads((HERE / "report.json").read_text(encoding="utf-8"))
    report = {
        "baseline": str(BASELINE),
        "candidate": str(HERE),
        "baseline_report_sha256": digest(BASELINE / "report.json"),
        "candidate_report_sha256": digest(HERE / "report.json"),
        "algorithm_source_unchanged": prior["algorithm_sha256"] == current["algorithm_sha256"],
        "algorithm_sha256": current["algorithm_sha256"],
        "acceptance_limits_unchanged": prior["acceptance"] == current["acceptance"],
        "cases": {},
        "exposure_controls": {},
        "stationary_scoring_note": "Unavailable endpoints are not zero pose error; helper maxima contain only the initial identity pose when all pairs are rejected.",
        "scope": "Two ideal rendered textures, perfect masks, subdegree motion with small transverse wobble, independent pixel noise and unsaturated global brightness offsets. This does not test large transverse wobble, field pose truth, real defects or grade accuracy.",
        "paper_context": "The 2021 paper describes a typical transverse bound of 10 degrees in Section 3.2. The 20-degree bound is a setup adaptation tested here with unchanged rejection limits, rather than a change to the photometric objective or publication accuracy claim.",
        "paper_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/",
    }
    for name, row in current["cases"].items():
        old = prior["cases"][name]
        before, after = old["result"]["settings"], row["result"]["settings"]
        changed = {key: {"before": before[key], "after": after[key]}
                   for key in after if before[key] != after[key]}
        report["cases"][name] = {
            "input_bytes_identical": digest(BASELINE / f"{name}_inputs.npz") == digest(HERE / f"{name}_inputs.npz"),
            "input_sha256": row["input_sha256"],
            "settings_changes": changed,
            "only_transverse_bound_changed": changed == {"transverse_angle_deg": {"before": 10.0, "after": 20.0}},
            "summary_unchanged": old["result"]["summary"] == row["result"]["summary"],
            "control_results_unchanged": old["control_results"] == row["control_results"],
            "baseline_summary": old["result"]["summary"],
            "candidate_summary": row["result"]["summary"],
        }
    for name, row in current["exposure_controls"].items():
        old = prior["exposure_controls"][name]
        report["exposure_controls"][name] = {
            "comparison_unchanged": old["comparison"] == row["comparison"],
            "control_results_unchanged": old["control_results"] == row["control_results"],
        }
    report["comparison_passed"] = (report["algorithm_source_unchanged"]
        and report["acceptance_limits_unchanged"]
        and all(all(row[key] for key in ("input_bytes_identical", "only_transverse_bound_changed", "summary_unchanged", "control_results_unchanged")) for row in report["cases"].values())
        and all(all(row.values()) for row in report["exposure_controls"].values()))
    (HERE / "bound_comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (HERE / "BOUND_COMPARISON.md").write_text(
        "# Transverse search bound comparison\n\n"
        "The exact same source, four frozen image sets and acceptance limits were used at 10 and 20 degrees. "
        "All input hashes match. The transverse bound is the only settings change. "
        "Every control outcome and summary is identical.\n\n"
        "Both moving textures return all ten pairs. Maximum 3D pose errors are 0.221953 and 0.094169 degrees; "
        "maximum projected landmark RMS errors are 0.202319 and 0.085987 pixels. "
        "Both 120-frame stationary textures reject all 119 pairs, producing no propagated endpoint, map or grade. "
        "Those unavailable results do not establish zero stationary pose error. Both brightness-offset controls pass.\n\n"
        "The [2021 paper, Section 3.2](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) describes a typical "
        "10-degree transverse bound. Trying 20 degrees adapts the search region to the setup while retaining "
        "the existing objective and rejection limits. These short-motion controls cover small transverse motion; "
        "they do not validate large transverse wobble, actual conveyor pose or defect grades.\n\n"
        "Machine-readable checks and exact hashes are in [bound_comparison.json](bound_comparison.json).\n",
        encoding="utf-8")
    manifest = {str(path.relative_to(HERE)): digest(path) for path in HERE.rglob("*")
                if path.is_file() and path.name != "sha256.json"}
    (HERE / "sha256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"comparison_passed": report["comparison_passed"], "cases": len(report["cases"]), "algorithm_sha256": report["algorithm_sha256"]}))
    if not report["comparison_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
