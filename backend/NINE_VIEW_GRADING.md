# Nine-view grading and per-fruit algorithm switching

**Timed 4–9 view extension:** [TIMED_VIEW_GRADING.md](TIMED_VIEW_GRADING.md)
documents operation-only calibration, timestamp acquisition, four detector
exports and the CPU-constrained Pi rehearsal. The progress-bin strategy below
remains available. Timed mode groups captured snapshots before inference.
The optimized CPU profile processes accepted snapshots during collection; see
[CPU measurements](diagnostics/cpu-optimization/RESULTS.md).
Current multiview grading uses any successfully processed snapshots; 4–9 views
is a capture target. Missing views do not block a grade. The complete-sequence
requirements and measurements below describe the earlier grading policy.

The application offers `surface_mapping` (the existing initial default) and
`nine_view`. Both use the same camera, D-FINE detector, TrackTrack association,
conveyor identity guard and D-FINE SEG checkpoint. Both model inputs remain
**640 × 640**. Nine-view grading avoids the mapping algorithm's geometry work,
but the available recording has **not met real-time acceptance**. See
[measured results](diagnostics/nine-view/RESULTS.md).

## Operation

Restart the backend once after installing this code. In the dashboard's
**Algorithm for entering fruit** panel, choose **Surface mapping** or
**Nine-view grading**. The buttons remain available during inspection. Changing
mode does not reopen the camera, reset the tracker or reload models.

Open **Nine-view acquisition and grading settings**. Set the inspection region
using normalized left/top/right/bottom coordinates and the conveyor direction.
If this region is unset, the existing Tracking performance region and direction
are resolved when each fruit enters. If both regions are unset, nine-view
results explicitly report `inspection_region_not_configured` and remain Review.
The benchmark's full-frame test region is not a verified conveyor calibration.

Each accepted physical-fruit association receives a frozen mode, configuration
version, resolved region, thresholds and surface settings at region entry.
Fruit observed before that entry have no assignment yet. Existing fruit drain
with their original settings after any switch; newly entering fruit use the
new version. The saved inspection configuration is separate from older tracking
and mapping settings; an absent/empty inspection configuration defaults to
surface mapping. Runtime configuration is stored in
`backend/runtime/inspection_config.json`.

```http
GET /api/inspection/config
POST /api/inspection/config
Content-Type: application/json

{"algorithm":"nine_view","expected_version":1,
 "nine_view":{"region":[0.1,0.1,0.9,0.9],"direction":"top_to_bottom",
              "decision_deadline_seconds":5,"expected_dwell_seconds":3,
              "expected_fruit_rate":0.3}}
```

Omit `expected_version` for an unconditional update, or send the version from
GET to detect a concurrent configuration change. Invalid settings return 422.
The five-second default deadline is an initial engineering setting: set it to
the measured time available before the downstream decision point. Expected
dwell/rate values are optional measurement inputs, not conveyor speed controls.
No actuator-control interface is introduced; the existing terminal result/report
publication remains the application's output.

## Acquisition and inference

The center of each accepted tracker box supplies conveyor progress. Nine equal
progress bins retain at most one crop each. A bin closes when the fruit advances
to a later bin, at exit, track loss, end of stream or expiry. Closed bins submit
individual crops progressively. Replacement within an open bin prefers higher
interior Laplacian variance, then lower glare, lower overlap and an earlier
original frame. Repeated frame indices cannot create another view.

Cheap checks reject undersized, frame-clipped, blurred or excessively reflective
crops and bounding boxes substantially overlapping another detected fruit.
Overlap is an occlusion proxy; it cannot measure occlusion by an undetected
object. Finalized crops receive the existing GrabCut foreground preprocessing
with three iterations; a failed or too-small visible mask fails that view.
Boundary estimation uses the existing smaller working mask and restores it to
the native crop; the defect model still receives its original 640-pixel input.
No spheroid, projection, rotation estimation, texture registration, atlas or
dense reconstruction runs in `nine_view`.

The result retains source frame indices, capture/source timestamps, bin,
progress, quality, model confidence evidence, failures, missing bins and a
run-scoped fruit UID. Recovered associations are accepted only through the
existing identity guard; uncertain associations are withheld from grading.
Retired/reused raw tracker IDs do not make an old result eligible for a second
publication. Published active identities retain a small tracking tombstone
until genuine loss, preventing stationary timeout results from being reopened.
The existing conveyor identity guard supports vertical conveyor directions.
Keep its direction/speed calibration consistent with the camera setup; the
four-direction bin selector alone does not validate horizontal identity recovery.

Exactly nine accepted crops from distinct source frames and nine successful
inferences are required. Missing bins, failed inference, poor masks, deadline
expiry and overload produce Review with an explicit reason. No duplicates fill
missing slots, and no other algorithm is used as a fallback. Nine distinct
frames or bins do **not** prove nine rotation angles or complete skin coverage.
The reported observation count, cadence, observed source span and missing bins
describe acquisition; the observed span can be a truncated association, rather
than the actual physical fruit's entire dwell time. A cadence × configured dwell
budget below nine, or fewer than nine tracking observations before closure, is
reported explicitly.

## Grade and calibration

There is no calibrated per-view Class 1/2/3 classifier in this repository.
D-FINE SEG supplies labelled instance masks and confidence scores. Within each
view, predictions below the configured confidence threshold (initially 0.50)
or minimum supported pixel count are discarded. Masks are intersected with the
visible fruit mask and unioned across instances/classes, counting overlapping
pixels once. Existing labels do not identify a normal stem/hilum category to
exclude, so this implementation introduces no new exclusion rule.

The per-view percentage is defect pixels / valid visible fruit pixels. Initial
thresholds are Class 1 below 10%, Class 2 from 10% through 20%, and Class 3 above
20%. These are an **experimental transfer** from surface-map thresholds,
**not** an established equivalence. A complete experimental result is marked
`grade_provisional=true`, `grade_scope=worst_supported_view` and carries its
calibration record. The final class is the worst supported severity among all
nine successful views; one supported severe localized defect can determine
Class 3. A majority vote cannot hide it. The contributing frame and percentage
are retained.

No defect areas are summed across views. Whole-surface percentages and coverage
are unset/unknown, while `worst_view_defect_pct` is displayed separately.
`evidence_complete` and `calibration_status` are independent: nine successful
model calls do not validate the thresholds. Marking calibration `validated`
requires a different record identifier; that is an operator-supplied claim, not
automatic verification of a calibration study.

Calibration needs independently labelled physical fruit, grading targets,
identity links and small-defect annotations across realistic sizes, rotations,
lighting, speeds and occlusion. Tune confidence/area thresholds on a calibration
set, then measure fruit-level grade accuracy, severe misses, false rejects and
incomplete decisions on separate fruit. Any backend/precision/preprocessing
change needs a paired small-defect recall check before becoming a default.

The optional chronological 3 × 3 contact sheet is encoded on the export worker.
Unfilled display cells are blank and are not counted as views. The sheet is
never model input. Individual crops, masks and overlays are also saved.

## Bounded scheduling and hardware profiles

Camera acquisition retains four raw frames. Detection/tracking uses the shared
bounded inference scheduler; crop selection runs with each accepted observation.
Nine-view mask preparation and progressive inference run separately. The engine
uses round robin selection among fruit ordered by deadline, at most two
in-flight batches, and a 25 ms dispatch wake interval. This bounds dispatch
delay; waiting for a busy shared device can take longer and is subject to the
fruit deadline. Detector requests precede queued model batches. Both models
load and warm once per inspection session, rather than on each mode switch.

Laptop defaults are batch size 4, 96 active nine-view fruit and 128 pending
accepted views. CPU defaults use batch size 1. The `pi4` profile limits active
nine-view fruit to 24 and pending views to 32, uses two PyTorch CPU threads and
one OpenCV thread, and defaults to CPU unless `FRUIT_DEVICE` is explicitly set.
An accepted view rejected by queue capacity marks its fruit overloaded; it
cannot silently become a complete clean grade. Excess active fruit publish an
overloaded result without retaining nine crop slots. Engine state is released
after publication, with expiry for lost/stationary fruit and deadlines.

Image/contact-sheet encoding and disk I/O use separate surface and nine-view
export workers. The combined completed-fruit queue is bounded at 16: when full,
processing waits for an export. Heavy surface exports can therefore still
reduce processing throughput in a mixed run; the benchmark includes this cost.
Existing surface evidence/identity rules are retained. The independent
`FRUIT_PIPELINE=reference|realtime` environment setting chooses the older
surface-mapping implementation profile; it is not the hot strategy switch.

```powershell
# Laptop, existing surface implementation initially selected
$env:FRUIT_DEVICE = 'cuda'
$env:FRUIT_HARDWARE_PROFILE = 'laptop'
$env:FRUIT_PIPELINE = 'reference'
npm run dev
```

On a Pi 4 with a compatible installed CPU PyTorch/torchvision environment,
the existing dependencies, both checkpoints and sibling model-source projects:

```bash
export FRUIT_DEVICE=cpu
export FRUIT_HARDWARE_PROFILE=pi4
export FRUIT_CPU_THREADS=2
python -m uvicorn main:app --host 0.0.0.0 --port 8000  # from backend/
```

This uses the actual eager Torch CPU model backend; there are no compatible
ONNX/TensorRT exports installed in this checkout. ARM dependency installation,
model execution, memory consumption and sustained throughput require a real Pi
test. Laptop CPU execution verifies a CPU code path, not Pi performance. CUDA
or TensorRT is not assumed for Pi 4. Input resolution and precision defaults
were not reduced.

On the Pi, run the benchmark from `backend/` with its local interpreter:

```bash
python benchmark_nine_view.py --video /path/to/conveyor.mp4 --device cpu --hardware pi4 --repeats 3
```

## Reproducible verification

```powershell
./backend/venv/Scripts/python.exe -B -m unittest discover -s backend -p 'test_*.py'
npm run lint
npm run build
# Optional headless UI test with Playwright and installed Microsoft Edge:
./backend/venv/Scripts/python.exe -m pip install --target backend/runtime/ui-tools playwright
./backend/venv/Scripts/python.exe -B scripts/check_nine_view_ui.py

# Actual source-paced load; repetition extends duration, not accuracy evidence
./backend/venv/Scripts/python.exe -B backend/benchmark_nine_view.py --video path/to/conveyor.mp4 --repeats 3
# Shorter, explicitly labelled active-switch experiment
./backend/venv/Scripts/python.exe -B backend/benchmark_nine_view.py --video path/to/conveyor.mp4 --frames 90 --switch-seconds 0.45
# Same CPU backend/settings; run on the actual Pi to measure Pi performance
./backend/venv/Scripts/python.exe -B backend/benchmark_nine_view.py --video path/to/conveyor.mp4 --device cpu --hardware pi4
```

The producer runs at the recording's original FPS, without reencoding, slowing
playback or waiting for inference. If processing falls behind, overwritten
frames remain counted as dropped. Source timestamps, measured frame age,
selection/inference timings, pending/in-flight peaks, memory and utilization,
per-fruit selected/processed crops, incomplete reasons and publication p50/p95
latency/deadline misses are saved under `diagnostics/nine-view/<run>/` with
source/checkpoint fingerprints. Full result/image evidence goes under
`results/<job_id>/`. Pi temperature/throttling are sampled when available.
Model loading/warmup are excluded; end-of-stream work and export are included.

Arrivals count accepted tracker associations, not independently verified
physical fruit. The nominal sample requirement is **9 × physical fruit arrivals
per second**, in addition to detection/tracking. The benchmark reports the
association-derived estimate and optional configured physical rate. Its
segmenter-only rate is an upper bound excluding all other work; its detector
budget indicates whether detection alone can keep up. No grade rate or
accuracy claim can be made from incomplete evidence.

After independent identity/grade annotation, use a JSON object mapping the
run's `fruit_uid` to `Class 1`, `Class 2` or `Class 3`:

```powershell
./backend/venv/Scripts/python.exe -B backend/benchmark_nine_view.py --score-report backend/results/JOB/report.json --labels labels.json
```

This reports accuracy among graded matched fruit, incomplete labelled fruit,
severe misses, severe unassessed fruit and false rejects separately. Missing
labels remain explicitly unavailable. No labelled data or Pi hardware was
available for this implementation.

## Research basis and adaptations

* Zou, X., Zhao, J., Li, Y., and Holmes, M. (2010), **In-line detection of apple
  defects using three color cameras system**, *Computers and Electronics in
  Agriculture* **70**(1), 129–134.
  [Original paper, DOI 10.1016/j.compag.2009.09.014](https://doi.org/10.1016/j.compag.2009.09.014).
  Three cameras capture three images each of rotating apples. This supports
  fixed-count multiview acquisition; its apple stem/calyx counting rules do not
  establish naartjie classes. Our one-camera nine-bin acquisition is an adaptation.
* Li, H., Wang, X., Bu, Y., David, C. C., and Chen, X. (2025), **YOLOv8-Orah:
  An Improved Model for Postharvest Orah Mandarin (Citrus reticulata cv. Orah)
  Surface Defect Detection**, *Agronomy* **15**(4), 891.
  [Original paper, DOI 10.3390/agronomy15040891](https://www.mdpi.com/2073-4395/15/4/891).
  Its single-camera rolling-conveyor acquisition collects ten different poses
  of a mandarin. Nine images and our existing D-FINE SEG model are adaptations.
* Ko, K. E., Jang, I., Choi, J. H., Lim, J. H., and Lee, D. U. (2021),
  **Stochastic Decision Fusion of Convolutional Neural Networks for Tomato
  Ripeness Detection in Agricultural Sorting Systems**, *Sensors* **21**(3), 917.
  [Original paper, DOI 10.3390/s21030917](https://www.mdpi.com/1424-8220/21/3/917).
  Its calibrated stochastic fusion combines multiple-view ripeness predictions.
  Our worst-supported-view defect-severity rule is an engineering adaptation,
  not a reproduction of that stochastic method.

None of these papers validates this camera's whole-skin coverage, Pi 4 speed or
the transferred naartjie per-view grading thresholds.

## Implementation files

`inspection_config.py` provides persisted, immutable entry snapshots;
`inspection_pipeline.py` routes shared tracking observations and freezes
finished evidence; `nine_view.py` implements acquisition, deadlines, bounded
scheduling and fusion; `inspection_export.py` publishes individual evidence and
contact sheets. `main.py` integrates these with existing live/video execution
and the API, while `dfine_segmenter.py` adds warmup without advancing the tracker.
The dashboard changes are in `src/InspectionMode.jsx`, `src/App.jsx` and
`src/App.css`. Verification is in `test_nine_view.py`, the existing surface
fixtures, `benchmark_nine_view.py` and `scripts/check_nine_view_ui.py`.
