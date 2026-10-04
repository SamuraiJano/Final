"""Import independent manual physical-fruit labels into a prepared dataset.

The input is an annotation bundle exported by the blind annotation page. This
module validates its structure and provenance; it cannot establish that a human
assigned the correct physical identity. Prediction files are never modified.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any


class AnnotationError(ValueError):
    """An annotation bundle is inconsistent with its prepared dataset."""


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AnnotationError(f"{field} must be a positive integer")
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnnotationError(f"{field} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise AnnotationError(f"{field} must be a finite number")
    return value


def _frame_numbers(manifest: dict[str, Any]) -> set[int]:
    records = manifest.get("frames")
    if not isinstance(records, list) or not records:
        raise AnnotationError("manifest.frames must be a nonempty list")
    numbers = []
    for position, record in enumerate(records):
        if isinstance(record, dict):
            number = record.get("frame", record.get("local_frame"))
        else:
            number = record
        numbers.append(_positive_int(number, f"manifest.frames[{position}]"))
    if len(numbers) != len(set(numbers)):
        raise AnnotationError("manifest frame numbers must be unique")
    if set(numbers) != set(range(1, len(numbers) + 1)):
        raise AnnotationError("manifest frames must use consecutive local numbers 1..N")
    return set(numbers)


def validate_bundle(manifest: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate labels without reading or consulting tracker predictions."""
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        raise AnnotationError("manifest must have schema_version 1")
    if not isinstance(bundle, dict) or type(bundle.get("schema_version")) is not int or bundle.get("schema_version") != 1:
        raise AnnotationError("annotation bundle must have schema_version 1")
    dataset_id = manifest.get("dataset_id")
    if not isinstance(dataset_id, str) or not re.fullmatch(r"[0-9a-f]{64}", dataset_id):
        raise AnnotationError("manifest.dataset_id must be a SHA-256 hexadecimal string")
    if bundle.get("dataset_id") != dataset_id:
        raise AnnotationError("annotation dataset_id does not match the prepared dataset")
    width = _positive_int(manifest.get("width"), "manifest.width")
    height = _positive_int(manifest.get("height"), "manifest.height")
    frame_numbers = _frame_numbers(manifest)

    annotator = bundle.get("annotator")
    if not isinstance(annotator, str) or not annotator.strip():
        raise AnnotationError("annotator must be a nonblank name or stable identifier")
    reviewed = bundle.get("reviewed_frames")
    if not isinstance(reviewed, list):
        raise AnnotationError("reviewed_frames must be a list")
    reviewed_numbers = [_positive_int(value, "reviewed frame") for value in reviewed]
    reviewed_set = set(reviewed_numbers)
    if len(reviewed_set) != len(reviewed_numbers):
        raise AnnotationError("reviewed_frames must not contain duplicates")
    if not reviewed_set.issubset(frame_numbers):
        raise AnnotationError("a reviewed frame is absent from the manifest")

    unresolved = bundle.get("unresolved_annotations")
    if not isinstance(unresolved, list):
        raise AnnotationError("unresolved_annotations must be a list")
    unresolved_rows = []
    for position, issue in enumerate(unresolved):
        if not isinstance(issue, dict):
            raise AnnotationError(f"unresolved_annotations[{position}] must be an object")
        frame = _positive_int(issue.get("frame"), "unresolved frame")
        if frame not in frame_numbers:
            raise AnnotationError("an unresolved frame is absent from the manifest")
        reason = issue.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise AnnotationError("each unresolved annotation needs a nonblank reason")
        unresolved_rows.append({"frame": frame, "reason": reason.strip()})

    raw_rows = bundle.get("rows")
    if not isinstance(raw_rows, list):
        raise AnnotationError("rows must be a list of ten-field MOT rows")
    identities, seen, rows = set(), set(), []
    for position, row in enumerate(raw_rows):
        if not isinstance(row, list) or len(row) != 10:
            raise AnnotationError(f"rows[{position}] must contain exactly ten values")
        frame = _positive_int(row[0], f"rows[{position}].frame")
        physical_id = _positive_int(row[1], f"rows[{position}].physical_id")
        if frame not in frame_numbers:
            raise AnnotationError(f"rows[{position}] refers to a frame absent from the manifest")
        if (frame, physical_id) in seen:
            raise AnnotationError(f"physical ID {physical_id} has two boxes in frame {frame}")
        seen.add((frame, physical_id))
        x, y, w, h = [_number(value, f"rows[{position}].bbox") for value in row[2:6]]
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise AnnotationError(f"rows[{position}] must describe a positive visible box within the image")
        suffix = [_number(value, f"rows[{position}].MOT suffix") for value in row[6:]]
        if suffix != [1.0, -1.0, -1.0, -1.0]:
            raise AnnotationError(f"rows[{position}] must end with 1,-1,-1,-1")
        identities.add(physical_id)
        # Preserve integer coordinates as integers in the resulting CSV.
        rows.append([frame, physical_id, *row[2:6], 1, -1, -1, -1])

    rows.sort(key=lambda row: (row[0], row[1]))
    complete = reviewed_set == frame_numbers and not unresolved_rows and bool(rows)
    return {
        "rows": rows,
        "annotation_complete": complete,
        "annotator": annotator.strip(),
        "reviewed_frames": sorted(reviewed_set),
        "unresolved_annotations": unresolved_rows,
        "total_frames": len(frame_numbers),
        "reviewed_frame_count": len(reviewed_set),
        "labelled_unreviewed_frames": sorted({row[0] for row in rows} - reviewed_set),
        "labelled_observation_count": len(rows),
        "physical_fruit_count": len(identities),
        "unresolved_count": len(unresolved_rows),
    }


def _stage(path: Path, payload: bytes) -> Path:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        stream.write(payload)
        temporary = Path(stream.name)
    return temporary


def import_annotations(dataset: Path, annotations: Path) -> dict[str, Any]:
    """Write validated ground_truth.csv and annotation state into manifest.json."""
    dataset = Path(dataset).resolve()
    manifest_path = dataset / "manifest.json"
    ground_truth_path = dataset / "ground_truth.csv"
    annotations = Path(annotations).resolve()
    if not dataset.is_dir() or not manifest_path.is_file():
        raise AnnotationError("dataset must be a prepared directory containing manifest.json")
    if manifest_path.is_symlink() or ground_truth_path.is_symlink():
        raise AnnotationError("dataset manifest and ground-truth targets must not be symbolic links")
    if annotations in (manifest_path, ground_truth_path):
        raise AnnotationError("the input annotation bundle cannot be an output file")
    original_manifest_bytes = manifest_path.read_bytes()
    annotation_bytes = annotations.read_bytes()
    try:
        manifest = json.loads(original_manifest_bytes)
        bundle = json.loads(annotation_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise AnnotationError(f"invalid JSON: {error}") from error
    validated = validate_bundle(manifest, bundle)
    csv_buffer = io.StringIO(newline="")
    csv.writer(csv_buffer, lineterminator="\n").writerows(validated["rows"])
    csv_bytes = csv_buffer.getvalue().encode("utf-8")
    metadata = {key: value for key, value in validated.items() if key not in ("rows", "annotation_complete")}
    metadata.update({
        "bundle_sha256": hashlib.sha256(annotation_bytes).hexdigest(),
        "ground_truth_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "imported_at_utc": datetime.now(timezone.utc).isoformat(),
        "label_source": "independent manual annotation bundle",
        "limitation": "Import validates format and declared review completeness, not human identity correctness.",
    })
    updated = dict(manifest)
    updated["annotation_complete"] = validated["annotation_complete"]
    updated["reviewed_frames"] = validated["reviewed_frames"]
    updated["unresolved_annotations"] = validated["unresolved_annotations"]
    updated["annotation_metadata"] = metadata
    new_manifest_bytes = (json.dumps(updated, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    old_ground_truth = ground_truth_path.read_bytes() if ground_truth_path.exists() else None
    staged = []
    replaced_ground_truth = False
    try:
        staged_csv = _stage(ground_truth_path, csv_bytes)
        staged.append(staged_csv)
        staged_manifest = _stage(manifest_path, new_manifest_bytes)
        staged.append(staged_manifest)
        os.replace(staged_csv, ground_truth_path)
        replaced_ground_truth = True
        os.replace(staged_manifest, manifest_path)
    except BaseException:
        if replaced_ground_truth:
            if old_ground_truth is None:
                ground_truth_path.unlink(missing_ok=True)
            else:
                rollback = _stage(ground_truth_path, old_ground_truth)
                os.replace(rollback, ground_truth_path)
        raise
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)
    return {
        "dataset": str(dataset),
        "dataset_id": manifest["dataset_id"],
        "annotation_complete": validated["annotation_complete"],
        **metadata,
        "ground_truth": str(ground_truth_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = import_annotations(args.dataset, args.annotations)
    except (AnnotationError, OSError) as error:
        parser.exit(2, f"Annotation import rejected: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
