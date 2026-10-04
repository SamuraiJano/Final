"""Verify test tooling; this does not certify real-video tracking correctness."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

folder = Path(__file__).resolve().parent
backend = folder.parents[2]
records = []
checks = [
    ("python_checks", [sys.executable, "-m", "unittest", "test_tracking_test_preparation",
                       "test_tracking_annotation_import", "test_tracking_evaluation", "test_tracking_prediction_export",
                       "test_tracking", "test_entry_tracking", "test_fruit_identity", "-v"], 0),
    ("annotation_ui_checks", ["node", "test_tracking_annotation_ui.mjs"], 0),
    ("unreviewed_pilot_rejection", [sys.executable, "evaluate_tracking_test.py",
                                    "--ground-truth", str(folder / "ground_truth.csv"),
                                    "--predictions", str(folder / "predictions.csv"),
                                    "--manifest", str(folder / "manifest.json"),
                                    "--output-dir", str(folder / "unreviewed_evaluation")], 2),
]
for name, command, expected in checks:
    result = subprocess.run(command, cwd=backend, capture_output=True, text=True)
    (folder / f"{name}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    passed = result.returncode == expected
    records.append({"name": name, "expected_exit_code": expected, "exit_code": result.returncode,
                    "passed": passed, "log": f"{name}.txt"})
    print(f"{name}: {'PASS' if passed else 'FAIL'} (exit {result.returncode})", flush=True)
    if not passed:
        print(result.stdout + result.stderr)
manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
report = {
    "status": "tools_verified" if all(record["passed"] for record in records) else "tool_failure",
    "tracking_correctness": "not_measured; independent real-video annotations remain pending",
    "pilot_frames": len(manifest["frames"]), "annotation_complete": manifest["annotation_complete"],
    "checks": records,
    "algorithm_sha256": hashlib.sha256((backend / "algorithm.py").read_bytes()).hexdigest(),
    "tool_sha256": {name: hashlib.sha256((backend / name).read_bytes()).hexdigest() for name in
                    ("prepare_tracking_test.py", "import_tracking_annotations.py", "evaluate_tracking_test.py",
                     "tracking_annotation.html", "TRACKING_TEST_METHOD.md", "export_tracking_test_predictions.py")},
}
(folder / "tool_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
raise SystemExit(0 if report["status"] == "tools_verified" else 1)
