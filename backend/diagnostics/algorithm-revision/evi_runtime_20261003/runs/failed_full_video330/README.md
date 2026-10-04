# Full original-video API allocation failure

The original request started 2026-10-02T20:51:37.951279+02:00; it returned HTTP 500.
The captured API state reports **error at 330/515 frames**:
`Unable to allocate 1.26 MiB for an array with shape (115, 160, 9) and data type float64`. The service still returned health 200 at capture.

The midnight full-video verification target was not met. This failure concerns
runtime execution. It does not revoke the separately scored motion controls.
No completed aggregate report exists. The 256
partial track outputs cannot establish a completed grading result.

Original request, raw response (plain text despite its .json filename), validator
traceback, API traceback, execution snapshots and partial result JSON are copied.
The full partial-job image inventory is hashed; the original job remains at
`C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\results\78b4a03ccaa549de96ecd88c5efb5806`. The API error state has no failure timestamp. Original file last-write
times and capture times remain explicit proxies, not invented server timestamps.

See [summary](summary.json), [original request](original_request/request.json),
[raw response](original_request/response.json), [partial-job file hashes](partial_job_inventory.json)
and [service traceback](service/api_restart1_stderr.log).
