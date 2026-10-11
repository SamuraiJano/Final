# Tracking performance

Open **Tracking performance** in the dashboard. New video and live runs collect
raw TrackTrack IDs, box centres, frame numbers, timestamps and measured detection
+ tracking time automatically. Detection, association, identity correction,
view selection, masks and grading retain their existing logic.

## Set the inspection region once

Expand **Conveyor tracking region** and enter its left, top, right and bottom
edges as percentages of the camera image. Select the actual travel direction and
click **Apply for future runs**. The application initially uses its existing
top-to-bottom conveyor direction, including an environment-configured override.
It flags predominantly opposite observed motion.

There was no calibrated conveyor rectangle in this repository. Spatial metrics
therefore remain unavailable until a region is chosen. The form's initial
0 / 10 / 100 / 90 values are a suggestion, not physical calibration. Use the
actual valid single-lane inspection area. Parallel lanes, overtaking, large
camera motion or an incorrect region invalidate the crossing-order assumption.

A run freezes its starting configuration. Changing the settings does not mix
coordinate systems within an active run. **Recalculate this run** replays the
recorded boxes and IDs after inspection finishes; it performs no model inference
and preserves that run's other measurement settings. Older reports without the
new observation journal display “This saved run predates tracking metrics”.

Enable **Show processed IDs and 10% guides** to see the matching processed frame
with raw IDs above boxes and guides oriented along the selected direction.
This preview updates up to five times per second; measurement still runs on every
processed frame. In live mode, its frame counter refers to processed camera
frames, which can differ from the camera's capture-frame count.

## Measurements

- Checkpoints default to 0, 1, …, 100%. Box centres are projected along the
  selected direction within the configured rectangle. Crossings are interpolated
  between consecutive processed observations of the same raw ID, with a default
  maximum elapsed gap of 0.5 seconds. Missing observations and longer live gaps
  are not interpolated. Each ID crosses each checkpoint at most once; backwards
  jitter cannot inflate coverage.
- **ID Continuity** is `100 × completed IDs / valid entering IDs`. A valid entry
  requires an observed forward crossing of 0%; completion requires the same raw
  ID at every checkpoint through 100%. IDs already inside when recording starts
  and late detections with no observed entry are excluded from the denominator.
  Unfinished entering tracks remain in this requested denominator and are shown
  separately. Thus a stopped run's overall continuity can be lower without those
  unfinished tracks being declared lost.
- For each adjacent region, **Regional ID Continuity** is
  `100 × intersection(start IDs, end IDs) / start IDs`. Regions with no start IDs
  are unavailable. A comparison awaiting an unfinished ID's next crossing is
  also unavailable; it is not treated as a failure at the end of a recording.
  Mean, minimum and pass rate use only evaluated regions.
- A **regional pass** requires 100% continuity and zero order inversions. Crossing
  order uses interpolated frame numbers. Tied crossings are excluded from pair
  comparisons. Order consistency is the percentage of comparable common-ID
  pairs whose order is retained; it is unavailable with no comparable pairs.
- **Possible ID Swaps** counts pair-order inversion observations between adjacent
  checkpoints. Repeated reversals of one pair can produce multiple observations.
  This is evidence of a possible swap under the single-lane assumption, not a
  confirmed physical-identity error.
- **ID Fragmentations** are suspected replacements: a missing ID last seen inside
  the region and a newly appearing interior ID within ten processed frames, near
  the old ID's centre predicted from its latest measured motion. The distance
  gate is 0.75 of the larger box dimension. Ambiguous nearby candidates are
  rejected unless the nearest has a distance advantage above 0.25 box dimensions.
  This heuristic never merges raw IDs or repairs checkpoint histories.
- **Lost Tracks** counts valid entering IDs last seen inside the region and absent
  for more than the configured grace period, default 30 processed frames, before
  crossing 100%. Ending a run does not advance the clock or force a loss. A raw
  ID returning later removes its earlier provisional loss. Fragmentation and
  loss counts can overlap because they describe different aspects of raw IDs.
- **Mid-region New IDs** first appear beyond the 5% entry and exit bands after
  recording begins. They can indicate fragmentation or delayed detection;
  initial visible IDs are left censored and do not create these events.
- **Processing FPS** is timed frames divided by measured detection + tracking
  seconds. Average time is the same duration divided by timed frames in ms.
  Measurement surrounds the existing detector's `track()` call and conversion
  of its fruit output. It excludes capture, identity correction, segmentation,
  mapping, waiting, metrics storage and preview drawing. It is not camera FPS or
  the application's full inspection throughput. Empty detection frames count.

Per-track coverage sums adjacent checkpoint intervals observed under that raw
ID; it is not just the distance between the first and last checkpoint. The event
table and searchable per-ID details come from backend calculations. IDs here are
raw TrackTrack IDs, which can differ from corrected fruit/capture IDs elsewhere
in the grading dashboard.

These application-specific measurements have no manually annotated tracking
ground truth. They are not HOTA, IDF1, MOTA, or verified tracking accuracy.

## Storage and exports

Each new run writes to `backend/results/<job_id>/`:

| File | Contents |
| --- | --- |
| `tracking_config.json` | Frozen region, direction and measurement settings |
| `tracking_observations.jsonl` | One raw observation record per processed frame, including empty frames and measured timing |
| `tracking_metrics.json` | Summary, regional results, events and per-ID details |
| `tracking_summary.csv` | Scalar measurements, run ID, tracker, region coordinates, direction and interval |
| `region_continuity.csv` | Start/end counts, intersection, continuity, order consistency, inversions, missing/new IDs, pass and pending status |
| `checkpoint_crossings.csv` | Checkpoint, raw ID, fractional crossing frame, timestamp and centre coordinates in source-image pixels |
| `tracking_events.csv` | Frame, position, event type, raw IDs and description |

CSV links export the selected run. During collection they save a current
snapshot; final CSVs are written automatically. Blank numerical fields mean
unavailable, not zero. List fields use JSON arrays. Configuration for future runs
is stored in ignored local state at `backend/runtime/tracking_metrics_config.json`.
The existing upload cancellation policy still discards the cancelled run's
output folder; it does not create a successful report.

## Implementation and verification

`tracking_metrics.py` owns the checkpoint calculations, events, storage and
exports. `NaartjiePipeline.process_frame` passes its existing fruit-filtered raw
output to this observer before identity correction, so correction cannot conceal
raw-ID fragmentation. `main.py` creates a new collector for each video/live run,
exposes run/config/export endpoints and renders the processed preview.
`src/TrackingPerformance.jsx` formats backend values and renders the chart;
it does not recalculate tracking statistics.

Run the backend suite from `backend`:

```powershell
venv/Scripts/python.exe -B -m unittest discover -s . -p 'test_*.py'
```

From the workspace root, run `npm run build`, `npm run lint`, and the isolated
headless UI check:

```powershell
backend/venv/Scripts/python.exe -B scripts/check_tracking_metrics_ui.py
```

The browser check uses the installed local Playwright tools and headless Edge,
isolated test data and temporary configuration. It checks cards, graph hover,
events, per-ID inspection, downloads, region replay, mobile overflow and reset.

`validate_tracking_metrics.py` additionally replays the original video's retained
40,334 raw observations across 795 frames and compares instrumented pipeline
state with the frozen pre-feature algorithm on 32 source frames. Its demonstration
region is explicitly uncalibrated. It leaves processing FPS unavailable because
the older observations lack per-frame detection + tracking time. The diagnostic
replay does not modify the original report or publish a tracking-accuracy claim.
Evidence is in `diagnostics/tracking-performance/`.
