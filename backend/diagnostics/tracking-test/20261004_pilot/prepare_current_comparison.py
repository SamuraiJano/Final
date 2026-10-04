"""Align freshly replayed tracker outputs to this pilot's frozen local frames."""
import csv
import hashlib
import json
from pathlib import Path
import sys

folder = Path(__file__).resolve().parent
backend = folder.parents[2]
sys.path.insert(0, str(backend))
from prepare_tracking_test import prediction_rows

source = backend / "diagnostics/tracking-ground-truth/current_tracker_20261004"
manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
report = json.loads((source / "report.json").read_text(encoding="utf-8"))
assert report["input_sha256"]["video"] == manifest["source_sha256"], "Different video"
assert report["source_start_frame"] == manifest["source_start_frame"] == 0, "Different start frame"
assert report["source_end_frame"] == manifest["source_end_frame"] == 180, "Different end frame"
assert (report["width"], report["height"]) == (manifest["width"], manifest["height"]), "Different image dimensions"
outputs = {}
for name, cached_name in (("raw", "tracking.json"), ("capture", "capture_tracking.json")):
    payload = (source / cached_name).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == report["outputs_sha256"][cached_name], "Changed export"
    rows = prediction_rows(json.loads(payload), 0, 180)
    target = folder / f"predictions_current_{name}.csv"
    with target.open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream).writerows(rows)
    outputs[name] = {"file": target.name, "observations": len(rows),
                     "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
provenance = {"mode": report["mode"], "source_report": str((source / "report.json").resolve()),
              "source_report_sha256": hashlib.sha256((source / "report.json").read_bytes()).hexdigest(),
              "source_video_sha256": manifest["source_sha256"], "source_start_frame": 0, "source_end_frame": 180,
              "actual_detector_inference_calls": report["actual_detector_inference_calls"],
              "outputs": outputs,
              "status": "predictions_prepared; physical identity ground truth remains pending"}
(folder / "candidate_predictions.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
print(json.dumps(provenance, indent=2))
