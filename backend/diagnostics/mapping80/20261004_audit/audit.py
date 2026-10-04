"""Audit a saved complete video run without recomputing or changing its maps.

Run from the repository root with backend/venv/Scripts/python.exe -B <this file>.
The outputs distinguish raw tracker records, captured-view eligibility, partial
map production, and coverage completeness; none are labelled physical fruits.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RUN = ROOT / "backend/results/ea6e595b8f3f45f2b5edfda8dafff3f2/report.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counter(values) -> dict:
    return dict(collections.Counter(values).most_common())


def quantiles(values) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {}
    return {
        "minimum": ordered[0],
        "p25_nearest": ordered[round((len(ordered) - 1) * .25)],
        "median": statistics.median(ordered),
        "p75_nearest": ordered[round((len(ordered) - 1) * .75)],
        "maximum": ordered[-1],
    }


def split_reason(reason: str) -> str:
    text = reason.lower()
    if "original frame" in text or "missing" in text or "non-consecutive" in text:
        return "missing_original_frames"
    if "too small" in text:
        return "motion_below_minimum"
    if "disagree" in text:
        return "coarse_native_disagreement"
    if "longitude" in text:
        return "longitude_step_outside_bounds"
    if "texture" in text or "point" in text:
        return "insufficient_texture_or_points"
    match = re.search(r"rotation\s+([\d.]+)\s*deg,\s*error\s+([\d.]+)", text)
    if match:
        angle, error = map(float, match.groups())
        if error > .58:
            return "rotation_residual_above_0_58"
        if angle >= 20:
            return "rolling_search_boundary_20_degrees"
        return "other_rotation_rejection"
    return "other"


def duration_metrics(rows: list[dict], fps: float) -> dict:
    measurements = collections.defaultdict(list)
    for row in rows:
        frames = sorted(observation["frame"] for observation in row["tracking_history"]
                        if not observation.get("touches_frame_edge", False))
        longest = current = 0
        previous = None
        for frame in frames:
            current = current + 1 if previous is not None and frame == previous + 1 else 1
            longest = max(longest, current)
            previous = frame
        measurements["tracking_lifetime_sec"].append(
            (row["last_seen_frame"] - row["first_seen_frame"]) / fps)
        measurements["full_bbox_span_sec_including_gaps"].append((frames[-1] - frames[0]) / fps)
        measurements["longest_continuous_full_bbox_interval_sec"].append(max(0, longest - 1) / fps)
        views = row.get("view_frames", [])
        measurements["accepted_view_span_sec_including_gaps"].append(
            (max(views) - min(views)) / fps if len(views) >= 2 else 0)
    return {name: {**quantiles(values), "count_at_least_1_sec": sum(v >= 1 for v in values),
                  "count_at_least_2_sec": sum(v >= 2 for v in values)}
            for name, values in measurements.items()}


def main() -> None:
    report = json.loads(RUN.read_text(encoding="utf-8"))
    tracking_metadata_path = ROOT / "backend/diagnostics/entry-tracking/entry_full_20261002/report.json"
    tracking_metadata = json.loads(tracking_metadata_path.read_text(encoding="utf-8"))
    fps = tracking_metadata["fps"]
    fruits = report["fruits"]
    maps = [row for row in fruits if row.get("surface_map")]
    zero = [row for row in fruits if row["views"] == 0]
    one = [row for row in fruits if row["views"] == 1]
    eligible = [row for row in fruits if row["views"] >= 2]
    inside = [row for row in fruits if any(
        not observation.get("touches_frame_edge", False)
        for observation in row.get("tracking_history", [])
    )]
    transit = [row for row in inside if row["first_seen_frame"] > 0
               and row["last_seen_frame"] < report["metrics"]["frames"] - 1
               and row["tracking_history"][0]["touches_frame_edge"]
               and row["tracking_history"][-1]["touches_frame_edge"]]
    unusable = []
    for row in zero + one:
        full_frames = [observation["frame"] for observation in row["tracking_history"]
                       if not observation.get("touches_frame_edge", False)]
        unusable.append({
            "raw_track_id": row["track_id"], "usable_views": row["views"],
            "tracked_frames": row["tracked_frames"],
            "first_seen_frame": row["first_seen_frame"],
            "last_seen_frame": row["last_seen_frame"],
            "full_bbox_observations": len(full_frames),
            "full_bbox_frames": full_frames,
            "rejected_views": row.get("rejected_views", {}),
            "tracking_evidence": row.get("tracking_evidence", []),
        })
    unusable.sort(key=lambda row: (row["full_bbox_observations"], row["tracked_frames"]), reverse=True)
    full = [row for row in maps if row["observed_surface_pct"] >= 80
            and row["observed_longitude_deg"] >= 350]
    split = [pair for row in fruits for pair in row.get("view_selection", [])
             if pair.get("status") == "split"]
    rejected = collections.Counter()
    zero_rejected = collections.Counter()
    for row in fruits:
        rejected.update(row.get("rejected_views", {}))
        if row["views"] == 0:
            zero_rejected.update(row.get("rejected_views", {}))
    overlaps_path = ROOT / "backend/diagnostics/identity-mapping-check/20261004_scene_motion_v3/map_overlap.json"
    overlap = json.loads(overlaps_path.read_text(encoding="utf-8"))
    guard_path = ROOT / "backend/diagnostics/identity-guard/20261004_scene_motion_v3/summary.json"
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    denominators = {}
    for name, rows in (("all_raw_tracker_records", fruits),
                       ("records_with_any_fully_in_frame_observation", inside),
                       ("records_with_observed_edge_full_edge_transit_within_clip", transit),
                       ("records_with_at_least_one_usable_view", [r for r in fruits if r["views"] >= 1]),
                       ("records_with_at_least_two_usable_views", eligible)):
        n = len(rows)
        any_maps = sum(bool(row.get("surface_map")) for row in rows)
        complete = sum(bool(row.get("surface_map")) and row["observed_surface_pct"] >= 80
                       and row["observed_longitude_deg"] >= 350 for row in rows)
        area80 = sum(bool(row.get("surface_map")) and row["observed_surface_pct"] >= 80
                     for row in rows)
        denominators[name] = {
            "records": n,
            "map_count_any_coverage": any_maps,
            "map_rate_any_coverage_pct": 100 * any_maps / n,
            "map_count_surface80_longitude350": complete,
            "map_count_surface80_without_longitude_gate": area80,
            "map_rate_surface80_without_longitude_gate_pct": 100 * area80 / n,
            "complete_map_rate_pct": 100 * complete / n,
            "target_count_for_80_pct": math.ceil(.8 * n),
            "additional_complete_maps_needed_for_80_pct": math.ceil(.8 * n) - complete,
        }
    result = {
        "run_id": report["job_id"],
        "source_name": report["source_name"],
        "report_created_at": report["created_at"],
        "report_sha256": digest(RUN),
        "historical_run_algorithm_sha256": report["metrics"]["algorithm_sha256"],
        "current_algorithm_sha256_at_audit": digest(ROOT / "backend/algorithm.py"),
        "historical_geometry_settings": report["metrics"]["geometry_settings"],
        "denominators": denominators,
        "fps": fps,
        "fps_source_sha256": digest(tracking_metadata_path),
        "duration_metrics": {
            "ever_full_bbox_records": duration_metrics(inside, fps),
            "observed_transit_proxy_records": duration_metrics(transit, fps),
        },
        "statuses": counter(row["status"] for row in fruits),
        "saved_failure_reasons": counter(row.get("reason", "none") for row in fruits),
        "zero_usable_view_records": len(zero),
        "one_usable_view_records": len(one),
        "two_view_eligible_records_with_no_map": len(eligible) - len(maps),
        "unusable_record_full_bbox_observation_buckets": counter(
            "0" if row["full_bbox_observations"] == 0 else
            "1" if row["full_bbox_observations"] == 1 else
            "2-9" if row["full_bbox_observations"] < 10 else
            "10-29" if row["full_bbox_observations"] < 30 else "30+"
            for row in unusable),
        "total_tracking_observations": sum(len(row["tracking_history"]) for row in fruits),
        "total_full_bbox_observations": sum(
            not observation.get("touches_frame_edge", False)
            for row in fruits for observation in row["tracking_history"]),
        "zero_usable_view_records_always_on_image_edge": sum(all(
            observation.get("touches_frame_edge", False)
            for observation in row.get("tracking_history", [])) for row in zero),
        "record_counts_by_minimum_usable_views": {
            str(threshold): sum(row["views"] >= threshold for row in fruits)
            for threshold in (1, 2, 5, 10, 20, 30, 50, 60, 80)},
        "view_rejections": dict(rejected.most_common()),
        "view_rejections_among_zero_view_records": dict(zero_rejected.most_common()),
        "map_metrics_quantiles": {metric: quantiles(row[metric] for row in maps)
            for metric in ("observed_surface_pct", "observed_longitude_deg",
                           "rotation_coverage_deg", "map_longitude_span_deg")},
        "map_counts_by_surface_threshold": {
            str(threshold): sum(row["observed_surface_pct"] >= threshold for row in maps)
            for threshold in (20, 25, 30, 40, 50, 60, 65, 70, 75, 80, 85, 90)},
        "map_counts_by_longitude_threshold": {
            str(threshold): sum(row["observed_longitude_deg"] >= threshold for row in maps)
            for threshold in (90, 120, 180, 240, 270, 300, 330, 350, 360)},
        "complete_surface80_longitude350_raw_track_ids": [row["track_id"] for row in full],
        "surface80_but_incomplete_longitude_raw_track_ids": [row["track_id"] for row in maps
            if row["observed_surface_pct"] >= 80 and row["observed_longitude_deg"] < 350],
        "pair_statuses": counter(pair.get("status", "none") for row in fruits
            for pair in row.get("view_selection", [])),
        "split_reason_buckets": counter(split_reason(pair.get("reason", "")) for pair in split),
        "total_usable_views": sum(row["views"] for row in fruits),
        "total_selected_mapped_views": sum(len(row.get("mapped_view_frames", [])) for row in maps),
        "guard_v3_overlap_audit": {
            "source_sha256": digest(overlaps_path),
            "maps_with_detected_identity_boundary_in_selected_views": sum(
                row["produced_map"] and row["boundary_inside_mapped_views"] for row in overlap),
            "maps_with_detected_identity_boundary_elsewhere_in_captured_views": sum(
                row["produced_map"] and row["boundary_inside_captured_views"] for row in overlap),
            "guard_summary_sha256": digest(guard_path),
            "raw_tracker_ids": guard["raw_tracker_ids"],
            "capture_segments": guard["capture_segments"],
            "decisions": guard["decisions"],
        },
        "limitations": [
            "Tracker records and guard segments are not labelled unique physical fruits.",
            "The edge-full-edge transit proxy is descriptive and must not replace an independently labelled inspection-ROI entry count.",
            "The saved complete run predates the fruit340 retry and identity guard; this is not a full rerun of current production.",
            "Historical run used 65% surface threshold and strict grading; current app uses 80% and permits provisional observed-area grading.",
            "The 304/474 ceiling applies only to these saved usable-view sets with at least two views required; recapture, better segmentation, extra cameras, or identity reconciliation could change eligibility.",
            "Estimated coverage measures geometric occupancy; no calibrated surface-pose or defect-area ground truth establishes map accuracy.",
            "Detected guard boundaries do not prove physical identity switches and do not rule out smooth switches.",
        ],
    }
    (OUT / "audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    rows = []
    for row in fruits:
        rows.append({key: row.get(key) for key in (
            "track_id", "views", "status", "reason", "tracked_frames", "first_seen_frame",
            "last_seen_frame", "observed_surface_pct", "observed_longitude_deg")})
    (OUT / "records.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    (OUT / "unusable_records.json").write_text(json.dumps(unusable, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "denominators", "split_reason_buckets", "map_metrics_quantiles",
        "guard_v3_overlap_audit")}, indent=2))


if __name__ == "__main__":
    main()
