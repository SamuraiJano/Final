# Standalone naartjie tracker comparison

This is the main experiment for comparing tracker choices. The existing regional
Tracking Performance journal stays separate; the comparison does not import it,
the application pipeline, identity correction, segmentation, view selection or
grading. Running an experiment never selects a production tracker.

The [official Ultralytics tracking documentation](https://docs.ultralytics.com/modes/track/)
links **Which Object Tracker Performs Better? | Speed, FPS & ID Stability |
Ultralytics YOLO26** ([video](https://www.youtube.com/watch?v=ZsxHIN2PoiY)).
This experiment follows its speed/raw-ID/lifetime comparison approach with the
installed tracker APIs. The linked video was unavailable to automated browsing;
the implementation uses the official documentation and the requested metric
definitions. It does not claim that its heuristic thresholds or report layout
are official Ultralytics definitions.

## Run once for all six trackers

From the repository root:

```powershell
npm run compare:trackers
```

Select a conveyor video and a trained detection checkpoint in the two file
dialogs. The detector picker starts at the application's final D-FINE checkpoint
(`backend/models/D-FINE/detection/best_stg1.pth`, or `FRUIT_DETECTOR_WEIGHTS`).
Both timing modes and all six trackers run automatically. The terminal prints
progress and the completed HTML report path. Canceling a picker exits before
processing. File dialogs require Python's standard Tkinter installation;
the CLI works without a display.

```powershell
./backend/venv/Scripts/python.exe backend/tracker_comparison.py --video "C:\path\conveyor.mp4"
./backend/venv/Scripts/python.exe backend/tracker_comparison.py --video "C:\path\conveyor.mp4" --model "C:\path\best_stg1.pth" --trackers all --annotated
./backend/venv/Scripts/python.exe backend/tracker_comparison.py --video "C:\path\conveyor.mp4" --mode cached
```

`--mode both` is the default. `--mode full` measures detector + tracker on a
complete video pass per tracker. `--mode cached` detects once, then measures
only tracker replay on identical cached boxes. A selected local Ultralytics
object-detection `.pt` is also supported; no models are downloaded or trained.
For an application comparison, keep the final naartjie detector selected.

Common settings: confidence `0.25`, class-wise NMS IoU `0.7`, square detector
input `640 × 640`, device `FRUIT_DEVICE` or `cuda`. Set `--conf`, `--iou`,
`--imgsz` and `--device cpu` explicitly when needed. Each setting applies to
every selected tracker. CUDA is never silently replaced by CPU. The D-FINE
loader comes from the existing sibling `Inference Runner/backend/python`;
it uses the same checkpoint, image processor and postprocessing as the app.
The comparison uses the app's existing duplicate-detection NMS function.
For a selected YOLO checkpoint, stride alignment is resolved once and both the
requested and effective detector input sizes are recorded; the same effective
size is then passed to every tracker run.

The benchmark's default TrackTrack is the installed YAML variant. The normal
application adds entry-box association and overrides confirmation/penalty
settings; those production changes remain intact and are excluded here. This
allows the tracker algorithms to receive one identical detection interface.
YOLO-specific pre-NMS recovered candidates are excluded from TrackTrack for
both detector types so that its replay uses the same common post-NMS input.

## Installed interfaces inspected before implementation

The local installation inspected on 8 October 2026 is **Ultralytics 8.4.170**.
All six configurations were found under its actual `cfg/trackers` directory:

| Tracker | Installed YAML | Registered class |
| --- | --- | --- |
| ByteTrack | `bytetrack.yaml` | `BYTETracker` |
| BoT-SORT | `botsort.yaml` | `BOTSORT` |
| OC-SORT | `ocsort.yaml` | `OCSORT` |
| Deep OC-SORT | `deepocsort.yaml` | `DeepOCSORT` |
| FastTracker | `fasttrack.yaml` | `FASTTracker` |
| TrackTrack | `tracktrack.yaml` | `TRACKTRACK` |

The tool discovers each YAML by its real `tracker_type` and constructs the
registered class with its installed arguments plus the common runtime device,
as Ultralytics' tracking callback does. No association/confirmation/GMC settings
are invented or normalized. Every class supports `reset()` and
`update(Boxes(raw_detections), original_frame)`. Cached detections are copied
before update so a tracker cannot mutate the common input. Empty frames also
call update. Installed defaults have ReID off; appearance-enabled experiments
would require a separate protocol. An unsupported installation or an enabled
ReID config fails clearly rather than substituting an algorithm.

## Timing and fairness

The video is decoded once into a canonical manifest of timestamps and frame
SHA-256 fingerprints. Cached mode also stores detection arrays, offsets and
detector-only durations in `detections.npz`. Every subsequent video pass verifies
its source frame and timestamp before tracker processing. Incomplete decoding
or differing frame counts fail the experiment. The source video and checkpoint
are hashed before and after the run.

Three initial detector warm-up frames and three disposable tracker warm-up
frames per mode/tracker are excluded by default (`--warmup 3`). After warm-up,
the tracker is freshly constructed and reset, including its ID counter, and
starts from frame **0**. All measured runs include **every** video frame.

`time.perf_counter()` measures only these sections:

| Mode | Included | Reported speed |
| --- | --- | --- |
| Full | detector preprocessing, inference, postprocessing/NMS, CPU box transfer, box adapter, tracker update including configured GMC | Measured detection + tracking FPS |
| Cached | cached box adapter and tracker update including configured GMC | Measured tracker-only FPS |
| Shared detection pass | preprocessing, inference, postprocessing/NMS and CPU transfer | Separate detector-only reference |

CUDA is synchronized before the start and before the stop. Video decoding,
frame verification, model loading, warm-up, cache reads/writes, diagnostics,
box drawing, video encoding, CSV/JSON writing and HTML generation are excluded.
Processing FPS = processed frames / summed processing seconds. Mean ms/frame =
1,000 × summed processing seconds / processed frames. Source/video FPS is a
separate metadata value. Cached replay and detector reference timings are never
added together and presented as measured full-pipeline speed. Full here means
**detection + tracking**, not the application's segmentation/grading throughput.

All trackers run sequentially in the displayed protocol order on the same
device. Real timing may vary with other workloads and thermal conditions;
metadata records the hardware and a GPU load snapshot. Repeat on an idle system
before making a final engineering choice. The tool does not stop other jobs.
Cached replay is the strongest comparison of tracker behaviour because its
detection sequence hashes must match. Full mode also records whether detections
match the cached pass exactly, exposing numerical detector variation.

## Raw-ID metrics and diagnostic definitions

Raw tracker IDs are saved exactly as returned. “Active” means IDs returned by
the current update, rather than lost IDs retained inside a tracker's buffer.
The mean active count includes empty frames. Every ID retains its first/last
source frame and timestamp, observed count, box dimensions and consistency:

```text
lifetime_seconds = last_timestamp - first_timestamp
consistency_percent = 100 * observed_frames / (last_frame - first_frame + 1)
processed_video_frames_percent = 100 * observed_frames / all_processed_frames
```

A one-frame ID has zero elapsed lifetime. The first/last interval may be
censored by video boundaries, so this is an **observed** lifetime. Mean,
median, min/max and distributions are saved. No guessed physical visible
lifetime or downstream corrected fruit ID enters these statistics.

The following thresholds are **application-defined diagnostics**:

- Short-lived IDs: elapsed lifetimes strictly below `0.25`, `0.5` and `1` second;
  counts and proportions are saved. Empty output yields zero counts and null
  proportions, rather than implying successful stability.
- Substantial persistence: observed lifetime at least `1` second and consistency
  at least `90%`. Change the time with `--substantial-seconds`.
- Lifetime distribution bins: `[0, .25)`, `[.25, .5)`, `[.5, 1)`, `[1, 2)`,
  `[2, 5)`, `[5, ∞)` seconds.
- Suspected ID Fragmentations: a never-before-observed ID appears within `0.5`
  seconds of a missing ID's last observation, of the same class, with width and
  height ratios between `0.5` and `2`. Its centre is within `0.5` box diagonals
  of the old ID's timestamp-based linear continuation. The distance uses the
  larger old/new diagonal; velocity uses the last two observations, or zero
  velocity if only one exists. Nearest normalized-distance pairs are assigned
  once per old/new ID within that frame. Use `--fragment-window-seconds` and
  `--fragment-distance` to change the window/distance.

Fragmentation candidates are saved as **Suspected ID Fragmentation** events;
the summary calls them **Suspected ID Fragmentations**. No pair is merged.
Nearby fruit, genuine exits and new entries can create false candidates. There
are no verified physical-identity errors or formal ground-truth MOT metrics.
Stability, lifetime and speed must be considered together; there is no combined
score, automatic winner, or production tracker switch.

## Outputs and local report

Each run creates a new UTC timestamp + random-ID folder under
`backend/results/tracker_comparison/`. Choose another parent with `--output`.
Prior runs are never overwritten.

```text
<run>/
  run_metadata.json
  status.json
  input_manifest.json
  detections.npz                 # cached/both mode only
  comparison_summary.csv
  comparison_summary.json
  report.html
  bytetrack/
    full/                       # mode subfolders only when using both modes
      summary.json
      tracker_config.json
      bytetrack.yaml
      tracks.csv
      events.csv
      observations.csv
      frames.csv
      annotated.mp4             # --annotated only
    cached/...
  botsort/...
  ocsort/...
  deepocsort/...
  fasttrack/...
  tracktrack/...
```

Open `report.html` directly in a browser. Styles, data and SVG chart code are
embedded; no CDN or server is required. Choose the timing mode, sort the
comparison columns, choose a tracker and filter raw IDs. Charts show speed,
ms/frame, mean/median lifetime, unique IDs, consistency, suspected fragmentation
and the selected tracker's lifetime distribution. CSV links work locally.
Per-ID tables show up to 200 matching rows; CSVs retain every row.

Metadata includes UTC start/end, git commit and dirty state, Python/Ultralytics/
PyTorch/CUDA versions, CPU/GPU/device, threads, preprocessing, checkpoint/video
paths and hashes, source FPS/resolution/declared and decoded frame counts,
timestamp method, common confidence/IoU/input size, warm-up policy, timing
boundaries, algorithm YAML contents/hashes, tracker implementation file hashes,
D-FINE loader hash and experiment source hashes. Source timestamps use video
`POS_MSEC`, with frame/source-FPS fallback when missing or non-increasing;
processing FPS never determines those timestamps.
Exact experiment source files are retained in `source_snapshot/` for auditing
the code used by a run, including when the working tree has uncommitted changes.

`status.json` marks a failed or interrupted run clearly and preserves available
diagnostics; incomplete results do not produce a completed HTML report.

## Verification

```powershell
cd backend
./venv/Scripts/python.exe -m unittest test_tracker_comparison -v
./venv/Scripts/python.exe -m unittest discover -p "test_*.py"
./venv/Scripts/python.exe validate_tracker_comparison.py "path\to\completed\run"
```

Focused tests cover the installed six APIs, reset/ID counters, shared frame
sequence/model/confidence/IoU, immutable cache, complete frame counts, raw IDs,
summary/per-ID arithmetic, time-based suspected fragmentation, timing boundaries
and CUDA synchronization, MP4 encoding outside timing, no overwrite, clear
failure states and offline report/script-data escaping. The new tool is isolated
from the production application modules. Real-video evidence and complete-suite
validation are recorded under `backend/diagnostics/tracker-comparison/`.
