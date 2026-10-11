# Streaming implementation trial — 9 October 2026

Both models remain **640 × 640**. Batched segmentation and vectorised fusion
are enabled in the default reference profile. The feature-motion/incremental
mapping profile is available through `FRUIT_PIPELINE=realtime`; it remains
experimental because it loses usable maps on the paired real crop sequences.

The final complete-video replay processed **795/795 frames at 0.965 FPS**,
against a 29.93 FPS source. It produced 28 partial maps and no complete maps.
**The real-time target was not met.** The experiment also failed the paired
real-crop mapping check, so its lower motion-computation cost cannot be presented
as a successful reconstruction speedup.

## Complete original-video replay

The [full pipeline result](20261009T154732Z_d2120d/pipeline.json) and
[normal inspection report](../../../results/926ce82454ed44e28dbf3b30516257ca/report.json)
come from fresh FP32 inference with both unchanged checkpoints and no recorded
frame drops. Model loading is excluded from complete-pipeline throughput;
decode, capture, inference, mapping, final draining and file exports are included.

| Measure | Final result |
| --- | ---: |
| Original frames processed | 795 / 795 |
| Complete pipeline time | 823.929 seconds (13.73 minutes) |
| Complete pipeline FPS | 0.964888 |
| Source FPS | 29.930801 |
| Frame-processing FPS, excluding work outside `process_frame` | 0.998781 |
| Frame-processing p95 | 1,711.8 ms |
| Selected-view defect availability p95 | 12,078 ms |
| Detector calls | 795 |
| Segmented views requested / completed | 57 / 57 |
| Segmentation batches | 28 |
| Capture records | 556 |
| Usable maps | 28 |
| Complete maps | 0 |
| Median usable-map surface coverage | 25.513% |
| Provisional Class 1 / Review | 27 / 529 |

One usable map has uncertain identity and remains Review; 528 records have no
usable map. These capture records are not independently verified physical
fruit counts. The tracking region was not configured, so regional continuity
metrics are unavailable. Existing identity checks still ran.

CPU silhouette tasks accumulated 1,017.943 seconds and motion tasks
1,085.810 seconds across the four fruit workers. These are summed task durations,
not additive wall times. Online fusion accumulated only 0.553 seconds. The
run accepted 29 keyframes, spent its bounded full-search recovery on 399 fruit,
and split 2,841 unsupported motion windows. This confines the speed claim:
array-based fusion is cheap, but repeated silhouettes, motion checks and model
execution still prevent real-time inspection on this footage.

[All 11 output integrity checks passed](20261009T154732Z_d2120d/integrity.json):
795 actual detector calls, unchanged 640 inputs, all 57 requested segmentations
completed, no pending batches/fruit after draining, no grades on failed or
uncertain identities, explicit partial grades, bounded selected-view counts,
matching final source hashes, and valid map/binary-mask files. A representative
saved overlay was also inspected. These checks establish execution integrity,
not physical reconstruction or defect accuracy.

## Reproducible inputs and software

The source is `WIN_20260818_13_05_49_Pro.mp4`, 795 frames at
29.93080149 FPS and 1920 × 1080. Its SHA-256 is
`ae12db73e219a666b639725e9c729e9d3f79e80c4fc6c369795187f67acf8198`.
The full replay uses the original video, not an excerpt reencoding or cached
detections. The two trained checkpoints are unchanged.

The final [request record](20261009T154732Z_d2120d/request.json) contains
checkpoint/source hashes, source snapshots, options, memory headroom and software
versions. Hardware is an RTX 4060 Laptop GPU; runtime is Windows 11, Python
3.12.6, PyTorch 2.6.0+cu124 and OpenCV 5.0.0. Desktop activity can affect timing;
these are measurements on this machine, not a hardware-independent guarantee.

Before editing, the existing working-tree sources were frozen in
[baseline_source](baseline.json). Existing earlier user changes and checkpoints
were retained. The default reference estimator still uses its original full
texture search, with the new fusion and batched defect adapter.

## Fresh model benchmark at 640

The [final model measurements](20261009T154732Z_d2120d/models.json) use 20
detector/tracker frames and eight immutable masked crops, after warmup. Detection
is timed once per precision mode; its value is shared by that mode's two
segmentation rows. Detector timing includes preprocessing, forward inference,
postprocessing and tracking. Segmentation timing includes original-size mask
adaptation and CPU transfer. CUDA is synchronised around timed calls.

| Mode | Detection + tracking FPS | Defect crops/s, single | Defect crops/s, batch four |
| --- | ---: | ---: | ---: |
| FP32 | 5.75 | 11.24 | 31.47 |
| CUDA FP16 autocast | 5.57 | 9.36 | 24.64 |

FP32 batching improved effective segmentation throughput **2.80×** on this
small cohort. Agreement with FP32 single-crop masks was 0.98607 class-mask IoU,
with 21 changed class-mask pixels. FP16 agreement was 0.98280, with 26 changed
pixels and some detector count differences. These are prediction-agreement
checks, not labelled accuracy. FP16 is optional and disabled by default.

Earlier repetitions measured FP32 detector/tracker throughput of 6.24–6.49 FPS
and batched segmentation of 30.79–32.33 crops/s. The small cohort does not cover
the full conveyor workload. Detection/tracking alone remained below the source
rate in every repetition; CPU mapping optimisations cannot remove that limit.

## Paired frozen crop sequences

The [final geometry comparison](20261009T154732Z_d2120d/geometry.json) uses five
records selected with seed 817 from the existing frozen crop/mask archive.
Both estimators receive identical arrays. Baseline settings are frozen from
`mapping80/20261006_final/final_v4/settings.json`. Online mapping uses its
15-degree scheduling target, direct inverse/texture verification and at most
one full-search recovery per fruit.

| Record | Reference seconds | Reference surface coverage | Online seconds | Online usable map |
| --- | ---: | ---: | ---: | --- |
| 123 | 20.948 | 30.232% | 1.490 | No |
| 461 | 21.628 | 27.979% | 1.632 | No |
| 254 | 14.700 | 28.109% | 1.596 | No |
| 275 | 19.578 | Failed | 1.614 | No |
| 161 | 13.202 | 31.850% | 1.630 | No |

The online path spent less time but lost all four usable reference maps. This
is a **quality regression**, not a successful map speedup. It justifies keeping
the reference motion estimator as the default. Synthetic full-turn controls
recover at least 80% surface and 350-degree longitude, but that has not
transferred to these real crop sequences.

These timings exclude neural models. Online geometry-only rows use explicitly
artificial all-clear masks to exercise atlas fusion; no defect or grade accuracy
is evaluated. Failure remains failure, and disconnected motion segments are
not combined into coverage.

## Initial 80-frame development replay

The earlier [80-frame test](20261009T151530Z_31e871/pipeline.json), job
`1f72c184b98049bbba7663d98f014834`, ran both models on a separately labelled
reencoded excerpt before the final ellipse-cache/Jacobian optimisations.
It processed 80/80 frames in 130.93 seconds excluding model loading:
**0.611 FPS**, four partial maps, zero complete maps, 104 capture records,
and median mapped surface coverage 25.341%. Its selected-defect update p95 was
20.83 seconds. This is not the final full-video outcome and should not be used
as a paired before/after comparison with the original video.

## Checks and implementation boundaries

[All 268 backend tests passed](backend_tests.txt) in 152.350 seconds.
`npm run lint` and `npm run build` also passed. The new controls cover measured
rotation on independently rendered skin; stationary/flat rejection; a full
online turn without rebuilding at exit; exact scalar/vector fusion pixels,
overlapping masks and area on spheres/oblates/repeated turns; delayed masks
preventing an all-clear grade; selected-view batching and source evidence;
inference priority/error/overload/draining; capture-sequence gaps; variable-size
crop output coordinates at 640; and existing cancellation/cleanup and identity
rules. The live tracking fixture was updated for the new timestamped frame
interface. An initial suite run exposed that fixture mismatch; the corrected
complete suite passed.

A CUDA Graph experiment failed during the detector's dynamic spatial-shape
construction, and eager fallback in that same process encountered an invalid
capture state. The experiment was removed from the implementation; the final
fresh-process benchmarks use eager inference. No graph acceleration claim is
made. No TensorRT engine was produced in this trial.

The application retains provisional grading of observed skin. Mapping failure,
pending defect observations and uncertain identity withhold grades. Capture
overruns are counted, and the original frame numbers prevent a dropped-frame
stream from appearing to provide dense motion evidence. A preview running
smoothly is not evidence of inspection throughput.

See [REALTIME_PIPELINE.md](../../../REALTIME_PIPELINE.md) for architecture,
activation commands, bounded buffers and metric definitions. Physical identity,
pose and defect labels are still needed to establish conveyor accuracy.
