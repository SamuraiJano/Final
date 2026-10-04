# Deferred local update

`scripts/reload_api_when_idle.py` waits for analysis ID
`3cd9d9cd-ec24-4e82-bad4-85644b7f5dd1`. It does not stop the active
797-frame video, send cancellation requests, change tracker code, or run models.
Every poll uses GET requests and checks the recorded API/dashboard process trees,
PID creation times, commands, working directories, port 8000 ownership, source
hashes, and the previous launch record. A changed run ID, decreasing progress,
changed source or changed owned process causes an abort.

The default is read-only: after two terminal analysis/live-idle observations at
least 20 seconds apart it reports `ready_for_restart` and exits. `--check-once`
makes one GET-only observation and always exits without a restart.
`--restart-when-idle` explicitly enables the existing guarded restart helper.
The queue checks the same run ID and sources again immediately before handoff;
the existing helper repeats its ownership/source/analysis/live checks before
stopping only the recorded idle API. Vite and training are not restarted.
The new launch goes into `service_20261003/defect_maps_80`.

Optional `--completed-job-id 5582c6f789f1497abd45cfc08f2b4863` preserves the original
completed job and creates a separate derived job with coloured defect overlays
and an 80% regular-grade target, using `render_saved_defect_maps.py` and zero
model calls. The original job has old runtime `main.py` hash `76a66ac9...` and
algorithm hash `f10e8393...`. The helper requires these saved source snapshots,
the exact job ID, 797 completed frames, and the original 65% geometry setting.
It only does this after `complete`, with live inspection idle; error or cancelled
completion skips rendering. The report must exist before rendering begins.

The run-to-job binding was inferred from the sole incomplete results folder
observed while the API's single analysis slot was occupied. The status response
does not expose the saved job ID directly. Completed report and snapshot checks
reduce the chance of using the wrong job, but do not turn this inference into a
direct API identity link.

Run from the workspace using the existing virtual environment:

```powershell
.\backend\venv\Scripts\python.exe -B scripts/reload_api_when_idle.py --check-once
.\backend\venv\Scripts\python.exe -B scripts/reload_api_when_idle.py --restart-when-idle --completed-job-id 5582c6f789f1497abd45cfc08f2b4863 --expected-frames 797
```

The root agent must review and launch the second command explicitly. This helper
does not detach itself. Any background launch must use a hidden window and a
recorded PID/creation time. `state.json` is replaced atomically and `polls.jsonl`
records observations and decisions. `queue.lock` prevents two queue instances.
After a crash, a stale lock requires inspection; the helper does not delete it
automatically. Waiting is limited to two hours, with 20-second default polling.

This is a guarded, **non-atomic** restart. Another client could start a new run
between the existing helper's final status GET and process termination. The
helper does not claim this race is impossible. Do not begin another video during
the final restart handoff. Removing that race requires a reservation shared with
the production analysis lock. No such production change is made here.

CPU-only scripted tests are in `tests.txt` and `tests.json`. They use no HTTP,
start or stop no service, and request no inference. They test waiting, terminal
states, live activity, identity changes, decreasing/invalid progress, minimum
confirmation time, reset after activity, source changes, failed process
ownership, and completed job identity/frame/source/policy checks.
