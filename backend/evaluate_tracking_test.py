"""Evaluate tracker output against independently reviewed physical-fruit labels.

Input is MOTChallenge CSV: frame, identity, x, y, width, height, [confidence].
Frames and identities are positive integers; boxes use original-image pixels.
GT requires inclusion column 7 equal to 1. This protocol deliberately rejects
ignored fruit rather than silently changing the denominator. Explicitly empty
reviewed frames are retained through the manifest and count false positives.

Trajectory IDF1 follows the potential-match/global-assignment definition in
TrackEval's Identity metric. Other metrics are disclosed custom diagnostics;
this is not an implementation of HOTA or CLEAR MOT.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment


IDF1_REFERENCE = "https://github.com/JonathonLuiten/TrackEval/blob/master/trackeval/metrics/identity.py"


@dataclass(frozen=True)
class Observation:
    frame: int
    identity: int
    box: tuple[float, float, float, float]
    confidence: float | None = None


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if not np.isfinite(number) or number < 1 or number != int(number):
        raise ValueError(f"{name} must be a positive integer")
    return int(number)


def validate_manifest(manifest: dict[str, Any]) -> list[int]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    if manifest.get("frame_index_base") != 1 or manifest.get("coordinate_format") != "xywh":
        raise ValueError("manifest must declare frame_index_base=1 and coordinate_format='xywh'")
    if manifest.get("annotation_complete") is not True:
        raise ValueError("ground truth is unreviewed: annotation_complete must be true")
    if manifest.get("unresolved_annotations"):
        raise ValueError("resolve all unresolved_annotations before evaluating tracking")
    if not isinstance(manifest.get("frames"), list) or not manifest["frames"]:
        raise ValueError("manifest frames must explicitly list every reviewed frame, including empty frames")
    frames = [_positive_integer(value, "manifest frame") for value in manifest["frames"]]
    if frames != sorted(set(frames)):
        raise ValueError("manifest frames must be unique and strictly increasing")
    if frames != list(range(1, len(frames) + 1)):
        raise ValueError("manifest frames must be consecutive local numbers 1..N; skipped frames cannot be scored as complete")
    if not isinstance(manifest.get("reviewed_frames"), list):
        raise ValueError("manifest reviewed_frames must list every reviewed frame")
    reviewed = [_positive_integer(value, "reviewed frame") for value in manifest["reviewed_frames"]]
    if sorted(reviewed) != frames or len(set(reviewed)) != len(reviewed):
        raise ValueError("reviewed_frames must cover every manifest frame exactly once")
    return frames


def read_mot(path: str | Path, *, ground_truth: bool) -> list[Observation]:
    """Parse CSV strictly; do not silently drop invalid rows or low scores."""
    path = Path(path)
    rows: list[Observation] = []
    seen: set[tuple[int, int]] = set()
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for line_number, row in enumerate(csv.reader(stream), 1):
            if not row or all(not item.strip() for item in row) or row[0].lstrip().startswith("#"):
                continue
            prefix = f"{path.name}:{line_number}"
            if len(row) < (7 if ground_truth else 6):
                raise ValueError(f"{prefix}: expected frame,id,x,y,w,h" + (",inclusion=1" if ground_truth else "[,confidence]"))
            frame = _positive_integer(row[0], f"{prefix} frame")
            identity = _positive_integer(row[1], f"{prefix} identity")
            try:
                box = tuple(float(item) for item in row[2:6])
            except ValueError as exc:
                raise ValueError(f"{prefix}: bbox coordinates must be numeric") from exc
            if not all(np.isfinite(value) for value in box) or box[2] <= 0 or box[3] <= 0:
                raise ValueError(f"{prefix}: bbox must be finite with positive width and height")
            confidence = None
            if len(row) >= 7:
                try:
                    confidence = float(row[6])
                except ValueError as exc:
                    raise ValueError(f"{prefix}: column 7 must be numeric") from exc
                if not np.isfinite(confidence):
                    raise ValueError(f"{prefix}: column 7 must be finite")
                if ground_truth and confidence != 1:
                    raise ValueError(f"{prefix}: GT inclusion must be 1; ignored fruit are not permitted in this test")
            key = (frame, identity)
            if key in seen:
                raise ValueError(f"{prefix}: duplicate identity {identity} in frame {frame}")
            seen.add(key)
            rows.append(Observation(frame, identity, box, confidence))
    return sorted(rows, key=lambda observation: (observation.frame, observation.identity))


def pairwise_iou(first: list[Observation], second: list[Observation]) -> np.ndarray:
    if not first or not second:
        return np.zeros((len(first), len(second)), dtype=float)
    a = np.asarray([observation.box for observation in first], dtype=float)
    b = np.asarray([observation.box for observation in second], dtype=float)
    left = np.maximum(a[:, None, :2], b[None, :, :2])
    right = np.minimum(a[:, None, :2] + a[:, None, 2:], b[None, :, :2] + b[None, :, 2:])
    intersection = np.prod(np.maximum(0, right - left), axis=2)
    union = np.prod(a[:, 2:], axis=1)[:, None] + np.prod(b[:, 2:], axis=1)[None, :] - intersection
    return intersection / union


def match_frame(similarity: np.ndarray, threshold: float) -> list[tuple[int, int]]:
    """Maximise valid match count first and total IoU second."""
    if not similarity.size:
        return []
    valid = similarity >= threshold
    bonus = min(similarity.shape) + 1
    score = valid * (bonus + similarity)
    rows, columns = linear_sum_assignment(-score)
    return [(int(row), int(column)) for row, column in zip(rows, columns) if valid[row, column]]


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator / denominator) if denominator else None


def evaluate_tracking(
    ground_truth: list[Observation], predictions: list[Observation], manifest: dict[str, Any],
    *, iou_threshold: float = 0.5, allow_empty_ground_truth: bool = False,
) -> dict[str, Any]:
    frames = validate_manifest(manifest)
    if not np.isfinite(iou_threshold) or not 0 < iou_threshold <= 1:
        raise ValueError("IoU threshold must be greater than 0 and at most 1")
    if not ground_truth and not allow_empty_ground_truth:
        raise ValueError("empty ground truth cannot measure tracking correctness; annotate physical fruit first")
    allowed_frames = set(frames)
    for name, observations in (("ground truth", ground_truth), ("predictions", predictions)):
        seen = set()
        for observation in observations:
            if observation.frame not in allowed_frames:
                raise ValueError(f"{name} contains frame {observation.frame} outside the manifest")
            _positive_integer(observation.identity, f"{name} identity")
            if not all(np.isfinite(value) for value in observation.box) or observation.box[2] <= 0 or observation.box[3] <= 0:
                raise ValueError(f"{name} has an invalid bounding box")
            if (observation.frame, observation.identity) in seen:
                raise ValueError(f"{name} contains a repeated identity in one frame")
            seen.add((observation.frame, observation.identity))

    gt_ids = sorted({row.identity for row in ground_truth})
    pred_ids = sorted({row.identity for row in predictions})
    gt_index = {identity: index for index, identity in enumerate(gt_ids)}
    pred_index = {identity: index for index, identity in enumerate(pred_ids)}
    potential = np.zeros((len(gt_ids), len(pred_ids)), dtype=np.int64)
    gt_by_frame = {frame: [] for frame in frames}
    pred_by_frame = {frame: [] for frame in frames}
    for row in ground_truth:
        gt_by_frame[row.frame].append(row)
    for row in predictions:
        pred_by_frame[row.frame].append(row)
    fruit = {
        identity: {"ground_truth_id": identity, "visible_frames": 0, "matched_frames": 0,
                   "matched_ids": {}, "id_switches": 0, "fragmentations": 0,
                   "duplicate_frames": [], "last_matched_id": None, "missed_since_match": False}
        for identity in gt_ids
    }
    associations: dict[int, set[int]] = {identity: set() for identity in pred_ids}
    prediction_counts = {identity: 0 for identity in pred_ids}
    for row in predictions:
        prediction_counts[row.identity] += 1
    frame_records = []
    switch_events = []
    fragmentation_events = []
    duplicate_events = []
    matched_ious = []
    tp = fp = fn = 0
    for frame in frames:
        gt = sorted(gt_by_frame[frame], key=lambda row: row.identity)
        pred = sorted(pred_by_frame[frame], key=lambda row: row.identity)
        similarity = pairwise_iou(gt, pred)
        for g, p in zip(*np.nonzero(similarity >= iou_threshold)):
            potential[gt_index[gt[g].identity], pred_index[pred[p].identity]] += 1
        matches = match_frame(similarity, iou_threshold)
        matched_gt = {g: p for g, p in matches}
        matched_pred = {p for _, p in matches}
        tp += len(matches)
        fp += len(pred) - len(matches)
        fn += len(gt) - len(matches)
        matched_ious.extend(float(similarity[g, p]) for g, p in matches)
        for g, observation in enumerate(gt):
            record = fruit[observation.identity]
            record["visible_frames"] += 1
            if g not in matched_gt:
                if record["last_matched_id"] is not None:
                    record["missed_since_match"] = True
                continue
            predicted_id = pred[matched_gt[g]].identity
            previous = record["last_matched_id"]
            if previous is not None and predicted_id != previous:
                record["id_switches"] += 1
                switch_events.append({"frame": frame, "ground_truth_id": observation.identity,
                                      "previous_prediction_id": previous, "prediction_id": predicted_id})
            if record["missed_since_match"]:
                record["fragmentations"] += 1
                fragmentation_events.append({"frame": frame, "ground_truth_id": observation.identity})
            record["matched_frames"] += 1
            counts = record["matched_ids"]
            counts[predicted_id] = counts.get(predicted_id, 0) + 1
            record["last_matched_id"] = predicted_id
            record["missed_since_match"] = False
            associations[predicted_id].add(observation.identity)
        for p, observation in enumerate(pred):
            if p in matched_pred or not matched_gt:
                continue
            candidates = [g for g in matched_gt if similarity[g, p] >= iou_threshold]
            if not candidates:
                continue
            g = max(candidates, key=lambda index: similarity[index, p])
            identity = gt[g].identity
            # An extra box still associates its ID with this physical fruit;
            # reuse must also catch an ID that appeared as a duplicate here.
            associations[observation.identity].add(identity)
            fruit[identity]["duplicate_frames"].append(frame)
            duplicate_events.append({"frame": frame, "ground_truth_id": identity,
                                     "extra_prediction_id": observation.identity,
                                     "matched_prediction_id": pred[matched_gt[g]].identity})
        frame_records.append({"frame": frame, "gt_count": len(gt), "prediction_count": len(pred),
                              "tp": len(matches), "fp": len(pred) - len(matches), "fn": len(gt) - len(matches),
                              "matches": [{"ground_truth_id": gt[g].identity,
                                           "prediction_id": pred[p].identity,
                                           "iou": float(similarity[g, p])} for g, p in matches]})

    reused = {identity: sorted(targets) for identity, targets in associations.items() if len(targets) > 1}
    records = []
    for identity in gt_ids:
        record = fruit[identity]
        counts = record.pop("matched_ids")
        record.pop("last_matched_id")
        record.pop("missed_since_match")
        dominant_id = max(counts, key=lambda value: (counts[value], -value)) if counts else None
        dominant_count = counts.get(dominant_id, 0)
        record["prediction_ids"] = sorted(counts)
        record["matched_frames_by_prediction_id"] = {str(key): counts[key] for key in sorted(counts)}
        record["dominant_prediction_id"] = dominant_id
        record["visible_frame_recall"] = _ratio(record["matched_frames"], record["visible_frames"])
        record["dominant_id_visible_frame_coverage"] = _ratio(dominant_count, record["visible_frames"])
        record["dominant_id_matched_frame_share"] = _ratio(dominant_count, record["matched_frames"])
        record["dominant_id_prediction_purity"] = _ratio(dominant_count, prediction_counts.get(dominant_id, 0))
        record["reused_prediction_ids"] = sorted(set(counts).intersection(reused))
        record["duplicate_frames"] = sorted(set(record["duplicate_frames"]))
        failures = []
        if record["visible_frame_recall"] < 0.95:
            failures.append("visible_frame_recall_below_95_percent")
        if record["dominant_id_visible_frame_coverage"] < 0.90:
            failures.append("dominant_id_coverage_below_90_percent")
        if record["id_switches"]:
            failures.append("identity_switch")
        if record["reused_prediction_ids"]:
            failures.append("prediction_id_reused_for_another_fruit")
        if record["duplicate_frames"]:
            failures.append("simultaneous_duplicate_boxes")
        record["strict_tracking_success"] = not failures
        record["failure_reasons"] = failures
        records.append(record)

    # Each global identity assignment contributes its potential overlap count.
    # Assigning a trajectory to a dummy ID contributes zero. Maximising this sum
    # is equivalent to TrackEval's augmented minimum (IDFP + IDFN) assignment.
    idtp = 0
    if potential.size:
        assigned_gt, assigned_pred = linear_sum_assignment(-potential)
        idtp = int(potential[assigned_gt, assigned_pred].sum())
    idfn = len(ground_truth) - idtp
    idfp = len(predictions) - idtp
    successes = sum(record["strict_tracking_success"] for record in records)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    idf1 = idtp / max(1, idtp + 0.5 * idfp + 0.5 * idfn)
    success_rate = _ratio(successes, len(records))
    gate_requirements = {
        name: {"observed": value, "minimum": 0.95, "passed": value is not None and value >= 0.95}
        for name, value in (("detection_precision", precision), ("detection_recall", recall),
                            ("IDF1", idf1), ("stable_physical_identities_in_window", success_rate))
    }
    primary_threshold = iou_threshold == 0.5
    return {
        "schema_version": 1,
        "validation_status": "ground_truth_validated" if ground_truth else "reviewed_empty_sequence",
        "annotation_complete": True,
        "protocol": {
            "frame_index_base": 1, "coordinate_format": "xywh", "iou_threshold": iou_threshold,
            "all_predictions_evaluated": True, "ignored_gt_rows": 0,
            "frame_matching": "maximum valid match cardinality, then maximum total IoU",
            "id_switch": "change from last matched prediction ID, including after a missed visible frame",
            "fragmentation": "matched, missed GT-visible observation, then matched again",
            "duplicate": "unmatched extra prediction overlapping a matched GT at the IoU threshold",
            "strict_success": "visible-frame recall >=0.95; dominant-ID visible-frame coverage >=0.90; no ID switches, reused IDs or duplicate boxes",
            "idf1_reference": IDF1_REFERENCE,
            "custom_diagnostics": "detection assignment, switches, fragmentation, duplicate/reuse events and fruit success are protocol-specific; no HOTA or MOTA claim",
        },
        "counts": {"evaluated_frames": len(frames), "reviewed_empty_frames": sum(not gt_by_frame[f] for f in frames),
                   "physical_fruit": len(gt_ids), "prediction_ids": len(pred_ids),
                   "gt_observations": len(ground_truth), "prediction_observations": len(predictions)},
        "detection": {"tp": tp, "fp": fp, "fn": fn,
                      "precision": precision, "recall": recall,
                      "mean_matched_iou": float(np.mean(matched_ious)) if matched_ious else None},
        "identity": {"IDTP": idtp, "IDFP": idfp, "IDFN": idfn,
                     "IDP": idtp / max(1, idtp + idfp), "IDR": idtp / max(1, idtp + idfn),
                     "IDF1": idf1,
                     "id_switches": len(switch_events), "fragmentations": len(fragmentation_events),
                     "reused_prediction_ids": len(reused), "duplicate_observations": len(duplicate_events)},
        "fruit_tracking": {"successful": successes, "total": len(records),
                           "strict_success_rate": success_rate},
        "acceptance_gate": {
            "scope": "proposed numeric requirements for the observed window; not final full-path acceptance",
            "primary_iou_threshold": 0.5, "is_primary_threshold": primary_threshold,
            "requirements": gate_requirements,
            "numeric_window_pass": all(item["passed"] for item in gate_requirements.values()) if primary_threshold else None,
            "final_tracking_acceptance": "not_assessed",
            "pending_evidence": ["independently reviewed complete entry-to-exit cohort and entrant counts",
                                 "at least 100 independent entrants across at least three reserved clips",
                                 "representative and challenge samples reported separately",
                                 "zero verified wrong-fruit mixing in retained map-capture sequences"],
        },
        "per_fruit": records, "per_frame": frame_records,
        "events": {"id_switches": switch_events, "fragmentations": fragmentation_events,
                   "duplicates": duplicate_events, "id_reuse": {str(key): values for key, values in sorted(reused.items())}},
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_report(result: dict[str, Any], directory: str | Path) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "tracking_evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    detection = result["detection"]
    identity = result["identity"]
    fruit = result["fruit_tracking"]
    rate = f"{fruit['strict_success_rate']:.1%}" if fruit["strict_success_rate"] is not None else "not measurable (no physical fruit)"
    gate = result["acceptance_gate"]
    gate_status = "pass" if gate["numeric_window_pass"] is True else "fail" if gate["numeric_window_pass"] is False else "not assessed (sensitivity threshold)"
    lines = ["# Tracking evaluation", "", f"Validation: **{result['validation_status']}**.", "",
             f"Strict physical-fruit tracking success: **{fruit['successful']}/{fruit['total']} ({rate})**.", "",
             f"IDF1: **{identity['IDF1']:.4f}** (IDTP {identity['IDTP']}, IDFP {identity['IDFP']}, IDFN {identity['IDFN']}).",
             f"Detection matches: TP {detection['tp']}, FP {detection['fp']}, FN {detection['fn']}.",
             f"Switches {identity['id_switches']}; fragmentation events {identity['fragmentations']}; reused IDs {identity['reused_prediction_ids']}; duplicate observations {identity['duplicate_observations']}.", "",
             f"Proposed numeric window gate: **{gate_status}**. It requires >=95% detection precision, recall, IDF1 and stable physical identities at IoU 0.50. Final full-path acceptance is **not assessed**; see pending evidence in the JSON.", "",
             "A successful fruit has >=95% recall across GT-visible frames, >=90% dominant-ID coverage across those same frames, and no identity switches, reused IDs or simultaneous duplicates.", "",
             "All declared reviewed frames are evaluated, including empty frames. All prediction rows are counted without a confidence filter. Ignored GT rows are prohibited in this protocol.", "",
             "IDF1 uses all potential IoU matches and a single global trajectory assignment. Other diagnostics use the explicit custom conventions in the JSON; HOTA and MOTA are not calculated.", "",
             f"IDF1 reference: {IDF1_REFERENCE}", "",
             "| Physical fruit | Recall | Dominant coverage | Switches | Fragments | Result |", "|---|---:|---:|---:|---:|---|"]
    for record in result["per_fruit"]:
        lines.append(f"| {record['ground_truth_id']} | {record['visible_frame_recall']:.1%} | {record['dominant_id_visible_frame_coverage']:.1%} | {record['id_switches']} | {record['fragmentations']} | {'pass' if record['strict_tracking_success'] else ', '.join(record['failure_reasons'])} |")
    (directory / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--allow-empty-ground-truth", action="store_true", help="Only for explicitly reviewed empty-sequence controls; cannot measure fruit success")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be a JSON object")
        metadata = manifest.get("annotation_metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("manifest annotation_metadata must be an object")
        expected_gt_hash = metadata.get("ground_truth_sha256")
        if expected_gt_hash is not None and expected_gt_hash != _sha256(args.ground_truth):
            raise ValueError("ground truth hash differs from imported reviewed annotations; re-review and re-import changes")
        gt = read_mot(args.ground_truth, ground_truth=True)
        pred = read_mot(args.predictions, ground_truth=False)
        result = evaluate_tracking(gt, pred, manifest, iou_threshold=args.iou_threshold,
                                   allow_empty_ground_truth=args.allow_empty_ground_truth)
        result["inputs"] = {name: {"path": str(path.resolve()), "sha256": _sha256(path)} for name, path in (
            ("ground_truth", args.ground_truth), ("predictions", args.predictions), ("manifest", args.manifest))}
        write_report(result, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Tracking evaluation rejected: {exc}", file=sys.stderr)
        return 2
    print(f"Tracking evaluation written to {args.output_dir / 'tracking_evaluation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
