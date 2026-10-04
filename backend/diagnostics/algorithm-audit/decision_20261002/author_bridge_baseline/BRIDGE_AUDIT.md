# Author bridge audit — 2 October 2026

The spheroid formulas remain consistent with the saved research methods. The
additional step that skips views and reconnects later texture matches needs
stronger validation: it accepted all four nonadjacent transitions for which exact
chains of author annotations supply endpoint truth, with errors of 16.41–41.38 px.
This finding supports a change to transition acceptance. It does not isolate all
geometry, texture or camera errors and does not establish field accuracy.

## What was tested

All 578 original images in 36 public author sequences were used with the frozen
operational settings: automatic sphere/oblate selection, x axis, negative author
rotation direction, bidirectional MAD, and rotating-view selection. No detector,
tracker, defect model or user's video was run in this audit. Masks were derived
from the authors' black backgrounds and are not silhouette ground truth.

All 497 published point labels span adjacent views. The existing benchmark scores
these adjacent estimates independently, so its 458/497 predictions and 5.103 px RMS
do not validate a later accepted nonadjacent bridge. This audit joins annotations
only when their `(view, x, y)` endpoints are **exactly equal**; it adds no interpolated
labels. Annotation line numbers are retained. Multiple possible feature positions
at either endpoint would be excluded as ambiguous.

Twenty nonadjacent bridges were selected; only four have exact chained feature
endpoints. The other sixteen are unverified. Four predictions returned, all missed
by more than the existing 5 px reporting indicator: RMS 29.291 px, median 25.549 px.
These four endpoint pairs are correlated with existing labels and are not a new
independent or held-out test set.

| Author sequence | Bridge | Annotation lines | Error px | Approx. lifted separation ° |
| --- | --- | --- | ---: | ---: |
| mandarins/obj0000 | 4 → 6 | 9, 8 | 34.06 | 59.69 |
| tomatoes/obj0004 | 6 → 8 | 93, 92 | 41.38 | 66.89 |
| tomatoes/obj0009 | 7 → 10 | 151, 150, 147 | 17.04 | 40.88 |
| tomatoes/obj0009 | 13 → 17 | 161, 160, 158, 159 | 16.41 | 0.24 |

![Four accepted bridges with available author endpoint labels](author_bridge_failures.png)

Figure 1. Original author pixels with source, target and predicted feature
positions. All four available labelled bridge cases are shown. Yellow is the
author source, green the author target, and red the algorithm prediction. Counts
and error are based on the unresized source coordinates.

Both endpoints of every case lie on a finite front-facing estimated surface.
The first two lifted angular separations exceed the search domain's maximum total
rotation magnitude `sqrt(55²+10²) = 55.90°`. This suggests that skipping views can
pass beyond the feasible rotation range and find a smaller apparent match. The
lifting depends on an approximate spheroid, so these are not measured 3D rotations.

Direct bridge rotation differs from independently estimated adjacent composition
by 34.29°, 26.57°, 4.73° and 6.53°. The first three compositions include at least
one residual-rejected pair and are diagnostic only. In the last case all four
adjacent residuals pass: composing them yields 8.55 px reprojection error, compared
with 16.41 px for the selected direct bridge. A cycle check could expose some
disagreement but would not certify every case. Relaxing failed pair gates is not
validated by this experiment.

## Isolated candidate and outcome

The isolated snapshot adds a maximum normalized residual of **0.5 only for a
nonadjacent transition**. Production code was unchanged during these runs. The
threshold was chosen after inspecting this development evidence; no held-out
accuracy improvement is claimed.

| Indicator | Previous selector | Candidate bridge residual ≤ 0.5 |
| --- | ---: | ---: |
| Original images / sequences | 578 / 36 | 578 / 36 |
| Geometry fits / maps, including partial | 36 / 34 | 36 / 34 |
| Ordinary independent adjacent predictions / labels | 458 / 497 | 458 / 497 |
| Ordinary independent adjacent RMS px | 5.103 | 5.103 |
| Original labels measurable on retained selected poses | 305 / 497 | 285 / 497 |
| Selected-pose RMS px, different returned subsets | 4.806 | 4.924 |
| Nonadjacent selected bridges | 20 | 4 |
| Accepted known bad labelled bridges | 4 | 0 |
| Remaining bridges with endpoint truth | 4 | 0 |
| Author maps meeting current coverage gates | 17 | 13 |
| Partial maps / mapping failures | 17 / 2 | 21 / 2 |

![Candidate selection and availability](bridge_guard_comparison.png)

Figure 2. The candidate is an exclusion safeguard. Recomputed selection can
create different bridges; the four remaining bridges have no exact chained
endpoint labels. Removing the four observed failures does not establish zero
remaining error. Adjacent RMS remains unchanged because its estimator was not
changed. Lower selected-pose availability and coverage eligibility are reported
instead of being hidden. No author grade accuracy is measured.

## Recommended next test

Do not rewrite the spheroid equations based on these results. Improve acceptance
of skipped transitions and test direct versus composed rotations, search-domain
limits, and repeated-feature ambiguity on analytic sequences with known variable
motion. Distinguish valid low-motion views from failed or unmeasured views before
joining a gap. On the user's camera, manually label feature correspondences and
loop closure on one fully rotating tracked naartjie; tracking alone supplies no
surface-motion truth. Different GrabCut masks and shape choices should be compared
on the **same frozen crops**, rather than interpreting a changed map as improved
accuracy without labels.

The 0.5 candidate can exclude observed bad bridges, but is a conservative
development safeguard rather than a demonstrated complete solution. The
unlabelled long gaps and inaccurate adjacent cases remain material limitations.

## Evidence and reproduce

- Full baseline audit: `report.json`, algorithm and validator snapshots here.
- Candidate bridge audit: `../candidate_bridge_guard_050_20261002/report.json`.
- Full candidate 36-object benchmark: `../../runs/candidate_bridge_guard_050_20261002/report.json`.
- Candidate snapshot: `../residual_guard_candidate_source/algorithm_snapshot.py`.
- Primary methods: [2021 spheroid and rotation paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/),
  [2022 surface map paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
  Local saved copies are `../../papers/PMC8004661.txt` and `../../papers/PMC9323781.txt`.

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_author_bridges.py --label NEW_BASELINE
./backend/venv/Scripts/python.exe -B backend/validate_author_bridges.py --label NEW_CANDIDATE --algorithm-snapshot backend/diagnostics/authors-benchmark/bridge_runs/residual_guard_candidate_source/algorithm_snapshot.py
./backend/venv/Scripts/python.exe -B backend/benchmark_authors.py run --label NEW_FULL_CANDIDATE --groups mandarins oranges tomatoes --direction -1 --bidirectional --select-views --minimum-rotation 0 --minimum-longitude 350 --algorithm-snapshot backend/diagnostics/authors-benchmark/bridge_runs/residual_guard_candidate_source/algorithm_snapshot.py
```

The report snapshots and hashes identify the exact code and settings used. Later
source edits must not be cited as though these frozen runs tested them.
