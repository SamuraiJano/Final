# Nine-view implementation measurements

Measured 9 October 2026 UTC (the final CPU run ended after midnight South
African time). The new algorithm and hot switch execute, but **this recording
fails real-time acceptance**. Both model inputs remain 640 × 640, FP32.
The shared detector/tracker was retained; no low-resolution or lower-view-count
mode was substituted.

## Available hardware and acquisition

Windows laptop, NVIDIA GeForce RTX 4060 Laptop GPU, AMD64 CPU, PyTorch
2.6.0+cu124, Transformers 4.57.1 and OpenCV 5.0.0. The CPU experiment ran on
**the laptop**, using the `pi4` resource profile: CPU inference, batch size one,
two PyTorch intra-op threads, one OpenCV thread, 24 active nine-view fruit and
32 pending views. A Raspberry Pi was not available. ARM compatibility,
temperature, throttling and Pi throughput remain unmeasured.

The original `WIN_20260818_13_05_49_Pro.mp4` contains 795 frames at
29.9308014929 FPS. Sustained loads repeat it three times at its original rate:
2,385 source frames over approximately 79.68 seconds. Repetition is load
extension, not independent fruit or accuracy evidence. The full-frame test
region and five-second deadline were explicit experimental settings; there was
no independently calibrated dwell time, sorter decision point or physical
arrival-rate ground truth.

Acquisition has a four-frame ring. The producer never waits for inference.
Overwritten source frames, failed/missing crops, uncertain identity, overloads
and late decisions stay counted. Timing excludes loading/warmup and includes
end-of-stream publication. The final CPU benchmark also explicitly drains
expired in-flight model work before recording duration/model counters. Both
final sustained runs ended with zero pending views, in-flight batches and
active engine fruit; there is no uncounted model tail in these two results.

## End-to-end results

| Measurement | Laptop CUDA, sustained | Laptop CPU, sustained | Laptop CUDA, active switches |
| --- | ---: | ---: | ---: |
| Source frames | 2,385 | 2,385 | 90 |
| Processed frames | 114 | 56 | 7 |
| Dropped capture frames | 2,271 | 2,329 | 83 |
| End-to-end processed FPS | **1.392** | **0.650** | **0.260** |
| Wall time, seconds | 81.922 | 86.187 | 26.937 |
| Frame age p50 / p95, seconds | 0.591 / 0.953 | 1.244 / 1.995 | 1.580 / 4.156 |
| Nine-view terminal records | 1,836 | 2,525 | 110 |
| Complete nine-view evidence / grades | **0 / 0** | **0 / 0** | **0 / 0** |
| Complete nine-view fruit/second | 0 | 0 | 0 |
| Publication latency p50 / p95, seconds | 2.496 / 6.910 | 1.710 / 6.001 | 3.109 / 5.439 |
| Publication deadline misses | 519 | 298 | 17 |
| Mean detection time, ms | 157.12 | 288.99 | 190.11 |
| Effective segmentation time/crop, ms | 65.08 | 1,141.57 | 63.98 |
| Peak process RSS, GiB | 1.78 | 1.20 | 1.69 |
| Duplicate terminal UIDs | **0** | **0** | **0** |

Terminal records are accepted tracker associations, **not a verified count of
physical fruit**. Frame loss and association fragmentation affect that count.
GPU/CPU association arrivals were 23.04/31.69 per source second; the corresponding
9× sample budgets were 207.37/285.19 crops per second. These are explicitly
association-derived estimates, not validated conveyor capacities. No independently
labelled fruit were available: grade accuracy, severe misses and false rejects
are unavailable, rather than zero.

GPU evidence selected 1,172 crops and successfully assessed 598 before terminal
closure, across 1,836 records: means 0.638/0.326, maxima 5/4 per record. CPU
evidence selected 301 and successfully assessed four, across 2,525 records:
means 0.119/0.0016, maxima 2/1. Late inference is counted in model work but cannot
amend a terminal result. No fruit was padded to nine or graded clean from
incomplete evidence.

GPU final reasons: 1,027 missing-bin cases, 359 uncertain associations, 294
decision-deadline cases, 14 foreground-mask failures and 142 active-buffer
overload cases. CPU final reasons: 2,107 active-buffer overloads, 90 missing-bin
cases, 40 uncertain associations and 288 deadline cases. Final reason/status
can prioritize an identity review over an earlier acquisition failure; the
engine counters additionally retain all active overload attempts (158 GPU,
2,136 CPU). Publication misses include terminal results that were already
incomplete when their deadline passed; they are not limited to timeout statuses.

GPU selection accumulated 3.893 seconds and finalized-mask preparation 25.922
seconds. CPU selection accumulated 1.026 seconds and mask preparation 1.830
seconds. GPU `inference_and_masks` accumulated 148.602 seconds; CPU 168.980
seconds. Those per-batch elapsed values overlap and include shared-device queue
waits, so they must not be added to wall time. Actual model execution timings
are reported separately. Peak pending views were 98 GPU / 21 CPU, peak active
engine fruit 96 / 24 and peak in-flight batches two for both.

CUDA device utilization peaked at 100% (mean sampled utilization 66.6%), with
up to 3,690 MiB device memory reported. NVIDIA samples describe the whole
device, not exclusively this process. CPU process utilization peaked at 772%
in the GPU run and 366% in the CPU run; psutil's process percentage sums cores.
All raw resource samples, per-fruit counts and incomplete reasons are retained
in the linked JSON evidence.

## Active switching and retained surface behavior

The 90-frame source-paced test made six switches in both directions while
48–113 identities remained active. It reused the same models, camera producer
and tracking pipeline. It published 110 nine-view records and 47 surface
records, with no duplicate terminal UID. The surface results were five existing
provisional/partial grades and 42 mapping failures. This is a short switching
execution test, not a sustained successful throughput or accuracy test.

Additional tests exercise twenty rapid configuration toggles, immutable entry
settings, region entry, continued tracking after publication, recovered/reused
IDs, late callbacks and exactly one terminal publication. A detached surface
fixture produces the same map pixels, defect percentage, status and grade as
the original mapping function while the live mode/settings change.

Final verification passed **294 backend tests**, frontend `npm run lint`,
`npm run build` and the isolated headless browser checks. The browser fixture
is explicitly synthetic and supplies no model-accuracy evidence. The lint
configuration excludes generated runtime tooling as well as existing archives.

## Capacity and the next practical bottleneck

At the measured CUDA detector time, detection alone has an approximate ceiling
of **6.36 FPS**. Processing every frame of this 29.93 FPS source would consume
**4.70 seconds of serial detector work per source second**, before segmentation,
tracking or export. Consequently, reducing physical fruit arrival rate alone
cannot make the current every-frame detector keep up with this camera source.

The segmenter-only idealized bound is **1.71 nine-view fruit/second on CUDA**
or **0.097 fruit/second on laptop CPU**, excluding all detection and other work.
They are model-time ceilings, not supported operating rates: the sustained
experiment successfully graded **zero** fruit.

For an explicit hypothetical lower detection cadence `f`, a serial device
budget gives:

`fruit_rate <= max(0, 1 - f * detector_seconds) / (9 * crop_seconds)`.

For CUDA, `f=4` gives at most approximately **0.634 fruit/second**, with a
sampling budget requiring roughly **2.25 seconds of dwell** for nine bins.
This excludes masks, tracking, export, quality rejection and identity errors.
It is a calculation for a future experiment, **not a measured real-time mode**.
No detection cadence reduction or playback slowdown was used to claim success.

The practical next work is accelerating the shared 640-pixel model execution
with a compatible export/backend, or evaluating a faster trained model at 640,
then validating small-defect recall and identity under any proposed cadence
change. Crop inference must retain nine samples per fruit. A narrower,
physically calibrated inspection region may reduce crop workload, but by itself
does not speed the current full-frame detector. Pi 4 requires an actual-device
test and likely a substantially lighter CPU-compatible model/backend; the
current laptop CPU result provides no evidence that this checkpoint can meet
Pi real-time requirements.

## Reproduction and evidence

See [operation, implementation and research references](../../NINE_VIEW_GRADING.md).

* [Final sustained CUDA request and fingerprints](20261009T215556Z_8ecb80/request.json),
  [measurements](20261009T215556Z_8ecb80/benchmark.json),
  [normal result report](../../results/a68282d1d5964164a49b2582833c508d/report.json).
* [Final sustained laptop CPU request and fingerprints](20261009T220145Z_976199/request.json),
  [measurements](20261009T220145Z_976199/benchmark.json),
  [normal result report](../../results/f68f636e84504988be2fa6d3ada0078a/report.json).
* [Active-switch request](20261009T215026Z_a00480/request.json),
  [measurements](20261009T215026Z_a00480/benchmark.json),
  [normal result report](../../results/aafc5116404741e599c2fa06e023ef98/report.json).
* [Browser checks and fingerprints](ui/checks.json),
  [switch/settings screenshot](ui/mode-and-settings.png),
  [explicit synthetic provisional-result screenshot](ui/complete-provisional-result.png).

Earlier folders retain development failures and superseded timings. In
particular, the earlier short/sustained CPU timings recorded one expired model
batch still in flight at measurement time; the final CPU result above drains
it explicitly. GPU runs and the mixed switching run had no remaining model
work at measurement. The two initial failed replays exposed tracking-history
and NumPy JSON-serialization integration bugs, now fixed and covered by tests.
Generated image/result files remain local according to `.gitignore`.
