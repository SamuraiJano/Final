"""Preserve unadopted matcher trials without declaring a final algorithm validated.

This copies frozen inputs/results and makes figures from recorded measurements.
It does not rerun estimators, models or incomplete video jobs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path
import re
import shutil
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np

from build_algorithm_revision_evidence import read_json, save_json, sha256, table


BACKEND = Path(__file__).resolve().parent
DIAGNOSTICS = BACKEND / "diagnostics"
DEVELOPMENT_COLLECTIONS = (
    "algorithm-revision/camera_shading_inputs_20261002",
    "algorithm-revision/full_turn_x12_wobble_20261002",
    "algorithm-revision/full_turn_refine20_20261002",
    "algorithm-revision/full_turn_x12_refine20_20261002",
    "algorithm-revision/fixed_refine20_conveyor_20261002",
    "authors-benchmark/runs/hybrid_refine20_profile_20261002",
    "authors-benchmark/bridge_runs/hybrid_refine20_retained_20261002",
    "algorithm-revision/native_recheck_author_comparison_20261002",
    "algorithm-revision/lighting_plane_source",
    "algorithm-revision/full_turn_x12_plane_20261002",
    "algorithm-revision/fixed_plane_20261002",
    "algorithm-revision/camera_shading_baseline_20261002",
    "algorithm-revision/camera_shading_plane_20261002",
    "algorithm-revision/aligned_patch_source",
    "algorithm-revision/full_turn_x12_aligned_20261002",
    "algorithm-revision/fixed_aligned_20261002",
    "algorithm-revision/fixed_aligned_bound20_20261002",
    "algorithm-revision/aligned_patch_fast_source",
    "algorithm-revision/full_turn_x12_aligned_fast20_20261002",
    "algorithm-revision/fixed_aligned_fast_bound20_20261002",
    "algorithm-revision/camera_shading_fast_bound20_20261002",
    "authors-benchmark/runs/aligned_fast_author_profile_20261002",
    "algorithm-revision/aligned_contrast_source",
    "algorithm-revision/full_turn_x12_contrast20_20261002",
    "algorithm-revision/fixed_aligned_contrast20_20261002",
    "algorithm-revision/camera_shading_contrast_bound20_20261002",
    "algorithm-revision/aligned_pattern_source",
    "algorithm-revision/aligned_pattern_equivalence_20261002",
    "algorithm-revision/camera_shading_pattern20_20261002",
    "algorithm-revision/fixed_pattern20_conveyor_20261002",
    "algorithm-revision/fresh_texture_pattern20_20261002",
    # Numerical controls are separate from still-running motion/author trials.
    "algorithm-revision/aligned_detrended_pattern_source",
    "algorithm-revision/aligned_detrended_pattern_equivalence_20261002",
)
SHADING = (
    ("Green 951 / native20", "camera_shading_baseline_20261002"),
    ("Additive plane f03", "camera_shading_plane_20261002"),
    ("Aligned fast bf25", "camera_shading_fast_bound20_20261002"),
    ("Aligned contrast d3bf", "camera_shading_contrast_bound20_20261002"),
    ("Aligned full pattern 9a5a", "camera_shading_pattern20_20261002"),
)
ALLOWED = {".json", ".py", ".snapshot", ".md", ".txt", ".csv", ".png", ".pdf", ".npz", ".html"}


def available_collections():
    """Return archived collections only; missing candidates never become passes."""
    return [relative for relative in DEVELOPMENT_COLLECTIONS if (DIAGNOSTICS / relative).is_dir()]


def source_record(folder):
    report_path = folder / "report.json"
    metadata_path = folder / "metadata.json"
    report = read_json(report_path) if report_path.is_file() else {}
    metadata = read_json(metadata_path) if metadata_path.is_file() else {}
    digest = report.get("algorithm_sha256", metadata.get("candidate_sha256"))
    if digest is None and "source_sha256" in report:
        digest = report["source_sha256"].get("adjacent_native.py")
    candidates = [folder / "algorithm_snapshot.py", folder / "sources/adjacent_native.py"]
    snapshot = next((path for path in candidates if path.is_file()), None)
    if digest is not None and snapshot is not None and sha256(snapshot) != digest:
        raise ValueError(f"Frozen source mismatch: {folder.name}")
    return {"algorithm_sha256": digest,
            "snapshot": snapshot.relative_to(DIAGNOSTICS).as_posix() if snapshot else None,
            "source_snapshot_verified": bool(digest and snapshot),
            "report_sha256": sha256(report_path) if report_path.is_file() else None,
            "state": "archived_run" if report else "source_only_not_validation"}


def shading_rows(report, label):
    rows = []
    for name, case in report["cases"].items():
        stats, mapping = case["result"]["summary"], case["result"]["mapping"]
        stationary = case["kind"] == "stationary_120"
        # Stationary reference-scaffold zero maxima are explicitly not accuracy.
        rows.append({"profile": label, "case": name, "kind": case["kind"],
            "returned_pairs": stats["measured_pairs"], "attempted_pairs": stats["input_pairs"],
            "maximum_pose_error_deg": None if stationary else stats["maximum_pose_error_deg"],
            "maximum_landmark_rms_px": None if stationary else stats["maximum_landmark_rms_px"],
            "endpoint_pose_error_deg": None if stationary else stats["endpoint_pose_error_deg"],
            "mapping_status": mapping["status"], "grade": mapping.get("grade"),
            "observed_longitude_deg": mapping.get("observed_longitude_deg"), "passed": case["passed"],
            "accuracy_unavailable": stationary, "checks": case["checks"]})
    return rows


def api_state(folder):
    if not folder.is_dir():
        return {"state": "no_retained_request", "completed_outcome_claimed": False}
    summary_path, interruption_path = folder / "summary.json", folder / "interruption.json"
    summary = read_json(summary_path) if summary_path.is_file() else None
    if summary and summary.get("finished_at"):
        return {"state": "completed_execution", "summary": summary,
                "accuracy_verified": False, "completed_outcome_claimed": True}
    if interruption_path.is_file():
        return {"state": "interrupted_incomplete", "interruption": read_json(interruption_path),
                "completed_outcome_claimed": False}
    return {"state": "incomplete_no_final_report", "completed_outcome_claimed": False,
            "cause": "Not established by the archived records."}


def build(label="development_followup_20261002", refresh=False):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", label):
        raise ValueError("Use a simple evidence label")
    output = DIAGNOSTICS / "algorithm-revision" / label
    if output.exists() and not refresh:
        raise FileExistsError("Use a fresh label or --refresh for this generated supplement")
    output.mkdir(parents=True, exist_ok=True)
    copied, canonical_npz, aliases = [], {}, []

    def copy_file(source, relative):
        destination = output / relative
        digest = sha256(source)
        if source.suffix == ".npz":
            if digest in canonical_npz:
                aliases.append({"original_bundle_path": Path(relative).as_posix(),
                                "stored_once_at": canonical_npz[digest], "sha256": digest})
                return
            canonical_npz[digest] = Path(relative).as_posix()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append({"source": source.relative_to(BACKEND.parent).as_posix(),
                       "bundle_path": destination.relative_to(output).as_posix(), "sha256": digest})

    records = {}
    for relative in available_collections():
        folder = DIAGNOSTICS / relative
        records[relative] = source_record(folder)
        for source in sorted(folder.rglob("*")):
            if source.is_file() and source.suffix in ALLOWED and "__pycache__" not in source.parts:
                copy_file(source, Path(relative) / source.relative_to(folder))
    # Copy request/status evidence, not partially saved grades as a finished report.
    api_folder = DIAGNOSTICS / "api-runs/full_hybrid_wobble_20261002"
    if api_folder.is_dir():
        for source in sorted(api_folder.glob("*")):
            if source.is_file() and source.suffix in ALLOWED:
                copy_file(source, Path("api-runs/full_hybrid_wobble_20261002") / source.name)
    api = api_state(api_folder)
    copy_file(Path(__file__), "source/build_algorithm_development_evidence.py")
    copy_file(DIAGNOSTICS / "authors-benchmark/DEVELOPMENT_LOG.md", "source/DEVELOPMENT_LOG.md")
    copy_file(BACKEND.parent / "README.md", "source/README.md")
    copy_file(DIAGNOSTICS / "authors-benchmark/source_manifest.json", "author_provenance/source_manifest.json")
    for name in ("rotation_LICENSE", "maps_LICENSE"):
        copy_file(DIAGNOSTICS / "authors-benchmark/evidence_20261002/source_licenses" / name,
                  Path("author_provenance") / name)
    for name in ("validate_camera_shading.py", "compare_native_recheck_author_profiles.py",
                 "build_aligned_candidate.py", "validate_algorithm_revision.py"):
        if (BACKEND / name).is_file():
            copy_file(BACKEND / name, Path("source") / name)
    save_json(output / "source_records.json", records)
    save_json(output / "api_run_state.json", api)
    save_json(output / "input_references.json", {"method": "Identical NPZ payloads stored once by SHA256",
        "unique_npz_payloads": len(canonical_npz), "aliases": aliases})

    input_relative = "algorithm-revision/camera_shading_inputs_20261002"
    inputs = read_json(output / input_relative / "inputs.json")
    input_digest = sha256(output / input_relative / "inputs.json")
    reports, all_rows, summary_rows = {}, [], []
    for name, directory in SHADING:
        report = read_json(output / "algorithm-revision" / directory / "report.json")
        if report["input_manifest_sha256"] != input_digest or report["acceptance"] != inputs["acceptance"]:
            raise ValueError("Shading controls changed their frozen inputs or acceptance limits")
        if set(report["cases"]) != set(inputs["cases"]) or not report.get("completed_at"):
            raise ValueError("Incomplete shading suite cannot be counted as complete")
        for case_name, case in report["cases"].items():
            source = DIAGNOSTICS / input_relative / f"{case_name}.npz"
            if case["input_sha256"] != sha256(source) or case["input_sha256"] != inputs["cases"][case_name]["input_sha256"]:
                raise ValueError("Shading scene input SHA256 mismatch")
        reports[name] = report
        rows = shading_rows(report, name); all_rows.extend(rows)
        summary_rows.append([name, f"{sum(row['passed'] for row in rows)}/12",
            sum(row["returned_pairs"] for row in rows if row["kind"] == "stationary_120"),
            sum(not row["passed"] and row["grade"] is not None for row in rows), report["algorithm_sha256"][:12]])
    save_json(output / "shading_comparison.json", {"input_manifest_sha256": input_digest,
        "acceptance": inputs["acceptance"], "stationary_accuracy": "unavailable, never scored zero", "cases": all_rows})

    names = list(inputs["cases"])
    values = np.array([[int(report["cases"][case]["passed"]) for name, report in reports.items()] for case in names])
    fig, ax = plt.subplots(figsize=(13, 9))
    ax.imshow(values, cmap=ListedColormap(["#dfb6aa", "#bfd6bc"]), vmin=0, vmax=1, aspect="auto")
    labels = [name.replace("full_turn_x12_", "360deg /12deg ").replace("short_xy_", "Short x/y ")
              .replace("stationary_120_", "Stationary ").replace("lambertian_multiplicative_", "Lambertian ")
              .replace("linear_additive_", "Linear ").replace("texture_", "texture ") for name in names]
    ax.set(xticks=range(len(reports)), xticklabels=[name.replace(" / ", "\n") for name in reports],
           yticks=range(len(names)), yticklabels=labels)
    for row, case in enumerate(names):
        for column, (name, report) in enumerate(reports.items()):
            result = report["cases"][case]["result"]; stats = result["summary"]
            text = (f"{'PASS' if values[row,column] else 'FAIL'}\n{stats['measured_pairs']}/{stats['input_pairs']} returned"
                    if case.startswith("stationary_") else
                    f"{'PASS' if values[row,column] else 'FAIL'}\n{stats['maximum_pose_error_deg']:.2f}deg / {stats['maximum_landmark_rms_px']:.2f}px")
            ax.text(column, row, text, ha="center", va="center", fontsize=9, color="#26372c")
    ax.tick_params(length=0); ax.set_title(f"Same 12 independently rendered scenes: none of these {len(reports)} profiles passes all controls", pad=18)
    fig.text(.5, .012, "Limits unchanged: full turn 5deg /5px; short chain 1deg /1px; stationary all119 pairs unavailable and no map.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .035, 1, 1)); fig.savefig(output / "camera_shading_comparison.png", dpi=300)
    fig.savefig(output / "camera_shading_comparison.pdf"); plt.close(fig)

    # Actual failing map pixels with recorded errors, exported at report resolution.
    fail_case = "full_turn_x12_lambertian_multiplicative_texture_a"
    columns = [(name, directory) for name, directory in SHADING]
    fig, axes = plt.subplots(len(columns), 2, figsize=(11, 2.75 * len(columns)), gridspec_kw={"width_ratios": [3, 1]})
    figure_records = []
    for index, (name, directory) in enumerate(columns):
        prefix = Path("algorithm-revision") / directory
        surface, observed = [prefix / f"{fail_case}_{suffix}.png" for suffix in ("surface_map", "observed")]
        stats = reports[name]["cases"][fail_case]["result"]["summary"]
        mapping = reports[name]["cases"][fail_case]["result"]["mapping"]
        axes[index, 0].imshow(plt.imread(output / surface)); axes[index, 1].imshow(plt.imread(output / observed))
        axes[index, 0].set_title(f"{name}: actual generated map", loc="left", fontsize=10)
        axes[index, 1].set_title("Observed cells", fontsize=10)
        for ax in axes[index]: ax.axis("off")
        axes[index, 0].text(0, -.1, f"Reported {mapping['grade']}, longitude {mapping['observed_longitude_deg']:.0f}deg; "
            f"known-motion error {stats['maximum_pose_error_deg']:.3f}deg / {stats['maximum_landmark_rms_px']:.3f}px: FAIL",
            transform=axes[index, 0].transAxes, fontsize=9, color="#913b29")
        figure_records.append({"profile": name, "original_surface_image": surface.as_posix(),
            "surface_image_sha256": sha256(output / surface), "original_observed_image": observed.as_posix(),
            "observed_image_sha256": sha256(output / observed), "case": fail_case,
            "grade_is_arithmetic_execution_only": True, "ground_truth_motion_control_passed": False})
    fig.suptitle("Full-looking Class 1 outputs can fail the independently known motion test", fontsize=15)
    fig.tight_layout(rect=(0, .02, 1, .965)); fig.savefig(output / "false_eligible_maps.png", dpi=300)
    fig.savefig(output / "false_eligible_maps.pdf"); plt.close(fig)
    save_json(output / "figure_provenance.json", {"method": "Composite of unchanged archived map/coverage pixels with recorded control errors",
        "images_are_actual_algorithm_outputs": True, "figures": figure_records})

    fixed_labels = ("fixed_refine20_conveyor_20261002", "fixed_plane_20261002", "fixed_aligned_20261002",
                    "fixed_aligned_bound20_20261002", "fixed_aligned_fast_bound20_20261002", "fixed_aligned_contrast20_20261002",
                    "fixed_pattern20_conveyor_20261002")
    fixed_rows = []
    for directory in fixed_labels:
        report = read_json(output / "algorithm-revision" / directory / "report.json")
        for track in report["tracks"]:
            row = next(variant for variant in track["variants"] if variant["name"] == "adjacent_native")
            fixed_rows.append([directory.replace("_20261002", ""), track["track"], len(row["selected_frames"]),
                               f"{row['longitude_deg']:.3f}", row["status"]])
    author_fast = read_json(output / "authors-benchmark/runs/aligned_fast_author_profile_20261002/report.json")
    author_stats = author_fast["summary"]["all"]
    if author_stats["tracks"] != 15 or author_stats["labelled_correspondences"] != 132 or set(author_fast["summary"]) != {"all", "calibration", "evaluation", "mandarins"}:
        raise ValueError("The recorded fast-author trial is expected to contain only the fifteen mandarin sequences")
    native_compare = "algorithm-revision/native_recheck_author_comparison_20261002/NATIVE_RECHECK_COMPARISON.md"
    now = datetime.now(timezone(timedelta(hours=2))).isoformat()
    report = f"""# Continued algorithm tests: development supplement

Built {now}. **No final algorithm is declared operational or accuracy validated by this supplement.**
It preserves later experiments alongside the earlier sealed evidence. The source 951/native8
profile is known to fail horizontal full turns; extending rechecks to 20 improves that
synthetic case but regresses author availability and the fixed real conveyor examples.
Any earlier description of that phase as stable or final is superseded by these failures.
Paper geometry, actual models and historical results remain separate from this control evidence.

## What was tested, and why

1. Freeze inputs, true body rotations, projected landmarks and acceptance limits before estimating motion.
2. Run the actual sphere fit, two-axis matcher, pose propagation, adjacent selector and map fusion.
3. Score prediction availability together with errors. Rejected motion is unavailable, never zero-error.
4. Compare all author labels and common returned labels before adopting a setting.
5. Replay the same real crops/masks across candidates. Such replays check behavior; they have no field pose truth.
6. Preserve each source snapshot, parameters, inputs, measurements and exported images, including failures.

The original horizontal twelve-degree full-turn profile returns all 60 pairs yet
accumulates 11.092/6.189 degrees error and produces Class 1 maps. The native20 profile
passes that ideal full-turn control at 2.063/0.936 degrees, but author predictions
fall 462→416 and retained predictions 368→287. Common-label RMS worsens in both
audits. Fixed real track 98 coverage falls 360→188.390 degrees. This settings-only
trial is not an accepted solution. [Exact unchanged comparison]({native_compare}).

## Fixed-camera illumination: the same twelve independent scenes

Two analytical textures use additive linear lighting and multiplicative Lambertian
lighting, both fixed in camera coordinates. Each has one complete 360-degree turn,
one short known x/y chain and one 120-frame noisy stationary sequence. Perfect
masks and known geometry isolate matching from detection/segmentation. These
are development controls, not held-out real fruit or a full camera simulation.

The input manifest was frozen at {inputs['prepared_at']}, SHA256 `{input_digest}`.
No saturation is introduced. Full turns require all 30 pairs and errors ≤5 degrees/5 pixels.
Short chains require all 10 pairs, endpoint ≤1 degree and maximum landmark RMS ≤1 pixel.
Stationary controls require 119 unavailable pairs, a null endpoint and no map or grade.
These original limits are unchanged for all five profiles.

{table(['Exact source/profile', 'Passing scenes', 'False stationary returns /476pairs', 'Failed scenes that still produce a class', 'Source SHA256 prefix'], summary_rows)}

![All independently rendered scene outcomes](camera_shading_comparison.png)
[300-dpi PDF](camera_shading_comparison.pdf), [exact comparison](shading_comparison.json).

No profile passes all twelve controls. Contrast d3bf passes 11/12, but the Lambertian
texture A complete turn remains incorrect at 8.387 degrees/5.676 pixels while returning
all 30 pairs, 360 degrees observed longitude and Class 1. Plane f03 and fast bf25 also
produce false stationary maps. The stationary helper's reference-scaffold zero
maxima are not estimated zero motion and are not used to claim accuracy.

![Actual maps that pass coverage but fail known motion](false_eligible_maps.png)
[Exportable map comparison](false_eligible_maps.pdf), [image provenance](figure_provenance.json).
These Class 1 outputs use supplied all-clear defect observations to test arithmetic.
They are not predictions from the user's segmentation model or verified fruit grades.

The aligned f4 and fast bf25 variants pass their ideal twelve-degree turns. The frozen
f4 runs have no separate twelve-scene shading suite; the fast bf25 results cannot be
silently assigned to f4. The full nine-sample pattern source 9a5a passes 10/12:
Lambertian texture A fails both the complete turn (7.257 degrees /4.915 pixels)
and short chain (1.114-degree endpoint /1.402-pixel maximum landmark RMS).
It returns no stationary motion in all 476 pairs. Its numerical equivalence
controls pass; numerical invariance is not ground-truth motion accuracy.

An independently rendered fresh texture C was prepared with frozen acceptance
before estimation. Source 9a5a passes both twelve-degree turns under linear and
Lambertian lighting, maximum 0.606/0.581 degrees and 0.411/0.351 pixels. These two
passes remain separate from its texture-A failures. [Fresh-texture record](algorithm-revision/fresh_texture_pattern20_20261002/FRESH_TEXTURE_CONTROL.md).

The detrended nine-sample source 6f2c passes numerical equivalence and local
affine-gradient invariance checks. Its motion, real-crop and author trials are
still being evaluated outside this bounded supplement. Those numerical results
do not establish reconstruction accuracy or production adoption.

## Same real crops, selected development cases

{table(['Frozen trial', 'Track', 'Retained views', 'Observed longitude, deg', 'Status'], fixed_rows)}

The four tracks contain 215 original detector/tracker crops and extracted fruit masks.
No detector, tracker, GrabCut or defect-model call is repeated in these geometric
replays. A 360-degree map with missing_defect_masks receives no grade. A larger
connected segment does not establish accurate poses. No independently labelled
field rotation, surface map or grade truth is available for these cases.

## Author-data scope must stay explicit

The native20 comparison includes all 36 author sequences and 497 labels. The fast bf25
trial includes **only 15 mandarin sequences and 132 labels**. It returns
{author_stats['predicted_correspondences']}/132 at conditional RMS
{author_stats['errors_px_conditional_on_prediction']['rms']:.5f} pixels, with
{author_stats['errors_px_conditional_on_prediction']['within_5px']}/132 within 5 pixels.
The 39.55996-pixel error remains included. This is not an all-36-sequence benchmark;
no orange/tomato outcome is claimed for bf25. Source/profile differences prevent
using these partial author results as contrast d3bf or pattern 9a5a validation.
All development images have been inspected and are not held-out evaluation.

## Original video and incomplete API execution

Archived full_hybrid_wobble_20261002 state: **{api['state']}**.
No completed video outcome is claimed unless its completed summary and saved
execution snapshots exist. Saved frame counts or individual track results are not
a final report. The service was absent when work resumed after the credit interruption;
this supplement does not infer a cause. [Archived API state](api_run_state.json).
Recovery and any resumed/replayed job must be recorded under its own provenance.

## Report evidence and reproduction

Every copied payload has a SHA256 manifest. The 12 scene input NPZ files, original
renderers, frozen candidate sources, actual map PNGs, 300-dpi charts/PDFs, author
point overlays, unchanged reports and parameter records are retained. Duplicate
NPZ files are stored once by SHA256; [input_references.json](input_references.json)
resolves historical aliases. Original model checkpoints and full datasets are not
duplicated. [Frozen source records](source_records.json) identify every trial.

```powershell
./backend/venv/Scripts/python.exe -B backend/build_algorithm_development_evidence.py --label {label} --refresh
```

This script copies evidence; it does not rerun inference. Individual frozen scripts
and their recorded commands supply reproduction. This package documents both
successful controls and failed hypotheses. It is a development supplement rather
than a certificate of real conveyor grading accuracy.
"""
    (output / "DEVELOPMENT_TEST_REPORT.md").write_text(report, encoding="utf-8")
    figure_links = ["camera_shading_comparison.png", "false_eligible_maps.png", f"{input_relative}/rendered_inputs.png"]
    cards = "".join(f'<figure><img src="{item}" alt="Recorded algorithm development evidence"><figcaption>{html.escape(item)}</figcaption></figure>' for item in figure_links)
    gallery = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Naartjie: continued algorithm tests</title><style>body{{background:#f3f5f1;color:#23342a;font:17px/1.55 system-ui;margin:0}}main{{max-width:1150px;margin:auto;padding:28px}}a{{color:#225f41}}.status{{padding:18px;background:#f2ddd5;border-radius:8px}}img{{max-width:100%;height:auto}}figure{{background:white;padding:18px;border:1px solid #d4ddd3;margin:24px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 ui-monospace,monospace}}</style>
<main><h1>Continued algorithm testing: failures preserved</h1><p class="status">No final source is declared validated here.
The twelve-degree native8 control fails. No tested illumination profile passes all twelve scenes.
Coverage and a Class 1 output can coexist with incorrect motion. API state: {html.escape(api['state'])}.</p>
<p><a href="DEVELOPMENT_TEST_REPORT.md">Testing process and scope</a> · <a href="source_records.json">Frozen sources</a> · <a href="SHA256SUMS.txt">SHA256 manifest</a></p>
{cards}<h2>Complete development record</h2><pre>{html.escape(report)}</pre></main></html>'''
    (output / "index.html").write_text(gallery, encoding="utf-8")
    save_json(output / "bundle_summary.json", {"built_at": now, "status": "development_supplement_no_final_validation",
        "primary_source_declared": False, "field_motion_accuracy_verified": False, "grade_accuracy_verified": False,
        "api_state": api['state'], "api_completed_outcome_claimed": api['completed_outcome_claimed'],
        "shading_scenes": 12, "shading_profiles": len(reports), "any_all_shading_controls_pass": any(r['all_controls_passed'] for r in reports.values()),
        "author_fast_scope": {"sequences": 15, "fruit_group": "mandarins", "labels": 132},
        "unique_npz_payloads": len(canonical_npz), "duplicate_npz_aliases": len(aliases), "collections": list(records), "copied_sources": copied})
    links = re.findall(r'(?:href|src)="([^"]+)"', gallery) + re.findall(r'\]\(([^)]+)\)', report)
    local = [link for link in links if not link.startswith(("http:", "https:", "#"))]
    manifest = output / "SHA256SUMS.txt"; manifest.touch(exist_ok=True)
    missing = [link for link in local if not (output / html.unescape(link)).is_file()]
    if missing: raise FileNotFoundError(f"Generated evidence links missing: {missing}")
    save_json(output / "evidence_qa.json", {"generated_local_links_checked": len(local), "missing_links": [],
        "frozen_shading_inputs_and_acceptance_verified": True, "source_snapshots_checked_when_available": True,
        "no_unavailable_stationary_accuracy_scored_zero": True})
    files = sorted(path for path in output.rglob("*") if path.is_file() and path != manifest)
    manifest.write_text("".join(f"{sha256(path)}  {path.relative_to(output).as_posix()}\n" for path in files), encoding="utf-8")
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(output.rglob("*")):
            if path.is_file(): package.write(path, Path(output.name) / path.relative_to(output))
    with zipfile.ZipFile(archive) as package:
        if package.testzip(): raise ValueError("Archive failed CRC validation")
        entries = len(package.infolist())
    metadata = {"archive": archive.name, "sha256": sha256(archive), "entries": entries,
                "bytes": archive.stat().st_size, "crc_verified": True, "final_source_validated": False}
    save_json(archive.with_suffix(".zip.json"), metadata)
    print(json.dumps(metadata, indent=2)); return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="development_followup_20261002")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(); build(args.label, args.refresh)


if __name__ == "__main__": main()
