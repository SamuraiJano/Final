# Capture identity safeguards — 4 October 2026

**Current implementation:** [ConveyorIdentityManager](CONVEYOR_IDENTITY.md) is
now the default capture interface. It uses decoded/acquisition timestamps,
one-to-one motion association and local order, and can recover plausible lost
tracks. The version-3 guard described below remains unchanged and available as
explicit legacy mode; these historical replay counts are not current results.

**Current follow-up:** the [mapping attribution and rerun report](diagnostics/identity-mapping-check/20261004_scene_motion_v3/REPORT.md)
documents version 3, which corrects the initial guard's zero-motion assumption
using a consensus of conveyor motion during each track's first observations.
The updated 515-frame replay has 646 capture segments and 274 uncertain
segments. The historical version-1 counts below remain preserved. Actual
segmentation/mapping, seven paired geometry comparisons, known-area controls
and 88 software tests were rerun. The observed ID changes do not explain the
tested mapping limitation; smooth unseen identity changes remain unmeasured.

Changing tracker IDs can fragment a fruit's views; an ID switching to another
fruit can mix surfaces. Neither failure is established as the main cause of
the current poor maps. The earlier identity audit found that all 15 IDs involved
in its association disagreements failed to produce usable maps. More IDs than
expected is not, by itself, a measured duplicate-fruit count.

## Implemented behavior

`fruit_identity.py` runs inside `NaartjiePipeline.process_frame` before crops
enter `views_by_id`, hence before spheroid fitting. The detector and TrackTrack
configuration are unchanged. Direct callers of `add_tracked_detection` still
own their external identity contract and do not pass through the guard.

- Raw tracker IDs and map capture IDs are separate. Consecutive, mutually
  unambiguous motion matches can retain a capture ID when the raw ID changes.
  Recovery requires three prior observations and complete-box motion history.
- Predictions use recent observed center displacement. A size gate and a
  fruit-diameter-normalized prediction gate reject discontinuities. Matching
  checks competitors in both directions against frozen prior-frame state; the
  order of detections cannot let two observations take the same capture ID.
- Partial edge boxes retain the existing adapter's virtual-extent association.
  The guard does not infer new cross-ID links from clipped-box velocity.
- A missing observation, implausible jump, size discontinuity or ambiguous
  match closes continuity. Subsequent observations start a separate capture;
  old views are never appended into that capture for shape fitting.
- Affected captures are marked `identity_status='uncertain'`. They may retain
  an independently reconstructed map, but receive no grade, even with complete
  apparent coverage. This applies to both direct pipeline completion and API
  result writing. The dashboard explains the uncertainty.
- Reports preserve raw IDs, capture decisions, reasons, source tracker IDs and
  guard settings. Capture IDs cannot be reused after finalization. New video
  jobs snapshot the guard alongside the other execution sources.

The defaults (0.35 diameter prediction gate, 0.12 diameter ambiguity margin,
1.5 size ratio) are engineering choices, not thresholds validated by a paper.
Motion consistency does not prove identity. A visually indistinguishable
replacement at the same predicted location can still evade this guard.

## Replay evidence and tradeoff

[Machine-readable summary](diagnostics/identity-guard/20261004/summary.json),
[per-observation decisions](diagnostics/identity-guard/20261004/decisions.json),
and [segment metadata](diagnostics/identity-guard/20261004/segments.json) retain
the input and guard hashes. The replay used frozen actual tracker output and
original video dimensions, with no detector, segmenter or mapping inference.

| Indicator | Result |
| --- | ---: |
| Original frames / observations | 515 / 32,875 |
| Original raw IDs | 474 |
| Capture segments after checking | 665 |
| Motion-supported raw-ID reconnections | 1 |
| Observation-gap boundaries | 172 |
| Motion or size discontinuities | 20 |
| Ambiguous-association boundaries | 0 |
| Segments flagged uncertain | 308 |
| Segments with at most two observations | 176 (54 original raw IDs) |

The one reconnection is raw ID **244 → 248 at frame 212**. The
[four-frame context image](diagnostics/identity-guard/20261004/recovered_transition.jpg)
shows a heavily occluded fruit. Visual inspection is consistent with continuity,
but is not a labelled accuracy benchmark. This segment was already uncertain
following a gap and remains excluded from grading.

The larger number of records is intentional conservative segmentation, not
additional physical fruit. This change is **not a demonstrated reduction in
duplicate counting or an improvement in reconstructed coverage**. It prevents
the detected uncertain transitions from being pooled into a single shape fit.
Existing saved maps and reports were not regenerated. The local backend was
not running at completion; changes apply on its next start.

The optimized replay took about seven seconds. A broad distance prefilter
preserved every decision of the initial exhaustive implementation. Early
diagnostic directories `20261003` and `20261003_optimized` contain partial
outputs from a JSON key-type error; `20261004` is the completed replay.

## What the research supports

1. **ByteTrack (ECCV 2022):** discarding lower-confidence observations causes
   missed objects and fragmented trajectories; association can recover useful
   observations using track similarity. This supports retaining candidates for
   continuation while controlling new-track creation. It does not prescribe
   naartjie thresholds. [Paper](https://arxiv.org/abs/2110.06864)
2. **OC-SORT (CVPR 2023):** use observations to counter motion-estimation drift
   around occlusions and nonlinear motion. This motivates the independent
   observation-based continuity check here; this guard is not an OC-SORT
   implementation. [Paper](https://arxiv.org/abs/2203.14360)
3. **TrackTrack (CVPR 2025):** track-focused association and track-aware
   initialization use detection candidates while reducing redundant new
   tracks. The app already uses an installed implementation of this method.
   Its MOT17/MOT20/DanceTrack results do not establish performance on rotating
   naartjies. Replacing it solely because another tracker is popular is not
   justified. [Paper](https://openaccess.thecvf.com/content/CVPR2025/papers/Shim_Focusing_on_Tracks_for_Online_Multi-Object_Tracking_CVPR_2025_paper.pdf)

Separating capture at uncertainty is an application-specific engineering
decision motivated by reconstruction's need for same-fruit input, not a claim
that these papers evaluate this safeguard. Lowering the detector threshold,
enabling generic person ReID, or merging similar orange crops is not validated
by this replay. The cached detections were already filtered at 0.25, so they
cannot test a lower detector threshold fairly.

For a defensible next accuracy check, label 20–30 physical entry-to-exit paths,
including occlusions and these transitions; reserve paths before tuning.
Compare ID switches, physical-path fragmentation, wrong-fruit map merges and
count error on the same detector outputs. A separate identity layer cannot
recover invisible identity information. Calibrated conveyor pockets or lanes
can supply stronger constraints where the machine actually has them.

## Reproduce

From the project root:

```powershell
./backend/venv/Scripts/python.exe -B backend/replay_identity_guard.py
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'backend/runtime/ultralytics'
./backend/venv/Scripts/python.exe -B -m unittest discover -s backend -p 'test_*.py'
npm run build
npm run lint
```

Tests cover replacement IDs, simultaneous ID exchange, ambiguous neighbors,
one-to-one assignment, clipped entry, observation gaps, teleporting IDs,
retired IDs, future numeric collisions, JSON serialization, capture isolation
and withholding grades. They establish software behavior on known cases, not
physical identity accuracy or full reconstruction quality on this video.
