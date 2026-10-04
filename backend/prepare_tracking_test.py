"""Freeze consecutive, unannotated video frames and cached tracking predictions.

This prepares an independent human tracking test. It does not make ground truth
from tracker output, or rerun the detector. The generated annotator is blind to
predicted boxes and IDs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from datetime import datetime, timezone

import cv2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prediction_rows(cache: list, start: int, end: int) -> list[list]:
    """Convert original zero-based xyxy cache to local one-based MOT rows."""
    by_frame = {}
    for record in cache:
        frame = record.get("frame")
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("Cache frame must be a nonnegative integer")
        if frame in by_frame:
            raise ValueError(f"Duplicate cache frame {frame}")
        by_frame[frame] = record.get("tracks", [])
    missing = set(range(start, end + 1)) - by_frame.keys()
    if missing:
        raise ValueError(f"Missing cached frames: {sorted(missing)[:10]}")
    result = []
    for original in range(start, end + 1):
        identifiers = set()
        for row in by_frame[original]:
            if len(row) < 7:
                raise ValueError("Cache rows require x1,y1,x2,y2,id,confidence,class")
            x1, y1, x2, y2, identity, confidence, class_id = map(float, row[:7])
            if not all(math.isfinite(value) for value in (x1, y1, x2, y2, identity, confidence, class_id)):
                raise ValueError("Nonfinite tracking row")
            if identity != int(identity) or identity <= 0 or x2 <= x1 or y2 <= y1:
                raise ValueError("Invalid tracking ID or box")
            if identity in identifiers:
                raise ValueError(f"Repeated prediction ID within cache frame {original}")
            identifiers.add(identity)
            # Preserve actual detector boxes, including small image-edge overshoot.
            result.append([original - start + 1, int(identity), x1, y1,
                           x2 - x1, y2 - y1, confidence, -1, -1, -1])
    return result


def prepare(video: Path, predictions: Path, output: Path, start: int, end: int) -> dict:
    if start < 0 or end < start:
        raise ValueError("Require 0 <= start-frame <= end-frame (inclusive)")
    if output.exists():
        raise FileExistsError(f"Use a new output directory: {output}")
    cache = json.loads(predictions.read_text(encoding="utf-8"))
    if not isinstance(cache, list):
        raise ValueError("Predictions must be the cached [{frame,tracks}, ...] JSON")
    rows = prediction_rows(cache, start, end)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {video}")
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if width <= 0 or height <= 0 or not math.isfinite(fps) or fps <= 0:
            raise ValueError("Invalid video dimensions or FPS")
        video_hash = sha256_file(video)
        prediction_hash = sha256_file(predictions)
        provenance = predictions.parent / "report.json"
        try:
            cached_report = json.loads(provenance.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            cached_report = None
        if isinstance(cached_report, dict):
            recorded_video = cached_report.get("input_sha256", {}).get("video")
            if recorded_video and recorded_video != video_hash:
                raise ValueError("Cached tracker provenance belongs to a different source video")
        identity = hashlib.sha256(
            f"{video_hash}:{prediction_hash}:{start}:{end}:full_frame:v1".encode()
        ).hexdigest()
        output.mkdir(parents=True)
        images = output / "frames"
        images.mkdir()
        frame_hashes = {}
        # Decode sequentially to retain exact original frame indexing.
        for original in range(end + 1):
            ok, image = capture.read()
            if not ok:
                raise ValueError(f"Video ends before requested original frame {original}")
            if original < start:
                continue
            local = original - start + 1
            path = images / f"{local:06d}.jpg"
            if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 97]):
                raise OSError(f"Cannot save {path}")
            frame_hashes[str(local)] = sha256_file(path)
    finally:
        capture.release()
    with (output / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream).writerows(rows)
    (output / "ground_truth.csv").write_text("", encoding="utf-8")
    manifest = {
        "schema_version": 1, "dataset_id": identity,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "video": str(video.resolve()), "source_sha256": video_hash,
        "prediction_cache": str(predictions.resolve()), "prediction_cache_sha256": prediction_hash,
        "prediction_csv_sha256": sha256_file(output / "predictions.csv"),
        "prediction_provenance": cached_report,
        "source_frame_index_base": 0, "source_start_frame": start, "source_end_frame": end,
        "frame_index_base": 1, "coordinate_format": "xywh",
        "frames": list(range(1, end - start + 2)),
        "width": width, "height": height, "fps": fps,
        "roi_xyxy": [0, 0, width, height], "scope": "all visible fruit in full frame",
        "frame_image_sha256": frame_hashes,
        "annotation_complete": False, "reviewed_frames": [], "unresolved_annotations": [],
        "evaluation_role": "development pilot; existing video has been inspected during development",
        "prediction_role": "historical cached tracker outputs; not a fresh run of current production",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with (output / "physical_cohorts.csv").open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream).writerow([
            "physical_id", "first_visible_frame", "last_visible_frame", "entry_frame", "exit_frame",
            "left_censored", "right_censored", "unresolved_identity", "reviewer", "notes",
        ])
    template = Path(__file__).with_name("tracking_annotation.html").read_text(encoding="utf-8")
    annotation_metadata = {key: manifest[key] for key in
                           ("schema_version", "dataset_id", "frames", "width", "height", "fps", "source_start_frame")}
    encoded = json.dumps(annotation_metadata).replace("<", "\\u003c")
    (output / "annotate.html").write_text(template.replace("__DATASET_JSON__", encoded), encoding="utf-8")
    (output / "README.txt").write_text(
        "Open annotate.html in a browser. Assign independent physical-fruit IDs from the ORIGINAL images.\n"
        "Draw every visible fruit on every frame, including partial edge fruit. Review every frame.\n"
        "Do not use predictions.csv while annotating. Resolve uncertainty or record it before scoring.\n"
        "Export annotation_bundle.json, then import it with backend/import_tracking_annotations.py.\n"
        "Labels start EMPTY. This is a prepared test, not a measured tracking result.\n"
        "See backend/TRACKING_TEST_METHOD.md for definitions, commands and independent review.\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-frame", type=int, default=0, help="Original zero-based frame, inclusive")
    parser.add_argument("--end-frame", type=int, required=True, help="Original zero-based frame, inclusive")
    args = parser.parse_args()
    try:
        manifest = prepare(args.video, args.predictions, args.output_dir, args.start_frame, args.end_frame)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"dataset": str(args.output_dir.resolve()), "frames": len(manifest["frames"]),
                      "annotation_complete": False, "dataset_id": manifest["dataset_id"]}, indent=2))


if __name__ == "__main__":
    main()
