# Author-data reconstruction benchmark — 1 October 2026

**Result: the current implementation does not pass the end-to-end reference-data test.**
With the dataset's rotation direction, it produces **0 maps from 36 fruit sequences**.
This failure is reproducible without the user's detector, tracker, defect model,
GrabCut, video decoding, GPU inference, API, or dashboard.

Production `algorithm.py` was not edited. Its SHA-256 is `f971919a2989be845fbd79800890cc0fc8cfafb88c3650307f9f0d6e6a25ce59`.
The new scripts and evidence live separately under `backend/diagnostics/authors-benchmark`.

## What was tested

- All 578 individual images in the pinned 2021 authors' repository: 15 mandarin,
  10 orange, and 11 tomato sequences. Five mandarin sequences have no point annotations;
  they still count in geometry/map completion.
- All 497 published point correspondences: 132 mandarin, 179 orange, 186 tomato.
  Both forward and backward annotations are respected; points are never used to fit rotations.
- Each accepted rotation lifts an annotated source pixel into 3D, rotates it and
  projects it into the target view. Error is Euclidean pixel distance; RMS is
  `sqrt(mean(error_px**2))`. Rejected predictions are counted separately, never assigned zero error.
- The per-fruit centre-translation baseline uses exactly the same predicted subset.
- Author images already have black backgrounds. Masks are derived from nonblack pixels,
  retaining the largest component and filling enclosed holes. These are derived masks,
  not independently supplied ground-truth silhouettes. Original pixels are not resized before fitting.
- The source images show downward feature motion. With this code's positive visible
  z coordinate and image y increasing downward, this needs x-axis direction -1.
  Direction +1 is a separate control, not the correctness score.
- First object of each category is marked calibration (49 labels); remaining 33
  sequences / 448 labels are marked evaluation. No learned parameter fitting was done.
  All 81 accepted predictions in the primary run belong to the evaluation split.
- Source download checksums and all 994 annotation endpoint bounds were verified.

## Measurements

| Fruit | Sequences | Shape fits | Maps | Available predictions / labels | Our RMS on available predictions (px) | Paper Table 4 RMS (px) |
|---|---:|---:|---:|---:|---:|---:|
| Mandarins | 15 | 3/15 | 0/15 | 34/132 | 3.46 | 6.5 |
| Oranges | 10 | 6/10 | 0/10 | 47/179 | 3.61 | 2.53 |
| Tomatoes | 11 | 0/11 | 0/11 | 0/186 | Not measurable | 5.2 |

**Do not interpret the low mandarin RMS as outperforming the paper.** Our code only
returns 34 of its 132 mandarin correspondences. The paper's numbers are a reference
scale, not a matched-subset comparison: it describes about 200 labels per category,
whereas the public files contain the counts above. Overall prediction availability
is 81/497 (16.3%); held-out availability is 81/448 (18.1%). Full-map success is zero.

First failing stage per sequence: {'Shape / pose fit': 27, 'Texture gate': 6, 'Rotation pair gate': 2, 'Sequence uniformity gate': 1}.

![Benchmark summary](benchmark_summary.png)

## Controlled checks

| Check | Result | Meaning |
|---|---|---|
| Current auto shape, direction +1 | 9/36 shape fits; 0/36 maps; 3/497 predictions | Wrong direction for these 2021 images is harmful. |
| Auto shape, direction -1 | 9/36 shape fits; 0/36 maps; 81/497 predictions | Correcting direction does not repair reconstruction. |
| Force sphere, direction -1 (diagnostic only) | 36/36 shape fits; 0/36 maps; 294/497 predictions | Bypassing the oblate solver exposes further texture/sequence failures. |
| Black threshold 8 versus 0, direction +1 | Same fit/map/prediction counts | This small threshold change does not explain the baseline failure. |
| Exact geometry and exact 25-degree steps, symmetry-axis rotation | Map produced; 375 degrees recovered | Map stage can work in a favourable configuration. |
| Same exact inputs, equatorial-axis rotation | `No consistent angular progress` | A downstream coordinate-system defect remains even with perfect inputs. |

Forcing a sphere is not a proposed fix: its accepted mandarin predictions have RMS
10.19 px and errors up to 42.21 px. The sphere diagnostic changes the shape assumption,
not the production code or accuracy thresholds. Its accepted-subset overall RMS is
8.05 px; 203/497 correspondences still have no prediction.

An accurately aligned example from the primary run (mandarin obj0007, annotation 108,
0.19 px error; selected to illustrate a success, not represent all results):

![Accepted feature alignment](accepted_example.png)

A failure of the sphere approximation (mandarin obj0006, annotation 80, 42.21 px error;
selected to illustrate why bypassing the shape solver is insufficient):

![Sphere diagnostic error](sphere_error_example.png)

## Comparison with the papers

The [2021 paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) supplies the shape and
rotation method. The [2022 paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/) supplies
map construction. The following is a source/code review, not a claim to possess the authors' software.

| Component | Code comparison | Consequence |
|---|---|---|
| Silhouette covariance, sphere radius, oblate radii | The basic equations match (2021 Eqs. 1, 4, 5). | These formulas are not by themselves evidence that the whole pipeline is correct. |
| Green channel, 4x reduction, Gaussian high-pass, strong point selection | Broadly follows 2021 section 3.3. | Local minimum texture, minimum point and maximum point gates are extra settings. |
| Oblate pose ambiguity | Code replaces the paper's minor-axis trend/smoothing procedure with a constrained sign-sequence solver. | This custom stage rejects 27/36 primary sequences. It needs direct investigation. |
| Matching cost | Code divides absolute difference by a candidate-dependent texture scale; Eq. 17 uses mean absolute difference. | This can change the best rotation, not merely rescale a rejection threshold. |
| Pair and sequence acceptance | Code adds 1-degree minimum motion, error/texture limits, and a median-step uniformity gate. | A single rejected pair aborts the map. These choices are not validated by the dataset. |
| Map coordinate axes | 2022 section 2.1 places fruit y near the rotation axis. Code always makes oblate fruit y the short symmetry axis. | These differ for equatorial rolling. Exact-geometry diagnostic reproduces the failure. |
| Map sampling and blending | General parametrization and adjacent-view linear blending follow 2022 Eqs. 3 and 6. | Correct formulas do not rescue inconsistent axes or rejected rotations. |
| Grading | Local 350-degree, 65-percent and 10/20-percent settings are application choices. | No defect/grade ground truth was supplied in this benchmark; no grade accuracy is claimed. |

The exact-geometry diagnostic injects a known spheroid and analytical rotations into
map construction using scoped mocks, solely in the standalone benchmark process.
It does not measure detector accuracy or full reconstruction accuracy. At the
reference pose the short fruit axis is vertical. Rotation about that axis succeeds;
rotation about horizontal x fails. This isolates the map's coordinate assumption
from tracking, silhouette noise, motion estimation and the user's camera.

## Comparison with published maps

Two published FSMap mandarin examples were also checked. Their two-row montages were
split into 14 and 13 views at original pixel scale. View bounds are saved in
`map_reference/report.json`. These composite views have already been processed by
the authors; objM0005 contains visible background artifacts. They are supplementary
checks, not pristine raw-input benchmarks. Both abort at pose fitting. No output map
exists to score for pixel similarity, seam quality or defect-area agreement.

![Author map versus failed reconstruction](map_comparison.png)

The upper image is the authors' map from
[FSMap](https://github.com/csdemeras/FSMap), retained with its repository license and
source hash. The lower panel describes our actual failure; it is not a reconstructed map.

## Recommended next work

1. Keep this frozen baseline. Reproduce the exact-geometry equatorial case before changing any code.
2. Correct the map coordinate axes and associated spheroid radii together; a label swap alone is insufficient.
3. Compare a paper-faithful pose implementation against the current constrained solver on the calibration sequences.
4. Audit texture rejection and normalized matching cost; evaluate every change against held-out labels and completion rates.
5. Only after reference-data results are adequate, repeat with manually verified silhouettes from the user's conveyor.

Lowering grade thresholds cannot repair these earlier failures. Neither does an
attractive-looking map establish correct feature alignment or surface-area measurement.
This benchmark does not establish the user's tracker, silhouettes or defect model are accurate;
it establishes they are not necessary to reproduce the current reconstruction failures.

## Reproduce from the workspace root

```powershell
.\backend\venv\Scripts\python.exe -B backend/benchmark_authors.py download
.\backend\venv\Scripts\python.exe -B backend/benchmark_authors.py run --label current_settings --groups mandarins oranges tomatoes --direction 1 --mask-threshold 8
.\backend\venv\Scripts\python.exe -B backend/benchmark_authors.py run --label direction_plus_exact_black --groups mandarins oranges tomatoes --direction 1
.\backend\venv\Scripts\python.exe -B backend/benchmark_authors.py run --label dataset_orientation --groups mandarins oranges tomatoes --direction -1
.\backend\venv\Scripts\python.exe -B backend/benchmark_authors.py run --label sphere_diagnostic --groups mandarins oranges tomatoes --direction -1 --shape sphere
.\backend\venv\Scripts\python.exe -B backend/benchmark_mapping_reference.py
.\backend\venv\Scripts\python.exe -B backend/summarize_authors_benchmark.py
.\backend\venv\Scripts\python.exe -B -m unittest discover -s backend -p 'test_*.py'
```

Each run records settings, code snapshot/hash, every fruit failure, accepted rotations,
and every labelled correspondence. No detector weights are loaded. The four rotation
runs are CPU diagnostics; they never write to `backend/results` or affect the dashboard.

## Sources and integrity

- [2021 images and annotations](https://github.com/alalbiol/3d-rotation-estimation-fruits), commit
  `f20d6757052388c4f86048a0d5f7ad015c29bb08`.
- [2022 published maps](https://github.com/csdemeras/FSMap), commit
  `4e148a1b436374948a9102ad39cdc4d5b3e36eb3`.
- `source_manifest.json` records exact URLs, Git object checksums and SHA-256 hashes.
- XML/text copies of the open-access papers were fetched from Europe PMC under `papers/`.
- `summary.json` and each `runs/*/report.json` contain numerical results.

## Per-sequence primary results

| Sequence | Views | Shape | Accepted pairs | First map failure |
|---|---:|---|---:|---|
| mandarins/obj0000 | 12 | failed | 0/11 | No consistent oblate pose sequence through pair 2; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0001 | 13 | failed | 0/12 | Oblate pose mismatch at pair 5: 8.2 deg; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0002 | 15 | failed | 0/14 | Oblate pose mismatch at pair 5: 5.7 deg; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0003 | 15 | ok | 11/14 | Fruit has insufficient measurable surface texture |
| mandarins/obj0004 | 13 | failed | 0/12 | Oblate pose mismatch at pair 3: 6.3 deg; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0005 | 16 | failed | 0/15 | Oblate pose mismatch at pair 2: 6.6 deg; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0006 | 15 | failed | 0/14 | Oblate pose mismatch at pair 10: 8.0 deg; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0007 | 16 | ok | 12/15 | Unreliable pair 3: rotation 55.0 deg, error 0.235 |
| mandarins/obj0008 | 16 | failed | 0/15 | No consistent oblate pose sequence through pair 5; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0009 | 16 | failed | 0/15 | Oblate pose mismatch at pair 1: 5.1 deg; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0010 | 13 | ok | 10/12 | Unreliable pair 4: rotation 55.0 deg, error 0.429 |
| mandarins/obj0011 | 16 | failed | 0/15 | No consistent oblate pose sequence through pair 2; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0012 | 16 | failed | 0/15 | No consistent oblate pose sequence through pair 3; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0013 | 16 | failed | 0/15 | Oblate pose mismatch at pair 0: 6.4 deg; check silhouette quality, view spacing and rotation configuration |
| mandarins/obj0014 | 16 | failed | 0/15 | Oblate pose mismatch at pair 1: 11.1 deg; check silhouette quality, view spacing and rotation configuration |
| oranges/obj0001 | 16 | failed | 0/15 | No consistent oblate pose sequence through pair 3; check silhouette quality, view spacing and rotation configuration |
| oranges/obj0002 | 16 | ok | 10/15 | Fruit has insufficient measurable surface texture |
| oranges/obj0003 | 16 | failed | 0/15 | Oblate pose mismatch at pair 4: 6.8 deg; check silhouette quality, view spacing and rotation configuration |
| oranges/obj0004 | 16 | ok | 1/15 | Fruit has insufficient measurable surface texture |
| oranges/obj0005 | 16 | ok | 0/15 | Fruit has insufficient measurable surface texture |
| oranges/obj0006 | 16 | ok | 1/15 | Fruit has insufficient measurable surface texture |
| oranges/obj0007 | 16 | failed | 0/15 | Oblate pose mismatch at pair 2: 16.5 deg; check silhouette quality, view spacing and rotation configuration |
| oranges/obj0008 | 16 | ok | 15/15 | A pair rotation disagrees sharply with the other views; inspect tracking, pose and texture |
| oranges/obj0009 | 16 | ok | 7/15 | Fruit has insufficient measurable surface texture |
| oranges/obj0010 | 16 | failed | 0/15 | No consistent oblate pose sequence through pair 3; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0000 | 17 | failed | 0/16 | Oblate pose mismatch at pair 1: 7.1 deg; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0001 | 17 | failed | 0/16 | Oblate pose mismatch at pair 2: 5.5 deg; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0002 | 18 | failed | 0/17 | Oblate pose mismatch at pair 2: 10.4 deg; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0003 | 19 | failed | 0/18 | No consistent oblate pose sequence through pair 4; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0004 | 17 | failed | 0/16 | Oblate pose mismatch at pair 6: 5.8 deg; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0005 | 17 | failed | 0/16 | Oblate pose mismatch at pair 1: 6.5 deg; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0006 | 17 | failed | 0/16 | No consistent oblate pose sequence through pair 4; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0007 | 17 | failed | 0/16 | Oblate pose mismatch at pair 5: 10.3 deg; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0008 | 18 | failed | 0/17 | Oblate pose mismatch at pair 0: 5.3 deg; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0009 | 18 | failed | 0/17 | Oblate pose mismatch at pair 0: 10.0 deg; check silhouette quality, view spacing and rotation configuration |
| tomatoes/obj0010 | 19 | failed | 0/18 | Oblate pose mismatch at pair 4: 8.1 deg; check silhouette quality, view spacing and rotation configuration |
