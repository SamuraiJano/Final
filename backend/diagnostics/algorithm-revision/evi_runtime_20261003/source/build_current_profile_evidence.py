"""Build a fresh evidence pack from an explicitly approved source and run list.

Supply a JSON configuration after the final source and parameters are known.
This script only copies frozen evidence and plots recorded values. It never
reruns an estimator/model or turns execution success into verified grade accuracy.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import html
import hashlib
import json
from pathlib import Path
import re
import shutil
import textwrap
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle

from build_algorithm_revision_evidence import read_json, save_json, sha256, table

BACKEND = Path(__file__).resolve().parent
ALLOWED = {".json", ".jsonl", ".md", ".txt", ".log", ".diff", ".csv", ".py", ".js", ".mjs", ".css", ".svg", ".snapshot", ".png", ".jpg", ".pdf", ".npz", ".html"}


def local_path(value):
    path = (BACKEND / value).resolve()
    if not path.is_relative_to(BACKEND):
        raise ValueError("Evidence paths must stay inside backend")
    return path


def execution_source(report, folder):
    digest = report.get("algorithm_sha256", report.get("candidate_algorithm_sha256"))
    if digest is None:
        hashes = report.get("source_sha256", {})
        digest = hashes.get("adjacent_native.py", hashes.get("backend/algorithm.py"))
    snapshot = next((folder / relative for relative in ("algorithm_snapshot.py", "sources/adjacent_native.py", "algorithm.py.snapshot")
                     if (folder / relative).is_file()), None)
    if snapshot is not None:
        actual = sha256(snapshot)
        if digest is not None and digest != actual:
            raise ValueError(f"Report/source mismatch: {folder}")
        digest = actual
    return digest


def case_items(report, bounds=None):
    cases = report.get("cases", {})
    for name, case in (cases.items() if isinstance(cases, dict) else enumerate(cases)):
        if "bounds" in case:
            for bound, variant in case["bounds"].items():
                if bounds is None or float(bound) in bounds:
                    yield f"{name} /transverse {bound} deg", variant
        else:
            yield name, case


def declared_pass(case):
    for key in ("control_results", "checks"):
        flags = case.get(key)
        if isinstance(flags, dict) and any(value is False for value in flags.values()):
            return False
    for key in ("passed", "all_checks_passed", "all_controls_passed"):
        if isinstance(case.get(key), bool): return case[key]
    for key in ("control_results", "checks"):
        flags = case.get(key)
        if isinstance(flags, dict) and flags and all(isinstance(value, bool) for value in flags.values()):
            return all(flags.values())
    return None


def checked_settings(report, expected, bounds=None):
    variants = []
    if "settings" in report: variants.append(report["settings"])
    if "candidate_settings" in report: variants.append(report["candidate_settings"])
    for track in report.get("tracks", []):
        if not isinstance(track, dict): continue
        for variant in track.get("variants", []):
            if "settings" in variant: variants.append(variant["settings"])
    for _, case in case_items(report, bounds):
        settings = case.get("settings", case.get("result", {}).get("settings"))
        if settings is not None: variants.append(settings)
    if expected and not variants:
        raise ValueError("Expected profile parameters have no recorded settings to verify")
    for settings in variants:
        for key, value in expected.items():
            if settings.get(key) != value:
                raise ValueError(f"Recorded {key}={settings.get(key)!r} differs from configured {value!r}")
    return variants


def measured_checks(name, role, report, scope, bounds=None):
    """Keep unavailable measurements distinct from failing known-answer tests."""
    rows = []
    if role == "software":
        return [{"run": name, "check": case["name"], "status": "PASS" if case["exit_code"] == 0 else "FAIL", "scope": scope,
                 "details": f"Exit code {case['exit_code']}; started {case.get('started_at', 'unrecorded')}; exact command and console log retained"}
                for case in report["checks"]]
    if role == "model":
        stats, detection = report["segmentation"], report.get("detection", {})
        return [{"run": name, "check": "actual frozen-crop model execution", "status": "PASS" if report.get("passed_execution") else "FAIL", "scope": scope,
                 "details": f"{stats['calls']} actual segmenter calls; {stats['instances']} instances; mean {stats['mean_latency_ms']} ms/confidence {stats['mean_confidence']}; detector calls {detection.get('calls', 'unrecorded')}; no human pose/mask/grade truth"}]
    if role == "fixed":
        for track in report["tracks"]:
            for variant in track["variants"]:
                rows.append({"run": name, "check": f"track {track['track']} /{variant['name']}", "status": "UNAVAILABLE", "scope": scope,
                    "details": f"{len(variant['selected_frames'])} selected views; longitude {variant['longitude_deg']:.3f} deg; {variant['status']}; field pose accuracy unavailable"})
        return rows
    if role == "retained_author":
        summary = report["summary"]
        stats = summary["original_published_labels"]
        errors = stats["errors_px_conditional_on_prediction"]
        return [{"run": name, "check": "retained-map published labels", "status": "UNAVAILABLE", "scope": scope,
                 "details": f"{summary['tracks']} sequences; {stats['returned_predictions']}/{summary['author_labels_total']} returned; conditional RMS {errors.get('rms', 'unavailable')} px; {errors.get('within_5px', 0)} of all labels within 5 px; {summary['nonadjacent_selected_bridges']} nonadjacent bridges; no declared field accuracy threshold"}]
    if role == "author_comparison":
        for baseline, comparison in report["comparisons"].items():
            availability = comparison["availability"]
            rows.append({"run": name, "check": f"same labels versus {baseline}", "status": "UNAVAILABLE", "scope": scope,
                "details": f"{availability['both_returned']} common labels; RMS {comparison['baseline_same_returned_labels']['rms']:.6f} to {comparison['candidate_same_returned_labels']['rms']:.6f} px; {comparison['common_improved']} improved/{comparison['common_worsened']} worsened/{comparison['common_unchanged']} unchanged; {availability['newly_returned']} gained/{availability['lost']} lost/{availability['both_unavailable']} unavailable in both; no overall improvement acceptance claim"})
        return rows
    for case_name, case in case_items(report, bounds):
        result = case.get("result", case)
        stats = result.get("summary", {})
        if not stats and "variants" in case:
            result = next(iter(case["variants"].values())); stats = result.get("summary", {})
        passed = declared_pass(case)
        if passed is None: passed = stats.get("motion_control_pass")
        status = "UNAVAILABLE" if passed is None else ("PASS" if passed else "FAIL")
        stationary = case.get("kind") == "stationary_120" or case.get("stationary", False)
        detail = (f"{stats.get('measured_pairs', '?')}/{stats.get('input_pairs', '?')} pairs; "
                  + ("stationary pose accuracy unavailable; reference-scaffold zero maxima not scored" if stationary else
                     f"max pose {stats.get('maximum_pose_error_deg', 'unavailable')} deg; max landmark RMS {stats.get('maximum_landmark_rms_px', 'unavailable')} px"))
        if not stationary and stats.get("all_pairs_measured") is False:
            detail = f"{stats['measured_pairs']}/{stats['input_pairs']} pairs; complete-chain accuracy unavailable; reference-scaffold zeros not scored"
        if "absolute_error_percentage_points" in case:
            detail = (f"Known defect {case['expected_pct_of_observed']}%; measured {case['measured_pct_of_observed']}%; "
                      f"absolute error {case['absolute_error_percentage_points']} percentage points; grade {case['grade']}")
        rows.append({"run": name, "check": case_name, "status": status, "scope": scope,
                     "details": detail, "motion_accuracy_unavailable": stationary})
        if "clear_map_control_pass" in stats:
            rows.append({"run": name, "check": f"{case_name} /all-clear arithmetic", "status": "PASS" if stats["clear_map_control_pass"] else "FAIL",
                "scope": scope, "details": "Supplied all-clear defect observations; class arithmetic only, no neural mask/grade accuracy test"})
    for exposure_name, case in report.get("exposure_controls", {}).items():
        passed = declared_pass(case)
        rows.append({"run": name, "check": f"{exposure_name} /brightness offset", "status": "UNAVAILABLE" if passed is None else ("PASS" if passed else "FAIL"),
            "scope": scope, "details": f"Recorded exposure comparison {case['comparison']}; exact predeclared geometry/invariance flags retained"})
    for index, case in enumerate(report.get("coverage_controls", [])):
        passed = declared_pass(case)
        rows.append({"run": name, "check": f"known-pose coverage arithmetic /{case['true_rotation_deg']} deg", "status": "UNAVAILABLE" if passed is None else ("PASS" if passed else "FAIL"),
            "scope": scope, "details": f"Supplied true rotation {case['true_rotation_deg']} deg; observed longitude {case['observed_longitude_deg']:.3f} deg; status {case['status']}; mask/rotation supplied, not neural or motion accuracy"})
    if not rows:
        flag = next((report[key] for key in ("all_controls_passed", "all_checks_passed", "passed_execution", "passed") if key in report), None)
        if role == "software": flag = all(row["exit_code"] == 0 for row in report["checks"])
        if role == "author":
            stats = report["summary"]["all"]
            detail = (f"{stats['tracks']} sequences; {stats['predicted_correspondences']}/{stats['labelled_correspondences']} returned; "
                      f"conditional RMS {stats['errors_px_conditional_on_prediction'].get('rms', 'unavailable')} px; "
                      "no accuracy acceptance threshold declared")
            flag = None
        elif role == "api":
            if report.get("status") in {"failed", "error", "source_mismatch"} or report.get("passed_execution") is False:
                flag = False
                detail = f"Failed video execution at last published progress {report.get('frames_processed_at_last_status', 'unavailable')}/{report.get('frames_total', 'unavailable')}; {report.get('error', 'see original traceback')}; separate runtime failure, not an image-accuracy score"
            else:
                flag = bool(report.get("finished_at")) and report.get("status") == "complete"
                detail = "Completed video execution; accuracy unverified" if flag else "No completed final-video outcome"
                if not flag: flag = None
        else: detail = "Recorded implementation/execution check; field motion and grade accuracy unverified"
        rows.append({"run": name, "check": role, "status": "UNAVAILABLE" if flag is None else ("PASS" if flag else "FAIL"),
                     "scope": scope, "details": detail})
    return rows


def save_figure(figure, output, stem):
    figure.savefig(output / f"{stem}.png", dpi=300)
    figure.savefig(output / f"{stem}.pdf")
    plt.close(figure)


def api_breakdown(report):
    """Count saved records and their explicit reasons without inferring causes."""
    fruits = report["fruits"]
    statuses = Counter(row["status"] for row in fruits)
    grades = Counter(row.get("grade") or "Review" for row in fruits)
    review_reasons = Counter(row.get("reason") or row["status"] for row in fruits if not row.get("grade"))
    pairs = [pair for row in fruits for pair in (row.get("view_selection") or [])]
    capture_rejections = Counter()
    for row in fruits:
        capture_rejections.update(row.get("rejected_views") or {})
    return {"record_count": len(fruits), "frames": report["metrics"]["frames"], "statuses": dict(statuses),
            "video_duration_sec": report["metrics"]["video_duration_sec"],
            "analysis_duration_sec": report["metrics"]["analysis_duration_sec"],
            "grades": dict(grades), "review_reasons": dict(review_reasons),
            "capture_rejection_reason_events": dict(capture_rejections),
            "motion_diagnostic_statuses": dict(Counter(pair.get("status", "unrecorded") for pair in pairs)),
            "records": [{"track_id": row["track_id"], "status": row["status"], "grade": row.get("grade"),
                         "reason": row.get("reason"), "first_seen_frame": row.get("first_seen_frame"),
                         "last_seen_frame": row.get("last_seen_frame")} for row in fruits],
            "scope": "Saved track records, not manually verified unique fruits. Fruit reasons, rejected-capture attempts and pair splits have distinct denominators; event totals are not additional fruit counts. Automatic edge/silhouette rejection labels do not independently establish physical truncation. Observed map longitude is computed coverage, not ground-truth physical rotation. No manually labelled identity, pose, mask or grade truth."}


def descriptor_record(config, descriptor):
    """Validate a report's actual execution source and dataset-specific settings."""
    path = local_path(descriptor["path"])
    report = read_json(path)
    digest = execution_source(report, path.parent)
    role, primary = descriptor["role"], descriptor.get("primary", True)
    job = None
    settings_report = report
    if role == "api" and report.get("job_id"):
        job = local_path(f"results/{report['job_id']}")
        digest = sha256(job / "algorithm.py.snapshot")
        if (job / "report.json").is_file():
            final_report = read_json(job / "report.json")
            settings_report = dict(report, settings=final_report["metrics"]["geometry_settings"])
            if primary and descriptor.get("frames") is not None and final_report["metrics"]["frames"] != descriptor["frames"]:
                raise ValueError("Full-video report did not process the configured complete frame count")
            if primary:
                if report.get("algorithm_sha256") != digest or final_report["metrics"]["algorithm_sha256"] != digest or report.get("source_matches") is not True:
                    raise ValueError("API summary, aggregate and executed algorithm source disagree")
                fruits = final_report["fruits"]
                if report["fruits"] != len(fruits) or report["statuses"] != dict(Counter(row["status"] for row in fruits)) or report["grades"] != dict(Counter(row.get("grade") or "ungraded" for row in fruits)):
                    raise ValueError("API summary counts disagree with the completed aggregate")
                if read_json(path.parent / "response.json") != final_report:
                    raise ValueError("Saved API response differs from the job's aggregate report")
                if descriptor.get("video_sha256") and report["video_sha256"] != descriptor["video_sha256"]:
                    raise ValueError("Completed API did not use the configured original video")
                if sha256(Path(report["video"])) != report["video_sha256"]:
                    raise ValueError("Original video differs from the recorded request input")
        if primary and config.get("runtime_main_sha256"):
            if sha256(job / "main.py.snapshot") != config["runtime_main_sha256"]:
                raise ValueError("Completed API executed a different runtime main.py")
    if primary and digest != config["algorithm_sha256"]:
        raise ValueError(f"Primary run {descriptor['name']} did not execute the configured source")
    if descriptor.get("main_sha256"):
        hashes = report.get("source_sha256", {})
        actual_main = hashes.get("main.py", hashes.get("backend/main.py"))
        if actual_main != descriptor["main_sha256"]:
            raise ValueError(f"Run {descriptor['name']} used a different main.py")
    if role == "model":
        for filename, recorded_digest in report["source_sha256"].items():
            if sha256(path.parent / f"{filename}.snapshot") != recorded_digest:
                raise ValueError(f"Frozen model execution source differs: {filename}")
    if primary and role == "api" and not (job is not None and report.get("finished_at") and report.get("status") == "complete" and (job / "report.json").is_file()):
        raise ValueError("A primary full-video outcome needs a complete report and successful final response")
    settings = checked_settings(settings_report, descriptor.get("settings_expected", config["profile_settings"] if primary else {}), descriptor.get("bounds"))
    if role == "shading" and not report.get("completed_at"):
        raise ValueError("An unfinished lighting suite cannot be sealed")
    if role in {"author", "retained_author"}:
        stats = report["summary"]["all"] if role == "author" else {"tracks": report["summary"]["tracks"], "labelled_correspondences": report["summary"]["author_labels_total"]}
        for key in ("tracks", "labelled_correspondences"):
            if key in descriptor and stats[key] != descriptor[key]:
                raise ValueError(f"Author {key} scope differs")
    if role == "author_comparison":
        author = next(item for item in config["reports"] if item["role"] == "author" and item.get("primary", True))
        if sha256(local_path(author["path"])) != report["candidate_report_sha256"]:
            raise ValueError("Paired comparison does not reference this current author run")
        for comparison in report["comparisons"].values():
            if sha256(local_path(comparison["baseline_report"])) != comparison["baseline_report_sha256"]:
                raise ValueError("Paired author's baseline report changed")
    return path, report, digest, job, settings


def preflight(config_path, allow_pending=False):
    """Read-only checks; no output directory, figures, models or archive created."""
    config = read_json(config_path)
    label, expected = config["label"], config["algorithm_sha256"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", label) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("Specify a fresh label and an exact final-source SHA256")
    if not config.get("profile_settings") or not config.get("reports"):
        raise ValueError("Explicit final profile settings and named reports are required")
    if sha256(local_path(config["algorithm_source"])) != expected:
        raise ValueError("Configured final source/hash differs")
    names, records, pending, checked_inputs = set(), [], [], set()
    for descriptor in config["reports"]:
        name = descriptor["name"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in names:
            raise ValueError("Run names must be unique simple labels")
        names.add(name)
        if not local_path(descriptor["path"]).is_file() and descriptor.get("awaited") and allow_pending:
            pending.append({"name": name, "path": descriptor["path"]})
            continue
        path, report, digest, job, settings = descriptor_record(config, descriptor)
        if descriptor["role"] == "api" and descriptor.get("primary", True):
            checked_inputs.add(report["video"])
        input_directory = next((report[key] for key in ("input_directory", "frozen_input_directory", "original_input_directory", "prior_input_directory") if report.get(key)), None)
        if input_directory:
            folder = local_path(input_directory)
            for case_name, case in report.get("cases", {}).items():
                fixture = folder / case.get("input_file", f"{case_name}.npz")
                if not fixture.is_file(): fixture = folder / f"{case_name}_inputs.npz"
                if not fixture.is_file(): raise FileNotFoundError(fixture)
                if case.get("input_sha256") and sha256(fixture) != case["input_sha256"]:
                    raise ValueError("Scene input differs from its recorded hash")
                checked_inputs.add(str(fixture))
        for item in report.get("input_manifest", []):
            fixture = path.parent / item["file"]
            if sha256(fixture) != item["sha256"]: raise ValueError("Known-area input differs from its recorded hash")
            checked_inputs.add(str(fixture))
        if descriptor["role"] == "model":
            for track in report["tracks"]:
                folder = local_path(track["fixture"])
                for filename, input_digest in track["input_sha256"].items():
                    if sha256(folder / filename) != input_digest: raise ValueError("Real crop/mask input differs from its recorded hash")
                    checked_inputs.add(str(folder / filename))
        rows = measured_checks(name, descriptor["role"], report, descriptor["scope"], descriptor.get("bounds"))
        records.append({"name": name, "algorithm_sha256": digest, "report_sha256": sha256(path),
                        "outcomes": {status: sum(row['status'] == status for row in rows) for status in ('PASS', 'FAIL', 'UNAVAILABLE')}})
    for item in config.get("supplementary_collections", []):
        if not local_path(item["path"]).is_dir(): raise FileNotFoundError(item["path"])
    for item in config.get("workspace_files", []):
        path = (BACKEND.parent / item["path"]).resolve()
        if not path.is_relative_to(BACKEND.parent): raise ValueError("Workspace snapshot must stay inside this project")
        if item.get("sha256") and sha256(path) != item["sha256"]: raise ValueError(f"Configured workspace source differs: {path}")
        if not path.is_file(): raise FileNotFoundError(path)
    for item in config.get("report_figures", []):
        if not local_path(item["path"]).is_file(): raise FileNotFoundError(item["path"])
    for example in config.get("api_examples", []):
        descriptor = next(item for item in config["reports"] if item["name"] == example["api_run"])
        if not local_path(descriptor["path"]).is_file() and allow_pending and descriptor.get("awaited"):
            continue
        path, report, digest, job, settings = descriptor_record(config, descriptor)
        result = read_json(job / str(example["track"]) / "result.json")
        aggregate = read_json(job / "report.json")
        row = next(row for row in aggregate["fruits"] if row["track_id"] == example["track"])
        for key in ("status", "grade", "observed_surface_pct", "observed_longitude_deg", "defect_pct_of_observed"):
            if result.get(key) != row.get(key): raise ValueError("Actual API example differs from the completed aggregate report")
        expected_frames = example.get("expected_frames", {})
        actual_frames = {"entry": result["tracking_evidence"][0]["frame"], "last_seen": result["tracking_evidence"][-1]["frame"], "selected": result["view_evidence"][0]["frame"]}
        if any(actual_frames[key] != value for key, value in expected_frames.items()):
            raise ValueError("Actual API figure source-frame selection changed")
    return {"label": label, "algorithm_sha256": expected, "reports": records, "awaited_reports": pending,
            "referenced_input_files_verified": len(checked_inputs),
            "ready_to_seal": not pending, "evidence_generated": False}


def build(config_path):
    preflight(config_path, allow_pending=False)
    config = read_json(config_path)
    label, expected = config["label"], config["algorithm_sha256"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", label) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("Specify a fresh label and an exact final-source SHA256")
    if not config.get("profile_settings") or not config.get("reports"):
        raise ValueError("Explicit final profile settings and named reports are required")
    source = local_path(config["algorithm_source"])
    if sha256(source) != expected: raise ValueError("Configured final source/hash differs")
    output = BACKEND / "diagnostics/algorithm-revision" / label
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite a sealed trial.
    copied, aliases, npz_payloads, runs, checks, figures, figure_sources, input_records, api_outcomes, historical_figures = [], [], {}, {}, [], [], [], [], {}, []

    def copy_file(path, relative):
        destination = output / relative
        if not destination.resolve().is_relative_to(output.resolve()):
            raise ValueError("Generated evidence paths must stay inside the fresh pack")
        started_at = datetime.now(timezone(timedelta(hours=2))).isoformat()
        bounded_log = path.suffix == ".log"
        payload = path.read_bytes() if bounded_log else None
        digest = hashlib.sha256(payload).hexdigest() if bounded_log else sha256(path)
        if path.suffix == ".npz":
            if digest in npz_payloads:
                aliases.append({"original_bundle_path": Path(relative).as_posix(), "stored_once_at": npz_payloads[digest], "sha256": digest})
                return
            npz_payloads[digest] = Path(relative).as_posix()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if bounded_log: destination.write_bytes(payload)
        else: shutil.copy2(path, destination)
        if sha256(destination) != digest: raise ValueError(f"Source changed while copying: {path}")
        copied.append({"original_path": str(path), "bundle_path": Path(relative).as_posix(), "sha256": digest,
                       "capture_started_at": started_at, "capture_finished_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
                       "bounded_log_snapshot": bounded_log,
                       "capture_note": "Hash identifies this captured log payload; the operational service may append to the original later." if bounded_log else None})

    def collection(folder, relative):
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix in ALLOWED and "__pycache__" not in path.parts:
                copy_file(path, Path(relative) / path.relative_to(folder))

    copy_file(config_path, "configuration.json"); copy_file(source, "source/algorithm.py.snapshot")
    copy_file(Path(__file__), "source/build_current_profile_evidence.py")
    for item in config.get("workspace_files", []):
        copy_file((BACKEND.parent / item["path"]).resolve(), Path("workspace_context") / item["path"])
    for descriptor in config["reports"]:
        name, role = descriptor["name"], descriptor["role"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in runs: raise ValueError("Run names must be unique simple labels")
        path, report, digest, job, settings = descriptor_record(config, descriptor)
        primary = descriptor.get("primary", True)
        if primary and digest != expected:
            raise ValueError(f"Primary run {name} did not execute the configured source")
        bounds = descriptor.get("bounds")
        if role == "shading" and not report.get("completed_at"):
            raise ValueError("An unfinished lighting suite cannot be sealed as a final profile run")
        if role == "author":
            stats = report["summary"]["all"]
            for key in ("tracks", "labelled_correspondences"):
                if key in descriptor and stats[key] != descriptor[key]: raise ValueError(f"Author {key} scope differs")
        collection(path.parent, Path("runs") / name)
        for item in report.get("input_manifest", []):
            fixture = path.parent / item["file"]
            if sha256(fixture) != item["sha256"]: raise ValueError("Known-area frozen input differs")
            input_records.append({"run": name, "input": str(fixture), "sha256": item["sha256"]})
        # Lighting scenes and actual-model fixtures may live outside the run
        # folder. Freeze those exact inputs too, retaining their recorded hashes.
        input_directory = next((report[key] for key in ("input_directory", "frozen_input_directory", "original_input_directory", "prior_input_directory") if report.get(key)), None)
        if input_directory:
            inputs = local_path(input_directory)
            collection(inputs, Path("inputs") / name)
            for case_name, case in report.get("cases", {}).items():
                fixture = inputs / case.get("input_file", f"{case_name}.npz")
                if not fixture.is_file(): fixture = inputs / f"{case_name}_inputs.npz"
                if case.get("input_sha256") and sha256(fixture) != case["input_sha256"]:
                    raise ValueError("Scene input hash changed after the recorded run")
                input_records.append({"run": name, "input": str(fixture), "sha256": sha256(fixture)})
        if role == "model":
            for track in report["tracks"]:
                inputs = local_path(track["fixture"])
                collection(inputs, Path("inputs") / name / str(track["track"]))
                for filename, input_digest in track["input_sha256"].items():
                    if sha256(inputs / filename) != input_digest: raise ValueError("Frozen real crop/mask input differs")
                    input_records.append({"run": name, "input": str(inputs / filename), "sha256": input_digest})
        if job is not None:
            for filename in ("report.json", "metrics.json", "algorithm.py.snapshot", "main.py.snapshot", "dfine_segmenter.py.snapshot"):
                if (job / filename).is_file(): copy_file(job / filename, Path("api_execution") / name / filename)
            if primary and role == "api":
                api_outcomes[name] = api_breakdown(read_json(job / "report.json"))
                save_json(output / "api_execution" / name / "record_status_breakdown.json", api_outcomes[name])
                input_records.append({"run": name, "input": report["video"], "sha256": report["video_sha256"],
                                      "duplicated_in_bundle": False, "method": "Full original video; request/response and aggregate reconciled"})
        runs[name] = {"role": role, "primary": primary, "algorithm_sha256": digest, "report_sha256": sha256(path), "bounds_scored": bounds,
            "source_report": str(path), "scope": descriptor["scope"], "recorded_settings": settings,
            "report": report, "folder": path.parent}
        rows = measured_checks(name, role, report, descriptor["scope"], bounds)
        for row in rows: row["primary"] = primary
        checks.extend(rows)
    for supplement in config.get("supplementary_collections", []):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", supplement["name"]): raise ValueError("Use a simple supplement name")
        folder = local_path(supplement["path"])
        collection(folder, Path("supplementary") / supplement["name"])
        save_json(output / "supplementary" / supplement["name"] / "EVIDENCE_SCOPE.json", {"scope": supplement["scope"],
            "primary_algorithm_validation": False, "generated_current_model_figure": False})
    for item in config.get("report_figures", []):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", item["name"]): raise ValueError("Use a simple report-figure name")
        path = local_path(item["path"])
        relative = f"{item['name']}.png"
        copy_file(path, relative)
        if not path.with_suffix(".pdf").is_file(): raise FileNotFoundError("Report figure needs its original PDF too")
        copy_file(path.with_suffix(".pdf"), f"{item['name']}.pdf")
        historical_figures.append((item["caption"], relative))
        figure_sources.append({"figure": item["name"], "image": str(path), "sha256": sha256(path),
                               "scope": item["scope"], "current_source_validation": False})

    # Raw primary control measurements stay separate from ungraded/unknown poses.
    control_rows = [row for row in checks if row["primary"] and runs[row["run"]]["role"] in ("motion", "shading", "full_turn", "fresh_texture", "large_transverse")]
    values = {"PASS": 1, "FAIL": 0, "UNAVAILABLE": .5}
    if control_rows:
        from matplotlib.colors import ListedColormap
        fig, ax = plt.subplots(figsize=(12, max(3, .52 * len(control_rows) + 1.5)))
        ax.imshow(np.array([[values[row["status"]]] for row in control_rows]), aspect="auto", vmin=0, vmax=1,
                  cmap=ListedColormap(["#dfb6aa", "#e2e4df", "#bfd6bc"]))
        ax.set(xticks=[], yticks=range(len(control_rows)), yticklabels=[textwrap.fill(f"{row['run']}: {row['check']}", width=64, break_long_words=False) for row in control_rows])
        ax.tick_params(axis="y", labelsize=8)
        for index, row in enumerate(control_rows): ax.text(0, index, row["status"], ha="center", va="center", color="#25372b")
        ax.set_title("Current source: known-answer development controls; unavailable is not zero error")
        fig.tight_layout(); save_figure(fig, output, "control_outcomes"); figures.append(("Known-answer development control outcomes", "control_outcomes.png"))

    author_run = next((run for run in runs.values() if run["primary"] and run["role"] == "author"), None)
    worst = None
    if author_run:
        rows = author_run["report"]["correspondences"]
        returned = [row for row in rows if row.get("error_px") is not None]
        if returned:
            worst = max(returned, key=lambda row: row["error_px"])
            folder = local_path("diagnostics/authors-benchmark/data/rotation/data") / worst["group"] / worst["object"]
            fig, axes = plt.subplots(1, 2, figsize=(10, 5))
            for ax, index, point, title in zip(axes, (worst["source"], worst["target"]),
                    (worst["source_xy"], worst["target_xy"]), ("Original source annotation", "Target annotation and recorded prediction")):
                path = folder / f"im{index:02d}.png"
                copy_file(path, f"author_worst/im{index:02d}.png")
                ax.imshow(plt.imread(path)); ax.add_patch(Circle(point, 5, fill=False, color="#43d766", linewidth=2))
                ax.set_title(f"{title}\n{worst['group']}/{worst['object']}, original frame {index}", fontsize=10); ax.axis("off")
                figure_sources.append({"figure": "worst_author_pair", "image": str(path), "sha256": sha256(path)})
            axes[1].scatter(*worst["prediction"], marker="x", s=100, color="red", linewidth=2)
            fig.suptitle(f"Worst returned author label {worst['line']}: {worst['error_px']:.5f} pixels; failure remains counted")
            fig.tight_layout(); save_figure(fig, output, "worst_author_pair"); figures.append(("Worst actual returned author pair", "worst_author_pair.png"))
            save_json(output / "worst_author_label.json", worst)
        for name in ("source_manifest.json",):
            manifest_path = local_path(f"diagnostics/authors-benchmark/{name}")
            copy_file(manifest_path, f"author_provenance/{name}")
            for item in read_json(manifest_path)["files"]:
                image = local_path("diagnostics/authors-benchmark") / item["file"]
                if sha256(image) != item["sha256"]: raise ValueError("Author data differs from its frozen source manifest")
                input_records.append({"run": "author_provenance", "input": str(image), "sha256": item["sha256"],
                                      "source_url": item["url"], "duplicated_in_bundle": False})
        for name in ("rotation_LICENSE", "maps_LICENSE"):
            copy_file(local_path(f"diagnostics/authors-benchmark/evidence_20261002/source_licenses/{name}"), f"author_provenance/{name}")

    # A donor tracking sequence may have another source; require explicit provenance.
    for example in config.get("real_examples", []):
        track, name = str(example["track"]), example["name"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name): raise ValueError("Use a simple real-example name")
        donor = local_path(example["tracking_folder"])
        if sha256(donor.parent / "algorithm.py.snapshot") != example["tracking_algorithm_sha256"]:
            raise ValueError("Tracking donor source differs from its explicitly declared source")
        tracking = read_json(donor / "result.json")
        model = runs[example["model_run"]]
        if model["role"] != "model" or not model["primary"]: raise ValueError("Real model figure requires a current primary model run")
        model_track = next(row for row in model["report"]["tracks"] if str(row["track"]) == track)
        result = model_track["result"]; model_folder = model["folder"] / track
        entries = tracking["tracking_evidence"]
        first, last = entries[0], entries[-1]
        view = result["view_evidence"][0]
        images = [(donor / Path(first["crop"]).name, f"First tracking observation, frame {first['frame']}"),
                  (model_folder / Path(view["crop"]).name, f"Selected actual crop, frame {view['frame']}"),
                  (donor / Path(last["crop"]).name, f"Last tracking observation, frame {last['frame']}"),
                  (model_folder / Path(view["overlay"]).name, "Actual fruit boundary and predicted defects"),
                  (model_folder / "surface_map.png", f"Current map: {result['status']}; grade {result.get('grade')}"),
                  (model_folder / "observed.png", f"Observed longitude {result.get('observed_longitude_deg')} deg")]
        fig, axes = plt.subplots(2, 3, figsize=(12, 7))
        for index, (ax, (path, title)) in enumerate(zip(axes.flat, images)):
            copy_file(path, f"real_examples/{name}/{index}_{path.name}")
            ax.imshow(plt.imread(path)); ax.set_title(title, fontsize=10, wrap=True); ax.axis("off")
            figure_sources.append({"figure": f"real_{name}", "image": str(path), "sha256": sha256(path),
                "tracking_donor": index in (0, 2), "tracking_source_sha256": example["tracking_algorithm_sha256"] if index in (0, 2) else None})
        fig.suptitle(f"Real naartjie {track}: entry, observations, actual model output and map")
        fig.text(.5, .012, example["scope"] + " Model output and class are unverified against human labels.", ha="center", fontsize=8, wrap=True)
        fig.tight_layout(rect=(0, .04, 1, .95)); save_figure(fig, output, f"real_{name}"); figures.append((f"Real fruit {track}: tracking and model evidence", f"real_{name}.png"))
        save_json(output / f"real_examples/{name}/provenance.json", {"scope": example["scope"], "tracking_result_sha256": sha256(donor / "result.json"),
            "tracking_algorithm_sha256": example["tracking_algorithm_sha256"], "model_algorithm_sha256": model["algorithm_sha256"],
            "model_result": result, "field_accuracy_verified": False})

    # A fresh complete API example repeats detection/tracking/model inference.
    # Keep it separate from the controlled frozen-crop replay and source863 donor.
    for example in config.get("api_examples", []):
        name, track = example["name"], str(example["track"])
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name): raise ValueError("Use a simple API-example name")
        run = runs[example["api_run"]]
        if run["role"] != "api" or not run["primary"]: raise ValueError("Actual API figure requires a completed current primary API run")
        job = local_path(f"results/{run['report']['job_id']}")
        folder = job / track
        result = read_json(folder / "result.json")
        collection(folder, Path("api_examples") / name / "original_track")
        entries = result["tracking_evidence"]
        first, last = entries[0], entries[-1]
        view = result["view_evidence"][0]
        images = [(folder / Path(first["crop"]).name, f"Actual first tracking observation, frame {first['frame']}"),
                  (folder / Path(view["crop"]).name, f"Actual selected crop, frame {view['frame']}"),
                  (folder / Path(last["crop"]).name, f"Actual last tracking observation, frame {last['frame']}"),
                  (folder / Path(view["overlay"]).name, "Actual fruit boundary and model defect predictions"),
                  (folder / "surface_map.png", f"Actual API map: {result['status']}; {result.get('grade')}"),
                  (folder / "observed.png", f"Observed longitude {result['observed_longitude_deg']:.1f} deg; surface {result['observed_surface_pct']:.3f}%")]
        fig, axes = plt.subplots(2, 3, figsize=(12, 7))
        for index, (ax, (path, title)) in enumerate(zip(axes.flat, images)):
            copy_file(path, f"api_examples/{name}/{index}_{path.name}")
            ax.imshow(plt.imread(path)); ax.set_title(title, fontsize=10, wrap=True); ax.axis("off")
            figure_sources.append({"figure": f"api_{name}", "image": str(path), "sha256": sha256(path),
                                   "algorithm_sha256": run["algorithm_sha256"], "main_sha256": sha256(job / "main.py.snapshot"),
                                   "scope": "Actual full-pipeline API example, distinct from frozen replay and historical tracking donor; no human accuracy truth"})
        fig.suptitle(f"Original video, actual full-pipeline fruit {track}: predicted defect area {result['defect_pct_of_observed']:.6f}%")
        fig.text(.5, .012, "Fresh detector/tracker/model execution on the original video; configured class arithmetic, no human pose/mask/grade labels.", ha="center", fontsize=8)
        fig.tight_layout(rect=(0, .04, 1, .95)); save_figure(fig, output, f"api_{name}")
        figures.append((f"Actual original-video fruit {track}: separate full-pipeline example; grade accuracy unverified", f"api_{name}.png"))
        save_json(output / f"api_examples/{name}/provenance.json", {"scope": example["scope"], "job_id": job.name,
                  "algorithm_sha256": run["algorithm_sha256"], "main_sha256": sha256(job / "main.py.snapshot"),
                  "result_sha256": sha256(folder / "result.json"), "result": result, "field_accuracy_verified": False,
                  "detector_tracker_repeated": True, "frozen_replay": False})

    figures.extend(historical_figures)
    failed = any(row["status"] == "FAIL" for row in control_rows)
    unavailable = not control_rows or any(row["status"] == "UNAVAILABLE" for row in control_rows)
    headline = ("Current profile still fails declared known-answer development controls." if failed else
                "Some declared controls are unavailable." if unavailable else
                "The declared known-answer development controls pass; field motion and grade accuracy remain unverified.")
    execution_headline = ""
    if api_outcomes:
        data = next(iter(api_outcomes.values()))
        graded = data['record_count'] - data['grades'].get('Review', 0)
        execution_headline = (f"Complete offline execution succeeded for this clip: {data['frames']} frames, "
                              f"{graded}/{data['record_count']} records assigned a class ({100*graded/data['record_count']:.2f}%), "
                              f"{data['grades'].get('Review', 0)} Review. Grading remains very limited. "
                              f"A {data['video_duration_sec']}-second clip required {data['analysis_duration_sec']/60:.1f} minutes; this is not real-time operation. ")
    headline = execution_headline + headline
    now = datetime.now(timezone(timedelta(hours=2))).isoformat()
    formatted_rows = [[row["run"], row["check"], row["status"], "current" if row["primary"] else "comparison history", row["details"]] for row in checks]
    descriptions = "\n\n".join(f"**{name}** ({run['role']}, {'current source' if run['primary'] else 'comparison only'}, source `{run['algorithm_sha256']}`): {run['scope']}" for name, run in runs.items())
    api_sections = []
    for name, data in api_outcomes.items():
        api_sections.append(f"### {name}: complete video execution\n\n{data['frames']} frames; {data['record_count']} saved track records.\n\n" +
            table(['Saved status', 'Records'], list(data['statuses'].items())) + "\n\n" +
            table(['Configured class /Review', 'Records'], list(data['grades'].items())) + "\n\n" +
            table(['Copied reason for Review', 'Records'], list(data['review_reasons'].items())) + "\n\n" +
            table(['Automatic rejected-capture reason', 'Capture attempts'], list(data['capture_rejection_reason_events'].items())) + "\n\n" +
            table(['Motion diagnostic status', 'Pair events'], list(data['motion_diagnostic_statuses'].items())) +
            f"\n\n{data['scope']} [Raw counts and records](api_execution/{name}/record_status_breakdown.json).")
    report = f"""# Current algorithm profile: frozen testing evidence

Built {now}. **{headline}**
Exact source SHA256 `{expected}`. [Explicit parameters and input selection](configuration.json).
This report draws recorded results; it runs no estimator, model or resumed video job.

## What was tested

{descriptions}

## Full-video execution and remaining Review records

{chr(10).join(api_sections) if api_sections else 'No completed current-source full-video outcome is included.'}

## Checks and unavailable outcomes

{table(['Run', 'Check', 'Outcome', 'Source scope', 'Recorded measurement'], formatted_rows)}

PASS refers only to the stated predeclared control or execution check. Author point
accuracy has no declared acceptance threshold here and is reported with prediction
availability. A missing pose is unavailable, not an estimated zero rotation. A
stationary scaffold zero maximum is never scored as zero-error motion. An execution
PASS, full coverage or a Class 1 output does not prove correct surface geometry or grade.

## Actual images retained for the report

""" + "\n\n".join(f"![{title}]({relative})\n[300-dpi PNG]({relative}) · [PDF]({Path(relative).with_suffix('.pdf').as_posix()})" for title, relative in figures) + f"""

Worst returned author label: `{json.dumps(worst)}`. Prediction and annotation are
drawn on the unchanged original source/target images, with source-frame hashes.
Tracking donor images retain their separate source. Actual segmentation overlays
are predictions, not manual labels; the current model report and weights hashes,
when recorded, are copied without reinterpretation. Field accuracy remains unverified.

## Provenance and reproduction

Each named report collection is copied with original images, NPZ inputs, frozen
scripts, source snapshots, parameters and raw outputs. Identical NPZ payloads are
stored once by SHA256; input_references.json resolves aliases. Source records and
figure_provenance.json identify their origins. No previous sealed evidence is overwritten.

Research context: [2021 spheroid rotation paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 surface-map paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
This is an independent implementation. The selected source and recorded settings
identify its engineering adaptations; author-data correspondence scoring, controlled
motion scoring and real-model execution have different scopes and denominators.

```powershell
./backend/venv/Scripts/python.exe -B backend/build_current_profile_evidence.py --config <configuration.json>
```

Use a fresh output label. Software and synthetic development checks do not establish
held-out field motion, defect-mask accuracy, identity accuracy, grading accuracy
or real-time throughput. Completed video outcomes require their own complete
report and execution snapshots; saved partial rows do not establish completion.
"""
    (output / "VALIDATION_REPORT.md").write_text(report, encoding="utf-8")
    save_json(output / "checks.json", checks); save_json(output / "figure_provenance.json", figure_sources)
    save_json(output / "input_sha256.json", input_records)
    save_json(output / "input_references.json", {"unique_npz_payloads": len(npz_payloads), "aliases": aliases})
    save_json(output / "source_records.json", {name: {key: value for key, value in run.items() if key not in ("report", "folder")} for name, run in runs.items()})
    save_json(output / "bundle_summary.json", {"built_at": now, "algorithm_sha256": expected, "profile_settings": config["profile_settings"],
        "headline": headline, "declared_motion_controls_pass": not failed and not unavailable,
        "field_motion_accuracy_verified": False, "grade_accuracy_verified": False, "copied_sources": copied})
    cards = "".join(f'<figure><img src="{relative}" alt="{html.escape(title)}"><figcaption>{html.escape(title)}</figcaption></figure>' for title, relative in figures)
    gallery = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Current naartjie algorithm evidence</title>
<style>body{{font:17px/1.55 system-ui;color:#24382b;background:#f3f5f0}}main{{max-width:1150px;margin:auto;padding:28px}}.status{{background:#efddd5;padding:18px}}img{{max-width:100%;height:auto}}figure{{background:white;padding:18px;margin:24px 0}}pre{{font:14px/1.65 monospace;white-space:pre-wrap;overflow-wrap:anywhere}}</style>
<main><h1>Current algorithm profile: testing evidence</h1><p class="status">{html.escape(headline)}</p><p><a href="VALIDATION_REPORT.md">Testing report</a> · <a href="configuration.json">Exact source and settings</a> · <a href="SHA256SUMS.txt">Checksums</a></p>{cards}<pre>{html.escape(report)}</pre></main></html>'''
    (output / "index.html").write_text(gallery, encoding="utf-8")
    manifest = output / "SHA256SUMS.txt"; manifest.touch()
    links = re.findall(r'(?:href|src)="([^"]+)"', gallery) + re.findall(r'\]\(([^)]+)\)', report)
    missing = [link for link in links if not link.startswith(("http:", "https:", "#")) and not (output / html.unescape(link)).is_file()]
    if missing: raise FileNotFoundError(f"Generated evidence links missing: {missing}")
    save_json(output / "evidence_qa.json", {"missing_links": [], "source_and_configured_settings_checked": True,
        "no_previous_pack_overwritten": True, "algorithm_inference_rerun": False})
    manifest.write_text("".join(f"{sha256(path)}  {path.relative_to(output).as_posix()}\n" for path in sorted(output.rglob('*')) if path.is_file() and path != manifest), encoding="utf-8")
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(output.rglob("*")):
            if path.is_file(): package.write(path, Path(output.name) / path.relative_to(output))
    with zipfile.ZipFile(archive) as package:
        if package.testzip(): raise ValueError("Archive CRC failed")
        entries = len(package.infolist())
    metadata = {"archive": archive.name, "sha256": sha256(archive), "entries": entries, "bytes": archive.stat().st_size, "crc_verified": True}
    save_json(archive.with_suffix(".zip.json"), metadata); print(json.dumps(metadata, indent=2))
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--preflight", action="store_true", help="Verify available report sources/settings without creating figures or a ZIP; list explicitly awaited reports.")
    args = parser.parse_args()
    if args.preflight: print(json.dumps(preflight(args.config.resolve(), allow_pending=True), indent=2))
    else: build(args.config.resolve())


if __name__ == "__main__": main()
