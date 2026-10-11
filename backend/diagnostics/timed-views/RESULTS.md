# Timed-view full-pipeline benchmark — 11 October 2026

This records the earlier complete-sequence grading policy. Grading now uses
available processed snapshots at the user's request; missing scheduled views no
longer block a grade. These recorded comparisons were not rerun under that policy.

**The current pipeline did not pass real-time grading in any of the eight comparisons.** Timed capture is implemented at 640 pixels. Four views reduced the work, but the unchanged segmenter, tracking, missed capture windows and publication load still prevent grading every arrival.

## Timing measured before benchmarking

All 50 recordings were screened for moving fruit. Conservative full-operation ranges retain 717.260 seconds across 43 videos and exclude stopped tails, speed transitions and insufficiently long/empty sections. The five operation-review contact sheets were visually inspected. These are motion-based ranges rather than motor telemetry.

The offline timing fit uses 2,491 uncensored, quality-accepted tracker associations from 267.087 seconds across 30 recordings. Median usable dwell is **2.305 seconds** (5th/95th percentiles: 1.004/2.611 seconds). Four views at **0.2-second spacing** with 0.15-second lateness fit 95.50% of these associations; at **0.4 seconds** they fit 91.37%. Four views one or two seconds apart fit none. The fruit leaves the usable field before the fourth capture.

The same-implementation dense-scene pilot published 14 grades at 0.4-second spacing versus 8 at 0.2 seconds. Thus **four snapshots at 0.4 seconds** is the tested performance compromise (nominal times 0, 0.4, 0.8, 1.2 seconds after the first accepted crop). The UI measured preset uses 0.2 seconds for acquisition fit; enter 0.4 to reproduce this performance comparison. This is preliminary tuning, not proof of optimal timing or angular coverage.

## Common protocol

- Three operation-only scenes per model/profile: dense `WIN_20260818_13_05_49_Pro.mp4`, mixed `WIN_20260818_13_35_37_Pro.mp4`, sparse `WIN_20260818_13_52_31_Pro.mp4`; each replays 0.4–10.4 seconds at its original approximately 29.9 FPS.
- Four distinct source crops, 0.4-second spacing, 0.15-second lateness, 5-second decision deadline. Requested detection/tracking cadence: 10 updates/second. Missing crops, uncertain identity and late publication withhold the grade.
- Both model inputs remain 640 × 640 and FP32. HSV_FULL is converted after RGB letterboxing on each detector invocation; incoming video is decoded BGR and never preconverted as a whole.
- The existing native Torch segmentation checkpoint is unchanged. Complete fruit sequences receive bounded inference admission and earliest-deadline priority. Contact-sheet evidence reduces PNG export work; mask inference and defect fusion still run.
- Laptop: RTX 4060 Laptop GPU, supplied FP32 TensorRT detector engines. CPU rehearsal: NCNN YOLO / ONNX Runtime D-FINE, CUDA/Vulkan disabled, affinity to four physical cores `[0, 2, 4, 6]`, two Torch/two detector threads, one OpenCV thread, 3 GiB RSS watchdog.
- One replay per model/profile, with startup/warmup reported separately. Pipeline wall time includes processing, expired inference, evidence writes and drain. Background desktop load and run-to-run variance were not controlled. This is a preliminary benchmark.

## Results

Detector Hz below is actual detector calls divided by source duration. It is **not grading FPS** and does not mean every camera frame was processed. Timely grades are published, complete provisional decisions. Denominators are terminal tracker associations, including clip-boundary truncation and uncertain IDs; they are not ground-truth physical fruit counts.

| Profile | Detector | Detector Hz | Timely grades / associations | Complete evidence | Segmentation ms/crop | Peak RSS GiB | Deadline misses |
|---|---|---:|---:|---:|---:|---:|---:|
| Laptop CUDA | yolo_rgb | 3.87 | 23/371 | 27 | 155.0 | 3.44 | 95 |
| Laptop CUDA | yolo_hsv | 6.14 | 17/469 | 30 | 85.8 | 3.68 | 123 |
| Laptop CUDA | dfine_rgb | 7.44 | 47/477 | 54 | 75.9 | 3.33 | 117 |
| Laptop CUDA | dfine_hsv | 8.98 | 5/660 | 60 | 68.0 | 5.07 | 203 |
| Four-core CPU proxy | yolo_rgb | 5.21 | 0/411 | 0 | 1769.7 | 1.52 | 119 |
| Four-core CPU proxy | yolo_hsv | 3.97 | 0/424 | 0 | 1521.0 | 1.59 | 72 |
| Four-core CPU proxy | dfine_rgb | 2.67 | 0/539 | 0 | 1609.7 | 1.51 | 38 |
| Four-core CPU proxy | dfine_hsv | 2.80 | 0/709 | 0 | 2012.0 | 1.51 | 17 |

Segmentation ms/crop is measured effective inference-plus-mask wall cost divided by submitted crops, including batched work; it is not isolated model latency. Complete evidence can still be ungraded because identity is uncertain or publication is late.

**D-FINE RGB published the most timely laptop grades: 47/477 associations (9.85%).** Every CPU rehearsal published **zero** complete timely grades. The four-core runs spent roughly 1.5–2.0 seconds per segmentation crop; four views therefore exceed the five-second budget even before the rest of the pipeline at that effective rate. Laptop tracking and segmentation/export contention also reduce detector cadence below the requested 10 Hz. Changing snapshot arithmetic alone cannot remove these costs.

## Drops and latency

Capture overwrites discard older frames when the consumer falls behind. Timer skips are intentional cadence skips and counted separately. The latency columns below are the **largest per-clip 95th percentile**, not a pooled percentile.

| Profile / model | Source frames | Capture overwritten | Timer skips | Wall seconds incl. drain | Frame age p95 ms | Publication p95 s |
|---|---:|---:|---:|---:|---:|---:|
| laptop / yolo_rgb | 896 | 716 | 64 | 44.2 | 2780.8 | 11.77 |
| laptop / yolo_hsv | 896 | 556 | 156 | 40.7 | 377.6 | 7.01 |
| laptop / dfine_rgb | 896 | 427 | 246 | 47.6 | 260.0 | 6.67 |
| laptop / dfine_hsv | 896 | 372 | 255 | 45.0 | 177.2 | 6.32 |
| pi4 / yolo_rgb | 896 | 715 | 25 | 41.6 | 514.4 | 7.52 |
| pi4 / yolo_hsv | 896 | 771 | 6 | 44.1 | 752.5 | 5.93 |
| pi4 / dfine_rgb | 896 | 816 | 0 | 36.1 | 853.9 | 5.47 |
| pi4 / dfine_hsv | 896 | 811 | 1 | 36.2 | 948.6 | 3.45 |

All runs reported zero duplicate terminal UIDs. The machine-readable [comparison.json](comparison.json) includes selected/processed view histograms and status counts; [comparison.csv](comparison.csv) contains the aggregate numeric table. Each [model/profile folder](final_comparison/) retains request settings, source/model hashes, per-clip measurements, resource samples and links to actual result jobs.

## Interpretation and next test

Timing chooses snapshots without the centre-progress calculation. Shared tracking still uses boxes to preserve identity. Timers alone cannot associate simultaneous fruit or certify distinct skin angles. No independently labelled identities, defects or grades were available; these results measure workload and decision completion, not accuracy. The differing association counts also prevent declaring a detector accuracy winner.

The four-core run is **not ARM emulation or a prediction of Raspberry Pi FPS**. Desktop CPU instructions, clock, cache, memory, decoder, Windows and thermal behaviour differ. The 3 GiB check is a watchdog after processed frames, not a hard OS limit. Test the same paced script on the actual Pi before making deployment claims.

With this segmentation checkpoint retained, the tested settings are not sufficient for real-time sorting. A materially faster segmentation runtime/model or more inference capacity is needed for the measured arrival load. Raising deadlines does not solve sustained throughput overload. The planned replacement segmenter should be benchmarked using this same replay protocol.

Segmentation checkpoint SHA-256: `2869048b1bba2ca0e5cfb0416bf9977f79f851dd8907ffa8b07b54e8c6d049c0`. The corrupt HSV D-FINE ONNX copy was replaced by the locally verified original binary without retraining; see [repair provenance](model_repair.json). Recorded benchmark source snapshots were checked against their hashes; see [source verification](final_comparison/source_verification.json). Later metadata and mixed-mode cadence fixes do not alter these fixed timed replays.

Reproducible commands, calibration procedure and dashboard settings: [TIMED_VIEW_GRADING.md](../../TIMED_VIEW_GRADING.md).
