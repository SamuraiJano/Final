# Original-video runtime retry, 3 October 2026

The API and dashboard remained operational throughout one full original-video validation. The saved job is `ea6e595b8f3f45f2b5edfda8dafff3f2`; the analysis request ID is `e40c363cba5d4093ab647a438b1cbe96`. The parent validation client processed 515 distinct frames with no duplicate frame indices and saved 474 inspection records: 2 Class 1 and 472 requiring review. These counts describe algorithm/model outputs and do not establish manually verified grading accuracy or the number of unique physical fruit. Repeated analyses remain separate history records.

The 17.3-second original clip took approximately 37.4 minutes to process. This is an offline runtime test; real-time operation was not demonstrated. The complete API proof is in [the validator summary](../../../api-runs/full_pixel_switch_runtime_20261003/summary.json). The original saved output is [report.json](../../../../results/ea6e595b8f3f45f2b5edfda8dafff3f2/report.json).

## Service source and launch

The launcher verified these approved production source hashes before starting the API:

- `backend/algorithm.py`: `50bdd78eafcc5581d0368353c9996c2f95823c69f734dac6f778dc82f22c815d`
- `backend/main.py`: `4c0b69d815164c9e4745af72a69880a417ee6b940cc1792027be4b31e775cfdb`

[launch.json](launch.json) records full source and model hashes, retained source snapshots, hidden launch flags, timestamps, process trees, child environment settings and initial health. The API was started first as a detached direct uvicorn process (wrapper PID 17328, worker 21712). A separate Node manager (39332) then attached to that API and started Vite (32188). The dashboard is served at `http://localhost:5173`; the API listens at `http://127.0.0.1:8000`. These services were left running after validation.

[ready_after_validation.json](ready_after_validation.json) verifies at 13:14:53 SAST that both owned service trees were still alive, the frontend returned HTTP 200, API/CUDA/model health was ready, analysis was complete, and every launched source file still matched its startup SHA256. This read-only check did not request or cancel analysis.

The launch changed only child environment variables: `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, unbuffered/no-bytecode Python settings, and `YOLO_CONFIG_DIR` pointing to the writable workspace directory `backend/runtime/ultralytics`. It did not change a global shell profile or replace model weights. The separate Node manager owns Vite, so Refresh backend is intentionally disabled (`managed=false`).

The reusable launcher is [scripts/start_detached_services.py](../../../../../scripts/start_detached_services.py). Run it from the workspace with both expected SHA256 values and an unused `--folder` under `backend/diagnostics`. It refuses occupied service ports and mismatched source hashes; it does not kill an existing service or start analysis. The launch used this command:

```powershell
.\backend\venv\Scripts\python.exe -B scripts/start_detached_services.py --expected-algorithm-sha256 50bdd78eafcc5581d0368353c9996c2f95823c69f734dac6f778dc82f22c815d --expected-main-sha256 4c0b69d815164c9e4745af72a69880a417ee6b940cc1792027be4b31e775cfdb
```

[Launcher/monitor control checks](../launcher_checks/report.json) used mocked control states to verify hash rejection, bounded monitoring and terminal-state handling. Those control checks are separate from the actual full-video/API/UI evidence below.

## Actual dashboard evidence

[ui_progress/report.json](ui_progress/report.json) records the running API and real dashboard at frames 140–150/515. Its displayed quality counts belong to the previous completed report. No API responses were mocked in this capture.

[ui_completed/report.json](ui_completed/report.json) checks the exact final saved job and approved algorithm hash against the actual Vite/API dashboard. It records zero JavaScript page errors and GET-only browser API requests. The browser used an isolated headless Edge session with no user profile. Choosing the local video supplied a preview only; capture did not upload, request, stop or cancel an analysis.

- [Latest run](ui_completed/latest_run.png): 474 records, 2 Class 1, 472 Review.
- [All saved runs](ui_completed/all_saved_runs.png): six reports, 2,061 records, 17 Class 1 and 2,044 Review. Historical reports were preserved.
- [Class 1 filter](ui_completed/class1_filter.png): both graded records are accessible through the filter.
- [Fruit 98 inspection](ui_completed/fruit_098_inspection.png): loaded surface map, 85.2% observed surface, 4.5% predicted defects, first tracked frame 51, last tracked frame 138, and 88 tracked frames.
- [Fruit 98 entry and last seen](ui_completed/fruit_098_entry_and_last_seen.png): actual retained edge crops from frames 51 and 138. The narrow crop shape reflects the partially visible fruit at the image boundary.

The capture source is preserved separately in each UI evidence folder and its SHA256 is recorded in the corresponding report. The completed capture checked the actual report download link and loaded map/edge images.

## Runtime resource evidence

[resource_samples.jsonl](resource_samples.jsonl) contains 94 fsynced samples taken by a detached Python requests/psutil monitor, normally every 25 seconds. GPU readings came from hidden `nvidia-smi`. Only recorded API/dashboard process trees were inspected; unrelated process command lines were not collected. The monitor had a four-hour upper bound, exited normally after completion plus a final sample two seconds later, and did not stop services or cancel inference. See [monitor_summary.json](monitor_summary.json).

[resource_summary.json](resource_summary.json) reports minimum sampled available RAM of 8,290,611,200 bytes (7.72 GiB), maximum sampled owned API private memory of 3,621,527,552 bytes (3.37 GiB), and maximum OS-reported API worker peak RSS of 2,601,226,240 bytes (2.42 GiB). At the final sample, the API worker RSS was 1,654,358,016 bytes (1.54 GiB), private memory was 2,753,732,608 bytes (2.56 GiB), and available system RAM was 9,439,019,008 bytes (8.79 GiB). Owned dashboard private memory stayed below 267,300,864 bytes (0.25 GiB).

Total sampled GPU usage peaked at 1,468 MiB and remained at that level in the final sample. GPU memory was not shown returning to baseline. The measurements document runtime resources, progress and the observed reduction in CPU memory near completion. They are not a grading-accuracy measurement. Sampling can miss short peaks; system RAM and total GPU usage include other applications.

The resource figure was visually inspected and exported as [300-dpi PNG](resource_usage.png), [vector PDF](resource_usage.pdf) and [SVG](resource_usage.svg). [summarize_resources.py](summarize_resources.py) reproduces the summary and plot from the settled JSONL log.

API/dashboard stdout logs can continue receiving requests while the services remain alive. A report package should retain a bounded copy with its own capture timestamp and file hashes, rather than assume live logs will remain unchanged.
