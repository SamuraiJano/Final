"""Freeze a failed API attempt without changing its original outputs or service."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil

import requests

BACKEND = Path(__file__).resolve().parent
SAST = timezone(timedelta(hours=2))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def freeze():
    attempt = BACKEND / "diagnostics/api-runs/full_pixel_switch_trace_20261002"
    service = BACKEND / "diagnostics/algorithm-revision/service_20261002"
    job = BACKEND / "results/78b4a03ccaa549de96ecd88c5efb5806"
    output = BACKEND / "diagnostics/api-runs/full_pixel_switch_trace_failure_capture_20261003"
    output.mkdir(parents=True, exist_ok=False)
    captured_at = datetime.now(SAST).isoformat()
    records = []

    def copy(path, relative):
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(path)
        shutil.copy2(path, target)
        if digest(target) != before:
            raise RuntimeError(f"Source changed while copying {path}")
        records.append({"path": str(path), "copy": target.relative_to(output).as_posix(),
                        "sha256": before, "bytes": path.stat().st_size,
                        "last_write_at": datetime.fromtimestamp(path.stat().st_mtime, SAST).isoformat()})

    for path in sorted(attempt.glob("*")):
        if path.is_file():
            copy(path, Path("original_request") / path.name)
    for path in service.glob("full_pixel_switch*"):
        if path.is_file():
            copy(path, Path("validator_execution") / path.name)
    for name in ("api_restart1_stderr.log", "api_restart1_stdout.log", "launch.json",
                 "restart1.json", "runtime_config_evidence.json", "backend_algorithm.py.snapshot",
                 "backend_main.py.snapshot", "backend_dfine_segmenter.py.snapshot"):
        copy(service / "pixel_switch_trace_services" / name, Path("service") / name)
    for path in sorted(job.glob("*.snapshot")):
        copy(path, Path("partial_job") / path.name)
    for path in sorted(job.glob("*/result.json")):
        copy(path, Path("partial_job") / path.relative_to(job))

    api = {}
    for endpoint in ("health", "analysis/status"):
        response = requests.get("http://127.0.0.1:8000/api/" + endpoint, timeout=15)
        api[endpoint] = {"observed_at": datetime.now(SAST).isoformat(),
                         "http_status": response.status_code, "body": response.json()}
    state = api["analysis/status"]["body"]
    request = json.loads((attempt / "request.json").read_text(encoding="utf-8"))
    if state.get("run_id") != request["analysis_id"] or state.get("state") != "error":
        raise RuntimeError("The current API state no longer identifies this failed attempt")
    inventory = [{"path": path.relative_to(job).as_posix(), "sha256": digest(path),
                  "bytes": path.stat().st_size} for path in sorted(job.rglob("*")) if path.is_file()]
    summary = {"captured_at": captured_at, "status": "failed", "passed_execution": False,
               "algorithm_sha256": digest(job / "algorithm.py.snapshot"), "job_id": job.name,
               "request_started_at": request["started_at"], "analysis_id": request["analysis_id"],
               "video_sha256": request["video_sha256"], "frames_processed_at_last_status": state["frames_processed"],
               "frames_total": state["frames_total"], "error": state["error"], "api_observations": api,
               "response_http_status": 500,
               "response_status_evidence": "Preserved validator traceback raises HTTPError: 500 Server Error.",
               "failed_at": None, "failure_timestamp_limit": "API state/traceback record no error timestamp. Response-file last-write time is a capture proxy, not exact server failure time.",
               "deadline": "2026-10-03T00:00:00+02:00",
               "deadline_full_video_verification_met": False,
               "final_aggregate_report_exists": (job / "report.json").is_file(),
               "partial_track_result_count": len(list(job.glob("*/result.json"))),
               "partial_job_directory": str(job), "source_records": records,
               "scope": "Failed full-video execution, not a motion-accuracy failure. Partial outputs are not a completed grading report. Health 200 does not imply successful analysis."}
    for name, value in (("summary.json", summary), ("partial_job_inventory.json", inventory)):
        (output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    copy(Path(__file__), "freeze_failed_api_evidence.py")
    text = f"""# Full original-video API allocation failure

The original request started {request['started_at']}; it returned HTTP 500.
The captured API state reports **error at {state['frames_processed']}/{state['frames_total']} frames**:
`{state['error']}`. The service still returned health 200 at capture.

The midnight full-video verification target was not met. This failure concerns
runtime execution. It does not revoke the separately scored motion controls.
No completed aggregate report exists. The {summary['partial_track_result_count']}
partial track outputs cannot establish a completed grading result.

Original request, raw response (plain text despite its .json filename), validator
traceback, API traceback, execution snapshots and partial result JSON are copied.
The full partial-job image inventory is hashed; the original job remains at
`{job}`. The API error state has no failure timestamp. Original file last-write
times and capture times remain explicit proxies, not invented server timestamps.

See [summary](summary.json), [original request](original_request/request.json),
[raw response](original_request/response.json), [partial-job file hashes](partial_job_inventory.json)
and [service traceback](service/api_restart1_stderr.log).
"""
    (output / "README.md").write_text(text, encoding="utf-8")
    manifest = output / "SHA256SUMS.txt"
    manifest.write_text("".join(f"{digest(path)}  {path.relative_to(output).as_posix()}\n"
                               for path in sorted(output.rglob("*")) if path.is_file()), encoding="utf-8")
    print(json.dumps({"output": str(output), "summary": {key: summary[key] for key in
                     ("status", "frames_processed_at_last_status", "frames_total", "partial_track_result_count", "failed_at")}}, indent=2))


if __name__ == "__main__":
    freeze()
