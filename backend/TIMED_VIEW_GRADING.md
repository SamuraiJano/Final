# Timed 640-pixel multiview inspection

`timed` acquisition keeps **4–9 distinct source views per fruit**. Surface mapping
and the original progress-bin strategy remain available. Both neural networks
still receive **640 × 640** inputs. The segmentation checkpoint, its RGB
preprocessing, FP32 inference, labels and thresholds are unchanged. Defect-grade
thresholds remain experimental; no whole-surface coverage is inferred.

## Measured timing

All **50 videos** in `videos/` were scanned sequentially for fruit-feature motion.
Conservative stable-motion intervals exclude stopped tails, slow transitions,
empty scenes and very short sections. Each boundary has a 0.4-second guard.
There are **717.260 seconds** of retained operation across 43 recordings; seven
clips have no sufficiently long retained interval. Five
`diagnostics/timed-views/operation_review_*.jpg` contact sheets were visually
inspected. These are image-based ranges, not motor telemetry.

Usable dwell was measured on **2,491 uncensored, quality-accepted tracker
associations** from **267.087 seconds across 30 recordings** long enough to observe
entry and exit. Median dwell is **2.305 seconds**; the 5th/95th percentiles are
**1.004/2.611 seconds**. These are not independently labelled fruit IDs. Calibration
used the tracker's original camera-motion compensation; runtime subsequently
disables that compensation for the fixed inspection camera.

At approximately 10 detector updates/second, four timestamp windows **0.2 seconds
apart**, allowing **0.15 seconds lateness**, fit **95.50%** of measured associations.
Four views one second apart fit **none**: the fourth snapshot is too late. Nine
views at 0.2-second spacing fit about 80% before compute limits are considered.
Distinct timestamps do not certify different skin angles.

The paced pilots also test **0.4-second spacing** (91.37% offline acquisition fit).
On the dense pilot, that produced more published grades than 0.2 seconds with the
same implementation. The final four-model comparison consistently uses four
views at 0.4 seconds. This is a measured operational compromise, not proof of
optimal angular coverage. Recalibrate after changes to conveyor speed or camera
geometry. The earlier nine-view research supports multiview acquisition; reducing
to four views is the user's requested adaptation, not a published grading rule.

## Runtime work

Capture decodes arriving BGR frames at the source frame rate. The benchmark keeps
only the latest two frames. It never preconverts or caches a whole HSV video.
Detection/tracking run on a configurable timer (0.1-second requested updates in
the comparison). Each invocation letterboxes that frame in canonical RGB to 640,
then converts to **HSV_FULL** for an HSV model. H/S/V channel order is preserved;
values are divided by 255 once. Ordinary HSV with hue 0–179 is incompatible with
these models. This matches the controlled training's geometry-before-conversion
contract; the older standalone export demonstration converted before geometry.

After the first full, quality-accepted crop, each fruit uses its frozen elapsed-time
schedule. Snapshot selection never invokes the bounding-box-centre progress
function. TrackTrack and the existing identity guard still associate fruit;
a timer alone cannot identify whose crop was captured.

Missed timestamp windows remain empty. The pipeline never duplicates source
frames, bursts to catch up, or resets timers to disguise slow processing. A cheap
image-change check and configurable grace period stop accumulation in an unchanged
scene. This is a movement proxy, not rotation measurement.

Timed mode collects up to the requested number of views, then submits the captured
snapshots when their schedule finishes or the fruit leaves. **Any successfully
processed snapshot can produce a grade**; missing scheduled views do not block it.
The optimized CPU profile instead submits each accepted timed snapshot immediately
while the remaining views are collected, reducing initial queue delay.
The worst supported processed view determines the class. Sequences are grouped by
fruit, earliest deadline first, and batched where supported. The legacy
progress-bin mode retains progressive inference and fair scheduling.

Decision latency and deadline misses are still measured, but a successfully
computed grade is retained when publication is late. Frames with failed inference
do not contribute to the grade. The earlier four-model comparison used the old
complete-sequence grading rule; its measurements remain historical evidence and
must not be presented as a benchmark of this available-view policy.

CPU exported detection runs independently of segmentation. On CUDA, TensorRT
detection and unchanged Torch segmentation use separate streams. Additional
changes disable fixed-camera optical flow, expire lost tracker state by source
seconds, vectorize overlap checks, and read new-entry settings once per processed
frame. Timed grading bypasses 3D reconstruction and pose estimation.

The faster evidence option saves a contact sheet plus per-view statistics.
Individual source crops, masks and overlays remain selectable. Masks and neural
outputs are still computed for grading. Uncertain fruit identities or an absence
of successful inference still prevent a grade. Runtime decisions remain provisional.

## Detector exports

| Model ID | CPU backend | Laptop GPU backend |
|---|---|---|
| `yolo_rgb` | Provided FP32 NCNN pair | Provided FP32 TensorRT engine |
| `yolo_hsv` | Provided FP32 NCNN pair | Provided FP32 TensorRT engine |
| `dfine_rgb` | Provided FP32 ONNX / ONNX Runtime | Provided FP32 TensorRT engine |
| `dfine_hsv` | Provided FP32 ONNX / ONNX Runtime | Provided FP32 TensorRT engine |

The D-FINE HSV ONNX copy failed protobuf parsing and contained UTF-8 replacement
bytes. Its verified original was found in the local deployment bundle, checked
against the bundle's SHA-256, and copied as binary. The bad copy is retained as
`model_hsv.onnx.corrupt`; provenance is in `diagnostics/timed-views/model_repair.json`.
No retraining or weight modification occurred.

CUDA engines need the matching runtime: the local export records **TensorRT
11.2.1.2**, Windows, RTX 4060 Laptop GPU. The loader can reuse the existing local
training environment's installation, appending its path so inspection dependencies
keep precedence. Set `FRUIT_TENSORRT_PYTHON` to its site-packages directory if it
lives elsewhere. Other GPUs need compatible engines. CPU uses NCNN/ONNX.

## Use and reproduce

The dashboard's **Use measured timing** button applies the offline 0.2-second
preset to newly entering fruit. To match the 0.4-second performance benchmark,
select **Multiview grading**, **Elapsed time**, **4 views**, interval **0.4**,
lateness **0.15**, and contact-sheet evidence. Existing fruit retain their settings.
The initial mode stays surface mapping for compatibility.

Start the backend with its model and detector cadence:

```powershell
$env:FRUIT_DETECTOR_MODEL = 'dfine_rgb' # most timely grades in this laptop comparison
$env:FRUIT_DETECTION_INTERVAL = '0.1'
$env:FRUIT_NINE_BATCH = '8'
npm run dev
```

Run isolated paced comparisons without overwriting saved operator settings:

```powershell
backend/venv/Scripts/python.exe backend/benchmark_timed_views.py --model yolo_rgb --hardware laptop --interval .4 --label my_laptop_test
backend/venv/Scripts/python.exe backend/benchmark_timed_views.py --model yolo_rgb --hardware pi4 --interval .4 --label my_cpu_test
```

Repeat for all four model IDs. Defaults replay 10 seconds from three retained
operating sections: dense `13_05_49`, mixed `13_35_37`, sparse `13_52_31`. Each
recording has separate run-scoped identities. `--all-videos` replays **every retained
operating interval** at full length. `--clips`/`--seconds` choose subsets; `--views`
accepts 4–9; `--evidence full` includes the heavier image archive. Startup/warmup
is measured separately. Expired model work and export drain count in pipeline
wall time. Detector-only FPS is not the real-time acceptance criterion.

Reproduce offline calibration:

```powershell
backend/venv/Scripts/python.exe backend/calibrate_timed_views.py
$env:FRUIT_TRACKER_GMC = 'sparseOptFlow' # match recorded calibration association
backend/venv/Scripts/python.exe backend/calibrate_timed_views.py --measure-tracks
```

Offline upload analysis can run faster/slower than source time. Use paced replay
or the live camera workflow for real-time capacity; both convert HSV at runtime.

## Pi rehearsal limits

The `pi4` profile disables CUDA/NCNN Vulkan, pins the process to one logical CPU
on each of **four physical cores**, uses two Torch/two detector threads, and checks
a **3 GiB process RSS budget** to leave roughly 1 GiB for the OS. Queues/state are
bounded. This is an RSS watchdog after processed frames, **not a hard OS memory
cap**; transient/startup allocation and Windows/Linux accounting can differ.

The preliminary comparison is one unlabelled replay per model/profile, with
clip-start/clip-end truncation and identity uncertainty included. It is not a
sustained field accuracy test. Treat the model ranking as preliminary.

It is **not ARM emulation or predicted Pi FPS**. Desktop core speed, vector
instructions, caches, memory bandwidth, decoding, thermals and the OS differ.
Pi 4's Cortex-A72 cores and RAM options are documented in the
[official specifications](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/specifications/).
Run the same script on the actual Pi with ARM-compatible packages and the existing
segmenter source supplied through `DFINE_SEG_SOURCE`, then measure sustained load
and temperature. The current native Torch segmenter remains the main compute limit.

See [the full-pipeline results](diagnostics/timed-views/RESULTS.md) for all four
models, dropped frames, view counts, grades, deadlines, latency and RAM.

## Optimized CPU execution with the original weights

Set `FRUIT_CPU_OPTIMIZED=1`, `FRUIT_HARDWARE_PROFILE=pi4`, `FRUIT_DEVICE=cpu`,
and `FRUIT_DETECTOR_MODEL=yolo_rgb`. Use two detector threads and two segmentation
threads (`FRUIT_DETECTOR_THREADS=2`, `FRUIT_SEGMENTATION_THREADS=2`). Both inputs
remain 640 and segmentation uses a verified FP32 ONNX export of the same checkpoint.
The original checkpoint is retained and its hash is checked at startup.

The CPU profile uses HSV contour silhouettes, JPEG contact-sheet previews, one
in-flight segmentation request, lightweight image history and progressive timed
inference. HSV silhouettes are approximate; they preserve dark interior pixels
but have not been validated against labelled fruit boundaries. Set
`FRUIT_MASK_BACKEND=grabcut` to retain the previous silhouette preprocessing.
Full evidence keeps its lossless crops and masks. The defect model remains RGB.

```powershell
backend/venv/Scripts/python.exe backend/benchmark_timed_views.py --model yolo_rgb --hardware pi4 --optimized --capture-hz 10 --interval .4 --label optimized_cpu_trial
```

This replay grabs source frames sequentially at their original arrival schedule,
retrieves BGR at 10 Hz and uses a latest-two buffer. Skipped BGR retrievals are
reported separately from overwritten captured frames. It does not preconvert HSV.
See [CPU results and bottlenecks](diagnostics/cpu-optimization/RESULTS.md) for the
paired operation-only comparison, source snapshots, verification and remaining
fixed-model capacity limit. This profile has not achieved real-time grading.
