# Does the reconstruction algorithm need to change?

Recorded 2026-10-02T11:44:43.890642+02:00.

## Decision

**Yes: the motion-matching and view-selection adaptation needs correction and
validation.** The current tests have not identified a new algebraic error in the
spheroid equations, image lifting, surface coordinates or area Jacobian. They do
identify accepted bad skipped-frame matches and a mismatch between accepted
rotation vectors and the map's required longitude order.

The two tested quick safeguards remain experimental. Neither establishes accurate
conveyor reconstruction. Production algorithm/API/model-adapter bytes are unchanged
from the beginning of this audit. Existing saved maps and grades are not replaced.
The user's detection and defect-segmentation checkpoints are unchanged.

## 1. Verify motion on author data, including skipped frames

All 497 published correspondences connect adjacent images. The earlier benchmark
reported 458 predictions with RMS 5.103 pixels by checking adjacent estimates. That
result did not validate every longer transition introduced by the selector.

This audit reconstructs label chains only where one published target coordinate
exactly equals another published source coordinate for the same fruit and image.
No coordinate interpolation, fitted motion or model prediction supplies the endpoint
truth. The original annotation line numbers and chain paths are retained.

The production selector retained 20 nonadjacent
transitions across the 36 sequences. Only four had exact chained feature endpoints.
All four were accepted by the residual gate, but missed the endpoints by more than
five pixels:

| Author fruit | Image pair | Endpoint error, pixels | Original annotation lines |
| --- | --- | ---: | --- |
| mandarins/obj0000 | 4→6 | 34.06 | 9, 8 |
| tomatoes/obj0004 | 6→8 | 41.38 | 93, 92 |
| tomatoes/obj0009 | 7→10 | 17.04 | 151, 150, 147 |
| tomatoes/obj0009 | 13→17 | 16.41 | 161, 160, 158, 159 |

The four-endpoint RMS is 29.291 pixels. All endpoints lift finitely onto the visible
side of the estimated surface. Two lifted endpoint separations exceed the search's
maximum total angle (~55.90°); this is a model-based indication of an insufficient
search domain, not measured physical rotation. A long unknown gap can alias to an
apparently acceptable small rotation. Sixteen other baseline bridges have no exact
chain verification and must not be counted as correct.

The chained observations are correlated development evidence, separate from the
original 497-label denominator. Four labelled bridges do not establish general
bridge accuracy. [Detailed author audit](author_bridge_baseline/BRIDGE_AUDIT.md)
and its raw JSON retain projections, masks, chain provenance and composition checks.

## 2. Reproduce an actual map-ordering failure

Original fruit 491 is replayed using the cached original detector boxes and exact
video, without neural inference. All 75 box observations match the earlier tracking
cache exactly. Fresh GrabCut yields 59 usable crops versus the historical 60;
three retained mask comparisons have IoU 0.9953–0.9997. Thus this is a reproducible
failure on fresh masks, not byte-identical replay of every historical mask.

At frames 305→306, the selector accepts Rodrigues components x = +3.005° and
y = −5.262°, yet the map's fruit-fixed longitude moves backwards by 1.782°.
The selector tests the magnitude of the configured rolling component, whereas
surface fusion requires a consistently ordered longitude trajectory. Sideways
motion exceeds forward rolling motion in this accepted pair. The later order check
then rejects the entire selected segment.

![Actual source crops and the backwards map transition](longitude_failure/longitude_failure_comparison.png)

A sphere control avoids that ordering error but reaches only 214.58° observed
longitude. Changing every naartjie to a sphere is not supported by this outcome.
No manually measured motion truth was available to distinguish real wobble from
a false transverse texture match. [Full trace and methodology](longitude_failure/AUDIT.md).

## 3. Hold actual corrected-track crops fixed and change one assumption

The corrected tracker output is matched to original baseline IDs 125, 1 and 14.
These are one formerly numerically graded example and the first two recorded
objects, not a random or held-out sample. Each configuration receives identical
preserved crops and masks. Detection and defect inference are not rerun.

Corrected ID 98 has 66 complete crops, frames 62–127, while its tracked identity
spans frames 51–138. Its partial edge observations preserve tracking but do not
provide the complete silhouette required by the spheroid estimator.

| Same corrected fruit 98 | Estimated rotation | Observed longitude |
| --- | ---: | ---: |
| baseline_auto_x_positive_d4 | 241.03 | 335.59 |
| sphere_x_positive_d4 | 117.43 | 207.08 |
| auto_x_positive_d2 | 144.17 | 238.73 |
| negative_direction_control | 8.00 | 93.81 |
| vertical_axis_control | 23.89 | 118.98 |

The current x/positive/auto/d4 setting yields 241.03° estimated rolling motion and
335.59° observed longitude. The historical ID 125 run reported 380.96° / 360°.
That historical comparison changes both detector boxes and stochastic mask
extraction; it cannot isolate the cause. The within-experiment variants DO hold
all images and masks fixed and show substantial estimator/selection sensitivity.

All 15 combinations on the three corrected tracks remain below the 350° longitude
gate. Neither changing axis, direction, shape nor resolution demonstrated a reliable
full map. Coverage is not geometric accuracy. There are no defect masks or grades
in these tests. Each plotted cumulative curve starts at zero for its retained
segment; configurations can retain different starting frames.

![Identical crops under isolated assumptions](corrected_tracks/algorithm_sensitivity.png)

## 4. Test proposed safeguards before enabling them

**Skipped-frame residual guard:** an isolated algorithm snapshot rejects a bridge
over more than one captured-view index when normalized residual exceeds 0.5.
The threshold was chosen after inspecting these development failures; it is not
an independently validated confidence boundary.

- Nonadjacent bridges decrease 20→4.
  All four known bad chained bridges are excluded. The remaining four lack exact
  chain truth, so this is not a measured zero-error bridge result.
- Predictions for original adjacent labels whose endpoints survive selection
  decrease 305→285/497.
  Conditional RMS changes 4.806→
  4.924 pixels; these are different
  subsets, not an improvement comparison on a fixed denominator.
- The independent adjacent benchmark remains exactly 458/497 and 5.103 pixels RMS.
  Geometry still fits 36/36 and maps are still produced for 34/36, but coverage-eligible
  maps decrease 17→13; partial maps increase 17→21.
- The guard still accepts some long gaps with unverified endpoints. A stricter
  residual alone does not resolve unknown angular motion or texture ambiguity.

**Rolling-axis dominance guard:** an isolated wrapper rejects a pair when a
transverse Rodrigues component exceeds the configured rolling component. On the
same frozen fruit-491 inputs, the ordering failure becomes an ordered partial map
with 124.58° longitude. Corrected fruit 98 stays at 335.59°; fruit 1 increases from
110.66° to 147.31°, while fruit 14 decreases from 151.90° to 118.44°. None of the four
becomes coverage eligible. This guard fixes a specific incompatible transition but
has not demonstrated motion accuracy or an overall reconstruction improvement.

Both candidates and their before/after JSON remain in this package. They are not
enabled in the running application.

## What should change next

The next implementation should verify a skipped-frame join before using it in
surface fusion, distinguish measured small motion from failed/unmeasured motion,
and test the resulting fruit-fixed trajectory before accepting a connected segment.
An eight-image gap cap cannot express the same angular bound on the author sequence
and a densely sampled conveyor clip. Confidence must include motion ambiguity and
support across intermediate views, with evaluated prediction availability.

Use the four exact author chains, all original labels, and the reproduced 491
ordering failure as regression cases. Then use independently marked conveyor
landmarks and a verified complete turn to evaluate motion; visible image repetition
or a complete-looking map alone is insufficient. Defect-model and final-grade
accuracy remain separate tests after reconstruction passes.

The live-camera scheduler is a separate setup issue: it retains only the latest
camera frame and performs mapping in the processing loop. The recorded-video
tests do not establish that every live sensor frame is processed. A live queue,
timing and scheduling test is required before claiming immediate real-time entry
tracking or grading.

## Evidence and reproducibility

This folder retains real crops/masks/NPZ inputs, projected author points, selection
and longitude traces, all variants, candidate source, production source snapshots,
300-dpi PNG/PDF figures and checksums. Original author datasets, video and model
weights remain at their workspace paths; the full datasets are not duplicated here.
Source manifest URLs and checksums identify the pinned author data.

The research basis is the [2021 rotation method](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 surface-map method](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
This project is an independent implementation with an added capture/view-selection
stage. The new failures do not establish that the authors' unavailable source code
contains the same defects.

Run the isolated tests from the project root, using fresh labels:

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_algorithm_decision.py --label NEW_SENSITIVITY
./backend/venv/Scripts/python.exe -B backend/validate_longitude_failure.py --label NEW_LONGITUDE
./backend/venv/Scripts/python.exe -B backend/validate_rotation_dominance.py --label NEW_DOMINANCE
```

The author bridge audit's exact commands, reference report and candidate source
hash are in `author_bridge_baseline/BRIDGE_AUDIT.md` and the accompanying JSON.
The previous sealed reports and their historical grades remain unchanged.
