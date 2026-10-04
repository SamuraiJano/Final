# Fruit 340: partial mapping correction

Fruit 340's reliable selected sequence expands from frames **305–308 to
305–309**. Estimated observed surface increases from **26.4127% to 32.2200%**.
The recovered transition fits distributed image correspondences better, but
this is a partial correction. The remaining frames cannot currently support a
trusted complete map. There is no calibrated conveyor pose, coverage or defect
ground truth.

Final production algorithm SHA256:
`cf6c2dd19968f0c159a7e2ecb8d781eee0206a88d0bab104df8d087023706745`.
Original baseline SHA256:
`6c592861d9318456856f6a05c780f6a8fdd77c4c50286cc0b748ff094f397371`.

## Why it failed

The legacy fixture named **491 is physical raw tracker ID 340**. Earlier
pixel correspondence and continuity checks tie its 59 frozen crops to the same
raw ID. The selected sequence does not cross a detected identity boundary.
This does not rule out every smooth, unlabelled tracking switch, but the current
image evidence identifies a motion-model problem in this example.

- The fruit tumbles, including rotation around the camera axis. The normal
  matcher searches only two rotation components and assumes a positive rolling
  direction. Independent SIFT/ORB correspondences support roughly minus seven
  degrees of camera-axis rotation for frame 308 to 309. Diagnostic inverse
  matches also support backward rocking in some later pairs.
- Frame 308 to 309 failed the coarse downsampled residual gate at 0.617,
  before native matching ran. The final native 3D measurement passes the
  unchanged 0.58 limit with residual **0.3713** and independent inverse
  disagreement **1.3935 degrees**.
- The point sampler can concentrate on reflections. The persistent black
  freckle leaves its central 0.66-radius region in frame 311 (radius about
  0.715). Reverse samples then concentrate on the highlight. The old accepted
  310 to 311 pose misses that freckle by about **11.7 pixels**.
- Later views show much less visible surface change. Missing original frame
  330 also breaks the sequence. Neither repeated views nor assumed conveyor
  speed can supply missing surface evidence.

The [image investigation](../20261004_motion/REPORT.md) and
[matcher review](../20261004_review/REPORT.md) retain original crop illustrations,
all matches and approximate manual landmarks.

## What changed

For a failed coarse match in the dense recorded-video profile, the mapper can
retry native surface-aligned patterns with a bounded third rotation component.
The retry is enabled only when the rolling search bound is at most 20 degrees,
native aligned matching and bidirectional checks are configured, and native
refinement is enabled. Camera-axis rotation is bounded by 10 degrees.

The original residual, minimum rolling angle and rolling search bounds remain
in force. Rolling and camera-axis boundary solutions are rejected. Independently
fitted forward and reverse rotations must agree as inverses within three degrees;
both must also agree with the joint estimate within three degrees.

The retry requires **at least one native pixel of rolling displacement**.
Independent inverse consistency alone admitted 13 of 32 false stationary fits
in the preceding candidate; their maximum rolling displacement was 0.639
pixels. The floor rejects all 32 prescribed stationary component pairs.
The existing smoothed-green path still handles normal subpixel measurements.

The correction does not enable backwards rolling, select a different model
after a successful coarse match, bridge missing frames or infer a full turn.
Wider sparse/live profiles preserve their existing behavior. An exploratory
55-degree author-profile run was stopped after demonstrating substantially
higher cost; it is partial experimental evidence, not a completed benchmark of
the final source. Its 24 completed sequences took 758.82 seconds versus 226.78
seconds for the same historical sequences (3.35 times as long, with concurrent
workload differences). The final scope check matches all 16 checked author pairs,
including all 10 experimental rescues, to the original 55-degree behavior and
launches no three-axis retry. [Timing/scope assessment](../20261004_review/partial_author_scope_assessment.json)
and [exact pair parity](../20261004_review/scoped_author_path_parity.json) preserve
the measurements and limits.

## Evidence for the recovered pair

The native image matcher independently estimates frame 308 to 309 as
`[12.5235, -8.6043, -6.6061]` degrees. Its pose was not fitted to the SIFT/ORB
correspondences used below.

| All mutual descriptor matches | Count | Earlier two-component retry median | Final three-component retry median |
| --- | ---: | ---: | ---: |
| Raw SIFT | 10 | 5.4696 px | 1.1859 px |
| High-pass ORB | 23 | 5.3351 px | 1.2323 px |

Every mutual match is included, without RANSAC filtering. Large outliers remain:
the final means are 9.6656 and 7.8532 pixels, and maxima are 75.2881 and 88.8227
pixels respectively. Automatically matched points can be wrong; these are
image-correspondence checks, not calibrated pose accuracy. The separately checked
black freckle projects within **1.0455 pixels**, inside its approximate two-pixel
labelling uncertainty. Earlier accepted pairs retain documented errors.

[Exact comparison arrays](../20261004_motion/final_candidate_feature_evidence.json)
and [visually checked map/feature figure](../20261004_motion/fruit340_final_comparison.png)
preserve these limits and the rejected two-component attempt.

## Mapping and model replay

| Physical raw ID | Frozen input views | Baseline selected | Final selected | Baseline surface | Final surface |
| --- | ---: | --- | --- | ---: | ---: |
| 98 | 66 | 66–89 | 62–98 | 85.0736% | 84.9590% |
| 1 | 46 | 5–16 | 5–16 | 39.1436% | 39.1436% |
| 14 | 44 | 3–4 | 1–4 | 25.9621% | 32.4370% |
| 340 / fixture 491 | 59 | 305–308 | 305–309 | 26.4127% | 32.2200% |

The [paired geometry replay](../20261004_scoped_final_maps/report.json) uses the
same frozen inputs for both sources, with defect inference and grading disabled.
These estimates measure selected-view/map execution, rather than true physical
coverage. Increased availability alone does not establish better accuracy for
the other fruit.

The [final CUDA integration](../../algorithm-revision/fruit340_scoped_final_real_model_20261004/report.json)
loads the actual detector and defect-segmentation weights, then maps all 215
frozen views. It repeats segmentation and mapping, with zero detector inference
calls and no new tracking. This is not a fresh full-video analysis. The
replay makes **58 actual segmentation calls and returns 104 predicted instances**;
execution passes for all four fruit. Fruit 340's resulting
defect grade applies provisionally to observed surface only; the map
does not meet the app's 80% coverage target.

## Validation and remaining limits

The final software regression suite passes **94 tests**, including independently
rendered tumbling and stationary-noise cases, inverse disagreement, unchanged
residual/angle gates, and excluding the expensive retry from sparse profiles.

The [motion control findings](../20261004_controls/CONTROL_FINDINGS.md) and
[final scope verification](../20261004_controls/final_scope/FINAL_SCOPE_PROVENANCE.md)
retain the complete source/input provenance:

- All 19 established controls pass: 190 known moving pairs satisfy their fixed
  accuracy limits; 752 stationary/uniform pairs remain unavailable and produce
  no map or grade. Existing measured outputs are unchanged.
- Explicit native 3D component controls measure 60 of 60 known moving pairs;
  maximum propagated pose error is 0.1289 degrees and visible-landmark RMS is
  0.0838 pixels. All 32 stationary component pairs are rejected after the floor.
- One additional changing-light scene retains a baseline false stationary pose
  of 5.1427 degrees. Two complete-estimator tumbling scenes also retain baseline
  failures (about 20 degrees maximum propagated error), because their coarse
  two-component matches succeed and therefore never invoke the retry.

These synthetic controls are development tests with ideal masks. The successful
component results do not imply that the complete estimator always chooses the
right rotation model. The final scope-only change is separately recorded against
the tested candidate; all dense 20-degree paths are identical. Sparse-profile
parity and the partial wider-profile timing check are recorded in the matcher
review. [Known-area controls](../../authors-benchmark/synthetic_runs/fruit340_scoped_final_20261004/report.json)
separately pass the supplied 5%, 15% and 30% defect cases plus four coverage
gates; they bypass motion and segmentation.

The [research paper underlying the spheroid mapper](https://www.mdpi.com/1424-8220/21/6/2232)
explicitly distinguishes many captured views from examining the whole fruit
surface. The new native retry and its safety gates are this project's engineering
adaptations, not a claim that the paper validates them. Fruit 340 still needs
reliable pose measurements over a larger surface before its complete map or
whole-fruit grade can be trusted.

## Reproduce

From the project root, with fresh diagnostic labels:

```powershell
./backend/venv/Scripts/python.exe -B -m unittest discover -s backend -p 'test_*.py'
./backend/venv/Scripts/python.exe -B backend/validate_native_rotation_retry.py --baseline backend/diagnostics/fruit340-fix/20261004_candidate/baseline/algorithm.py --label <fresh-label>
./backend/venv/Scripts/python.exe -B backend/validate_model_mapping_integration.py --label <fresh-label>
./backend/venv/Scripts/python.exe -B backend/validate_synthetic_mapping.py --label <fresh-label>
```

The unit suite's mocked API message about submitting the complete original video
is not evidence that a new real full-video run occurred. Diagnostic replays
preserve earlier reports; the source change applies when the backend next loads
the algorithm and a new analysis runs.
