# Algorithm revision: testing and evidence

Built 2026-10-02T14:35:27.516726+02:00.
Status: **draft; revised full API run pending**.

**Full-turn motion accuracy FAILED on this development source.** It passes the limited small-motion/observability controls, but independently known complete turns reveal substantial drift despite full-looking maps and Class 1 arithmetic. It cannot be described as geometrically validated or accurate for conveyor grading.

The algorithm now measures consecutive usable frames, checks small successful
matches at original resolution with native noise filtering, and checks the exact fruit-fixed longitude
trajectory before combining views. Failed, missing or unobservable motion ends a
connected sequence. The spheroid model, MAD search, rotation-matrix propagation,
surface projection and area calculation remain based on the research papers.
See [the simple explanation](source/ALGORITHM_EXPLAINED.md).

Tested final revision algorithm SHA256: `863fd09cfa629c5b5b8ba7c73963fbe993441b3e3dd989f1e451d0a5f62c9db1`.
This identifies the retained execution source; later source edits are not covered
by these results. The user's detection and segmentation weights are unchanged.

## 1. Author images and published feature labels

All 578 original images in 36 sequences (15 mandarins, 10 oranges, 11 tomatoes)
and all 497 published correspondences were used. Labels score predictions; they
do not fit motion. The masks are derived from the black backgrounds. These data
were inspected during development and are not held-out evaluation.

| Indicator | Previous operational algorithm | Final revision |
| --- | --- | --- |
| Independent returned predictions / labels | 458/497 | 458/497 |
| Independent RMS, px | 5.10288 | 5.10295 |
| Within 5 px / all labels | 367/497 | 367/497 |
| Maps produced, including partial | 34 | 36 |
| Maps passing coverage gates; author defect truth absent | 17 | 14 |
| Partial maps / mapping failures | 17 / 2 | 22 / 0 |

Both algorithms return 458 independent adjacent predictions. Their conditional
RMS differs only slightly; this does not demonstrate a general accuracy improvement.
Maximum returned error remains 35.93046 px. Labels measurable on
retained map poses increase 305→348/497; revised
conditional RMS is 4.99793 px,
on a different retained subset. Coverage eligibility is not measured grade accuracy.

The selector creates 0
nonadjacent bridges. The SAME four historically bad exact label chains are checked:
4 are excluded and 0 return a
prediction. Their exclusion demonstrates removal of those connections, rather
than accurate reconstruction of the excluded surface. Chained labels are
correlated with original annotations.

![Author error and availability counts](algorithm-revision/adjacent_observable_source/author_accuracy_availability.png)

[Final source/profile](algorithm-revision/adjacent_observable_source/metadata.json) ·
[All original label predictions](authors-benchmark/runs/adjacent_observable_profile_20261002/report.json) ·
[Retained-pose audit](authors-benchmark/bridge_runs/adjacent_observable_retained_20261002/report.json).

## 2. Known motion and explicitly unavailable stationary motion

Two independent body textures render ten known variable x/y wobble transitions
on an analytical radius 55 sphere. Six front-facing body landmarks have
independently calculated target coordinates. Both moving scenes retain all ten
measurements and meet the unchanged one-degree endpoint-pose and one-pixel
maximum-landmark RMS controls. This is synthetic development evidence, not field
or complete-turn accuracy.

| Final observable scene | Returned / attempted pairs | Endpoint pose error, deg | Endpoint landmark RMS, px | Mapping |
| --- | --- | --- | --- | --- |
| variable_xy_texture_a | 10/10 | 0.773 | 0.701 | insufficient_longitude_coverage |
| variable_xy_texture_b | 10/10 | 0.272 | 0.248 | insufficient_longitude_coverage |
| stationary_120_texture_a | 0/119 | unavailable | unavailable | mapping_failed |
| stationary_120_texture_b | 0/119 | unavailable | unavailable | mapping_failed |

Each stationary scene has 120 independently noisy images and 119 adjacent pairs.
All 119 dominant-turn measurements are explicitly unavailable, all native
attempts are recorded, no endpoint pose is extrapolated, and no map or grade is
produced. No exact zero rotation is claimed. The helper's stationary maximum
error of zero refers only to the initial reference frame; it is not 119 scored
stationary predictions. Endpoint pose/landmark errors are null.

The final source applies native-only float-green Gaussian sigma 2 before the
physical-width sigma 5 high-pass recheck and a quarter-degree observable rolling
minimum consistently in direct measurement and selection. These are engineering
adaptations around the paper's spheroid and MAD estimator. Coarse failed matches
are not rescued. Moving thresholds and denominators are unchanged; stationary
control tests honest measurement unavailability rather than an invented zero.

![Final moving pose and landmark accuracy](algorithm-revision/observable_motion_controls_20261002/observable_moving_accuracy.png)
![Stationary measurements explicitly unavailable](algorithm-revision/observable_motion_controls_20261002/stationary_observability.png)
[Exact final observability record](algorithm-revision/observable_motion_controls_20261002/OBSERVABLE_MOTION_CONTROLS.md).

### Actual matcher over independently known complete turns

This control executes the actual geometry fit, image matcher, pose composition,
selector and surface fusion. Rotations are not mocked. It renders independent
body textures and 36 known spherical landmarks over a complete turn: 60 constant
six-degree transitions for texture A, and 120 alternating 0.6/5.4-degree transitions
for texture B. Perfect masks and analytical camera geometry isolate motion/fusion
from the detector and defect model. Explicit all-clear masks exercise zero-defect
class arithmetic; they do not validate the real segmentation model.

| Known complete turn | Returned / attempted pairs | Maximum 3D pose error, deg | Maximum front-visible landmark RMS, px | All-clear map class | Motion accuracy |
| --- | --- | --- | --- | --- | --- |
| constant_6deg_texture_a | 60/60 | 25.744 | 17.029 | Class 1 | FAIL |
| variable_06_54deg_texture_b | 120/120 | 21.415 | 14.371 | Class 1 | FAIL |

Both cases return every transition and produce 360-degree observed maps and Class 1
all-clear arithmetic, yet fail the predeclared five-degree pose and five-pixel
landmark controls. Thus a complete map, a low residual, or a grade does not prove
accurate surface reconstruction. The short moving and stationary-rejection passes
above remain valid within their scope and cannot outweigh this full-turn failure.
Further motion correction is being investigated in isolated candidates; no later
candidate is silently substituted for this source or its running API outcomes.

![Known full-turn pose and landmark error](algorithm-revision/full_turn_observable_20261002/full_turn_accuracy.png)
[Full actual-matcher control record](algorithm-revision/full_turn_observable_20261002/FULL_TURN_CONTROLS.md).


### Separate photometric development candidates

These isolated trials use their own frozen execution source and settings. They do not replace the observable-source outcomes above or its running API job. Original-green matching compares sampled green intensities after subtracting median brightness offset, while preserving high-pass texture selection and the spheroid/MAD search. A further candidate smooths compared green intensities with sigma 2. No accuracy or availability limit is relaxed.

| Isolated run | Source SHA prefix | Known scene | Returned / attempted | Known geometry error | Actual map status | Defined control |
| --- | --- | --- | --- | --- | --- | --- |
| [full_turn_native_20261002](algorithm-revision/full_turn_native_20261002/report.json) | 863fd09cfa62 | constant_6deg_texture_a | 60/60 | max 18.651 deg / 12.565 px | graded | FAIL |
| [full_turn_native_20261002](algorithm-revision/full_turn_native_20261002/report.json) | 863fd09cfa62 | variable_06_54deg_texture_b | 120/120 | max 13.878 deg / 9.383 px | graded | FAIL |
| [full_turn_green_20261002](algorithm-revision/full_turn_green_20261002/report.json) | 46a46f9aac7c | constant_6deg_texture_a | 60/60 | max 0.117 deg / 0.080 px | graded | PASS |
| [full_turn_green_20261002](algorithm-revision/full_turn_green_20261002/report.json) | 46a46f9aac7c | variable_06_54deg_texture_b | 120/120 | max 0.157 deg / 0.107 px | graded | PASS |
| [photometric_motion_controls_20261002](algorithm-revision/photometric_motion_controls_20261002/report.json) | 46a46f9aac7c | variable_xy_texture_a | 10/10 | endpoint 0.041 deg; max RMS 0.068 px | insufficient_longitude_coverage | PASS |
| [photometric_motion_controls_20261002](algorithm-revision/photometric_motion_controls_20261002/report.json) | 46a46f9aac7c | variable_xy_texture_b | 10/10 | endpoint 0.048 deg; max RMS 0.079 px | insufficient_longitude_coverage | PASS |
| [photometric_motion_controls_20261002](algorithm-revision/photometric_motion_controls_20261002/report.json) | 46a46f9aac7c | stationary_120_texture_a | 83/119 | endpoint unavailable | insufficient_longitude_coverage | FAIL |
| [photometric_motion_controls_20261002](algorithm-revision/photometric_motion_controls_20261002/report.json) | 46a46f9aac7c | stationary_120_texture_b | 0/119 | endpoint unavailable | mapping_failed | PASS |
| [photometric_smoothed_controls_20261002](algorithm-revision/photometric_smoothed_controls_20261002/report.json) | 1fb1a343f66e | variable_xy_texture_a | 10/10 | endpoint 0.222 deg; max RMS 0.202 px | insufficient_longitude_coverage | PASS |
| [photometric_smoothed_controls_20261002](algorithm-revision/photometric_smoothed_controls_20261002/report.json) | 1fb1a343f66e | variable_xy_texture_b | 10/10 | endpoint 0.085 deg; max RMS 0.086 px | insufficient_longitude_coverage | PASS |
| [photometric_smoothed_controls_20261002](algorithm-revision/photometric_smoothed_controls_20261002/report.json) | 1fb1a343f66e | stationary_120_texture_a | 0/119 | endpoint unavailable | mapping_failed | PASS |
| [photometric_smoothed_controls_20261002](algorithm-revision/photometric_smoothed_controls_20261002/report.json) | 1fb1a343f66e | stationary_120_texture_b | 0/119 | endpoint unavailable | mapping_failed | PASS |

The original-green full-turn control can pass while its independent stationary texture A returns false turns; that candidate is rejected. Stationary endpoints are unavailable after any missing transition, and no rejected measurement is scored as zero. Exposure-offset comparisons and exact acceptance results are retained in each motion-control JSON/Markdown. Passing these ideal development cases does not establish author, conveyor or defect-grade accuracy. The original-green chart's unsupported static annotation was corrected separately; original exports and explicit postprocessing provenance are retained without changing measurements.


### Preserved failed development controls

The earlier source `52c13a0452875653fb054053fcc0bdbb4a6ed9cb4227c697be32b62fbe811327` returned false stationary
motion when all subresolution estimates were propagated. Its raw failures remain
unchanged; this is a different source and a different test from final observable
measurement rejection. Both synthetic moving textures passed, while both
120-frame independent-noise stationary accuracy controls failed.

| Historical scene | Frames | Raw endpoint pose error, deg | Raw landmark RMS, px | Raw accuracy control |
| --- | --- | --- | --- | --- |
| variable_xy_texture_a | 11 | 0.762 | 0.691 | pass |
| variable_xy_texture_b | 11 | 0.278 | 0.254 | pass |
| stationary_120_texture_a | 120 | 59.768 | 45.540 | FAIL |
| stationary_120_texture_b | 120 | 7.388 | 6.718 | FAIL |

Native sigma 1.118 and sigma 2 prefilter trials reduce drift but do not pass all
original forced-zero-minimum raw accuracy controls. Their failures remain in
[the prefilter record](algorithm-revision/native_prefilter_trials_20261002/NATIVE_PREFILTER_TRIALS.md).
The final observability control never extrapolates unavailable poses or replaces
these failed raw errors with zero. It requires all stationary dominant turns to
be rejected and retains all ten real moving transitions per texture.

![Preserved stationary accuracy failure](algorithm-revision/extended_motion_controls_20261002/extended_motion_accuracy.png)
[Historical extended record](algorithm-revision/extended_motion_controls_20261002/EXTENDED_CONTROLS.md).


## 3. Hold the real conveyor images and masks fixed

Four selected tracks from the exact original clip are replayed with identical
frozen crops and masks for every variant. There are 215
complete input views. Detection, tracking, GrabCut and defect inference are not
rerun in this geometry comparison. These are development examples, not a random
or held-out conveyor sample, and they have no independent motion truth.

| Track | Complete input views | Retained views | Original frames | Observed longitude, deg | Result |
| --- | --- | --- | --- | --- | --- |
| 98 | 66 | 20 | 66–85 | 343.98 | insufficient_longitude_coverage |
| 1 | 46 | 6 | 11–16 | 125.75 | insufficient_longitude_coverage |
| 14 | 44 | 6 | 5–10 | 138.51 | insufficient_longitude_coverage |
| 491 | 59 | 4 | 305–308 | 161.53 | insufficient_longitude_coverage |

All four remain below the 350-degree longitude gate. Track491 changes from a late
ordering failure to an ordered partial map; the available segment remains short. Its reference frame changes
when the connected segment changes; this does not prove that the formerly
backwards transition is physically correct. More coverage or an ordered map is
not a substitute for independently marked conveyor landmarks and a verified turn.
An all-native-resolution candidate was also tested and rejected for short,
fragmented retained segments; its results are included.

![Fixed actual conveyor inputs](algorithm-revision/fixed_observable_conveyor_20261002/fixed_input_comparison.png)

## 4. Defect area arithmetic and real model integration

Known 5%, 15% and 30% longitude-wedge defects are projected using exact geometry
and known rotations. The motion estimator and neural models are deliberately
bypassed in this control. It tests repeated-defect union, area normalization and
the configured class arithmetic, rather than real defect-model accuracy.

| Known observed defect area | Measured | Absolute percentage-point error | Configured class |
| --- | --- | --- | --- |
| 5% | 5.14365% | 0.14365 | Class 1 |
| 15% | 15.17867% | 0.17867 | Class 2 |
| 30% | 30.09276% | 0.09276 | Class 3 |

All area and coverage controls pass. Known 375- and 270-degree turns support full
observed longitude; the 250- and 100-degree controls remain partial. The 10%/20%
class thresholds are local engineering rules, not author-validated conveyor grades.

The separate real D-FINE segmentation integration receives the same four frozen
conveyor inputs. It executes 36 real model
calls and returns 74 defect instances.
Masks, overlays, surface maps and diagnostics are saved. All four maps remain
partial and receive no grade. This confirms execution and report integration;
there is no defect-mask or grade truth to score accuracy. Model certainty is
not measured accuracy. Model checkpoints are identified by SHA256 below and are
not copied into the archive.

## 5. Software checks and revised full-video execution

All 37 Python tests, frontend build and frontend lint pass. Their actual
commands, timestamps, output and execution-source hashes are retained in
[software-checks/observable_motion_20261002](software-checks/observable_motion_20261002/summary.json).
Tests verify implementation behavior; they do not replace image-label accuracy tests.

The final observable-source API run is still pending at this report's build time. This draft contains the completed fixed-input and real-segmenter integration tests, but does not claim a completed revised full-video run. Rebuild with `--refresh` after its summary finishes.

## 6. Separate geometry and performance diagnostics

[The historical fixed-size spheroid audit](algorithm-revision/geometry_scale_audit_20261002/GEOMETRY_SCALE_AUDIT.md)
uses source 52c13 and the same frozen 215 real crops. Its source and selected
segments are historical. Tracks 98 and 491 have larger major-radius variability
than the author sample; perspective, mask error and real shape remain possible
causes. This does not justify a new geometry equation or establish a calibrated
camera discrepancy.

[The paired GrabCut thread test](algorithm-revision/grabcut_threads_20261002/GRABCUT_THREADS.md)
uses twelve real crops and 36 paired observations. Native 16 threads average 28.918 ms
versus 30.286 ms for one thread, with every paired mask bit-identical. Concurrent
load limits timing inference; this does not justify a production thread change
or explain the full pipeline runtime.

The prior full_revised API attempt was interrupted and remains incomplete.
Its request and any available interruption metadata are retained separately in
[prior_api_interruption.json](prior_api_interruption.json); it supplies no completed
full-video outcome in this pack. The final full_observable run is the only API
run eligible for the completed-run section above.

## Files, provenance and reproduce

The gallery contains real author/conveyor images, analytical controls, and
exportable 300-dpi PNG/PDF figures. The archive retains all result JSON, frozen
source, software output, model hashes and original annotation provenance.
Real NPZ inputs are stored once; duplicate historical inputs are resolved by
[input_references.json](input_references.json), with SHA256 equality checked.
The complete original author datasets and video are not duplicated; their source
manifest and input/run hashes identify them. The original video is
`WIN_20260818_13_29_43_Pro.mp4`, SHA256
`dc25964bf6052972cad761b0246f79906e768c6737bf4228ba44711d7272429c`.

The research basis remains the [2021 rotation paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 surface-map paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
This is an independent implementation; public author repositories provide data
and annotations rather than the reconstruction source used here.

From the original workspace, build from the frozen runs without rerunning models:

```powershell
./backend/venv/Scripts/python.exe -B backend/build_algorithm_revision_evidence.py --label evidence_observable_20261002 --refresh
```

The per-run validation scripts and settings provide the individual reproductions.
Each new test run must use a fresh label. [SHA256SUMS.txt](SHA256SUMS.txt) covers the
bundle payload; [bundle_summary.json](bundle_summary.json) identifies the sources
and scope. The report preserves failed candidates and explicitly separates known
synthetic answers, author feature-label accuracy, unlabelled conveyor coverage,
model execution, and software checks.
