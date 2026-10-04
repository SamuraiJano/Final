# Algorithm revision: testing and evidence

Built 2026-10-02T13:18:57.896927+02:00.
Status: **draft; revised full API run pending**.

**Development candidate: extended stationary-motion accuracy FAILED.** A further motion correction is being investigated. The absence of a grade in these stationary examples does not make their motion estimates accurate.

The algorithm now measures consecutive usable frames, checks small successful
matches at original resolution, and checks the exact fruit-fixed longitude
trajectory before combining views. Failed, missing or unobservable motion ends a
connected sequence. The spheroid model, MAD search, rotation-matrix propagation,
surface projection and area calculation remain based on the research papers.
See [the simple explanation](source/ALGORITHM_EXPLAINED.md).

Tested development-candidate algorithm SHA256: `52c13a0452875653fb054053fcc0bdbb4a6ed9cb4227c697be32b62fbe811327`.
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
| Independent RMS, px | 5.10288 | 5.10106 |
| Within 5 px / all labels | 367/497 | 367/497 |
| Maps produced, including partial | 34 | 36 |
| Maps passing coverage gates; author defect truth absent | 17 | 14 |
| Partial maps / mapping failures | 17 / 2 | 22 / 0 |

Both algorithms return predictions for the same 458 labels. Five predictions
change and improve on these development labels; the overall accuracy difference
is small. Maximum returned error remains 35.93046 px. Labels measurable on
retained map poses increase 305→348/497; revised
conditional RMS is 4.99775 px,
on a different retained subset. Coverage eligibility is not measured grade accuracy.

The selector creates 0
nonadjacent bridges. The SAME four historically bad exact label chains are checked:
4 are excluded and 0 return a
prediction. Their exclusion demonstrates removal of those connections, rather
than accurate reconstruction of the excluded surface. Chained labels are
correlated with original annotations.

![Author error and availability counts](algorithm-revision/adjacent_scaled_source/author_accuracy_availability.png)

[Author detail](algorithm-revision/adjacent_scaled_source/AUTHOR_RESULTS.md) ·
[All original label predictions](authors-benchmark/runs/adjacent_scaled_profile_20261002/report.json) ·
[Retained-pose audit](authors-benchmark/bridge_runs/adjacent_scaled_retained_20261002/report.json).

## 2. Known motion and independently rendered landmarks

An analytical radius-55 sphere is rendered at eleven known orientations spanning
0–8 degrees, with ten variable increments (0.5–1.5 degrees). Six front-facing
body landmarks have independently computed target image coordinates. The actual
matcher and fitted sphere estimate motion; failed chains are not interpolated.
All 10/10 transitions are measured.
Final three-dimensional pose error is 0.491 degrees,
endpoint landmark RMS is 0.447 px, and maximum
landmark RMS over the chain is 0.450 px. All controls
in this initial short-motion suite pass. Its stationary noise does not produce a grade or full
longitude; uniform untextured inputs supply no measured motion.

The earlier native-resolution candidate used sigma 1.25 at full image size and
failed: pose error 3.553 degrees, endpoint
landmark RMS 3.236 px. The final recheck
preserves physical filter width: sigma 1.25 in a quarter-size image becomes sigma
5 at original size. That rejected candidate and preprocessing trials are retained.
These synthetic controls do not validate complete real-fruit motion or final grades.

![Known motion and landmark errors](algorithm-revision/motion_resolution_scaled_20261002/motion_and_landmark_accuracy.png)
![Analytical versus estimated landmarks](algorithm-revision/motion_resolution_scaled_20261002/endpoint_landmark_comparison.png)

### Extended moving and stationary controls

Two independently rendered textures test known noncommuting x/y wobble. Two
additional 120-frame scenes are truly stationary with independent pixel noise.
Their complete measured chains are scored against exact pose and six landmarks;
their shorter selected partial-map spans are a separate output.

| Known scene | Frames | Endpoint pose error, deg | Endpoint landmark RMS, px | Accuracy controls |
| --- | --- | --- | --- | --- |
| variable_xy_texture_a | 11 | 0.762 | 0.691 | pass |
| variable_xy_texture_b | 11 | 0.278 | 0.254 | pass |
| stationary_120_texture_a | 120 | 59.768 | 45.540 | FAIL |
| stationary_120_texture_b | 120 | 7.388 | 6.718 | FAIL |

The moving controls pass, but both extended stationary controls fail accuracy.
The candidate returns spurious motion even though neither selected map receives
a grade or full longitude. In particular, a roughly eight-degree-looking rotation
or a protective Review result cannot certify geometric accuracy. These failures
mean this source must remain a development candidate. An isolated preprocessing
correction is under investigation; it is not included as a tested fix here.

![Extended pose and landmark accuracy](algorithm-revision/extended_motion_controls_20261002/extended_motion_accuracy.png)
[Full extended test record](algorithm-revision/extended_motion_controls_20261002/EXTENDED_CONTROLS.md).


## 3. Hold the real conveyor images and masks fixed

Four selected tracks from the exact original clip are replayed with identical
frozen crops and masks for every variant. There are 215
complete input views. Detection, tracking, GrabCut and defect inference are not
rerun in this geometry comparison. These are development examples, not a random
or held-out conveyor sample, and they have no independent motion truth.

| Track | Complete input views | Retained views | Original frames | Observed longitude, deg | Result |
| --- | --- | --- | --- | --- | --- |
| 98 | 66 | 20 | 66–85 | 343.98 | insufficient_longitude_coverage |
| 1 | 46 | 12 | 5–16 | 166.71 | insufficient_longitude_coverage |
| 14 | 44 | 5 | 5–9 | 130.48 | insufficient_longitude_coverage |
| 491 | 59 | 4 | 305–308 | 161.53 | insufficient_longitude_coverage |

All four remain below the 350-degree longitude gate. Track 491 changes from a
late ordering failure to an ordered partial map. Its reference frame changes
when the connected segment changes; this does not prove that the formerly
backwards transition is physically correct. More coverage or an ordered map is
not a substitute for independently marked conveyor landmarks and a verified turn.
An all-native-resolution candidate was also tested and rejected for short,
fragmented retained segments; its results are included.

![Fixed actual conveyor inputs](algorithm-revision/fixed_scaled_conveyor_20261002/fixed_input_comparison.png)

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
conveyor inputs. It executes 41 real model
calls and returns 76 defect instances.
Masks, overlays, surface maps and diagnostics are saved. All four maps remain
partial and receive no grade. This confirms execution and report integration;
there is no defect-mask or grade truth to score accuracy. Model certainty is
not measured accuracy. Model checkpoints are identified by SHA256 below and are
not copied into the archive.

## 5. Software checks and revised full-video execution

All 36 Python tests, frontend build and frontend lint pass. Their actual
commands, timestamps, output and execution-source hashes are retained in
[software-checks/adjacent_scaled_20261002](software-checks/adjacent_scaled_20261002/summary.json).
Tests verify implementation behavior; they do not replace image-label accuracy tests.

The complete revised API run is still pending at this report's build time. This draft contains the completed fixed-input and real-segmenter integration tests, but does not claim a completed revised full-video run. Rebuild with `--refresh` after its summary finishes.

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
./backend/venv/Scripts/python.exe -B backend/build_algorithm_revision_evidence.py --label evidence_20261002 --refresh
```

The per-run validation scripts and settings provide the individual reproductions.
Each new test run must use a fresh label. [SHA256SUMS.txt](SHA256SUMS.txt) covers the
bundle payload; [bundle_summary.json](bundle_summary.json) identifies the sources
and scope. The report preserves failed candidates and explicitly separates known
synthetic answers, author feature-label accuracy, unlabelled conveyor coverage,
model execution, and software checks.
