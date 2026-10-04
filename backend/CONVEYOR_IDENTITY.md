# Stable fruit identity after TrackTrack

TrackTrack remains the primary tracker. D-FINE detection, segmentation, GrabCut,
surface registration, rotation estimation and grading calculations are unchanged.

The production path is now:

```text
D-FINE -> TrackTrack (raw tracker_id, actual bounding box)
       -> ConveyorIdentityManager (stable fruit_id)
       -> existing chronological view capture -> existing surface mapper
```

## Where the identity changes

`NaartjiePipeline.process_frame` calls the manager after filtering fruit-class
TrackTrack observations and before `record_tracked_detection` or
`add_tracked_detection`. The manager returns one decision per input detection,
in the same order. Its `fruit_id` is also exposed as `capture_id` for compatibility
with the existing capture interface. `views_by_id`, capture stride, observation
history and map completion all use that stable ID. Raw IDs remain in
`tracking_history.raw_track_id` and `source_tracker_ids`; saved fruit metadata
also declares `fruit_id`. The existing API's `track_id` field remains the capture
key so the GUI needs no changes.

Stable IDs start at 1, increase monotonically and are never reused within a
pipeline/session, including after completion. They are not required to equal
TrackTrack's numbers. Direct external callers of `add_tracked_detection` still
own the identity contract and should supply their already stable fruit IDs.

## Association rules

Each active/lost `FruitState` retains its current raw ID, timestamp/centre/actual
box history, recent velocity, last accepted centre and last-seen frame/time.
History is bounded. Velocity is the median of consecutive complete-box
displacements divided by their actual elapsed seconds. Clipped entry/exit boxes
do not supply the conveyor-speed estimate. Before complete motion exists, the
prior is 395.83 pixels/second downward, as supplied for the representative
recording. Confirmed complete histories update a robust running scene median;
each fruit's own measured motion takes precedence.

Predictions are `previous centre + velocity * elapsed seconds`. The main cost
is prediction error divided by fruit box size. Size, backward-jump and
scale-relative motion gates reject implausible links. Raw-ID agreement supplies
only a small preference and cannot rescue a clearly worse trajectory.
SciPy's installed linear assignment solves the one-to-one association with
unmatched alternatives. Changed raw IDs require clear competing-assignment
margins. Ambiguous evidence starts an uncertain separate fruit segment and
preserves the existing uncertainty policy; it is not silently pooled into a map.

Order validation compares only pairs whose horizontal box intervals overlap
substantially or whose centre separation is small relative to their widths.
It requires these pairs to remain local neighbours in the current observation,
their prior order to be clearly separated, and predictions to preserve that
order. It can correct a feasible pair assignment within the secondary penalty,
or reject an unresolved local reversal. It never sorts every fruit globally by y.
Fruit that separate laterally are free to cross each other's y coordinate.

Lost fruits remain eligible for the TrackTrack instance's `max_time_lost`
buffer. Returning observations must still pass the predicted-motion and
ambiguity gates. No view is synthesized during the gap. The mapper's existing
gap/rotation reliability checks still apply: stable identity does not imply
known rotation or permit interpolation of unseen skin.

## Timestamp handling

Uploaded videos pass OpenCV's decoded `CAP_PROP_POS_MSEC` after each read.
Live capture records `time.monotonic()` at image acquisition and passes that
capture timestamp, rather than the completion time of inference. If a timestamp
is absent, nonfinite, negative or does not advance, the manager falls back to
the frame gap divided by the decoded FPS (configured fallback 29.9307).
Every observation records the timestamp source. There is no 60-FPS assumption.
The supplied representative recording decodes at 29.9308014929 FPS and its first
ten PTS values are nonuniform; this was checked directly before integration.

## Default configuration and debugging

The defaults are centralized in `ConveyorIdentitySettings`. The main switches
and supplied initial motion are illustrated in
`conveyor_identity.example.json`:

```json
{
  "conveyor_identity_validation": true,
  "conveyor_direction": "top_to_bottom",
  "enable_motion_validation": true,
  "enable_order_validation": true,
  "debug_identity_overlay": false,
  "debug_identity_csv": false,
  "reference_speed_px_s": 395.83,
  "fallback_fps": 29.9307
}
```

Other centralized defaults: eight recent observations; 30-frame fallback lost
buffer, overridden by the actual TrackTrack buffer; 0.35-diameter prediction
gate plus 0.04 per extra missed frame; 0.12 ambiguity margin; 0.03 raw-ID
preference; 1.5 size ratio; 0.2-diameter backward tolerance; 0.35 horizontal
overlap or 0.6-width horizontal centre separation; 0.15-height order separation;
0.2 order penalty; at least three complete observations before scene learning;
128 scene samples. These are tunable engineering defaults, not proven accuracy
thresholds. None requires physical-distance calibration.

From the project root, before starting/restarting the backend:

```powershell
$env:FRUIT_IDENTITY_CONFIG = Join-Path (Get-Location) 'backend/conveyor_identity.example.json'
$env:FRUIT_DEBUG_IDENTITY_OVERLAY = 'true'
$env:FRUIT_DEBUG_IDENTITY_CSV = 'true'
```

The example does not need modification to enable these environment overrides.
Debug files are written inside that analysis job's result directory:
`identity_debug.mp4` and `identity_debug.csv`. Overlay boxes show `T:<raw ID>
F:<stable ID>`, the recent stable trajectory, a cross at the next nominal-frame
prediction and a correction label. Rendering uses a copy of the source pixels.
The overlay movie uses nominal FPS for playback; actual association timing and
CSV times use decoded timestamps. There is no new GUI or visible helper window.

CSV columns are frame_number, timestamp, tracker_id, fruit_id, cx, cy,
predicted_cx, predicted_cy, prediction_error, vx, vy, identity_corrected and
correction_reason. Its prediction/error describe the current observation
predicted from the prior accepted state; first observations have no prediction.
Console correction messages and debug files are disabled by default.

Set `FRUIT_CONVEYOR_IDENTITY_VALIDATION=false` (or the corresponding JSON
boolean) to restore the pre-existing version-3 `FruitIdentityGuard`. Its tests
remain available; that legacy mode intentionally splits gaps. Debugging the new
manager is available when conveyor validation is enabled.

## Standalone tracking diagnostic

The existing prediction exporter now runs the same manager as production:

```powershell
./backend/venv/Scripts/python.exe backend/export_tracking_test_predictions.py --video 'C:\Users\USER\Pictures\Camera Roll\WIN_20260818_13_05_49_Pro.mp4' --output-dir backend/diagnostics/conveyor-identity/my_run --frames 795 --device cuda --debug-overlay --debug-csv
```

Use a new output directory. Without `--detections-cache`, this runs actual
D-FINE detection and TrackTrack. With an existing verified NPZ cache, both
tracker and manager are replayed against original pixels without detector
inference. It exports raw and stable-ID predictions separately, plus per-frame
decisions, metadata, timings, configuration, source snapshots and hashes.
It does not run defect segmentation, mapping or grading.

## Files changed

- `conveyor_identity.py`: new manager, centralized settings, state, assignment,
  timing, local-order validation and optional debug writer.
- `algorithm.py`: the existing capture interface selects the new manager,
  forwards timestamps, retains raw/stable identity metadata and exposes debug
  lifecycle methods. Surface/rotation/grading functions were not edited.
- `main.py`: forwards decoded or acquisition timestamps, opens/closes debug
  output, snapshots the new source and uses the manager's effective lost buffer
  before finalization. Model-loading logic and GUI are unchanged.
- `export_tracking_test_predictions.py`: diagnostic export uses the same
  manager, timing and optional debug outputs as production.
- `conveyor_identity.example.json`: configuration example.
- `test_conveyor_identity.py`: known-ID controls and capture integration tests.
- `test_algorithm.py`: capture assertions now distinguish stable ID 1 from raw
  ID 7 while retaining the same GrabCut and TrackTrack checks.
- `test_fruit_identity.py`: the legacy guard's pipeline test explicitly selects
  legacy mode. Other legacy tests and grade-uncertainty checks remain intact.
- `CONVEYOR_IDENTITY.md`: this implementation and usage record.
- `IDENTITY_GUARD.md`: points to the new default while preserving the legacy
  guard's historical evidence.

The initial full test run had two failures/errors from the old raw-ID-equals-map-ID
assumptions. A new edge control also exposed premature scene learning from only
one complete box; scene learning now requires three complete observations.
These were corrected rather than omitting the checks. Final test and replay
evidence is retained under `diagnostics/conveyor-identity/20261004`.

Software controls establish behavior on known cases. Real-video corrections and
lower fragmentation counts do not establish true physical identity accuracy.
Use the independently annotated method in `TRACKING_TEST_METHOD.md` before
claiming an accuracy percentage, and measure mapping coverage separately.

Final checks passed **174 Python tests**, including **27 new conveyor identity
tests**, plus frontend build and lint. The representative run made 795 actual
detector calls and retained 40,334 observations. It returned 542 raw IDs and
556 stable segments, including 57 uncertain segments, 95 same-raw-ID gap
recoveries and four motion-supported raw-ID reconnections. All four concern
clipped right-edge observations and are not verified physical ID swaps.

The initial scalar implementation took 96.2 seconds for manager replay. Batched
costs, local-neighbour filtering and cached measured velocities reduced the
measured replay to 13.2 seconds (about 16.6 ms/frame), with every decision and
numeric prediction unchanged over those 40,334 observations. This is a local
development measurement, not a complete pipeline throughput guarantee. The
actual detector/debug-video run used the initial scalar version; its source
snapshots are preserved. The final optimized source was separately replayed
against the same frozen tracker outputs, decoded timestamps and original
dimensions. No detector, segmenter or mapper inference was substituted.
