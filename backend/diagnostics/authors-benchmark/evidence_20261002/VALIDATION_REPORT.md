# Reconstruction validation and evidence

Generated: 2026-10-02T07:46:42.426245+02:00. All logged local times are SAST (UTC+02:00).

## Outcome and scope

The independent reconstruction implementation now fits all 36 author sequences and
produces 34 maps, including partial maps; the frozen baseline produced no maps.
It returns 458/497 labelled point predictions with RMS 5.103 px and median 2.264 px.
The deterministic first-32-track test produced **zero eligible grades**; it was not
the complete video. Full-video outcomes are reported below. Reliable grading
accuracy on the actual conveyor has **not been established**. The requested midnight
deadline was not met; this report does not claim otherwise.

The complete original video was submitted through the actual application API. It recorded 402 fruit records. Statuses: `{'mapping_failed': 120, 'insufficient_longitude_coverage': 274, 'graded': 8}`. Grades: `{'ungraded': 394, 'Class 1': 8}`. Saved application job: `f2276fe89ce24fe1a155c228a00e3f17`. These are algorithm outputs, not manually validated classifications.


The full video returned **8/402 algorithm-assigned grades** (1.99% availability). This percentage measures returned grades, not grading accuracy.

Analysis took 28.58 minutes for a 17.3-second video. The measured pipeline does not support real-time grading at this throughput.

| Mapping-failure reason | Records |
|---|---:|
| No complete, usable fruit silhouettes were captured. | 88 |
| No reliable rotating sequence; inspect motion, reflections and fruit masks | 20 |
| At least two views are required | 7 |
| Fruit-fixed longitude centers are not consistently ordered | 5 |

Detector calls: 515; predicted instances: 55057. Segmenter calls: 3169; predicted instances: 3418. These are inference/prediction counts, not unique fruit or unique defects.


## What was tested and with what

1. **Author-labelled motion:** all 578 original images in 36 sequences (15 mandarin,
   10 orange, 11 tomato); all 497 published correspondences (132/179/186).
   Five mandarin sequences have no point labels but remain in map-completion counts.
2. **Analytical geometry controls:** known oblate shape and rotations about either
   equatorial or symmetry axes; 16 views at 25° increments, expected total 375°.
3. **Known defect-area controls:** rendered sphere, known 5%, 15%, 30% masks and exact
   motion. The maximum measured area error was 0.179 percentage points, within the
   declared 1-point tolerance. All three expected grade classes passed.
4. **Coverage controls:** known 375°, 270°, 250°, 100° motion; full longitude was observed
   for the first two, while the latter two correctly remained ungraded.
5. **Model integration:** actual D-FINE detector, TrackTrack, GrabCut and the user's
   D-FINE-seg checkpoint on the exact 515-frame video
   `C:/Users/USER/Pictures/Camera Roll/WIN_20260818_13_29_43_Pro.mp4`.
   The recorded 32-track subset is the first 32 IDs with usable complete crops.
6. **Software regression:** 23 unit/integration-contract checks, including visibility,
   coordinate geometry, stationary-fruit rejection, missing-transition isolation,
   deferred segmentation, tracker identity, cancellation and inspection-history
   filtering beyond the old 60-result cutoff. Test, production-build and lint logs
   are retained in `software_checks/`, including exit codes and tested source hashes.
   A separate headless Edge check opened the real saved report, filtered Class 1,
   inspected track 125 and loaded all nine source evidence images without a page
   error. Its screenshots and observations are retained in `ui_checks/`.
7. **Optimization parity:** 42 real author pairs, scalar versus batched search;
   identical accepted rotations and rejection reasons, 8.71x faster search in this
   local microbenchmark. This is not an end-to-end speed claim.

## Method and denominators

Author masks were derived from nonblack pixels, retaining the largest component
and filling its external contour. They are not author-supplied mask ground truth.
No detector or defect network was used in the author reconstruction benchmark.
Coordinates were evaluated at the original image resolution. Annotated source points
were lifted onto the fitted spheroid, transformed by the estimated rotation and
projected into the target image. Forward and backward annotation order was respected.
Error is Euclidean pixel distance; RMS is `sqrt(mean(error_px**2))`.
Rejected predictions are counted as unavailable and never assigned zero error.

The declared calibration objects were the first object in each category (49 labels).
The remaining split has 448 labels. Because the dataset was inspected during ongoing
development, the revised results are **development-set results**, not a pristine held-out
test or an unbiased claim of field accuracy. Adjacent-pair point tests do not validate
every nonadjacent bridge introduced by view selection.

| Fruit | Sequences | Maps, including partial | Predictions / labels | RMS px | Median px | Paper Table 4 RMS px |
|---|---:|---:|---:|---:|---:|---:|
| Mandarins | 15 | 15 | 119/132 | 4.734 | 1.910 | 6.5 |
| Oranges | 10 | 9 | 175/179 | 3.316 | 2.006 | 2.53 |
| Tomatoes | 11 | 10 | 164/186 | 6.687 | 3.002 | 5.2 |

The paper's values provide context, not a matched-subset comparison: it describes
roughly 200 labels per category, while the public files contain the counts above.
The revised method predicts **367/497 labels within 5 px (73.84%)** and leaves 39
unpredicted. Maximum returned error is 35.930 px. Numerical coverage eligibility is
not proof that a map is geometrically accurate or that its grade is correct.

## Comparison with the research and retained changes

The [2021 method](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) estimates shape and
motion; the [2022 method](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/) constructs
surface maps. The available author repositories provide data and an annotation viewer;
the reconstruction algorithm itself was not found in those repositories. This project
is an independent implementation, not a copy of unpublished author software.

| Component | Finding and retained implementation |
|---|---|
| Spheroid reference frame | The short symmetry axis is not always the roller axis. Map axes, radii and area weights now remain consistent. |
| Silhouette pose | A custom exact rigid-pose gate rejected 27/36 reference sequences. The retained method follows the paper's silhouette trend. |
| Matching objective | The paper uses unnormalized MAD. The original normalized objective was different. MAD now drives search; normalized residuals gate matches. |
| Matching robustness | Bidirectional MAD is a separately evaluated engineering extension. It reduces large errors, with availability reported alongside error. |
| View spacing | Fruit can slip. Constant pair rotations are not required. Later texture matches which pass the residual gate may bypass unusable views; disconnected segments are not joined. These are algorithmic checks, not ground-truth verification. |
| Rotation versus coverage | Endpoint pre/post-roll observes additional surface. The gate uses actual observed longitude, while physical rotation remains a separate measurement. |
| Defect model | The user's checkpoint runs on each retained map-contributing crop. Deferred inference avoids processing discarded views, but occurs before the final coverage check, so partial maps can also contain predicted defects. |
| Grading | Area thresholds 10% and 20% are local engineering settings. The 2022 paper's learned map classifier is a different grading method. Its classification accuracy cannot be claimed for this pipeline. |

Current coverage gates are at least 350° observed map longitude and 65% observed
area. Latitude is restricted to ±60°; the polar caps remain unobserved. Grade 1 is
below 10% defect on observed area; Grade 2 is 10–20% inclusive; Grade 3 exceeds 20%.
These numerical settings are not a validated commercial grading specification.

## Exact-video findings and remaining discrepancy

The original clip has 515 distinct frames at 29.746 fps; global duplicate-frame
filtering does not explain its failures. In the 32-track integration test, 20 partial
maps and 12 failures were saved. Detection and segmentation calls completed, but
reconstruction did not establish sufficient reliable coverage for a grade.
Some crops visibly rotate while the motion matcher underestimates their motion.
Reflections, silhouette/pose noise and local matching ambiguity are plausible causes;
their individual causal contributions have not been experimentally isolated.

The complete original video was submitted through the actual application API. It recorded 402 fruit records. Statuses: `{'mapping_failed': 120, 'insufficient_longitude_coverage': 274, 'graded': 8}`. Grades: `{'ungraded': 394, 'Class 1': 8}`. Saved application job: `f2276fe89ce24fe1a155c228a00e3f17`. These are algorithm outputs, not manually validated classifications.

The dashboard's 711 Review entries in the original screenshot are historical
records from three saved runs. A new analysis adds a new report; it does not alter
those old records. The history previously stopped at 60 records BEFORE applying
class filters, which could hide later graded fruit. History now exposes all saved
records to filtering while keeping verbose motion diagnostics in the download.

The paper uses diffuse illumination to avoid highlights. This video has visible glare.
The setup also contains occluded, truncated, briefly observed and nonrotating fruit.
Those conditions must be separated from algorithm failures. A controlled next test
should use one identifiable fruit, a fixed overhead camera, diffuse lighting and a
manually verified complete turn. Mark 10–20 corresponding points across its rotation,
and record repeated features at loop closure. Only then can motion accuracy and
defect de-duplication on this camera be established. A separate labelled defect/grade
test is needed to measure the user's neural model and final grading accuracy.

Optical-flow matching, smooth pose selection, frame thinning and small-motion
accumulation were tried as isolated experiments. They did not provide convincing
improvement; the accumulation trial showed apparent feature duplication despite
greater numerical coverage. These trials are preserved but excluded from the retained
production algorithm. A complete-looking map was not accepted as proof of correctness.

## Evidence provenance and reproducibility

Retained algorithm SHA-256: `74af29eb38afd8f2eeadc8857e310d5e018288845c4a24d1205f188e991f373c`.
Detector SHA-256: `06f2675d12ec200b4a0419b1bd505c4aa113674c69ab6894684867bd194048b1`.
Segmenter SHA-256: `2869048b1bba2ca0e5cfb0416bf9977f79f851dd8907ffa8b07b54e8c6d049c0`.
Exact video SHA-256: `dc25964bf6052972cad761b0246f79906e768c6737bf4228ba44711d7272429c`.

Pinned author repositories:

- [Rotation data](https://github.com/alalbiol/3d-rotation-estimation-fruits/tree/f20d6757052388c4f86048a0d5f7ad015c29bb08), commit `f20d6757052388c4f86048a0d5f7ad015c29bb08`.
- [Surface map data](https://github.com/csdemeras/FSMap/tree/4e148a1b436374948a9102ad39cdc4d5b3e36eb3), commit `4e148a1b436374948a9102ad39cdc4d5b3e36eb3`.

The original files, licenses and per-file SHA-256 / Git blob checksums are retained
under `data/` and `source_manifest.json`. Every experimental run has its own settings,
source snapshot and results. Historical results have not been overwritten.
See `DEVELOPMENT_LOG.md` for the sequence of successful and unsuccessful experiments.

Run from the project root in PowerShell, using a NEW label each time:

```powershell
./backend/venv/Scripts/python.exe -B -m unittest discover -s backend -p 'test_*.py'
./backend/venv/Scripts/python.exe -B backend/benchmark_authors.py run --label NEW_AUTHOR_RUN --groups mandarins oranges tomatoes --direction -1 --bidirectional --select-views --minimum-rotation 0 --minimum-longitude 350
./backend/venv/Scripts/python.exe -B backend/validate_synthetic_mapping.py --label NEW_SYNTHETIC_RUN
./backend/venv/Scripts/python.exe -B backend/validate_pipeline_video.py 'C:/Users/USER/Pictures/Camera Roll/WIN_20260818_13_29_43_Pro.mp4' --label NEW_VIDEO_RUN --track-limit 32 --bidirectional
./backend/venv/Scripts/python.exe -B backend/validate_api_video.py 'C:/Users/USER/Pictures/Camera Roll/WIN_20260818_13_29_43_Pro.mp4' --label NEW_FULL_API_RUN
./backend/venv/Scripts/python.exe -B backend/validate_software_checks.py --label NEW_SOFTWARE_CHECKS
```

To replay an archived experimental implementation, `benchmark_authors.py` and
`replay_pipeline_crops.py` accept `--algorithm-snapshot PATH`. Source hashes and
settings must match the intended experiment; do not substitute a later implementation
while citing an earlier result. The dashboard totals aggregate historical saved runs;
old Review records are not retroactively reclassified by editing code.

## Figure captions

### Figure 1. Reference dataset: before and after

All 36 public sequences and all 497 labelled correspondences are included. Revised maps include partial maps: 17 meet the current coverage gates, 17 lack circumference coverage, 0 lack area coverage, and 2 fail. Author data have no defect-class truth; no fruit grades are validated here.

![Reference dataset: before and after](01_before_after.png)

### Figure 2. Accuracy and availability must be reported together

Each curve counts all 497 labels in its denominator, including rejected predictions. The revised method returns 458 predictions: RMS 5.103 px, median 2.264 px, maximum 35.930 px. It predicts 367/497 labels within 5 px. These are development-set results; labels were not used to fit rotations, but the dataset was inspected during development.

![Accuracy and availability must be reported together](02_error_distribution.png)

### Figure 3. Author-labelled feature projections: representative and worst cases

Yellow: annotated source feature. Green: author target label. Red: predicted target. The first three rows are selected by proximity to each category median error; the last is the largest returned error, so successes are not shown alone. Original image coordinates and author labels are retained in the JSON results.

![Author-labelled feature projections: representative and worst cases](03_labelled_correspondences.png)

### Figure 4. Isolating the map-coordinate defect

Geometry and rotations are supplied analytically in this control. Repairing the map reference axis and its associated radii fixes the equatorial-rolling failure. This tests downstream mapping independently of texture estimation, tracking and neural models.

![Isolating the map-coordinate defect](04_map_geometry_control.png)

### Figure 5. Known defect areas and grade arithmetic

A rendered sphere with exact geometry, exact rotations and true longitude-wedge masks is used. Repeated observations of one defect are fused into one map. The predeclared tolerance is one percentage point; all three cases pass. These are synthetic mapping controls, not measurements of the defect model’s accuracy.

![Known defect areas and grade arithmetic](05_known_defect_areas.png)

### Figure 6. Physical rotation differs from observed map coverage

The 2022 paper includes approximately 45° of pre-roll and post-roll. In an ideal control, 270° of physical motion therefore supports 360° of longitude. White denotes observed pixels. The 250° and 100° controls remain ungraded. Production requires 350° observed longitude and 65% area; unseen polar caps are not claimed as observed.

![Physical rotation differs from observed map coverage](06_motion_vs_coverage.png)

### Figure 7. Supplementary visual comparison with an author map

The source is a published montage, split into 14 crops without resizing the source pixels. The author map and the independent output use different longitude extents and are displayed at different scales. This is a qualitative comparison, not pixel-level equivalence, SSIM validation, or reproduction of the paper’s classifier.

![Supplementary visual comparison with an author map](07_author_map_comparison.png)

### Figure 8. The exact user video: saved intermediate stages

Track 5 is selected as a diagnostic example, not as a representative accuracy sample. The actual D-FINE models ran on CUDA. This run’s deterministic first 32 usable IDs produced 20 partial maps, 12 failures and zero grades. Track 5: 157.6° measured motion, 251.9° observed longitude. Red overlays are model predictions, not ground truth.

![The exact user video: saved intermediate stages](08_actual_model_pipeline.png)

### Figure 9. Producing a complete-looking image is not sufficient validation

An experimental accumulation of small rotations increased the numerical coverage, but visual inspection showed an apparent repeated landmark in the reconstructed map. This experiment was not enabled in production. Its source snapshot and failed validation evidence remain available. Visual inspection is qualitative and does not replace labelled 3D ground truth.

![Producing a complete-looking image is not sufficient validation](09_rejected_trial.png)

### Figure 10. Complete original video: every reported outcome

All 515 frames were submitted through the running application API, using the actual detector, tracker and segmenter. The run returned 402 tracked records; these are not manually verified unique fruit counts. 8 received algorithm-assigned grades. The other outcomes are retained. Grade availability is not classification accuracy.

![Complete original video: every reported outcome](10_full_video_outcomes.png)

### Figure 11. Track 125: first graded ID in the full run

Selected by smallest graded track ID, not by visual quality. 66 captured views, 33 used; 381.0 degrees measured motion, 360.0 degrees observed longitude, 85.49% observed area, 3.62% predicted defect on observed area: Class 1. This demonstrates complete pipeline execution; the motion, masks and grade have not been independently labelled as correct.

![Track 125: first graded ID in the full run](11_full_video_graded_example.png)

### Figure 12. Where full-video maps stop before grading

Every one of the 282 returned maps is plotted, including partial maps. Dashed lines are the 350-degree longitude and 65% area gates. Tracks for which mapping failed have no coverage coordinates and are counted separately in Figure 10. Numerical coverage alone does not establish correct reconstruction.

![Where full-video maps stop before grading](12_full_video_coverage.png)

