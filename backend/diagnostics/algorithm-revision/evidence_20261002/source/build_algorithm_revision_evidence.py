"""Build a reviewable evidence pack from explicitly named, frozen test runs.

This script copies results; it never reruns inference or changes saved analyses.
Use --refresh after the ongoing full API run finishes to update the report/ZIP.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import zipfile


BACKEND = Path(__file__).resolve().parent
DIAGNOSTICS = BACKEND / "diagnostics"
EXPECTED_ALGORITHM = "52c13a0452875653fb054053fcc0bdbb4a6ed9cb4227c697be32b62fbe811327"
ALLOWED = {".json", ".py", ".snapshot", ".md", ".txt", ".csv", ".png", ".pdf", ".npz"}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join(["---"] * len(headers)) + " |",
                      *["| " + " | ".join(map(str, row)) + " |" for row in rows]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="evidence_20261002")
    parser.add_argument("--refresh", action="store_true", help="Refresh the generated pack from its frozen inputs")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        raise ValueError("Use a simple folder label")
    output = DIAGNOSTICS / "algorithm-revision" / args.label
    if output.exists() and not args.refresh:
        raise FileExistsError("Pack already exists; use --refresh to rebuild its generated report and ZIP")
    output.mkdir(parents=True, exist_ok=True)

    copied, canonical_npz, input_aliases = [], {}, []

    def copy_file(source: Path, relative: Path | str):
        relative = Path(relative)
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = output / relative
        if source.suffix == ".npz":
            digest = sha256(source)
            if digest in canonical_npz:
                input_aliases.append({"original_bundle_path": relative.as_posix(),
                                      "stored_once_at": canonical_npz[digest], "sha256": digest})
                return
            canonical_npz[digest] = relative.as_posix()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append({"source": str(source.relative_to(BACKEND.parent)),
                       "bundle_path": relative.as_posix(), "sha256": sha256(destination)})

    def copy_collection(relative: str, exclusions=()):
        folder = DIAGNOSTICS / relative
        if not folder.is_dir():
            raise FileNotFoundError(folder)
        for source in sorted(folder.rglob("*")):
            if (source.is_file() and source.suffix in ALLOWED and
                    source.name not in exclusions and "__pycache__" not in source.parts):
                copy_file(source, Path(relative) / source.relative_to(folder))

    # Final inputs come first, so duplicate rejected-run NPZ files reference them.
    collections = [
        "algorithm-revision/fixed_scaled_conveyor_20261002",
        "algorithm-revision/motion_resolution_scaled_20261002",
        "algorithm-revision/adjacent_scaled_source",
        "algorithm-revision/real_segmenter_scaled_20261002",
        "authors-benchmark/runs/adjacent_scaled_profile_20261002",
        "authors-benchmark/bridge_runs/adjacent_scaled_retained_20261002",
        "authors-benchmark/synthetic_runs/adjacent_scaled_20261002",
        "algorithm-revision/motion_resolution_20261002",
        "algorithm-revision/native_all_20261002",
        "software-checks/adjacent_scaled_20261002",
    ]
    for relative in collections:
        copy_collection(relative)
    extended_path = DIAGNOSTICS / "algorithm-revision/extended_motion_controls_20261002/report.json"
    extended = read_json(extended_path) if extended_path.is_file() else None
    if extended is not None:
        copy_collection("algorithm-revision/extended_motion_controls_20261002")
    for relative in ["algorithm-revision/resolution_preprocess_trials_20261002.json",
                     "authors-benchmark/runs/operational_profile_v1/report.json",
                     "algorithm-audit/decision_20261002/author_bridge_baseline/report.json",
                     "authors-benchmark/source_manifest.json"]:
        copy_file(DIAGNOSTICS / relative, relative)
    for name in ("rotation_LICENSE", "maps_LICENSE"):
        copy_file(DIAGNOSTICS / "authors-benchmark/evidence_20261002/source_licenses" / name,
                  Path("author_provenance") / name)
    # These source files are supplementary workspace snapshots; execution source
    # is identified by the per-run snapshots and checked hashes below.
    for name in ["ALGORITHM_EXPLAINED.md", "benchmark_authors.py", "validate_author_bridges.py",
                 "validate_motion_resolution.py", "validate_algorithm_revision.py",
                 "validate_model_mapping_integration.py", "validate_synthetic_mapping.py",
                 "validate_software_checks.py", "build_algorithm_revision_evidence.py"]:
        copy_file(BACKEND / name, Path("source") / name)
    for source in sorted(BACKEND.glob("test_*.py")):
        copy_file(source, Path("source") / source.name)

    api_folder = DIAGNOSTICS / "api-runs/full_revised_20261002"
    api = None
    summary_path = api_folder / "summary.json"
    if summary_path.is_file():
        candidate_summary = read_json(summary_path)
        if candidate_summary.get("finished_at"):
            api = candidate_summary
            copy_collection("api-runs/full_revised_20261002")
            # Preserve actual run source/metrics and a small set of useful views.
            job = BACKEND / "results" / str(api["job_id"])
            if job.resolve().parent != (BACKEND / "results").resolve():
                raise ValueError("Invalid API job identifier")
            for filename in ("metrics.json", "algorithm.py.snapshot", "main.py.snapshot", "dfine_segmenter.py.snapshot"):
                if (job / filename).is_file():
                    copy_file(job / filename, Path("full_api_examples") / filename)
            results = []
            for path in job.glob("*/result.json"):
                row = read_json(path)
                results.append((float(row.get("observed_longitude_deg") or 0), path, row))
            for _, path, row in sorted(results, key=lambda item: item[0], reverse=True)[:4]:
                destination = Path("full_api_examples") / path.parent.name
                copy_file(path, destination / path.name)
                for image in path.parent.glob("*.png"):
                    copy_file(image, destination / image.name)

    author = read_json(output / "authors-benchmark/runs/adjacent_scaled_profile_20261002/report.json")
    baseline = read_json(output / "authors-benchmark/runs/operational_profile_v1/report.json")
    retained = read_json(output / "authors-benchmark/bridge_runs/adjacent_scaled_retained_20261002/report.json")
    chains = read_json(output / "algorithm-revision/adjacent_scaled_source/fixed_chain_report.json")
    motion = read_json(output / "algorithm-revision/motion_resolution_scaled_20261002/report.json")
    rejected_motion = read_json(output / "algorithm-revision/motion_resolution_20261002/report.json")
    conveyor = read_json(output / "algorithm-revision/fixed_scaled_conveyor_20261002/report.json")
    integration = read_json(output / "algorithm-revision/real_segmenter_scaled_20261002/report.json")
    synthetic = read_json(output / "authors-benchmark/synthetic_runs/adjacent_scaled_20261002/report.json")
    software = read_json(output / "software-checks/adjacent_scaled_20261002/summary.json")
    for name, report in [("author", author), ("motion", motion), ("integration", integration), ("synthetic", synthetic)]:
        if report["algorithm_sha256"] != EXPECTED_ALGORITHM:
            raise ValueError(f"{name} did not test the final algorithm source")
    if software["source_sha256"]["backend/algorithm.py"] != EXPECTED_ALGORITHM:
        raise ValueError("Software checks did not test the final source")
    if sha256(output / "algorithm-revision/adjacent_scaled_source/algorithm_snapshot.py") != EXPECTED_ALGORITHM:
        raise ValueError("Final source snapshot mismatch")
    tests_log = (output / "software-checks/adjacent_scaled_20261002/python_tests.txt").read_text(encoding="utf-8")
    test_count = int(re.search(r"Ran (\d+) tests", tests_log).group(1))
    if any(row["exit_code"] != 0 for row in software["checks"]):
        raise ValueError("A required software check failed")

    a0, a1 = baseline["summary"]["all"], author["summary"]["all"]
    selected = retained["summary"]["original_published_labels"]
    map_status = Counter(t["map"].get("result_status", "mapping_failed") for t in author["tracks"])
    variable = motion["cases"]["variable_small_motion"]["variants"]["adaptive_d4_to_d1"]["summary"]
    failed_variable = rejected_motion["cases"]["variable_small_motion"]["variants"]["adaptive_d4_to_d1"]["summary"]
    track_rows = []
    for track in conveyor["tracks"]:
        variant = next(v for v in track["variants"] if v["name"] == "adjacent_native")
        frames = variant["selected_frames"]
        track_rows.append([track["track"], track["input_count"], len(frames),
                           f"{frames[0]}–{frames[-1]}", f"{variant['longitude_deg']:.2f}", variant["status"]])
    area_rows = [[f"{row['expected_pct_of_observed']:.0f}%", f"{row['measured_pct_of_observed']:.5f}%",
                  f"{row['absolute_error_percentage_points']:.5f}", row["grade"]] for row in synthetic["cases"]]
    extended_rows = []
    if extended is not None:
        if extended["algorithm_sha256"] != EXPECTED_ALGORITHM:
            raise ValueError("Extended controls did not test this candidate source")
        for name, case in extended["cases"].items():
            result = case["variants"]["adaptive_d4_to_d1"]
            stats = result["summary"]
            controls = extended["control_results"][name]
            extended_rows.append([name, stats["frames"], f"{stats['endpoint_pose_error_deg']:.3f}",
                                  f"{stats['endpoint_landmark_rms_px']:.3f}",
                                  "pass" if controls["endpoint_pose_within_1deg"] and controls["all_landmark_rms_within_1px"] else "FAIL"])
    accuracy_failure = extended is not None and not extended["all_controls_passed"]
    candidate_status = ("**Development candidate: extended stationary-motion accuracy FAILED.** "
                        "A further motion correction is being investigated. The absence of a grade in "
                        "these stationary examples does not make their motion estimates accurate." if accuracy_failure else
                        "Development candidate; general conveyor accuracy has not been established.")
    extended_text = (f"""### Extended moving and stationary controls

Two independently rendered textures test known noncommuting x/y wobble. Two
additional 120-frame scenes are truly stationary with independent pixel noise.
Their complete measured chains are scored against exact pose and six landmarks;
their shorter selected partial-map spans are a separate output.

{table(['Known scene', 'Frames', 'Endpoint pose error, deg', 'Endpoint landmark RMS, px', 'Accuracy controls'], extended_rows)}

The moving controls pass, but both extended stationary controls fail accuracy.
The candidate returns spurious motion even though neither selected map receives
a grade or full longitude. In particular, a roughly eight-degree-looking rotation
or a protective Review result cannot certify geometric accuracy. These failures
mean this source must remain a development candidate. An isolated preprocessing
correction is under investigation; it is not included as a tested fix here.

![Extended pose and landmark accuracy](algorithm-revision/extended_motion_controls_20261002/extended_motion_accuracy.png)
[Full extended test record](algorithm-revision/extended_motion_controls_20261002/EXTENDED_CONTROLS.md).

""" if extended is not None else
                     "Extended independent moving/stationary controls are not yet included in this build.\n\n")
    api_text = (f"The complete revised API run finished at {api['finished_at']}. It produced "
                f"{api['fruits']} tracked report records: statuses `{json.dumps(api['statuses'])}`; "
                f"grades `{json.dumps(api['grades'])}`. These are pipeline outcomes, not verified unique-fruit "
                "or grading accuracy. The run request, response, summary, sources and selected image evidence "
                "are retained in this pack." if api else
                "The complete revised API run is still pending at this report's build time. This draft "
                "contains the completed fixed-input and real-segmenter integration tests, but does not "
                "claim a completed revised full-video run. Rebuild with `--refresh` after its summary finishes.")
    report = f"""# Algorithm revision: testing and evidence

Built {datetime.now(timezone(timedelta(hours=2))).isoformat()}.
Status: **{'completed full API run included' if api else 'draft; revised full API run pending'}**.

{candidate_status}

The algorithm now measures consecutive usable frames, checks small successful
matches at original resolution, and checks the exact fruit-fixed longitude
trajectory before combining views. Failed, missing or unobservable motion ends a
connected sequence. The spheroid model, MAD search, rotation-matrix propagation,
surface projection and area calculation remain based on the research papers.
See [the simple explanation](source/ALGORITHM_EXPLAINED.md).

Tested development-candidate algorithm SHA256: `{EXPECTED_ALGORITHM}`.
This identifies the retained execution source; later source edits are not covered
by these results. The user's detection and segmentation weights are unchanged.

## 1. Author images and published feature labels

All 578 original images in 36 sequences (15 mandarins, 10 oranges, 11 tomatoes)
and all 497 published correspondences were used. Labels score predictions; they
do not fit motion. The masks are derived from the black backgrounds. These data
were inspected during development and are not held-out evaluation.

{table(['Indicator', 'Previous operational algorithm', 'Final revision'], [
 ['Independent returned predictions / labels', f"{a0['predicted_correspondences']}/497", f"{a1['predicted_correspondences']}/497"],
 ['Independent RMS, px', f"{a0['errors_px_conditional_on_prediction']['rms']:.5f}", f"{a1['errors_px_conditional_on_prediction']['rms']:.5f}"],
 ['Within 5 px / all labels', f"{a0['errors_px_conditional_on_prediction']['within_5px']}/497", f"{a1['errors_px_conditional_on_prediction']['within_5px']}/497"],
 ['Maps produced, including partial', a0['maps_produced'], a1['maps_produced']],
 ['Maps passing coverage gates; author defect truth absent', 17, map_status['missing_defect_masks']],
 ['Partial maps / mapping failures', '17 / 2', f"{map_status['insufficient_longitude_coverage']} / {map_status['mapping_failed']}"]])}

Both algorithms return predictions for the same 458 labels. Five predictions
change and improve on these development labels; the overall accuracy difference
is small. Maximum returned error remains 35.93046 px. Labels measurable on
retained map poses increase 305→{selected['returned_predictions']}/497; revised
conditional RMS is {selected['errors_px_conditional_on_prediction']['rms']:.5f} px,
on a different retained subset. Coverage eligibility is not measured grade accuracy.

The selector creates {retained['summary']['nonadjacent_selected_bridges']}
nonadjacent bridges. The SAME four historically bad exact label chains are checked:
{chains['unavailable_chains']} are excluded and {chains['predicted_chains']} return a
prediction. Their exclusion demonstrates removal of those connections, rather
than accurate reconstruction of the excluded surface. Chained labels are
correlated with original annotations.

![Author error and availability counts](algorithm-revision/adjacent_scaled_source/author_accuracy_availability.png)

[Author detail](algorithm-revision/adjacent_scaled_source/AUTHOR_RESULTS.md) ·
[All original label predictions](authors-benchmark/runs/adjacent_scaled_profile_20261002/report.json) ·
[Retained-pose audit](authors-benchmark/bridge_runs/adjacent_scaled_retained_20261002/report.json).

## 2. Known motion and independently rendered landmarks

An analytical radius-55 sphere is rendered at eleven known orientations spanning
0–8 degrees, with ten variable increments (0.5–1.5 degrees). Six front-facing
body landmarks have independently computed target image coordinates. The actual
matcher and fitted sphere estimate motion; failed chains are not interpolated.
All {variable['measured_pairs']}/{variable['input_pairs']} transitions are measured.
Final three-dimensional pose error is {variable['final_pose_error_deg']:.3f} degrees,
endpoint landmark RMS is {variable['final_landmark_rms_px']:.3f} px, and maximum
landmark RMS over the chain is {variable['max_landmark_rms_px']:.3f} px. All controls
in this initial short-motion suite pass. Its stationary noise does not produce a grade or full
longitude; uniform untextured inputs supply no measured motion.

The earlier native-resolution candidate used sigma 1.25 at full image size and
failed: pose error {failed_variable['final_pose_error_deg']:.3f} degrees, endpoint
landmark RMS {failed_variable['final_landmark_rms_px']:.3f} px. The final recheck
preserves physical filter width: sigma 1.25 in a quarter-size image becomes sigma
5 at original size. That rejected candidate and preprocessing trials are retained.
These synthetic controls do not validate complete real-fruit motion or final grades.

![Known motion and landmark errors](algorithm-revision/motion_resolution_scaled_20261002/motion_and_landmark_accuracy.png)
![Analytical versus estimated landmarks](algorithm-revision/motion_resolution_scaled_20261002/endpoint_landmark_comparison.png)

{extended_text}
## 3. Hold the real conveyor images and masks fixed

Four selected tracks from the exact original clip are replayed with identical
frozen crops and masks for every variant. There are {sum(t['input_count'] for t in conveyor['tracks'])}
complete input views. Detection, tracking, GrabCut and defect inference are not
rerun in this geometry comparison. These are development examples, not a random
or held-out conveyor sample, and they have no independent motion truth.

{table(['Track', 'Complete input views', 'Retained views', 'Original frames', 'Observed longitude, deg', 'Result'], track_rows)}

All four remain below the 350-degree longitude gate. Track 491 changes from a
late ordering failure to an ordered partial map. Its reference frame changes
when the connected segment changes; this does not prove that the formerly
backwards transition is physically correct. More coverage or an ordered map is
not a substitute for independently marked conveyor landmarks and a verified turn.
An all-native-resolution candidate was also tested and rejected for short,
fragmented retained segments; its results are included.

![Fixed actual conveyor inputs](algorithm-revision/fixed_scaled_conveyor_20261002/fixed_input_comparison.png)

## 4. Defect area arithmetic and real model integration

Known 5%, 15% and 30% longitude-wedge defects are projected using exact geometry
and known rotations. The motion estimator and neural models are deliberately
bypassed in this control. It tests repeated-defect union, area normalization and
the configured class arithmetic, rather than real defect-model accuracy.

{table(['Known observed defect area', 'Measured', 'Absolute percentage-point error', 'Configured class'], area_rows)}

All area and coverage controls pass. Known 375- and 270-degree turns support full
observed longitude; the 250- and 100-degree controls remain partial. The 10%/20%
class thresholds are local engineering rules, not author-validated conveyor grades.

The separate real D-FINE segmentation integration receives the same four frozen
conveyor inputs. It executes {integration['segmentation']['calls']} real model
calls and returns {integration['segmentation']['instances']} defect instances.
Masks, overlays, surface maps and diagnostics are saved. All four maps remain
partial and receive no grade. This confirms execution and report integration;
there is no defect-mask or grade truth to score accuracy. Model certainty is
not measured accuracy. Model checkpoints are identified by SHA256 below and are
not copied into the archive.

## 5. Software checks and revised full-video execution

All {test_count} Python tests, frontend build and frontend lint pass. Their actual
commands, timestamps, output and execution-source hashes are retained in
[software-checks/adjacent_scaled_20261002](software-checks/adjacent_scaled_20261002/summary.json).
Tests verify implementation behavior; they do not replace image-label accuracy tests.

{api_text}

## Files, provenance and reproduce

The gallery contains real author/conveyor images, analytical controls, and
exportable 300-dpi PNG/PDF figures. The archive retains all result JSON, frozen
source, software output, model hashes and original annotation provenance.
Real NPZ inputs are stored once; duplicate historical inputs are resolved by
[input_references.json](input_references.json), with SHA256 equality checked.
The complete original author datasets and video are not duplicated; their source
manifest and input/run hashes identify them. The original video is
`WIN_20260818_13_29_43_Pro.mp4`, SHA256
`dc25964bf6052972cad761b0246f79906e768c6737bf4228ba44711d7272429c`.

The research basis remains the [2021 rotation paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 surface-map paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
This is an independent implementation; public author repositories provide data
and annotations rather than the reconstruction source used here.

From the original workspace, build from the frozen runs without rerunning models:

```powershell
./backend/venv/Scripts/python.exe -B backend/build_algorithm_revision_evidence.py --label {args.label} --refresh
```

The per-run validation scripts and settings provide the individual reproductions.
Each new test run must use a fresh label. [SHA256SUMS.txt](SHA256SUMS.txt) covers the
bundle payload; [bundle_summary.json](bundle_summary.json) identifies the sources
and scope. The report preserves failed candidates and explicitly separates known
synthetic answers, author feature-label accuracy, unlabelled conveyor coverage,
model execution, and software checks.
"""
    (output / "VALIDATION_REPORT.md").write_text(report, encoding="utf-8")
    save_json(output / "input_references.json", {"method": "Identical NPZ payloads stored once by SHA256",
                                                "unique_npz_payloads": len(canonical_npz), "aliases": input_aliases})
    save_json(output / "model_sha256.json", integration["model_sha256"])
    summary = {"built_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
               "algorithm_sha256": EXPECTED_ALGORITHM, "full_api_completed": api is not None,
               "extended_controls_included": extended is not None,
               "extended_accuracy_failed": accuracy_failure,
               "python_tests": test_count, "unique_npz_payloads": len(canonical_npz),
               "duplicate_npz_aliases": len(input_aliases), "model_sha256": integration["model_sha256"],
               "copied_sources": copied}
    save_json(output / "bundle_summary.json", summary)

    figures = [
        ("Author labels and availability", "algorithm-revision/adjacent_scaled_source/author_accuracy_availability.png"),
        ("Known rendered input scenes", "algorithm-revision/motion_resolution_scaled_20261002/rendered_control_inputs.png"),
        ("Known motion and landmark errors", "algorithm-revision/motion_resolution_scaled_20261002/motion_and_landmark_accuracy.png"),
        ("Independent endpoint landmarks", "algorithm-revision/motion_resolution_scaled_20261002/endpoint_landmark_comparison.png"),
        ("Actual conveyor: fixed-input comparison", "algorithm-revision/fixed_scaled_conveyor_20261002/fixed_input_comparison.png"),
        ("Rejected native sigma 1.25: landmark error", "algorithm-revision/motion_resolution_20261002/endpoint_landmark_comparison.png"),
        ("Rejected all-native: partial map comparison", "algorithm-revision/native_all_20261002/fixed_input_comparison.png"),
    ]
    if extended is not None:
        figures.insert(4, ("Extended stationary accuracy failure", "algorithm-revision/extended_motion_controls_20261002/extended_motion_accuracy.png"))
        figures.insert(5, ("Extended true-versus-predicted landmarks", "algorithm-revision/extended_motion_controls_20261002/extended_landmark_comparison.png"))
    cards = []
    for title, relative in figures:
        pdf = str(Path(relative).with_suffix(".pdf"))
        cards.append(f'<figure><a href="{html.escape(relative)}"><img src="{html.escape(relative)}" alt="{html.escape(title)}"></a>'
                     f'<figcaption>{html.escape(title)} · <a href="{html.escape(pdf)}">PDF</a></figcaption></figure>')
    for track in integration["tracks"]:
        frame = track["result"]["view_evidence"][0]["frame"]
        prefix = f"algorithm-revision/real_segmenter_scaled_20261002/{track['track']}"
        cards.append(f'<figure><img src="{prefix}/frame_{frame:05d}_overlay.png" alt="Actual segmentation overlay on track {track["track"]}">'
                     f'<figcaption>Real defect model: track {track["track"]}, frame {frame}; partial map, no grade.</figcaption></figure>')
    point_images = sorted((output / "authors-benchmark/runs/adjacent_scaled_profile_20261002").glob("*/*/point_*.png"))
    for path in point_images[::max(1,len(point_images)//6)][:6]:
        relative = path.relative_to(output).as_posix()
        cards.append(f'<figure><img src="{relative}" alt="Actual author correspondence scoring">'
                     '<figcaption>Actual author image: green annotation and red predicted feature.</figcaption></figure>')
    gallery = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Naartjie algorithm validation evidence</title><style>
body{{margin:0;background:#f4f5f2;color:#20332a;font:17px/1.55 system-ui,sans-serif}}main{{max-width:1150px;margin:auto;padding:28px}}
h1{{font-size:32px;line-height:1.15}}a{{color:#226648}}.status{{background:#e3ecd8;padding:14px 18px;border-radius:8px}}
figure{{margin:26px 0;background:white;padding:18px;border:1px solid #d9dfd6;border-radius:8px}}img{{max-width:100%;display:block;height:auto;margin:auto}}
figcaption{{margin-top:12px}}.links{{display:flex;gap:18px;flex-wrap:wrap}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.65 ui-monospace,monospace;background:white;padding:20px;border:1px solid #d9dfd6}}
</style><main><h1>Naartjie algorithm: tests and image evidence</h1>
<p class="status">{'Complete revised API run included.' if api else 'Draft: the revised full API run is still pending.'}
{'Extended stationary accuracy FAILED; this source is a development candidate.' if accuracy_failure else 'General conveyor accuracy remains unverified.'}
All four frozen conveyor cases remain partial. Coverage and model certainty are not accuracy.</p>
<p class="links"><a href="VALIDATION_REPORT.md">Testing report</a><a href="source/ALGORITHM_EXPLAINED.md">Simple algorithm explanation</a>
<a href="bundle_summary.json">Sources and hashes</a><a href="SHA256SUMS.txt">Payload checksums</a></p>
{''.join(cards)}<h2>Full testing record</h2><pre>{html.escape(report)}</pre></main></html>"""
    (output / "index.html").write_text(gallery, encoding="utf-8")

    # Verify generated local report/gallery links. Historical copied source reports
    # keep their original paths and command text as provenance, not rewritten data.
    manifest_path = output / "SHA256SUMS.txt"
    if not manifest_path.exists():
        manifest_path.write_text("Manifest is populated after link validation.\n", encoding="utf-8")
    links = re.findall(r'(?:href|src)="([^"]+)"', gallery)
    links += re.findall(r'\]\(([^)]+)\)', report)
    missing = [link for link in links if not link.startswith(("http:", "https:", "#")) and not (output / html.unescape(link)).exists()]
    if missing:
        raise FileNotFoundError(f"Broken generated evidence links: {missing}")
    save_json(output / "evidence_qa.json", {"generated_local_links_checked": len(links), "missing_links": missing,
                                           "final_source_hash_verified": True, "npz_deduplicated_by_hash": True,
                                           "full_api_completed": api is not None})
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
    (output / "SHA256SUMS.txt").write_text("".join(f"{sha256(path)}  {path.relative_to(output).as_posix()}\n" for path in files), encoding="utf-8")
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                package.write(path, Path(output.name) / path.relative_to(output))
    with zipfile.ZipFile(archive) as package:
        bad = package.testzip()
        if bad:
            raise ValueError(f"Archive CRC failure: {bad}")
        entries = len(package.infolist())
    archive_metadata = {"archive": archive.name, "sha256": sha256(archive), "entries": entries,
                        "bytes": archive.stat().st_size, "crc_verified": True,
                        "full_api_completed": api is not None}
    save_json(archive.with_suffix(".zip.json"), archive_metadata)
    print(json.dumps(archive_metadata, indent=2))


if __name__ == "__main__":
    main()
