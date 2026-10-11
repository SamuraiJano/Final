# CPU optimization measurements — 640, original segmentation weights

**The optimized pipeline does not keep up with the supplied moving conveyor footage.**
Segmentation improved from 2853 to 987 ms/snapshot
in the paired whole-pipeline runs (2.89x faster per call).
It produced 7 grades, 4 published before the five-second deadline,
among 402 tracked association records over 29.97 source seconds.
There were 0 fully processed four-view sequences. The reference produced
0 grades. These counts include boundary truncation and tracker fragmentation;
they are not ground-truth physical-fruit counts or accuracy measurements.

## Processes taking the longest

These are weighted mean elapsed times inside the actual paced pipeline. Stages run
concurrently; adding their times does not give wall time. Startup/warmup is recorded
separately. Both complete segmentation time and its neural component are shown.

| Process | Unit | Reference ms | Optimized ms |
|---|---|---:|---:|
| Segmentation, complete call | snapshot | 2853.42 | 987.12 |
| Segmentation neural inference (inside the call above) | snapshot | 2805.79 | 974.35 |
| Object detection, including input conversion | update | 118.12 | 126.77 |
| TrackTrack association | update | 30.87 | 31.46 |
| Physical identity validation | update | 14.48 | 14.80 |
| Video grab/retrieve | original source frame | 34.00 | 4.58 |
| Evidence and result publication | result record | 50.46 | 11.04 |

The segmentation neural network consumes 98.7% of segmentation time.
Snapshot timing arithmetic, preprocessing and mask fusion cannot remove that compute.
Source playback plus export/model drain took 47.97 seconds for
29.97 source seconds. Queues reached their bounds and work expired.
All three scenarios failed the timing/capacity acceptance check.

| Moving clip | Detector updates/source second | Segmentation ms/snapshot | Grades produced / timely | Complete four-view sequences | Wall s including drain |
|---|---:|---:|---:|---:|---:|
| WIN_20260818_13_05_49_Pro.mp4 | 3.80 | 963.9 | 3 / 2 | 0 | 15.86 |
| WIN_20260818_13_35_37_Pro.mp4 | 4.81 | 985.9 | 2 / 1 | 0 | 16.00 |
| WIN_20260818_13_52_31_Pro.mp4 | 7.11 | 1011.5 | 2 / 1 | 0 | 16.11 |

## Implemented CPU profile

- Original segmentation checkpoint and all five defect classes, FP32, 640 x 640.
  SHA256: `2869048b1bba2ca0e5cfb0416bf9977f79f851dd8907ffa8b07b54e8c6d049c0`. No retraining or quantization.
- Verified ONNX export of those weights, retaining source preprocessing and
  postprocessing. Class-mask unions matched exactly on 8 source crops;
  only 1 contained predicted defects. This is limited prediction
  agreement, not labelled small-defect recall or validated grading accuracy.
  Query ordering can differ between runtimes, so raw query indices are not a parity test.
- YOLO RGB ONNX CPU execution. On the isolated detector probe, two-thread ONNX
  took 94.5 ms versus 131.9 ms for NCNN; outputs matched to less than 0.001 pixel
  on that frame. This runtime ranking is for this desktop CPU, not proven for ARM.
- Two detector threads, two segmenter threads, OpenCV one thread; idle ONNX worker
  spinning disabled. A tested 1/3 detector/segmenter split improved segmentation
  but reduced detector cadence and did not deliver real-time grading.
- Four target views at 0, 0.4, 0.8 and 1.2 seconds after the first accepted observation.
  Selection uses source timestamps, without the progress/box-centre function.
  Process accepted timed snapshots immediately while remaining views are collected.
  Grade any successful available views, keeping the worst supported severity.
- One in-flight CPU segmentation request, bounded state/queues, repeated full-set
  expiry checks removed from individual readiness lookups.
- HSV contour silhouette instead of iterative GrabCut in the optimized profile.
  Filled contours retain dark interior defect pixels; bounding-box clipping prevents
  growth into adjacent fruit or rollers. HSV is used for the fruit silhouette;
  the trained defect segmenter still receives RGB. The silhouette is approximate:
  median agreement with GrabCut across 22 raw crops was
  0.927 IoU, minimum 0.789. Its effect on grade
  thresholds is not independently validated. Use `FRUIT_MASK_BACKEND=grabcut` to retain
  the previous silhouette preprocessing.
- Lightweight tracking history for contact-sheet evidence; JPEG contact-sheet
  previews, unchanged full-resolution model inputs and lossless full evidence;
  preview refresh capped at 2 Hz. Encoding/publication stays on the export worker.
- For this replay, decode/grab sequential incoming video at its original frame
  rate, retrieve BGR at 10 Hz, retain the latest two frames, and convert HSV only
  as frames/crops are processed. There is no preconverted video cache.

The isolated silhouette medians were 33.72 ms for GrabCut
and 0.65 ms for HSV. This is a secondary cost, much smaller
than the trained segmentation network.

## Fixed-model compute limit

| CPU threads | Native complete segmentation call, isolated median ms | ONNX neural inference alone, isolated median ms |
|---:|---:|---:|
| 1 | 2071.7 | 1694.8 |
| 2 | 1217.6 | 853.9 |
| 4 | 852.4 | 643.9 |

Fastest measured isolated neural execution: 643.9 ms/snapshot.
Even allocating all four desktop cores only to segmentation gives an upper ceiling
of 0.39 fruit/second for four views. Detection, capture, tracking,
grading and publication lower that ceiling. During the complete pipeline the measured
segmentation ceiling is about 0.25 fruit/second before
accounting for views that expire. A timer changes when work is requested; it does not
make the required neural inferences disappear.

Keeping these weights, 640 inputs, four views, the recorded conveyor load and CPU-only
Pi 4 hardware leaves no demonstrated path to real-time grading. More compute or a
lower physical fruit rate would be needed under that fixed-model constraint.
No cheap colour filter has been used to invent clean-fruit grades or skip defect inference.

## Reproduce

From the project root:

```powershell
backend/venv/Scripts/python.exe backend/benchmark_timed_views.py --model yolo_rgb --hardware pi4 --optimized --capture-hz 10 --interval .4 --label my_cpu_run
```

For the backend, set `FRUIT_HARDWARE_PROFILE=pi4`, `FRUIT_DEVICE=cpu`,
`FRUIT_DETECTOR_MODEL=yolo_rgb`, `FRUIT_CPU_OPTIMIZED=1`, `FRUIT_CPU_THREADS=2`,
`FRUIT_DETECTOR_THREADS=2`, `FRUIT_SEGMENTATION_THREADS=2`,
`FRUIT_TRACKING_PREVIEW_HZ=2`, and `FRUIT_DETECTION_INTERVAL=0.1` before startup.
Use timed four-view acquisition at 0.4 seconds in the existing settings panel.
The live camera retains its shared capture; `--capture-hz` is the video replay setting.
No existing server was restarted or its saved configuration changed for these tests.

To regenerate the segmentation export, install `onnx` in the backend environment,
run `probe_cpu_optimizations.py --export`, then `validate_cpu_segmentation.py`.
Regeneration clears the parity flag; the runtime refuses an unvalidated export.
The original D-FINE SEG source remains needed through `DFINE_SEG_SOURCE` on the Pi.

## Scope and evidence

Only CPU execution was used: four physical workstation cores, no CUDA or Vulkan.
The RSS watchdog reserves roughly 1 GiB for the OS; optimized measured peak RSS
was 2.01 GiB. It is a watchdog after processed frames, not a hard
OS memory cap. ARM instructions, clocks, cache, decoder, temperature and throttling
are not emulated. These numbers must not be presented as Raspberry Pi FPS.

The three moving sections are 0.4–10.4 seconds from the dense, mixed and sparse
recordings, using the existing calibration of all 50 videos. Stopped tails are excluded.
This short preliminary benchmark is not a sustained field test. No independently
labelled fruit identities, defect masks or grades are available in this comparison.

Primary raw data: [`cpu_reference_final`](../timed-views/cpu_reference_final/pi4_yolo_rgb/summary.json),
[`cpu_final_bbox`](../timed-views/cpu_final_bbox/pi4_yolo_rgb/summary.json),
[`runtime_probe.json`](runtime_probe.json), [`detection_probe.json`](detection_probe.json),
[`segmentation_parity.json`](segmentation_parity.json),
[`fruit_mask_probe.json`](fruit_mask_probe.json), and [`comparison.json`](comparison.json).
Each replay records model/source hashes and retains matching source snapshots.
Earlier profile probes, including the rejected silhouette that included rollers,
remain preserved separately. Historical four-model comparisons used another grading
policy and must not be combined with these measurements.

Validation: **307 backend tests passed** in 195.431 seconds. Added controls cover
progressive four-view timing without centre-based selection, dark defect pixels
inside HSV silhouettes, rejection of adjacent fruit/background, and JPEG evidence
metadata. The checkpoint hash and all 24 source snapshots for the primary paired
replays were verified. See [`validation.json`](validation.json) and
[`backend-tests.log`](backend-tests.log).
