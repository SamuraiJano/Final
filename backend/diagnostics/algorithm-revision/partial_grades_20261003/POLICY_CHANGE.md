# Partial-map grades requested by the user — 3 October 2026

The grading policy assigns a grade even when a map is partial. The app now assigns a
provisional class from the surface actually observed. The latest saved-map
update contains **293 Class 1, 1 Class 2 and 180 Review**. **292 of its 294
assigned classes are provisional**; the two maps meeting the original coverage
requirements retain their regular Class 1 grades.

This is a change to the grading decision. Reconstruction, learned predictions
and observed coverage did not improve as a result of this update.

## Exact calculation and display

The percentage used for grading is:

`100 × fused predicted defect area on observed surface / observed surface area`

Area retains the spheroid surface Jacobian weighting and the union of predicted
defect classes. Unseen map pixels are excluded from the denominator; they are
unassessed. Overlapping defect classes do not become duplicate defect area.

| Predicted defect percentage of observed surface | Assigned class |
| --- | --- |
| Less than 10% | Class 1 |
| 10% through 20%, including both endpoints | Class 2 |
| More than 20% | Class 3 |

The original targets of 65% observed surface and 350 degrees observed map
longitude still identify coverage-complete maps. A valid map below a target
receives status `graded_partial`, `grade_provisional: true`, and
`grade_scope: observed_surface`. The dashboard displays **Class N (partial)**
and the note: “Provisional grade based on the observed surface; unseen areas
were not assessed.” Complete maps retain status `graded`.

No usable map, no observed surface, missing/nonfinite/invalid defect observations,
invalid motion or an excessive pair gap still prevents a grade. An actual
completed segmentation pass with zero predicted defects is distinguished from
segmentation that was not performed. No assumed clean surface is inserted.
The observed-area policy is enabled in the app; the standalone `Settings()`
default remains strict so existing benchmarks keep their recorded criteria.
These thresholds are engineering settings, not validated commercial grade rules.

## Saved results and provenance

Original full-video mapping job: `ea6e595b8f3f45f2b5edfda8dafff3f2`.
It completed all 515 distinct frames using both real models on 3 October,
12:32:32–13:09:55 SAST, in 37.4 minutes. Under its strict coverage policy it
returned 474 records: 2 Class 1 and 472 Review. Of those Review records, 292
contain partial maps and 180 contain no usable reconstructed map.

Derived saved-map regrading job: `ed3aa02cca364812a145610aad627a83`,
published at 13:50:08 SAST. It reuses the original saved defect percentages,
maps and observations, with **zero new detector, segmenter or motion calls**.
Its 292 partial maps now receive 291 provisional Class 1 grades and one
provisional Class 2. The two original regular Class 1 grades are unchanged.
The remaining 180 records remain Review.

All **5,691 copied PNG files were verified byte-identical** by the regrading
script. The original report is preserved with SHA256:

`c4338b584bfe23f0a626340e0368ebbc6eb9baa1c21a785780b44e362701fda2`

The supplement's [474-row ledger](all_474_grades.csv) records before/after
grades, statuses and observed coverage. The builder separately checks unchanged
coverage, defect percentages, rotations, errors, view frames and tracking entry/
exit for every record. Selected original/updated result JSON and map image hashes
are retained. The full original report and all images remain in their job folder
and the earlier sealed evidence pack; this supplement duplicates only three
actual examples.

| Stage | Exact source SHA256 |
| --- | --- |
| Mapping/rotation which created the reused images | `50bdd78eafcc5581d0368353c9996c2f95823c69f734dac6f778dc82f22c815d` |
| Runtime API which completed the original video | `4c0b69d815164c9e4745af72a69880a417ee6b940cc1792027be4b31e775cfdb` |
| Updated grading decision | `f10e8393f1af64f67023f9519fcbf1b117d91418c1955ec44c2bd329fa22e657` |
| Updated app API enabling the policy | `76a66ac90ad2549775bce28f0ecb66b4348a4a0829219c770eb08349230d5f89` |

Original `algorithm.py.snapshot`, `main.py.snapshot` and model metrics retain
their original mapping provenance. Separate `grading_*` snapshots and
`grading_policy` metadata identify the newer decision source. Inherited model
timings/counts describe the original execution; they do not imply models ran
again. The script [regrade_saved_maps.py](regrade_saved_maps.py) is preserved as
an exact snapshot; its runnable workspace location is `backend/regrade_saved_maps.py`.

## Actual examples for the report

| Fruit | Before | Updated grade | Observed surface | Observed longitude | Predicted defects / observed surface |
| --- | --- | --- | --- | --- | --- |
| 32 | Review | Class 1 (partial) | 22.430% | 93.455° | 1.242% |
| 340 | Review | Class 2 (partial) | 26.516% | 157.232° | 17.842% |
| 98 | Class 1 | Class 1, coverage complete | 85.150% | 360.000° | 4.512% |

The [example gallery](index.html), [300-dpi PNG](figures/actual_partial_grade_examples_300dpi.png)
and [PDF](figures/actual_partial_grade_examples.pdf) use actual saved crops,
model overlays, surface maps and observed-area masks. They contain no generated
fruit imagery. Black unobserved map areas are unassessed. Red crop overlays are
model predictions, not human-verified defects. “Coverage complete” means meeting
the configured thresholds, not observing every square millimetre of the fruit.

## Separate dashboard-delivery fix

The first actual browser attempt failed while receiving the saved report through
the frontend proxy. The API already held the correct derived classes. A controlled
transfer reproduced an incomplete body with `Connection: close`, then verified
complete delivery of the same 3,774,048-byte response using a native HTTP agent
with keep-alive and an explicit keep-alive connection header. The final
`vite.config.js` SHA256 is:

`1b6582dca898de357a7b048a30489197d860509aa01c3c1803a03590079dec4e`

Algorithm f10, main76, App949, the models and saved map/grade data are unchanged.
The original 64-test record retains its earlier Vite hash. A separate transport
record captures the final configuration, raw response hashes, controlled failure
and fresh frontend build/lint. The earlier failed browser attempt remains distinct
from successful actual running-app screenshots. This fix delivers existing saved
results; it does not rerun detection, segmentation, rotation estimation or grading.

## Tests and evidence limits

The [software record](checks/summary.json) passes all **64 Python tests**,
frontend build and lint. Thirteen added tests in
[test_partial_grades.py](source/test_partial_grades.py) verify the requested
decision independently of learned inference:

1. The default standalone policy remains strict.
2. Partial-map grades use the exact 10%/20% boundary rules.
3. A coverage-complete map retains its regular grade.
4. Each configured coverage requirement can mark a grade partial.
5. Missing segmentation does not become a clean grade.
6. Invalid/nonfinite/out-of-range defect percentages remain ungraded.
7. Empty/nonfinite/out-of-range observed area remains ungraded.
8. Excessive pair gaps are not bypassed by allowing partial maps.
9. Unknown/nonfinite motion or longitude remains ungraded.
10. Changing the policy leaves reconstructed map/observed/defect arrays,
    measured coverage, rotations and errors unchanged.
11. A fully defective narrow observed latitude band remains 100% defective
    and Class 3, even when less than 10% of the full surface was observed.
12. Completed inference with zero predictions can assign a partial Class 1.
13. A map without completed defect observations remains ungraded.

The controlled map tests supply perfect silhouettes and known motion so that
they isolate grading arithmetic. They do not test detector or segmentation
accuracy. Their exact deterministic raw arrays are saved in
[policy_test_inputs.npz](controls/policy_test_inputs.npz) and described by
[control parameters](controls/method.json): two 100×100 views, radius 35 pixels,
centre (49.5, 49.5), constant BGR (35, 140, 235), and supplied 25-degree y rotation.
The clean and fully defective masks retain both denominator scenarios; motion
is supplied rather than estimated in these tests.

The [actual running-app report](actual_ui/report.json) passes at 18:02 SAST:
the latest job has exactly 474 records with 293/1/180 class counts and 292
provisional grades. Actual fruit 32 and 340 show partial class labels, their
coverage, the provisional note and loaded maps; fruit 98 retains its regular
grade, and no-map fruit 47 remains Review. All-saved history counts 2,535 records
across seven saved runs; it includes older development and derived regrading
records rather than unique physical fruit. The check uses only GET requests,
leaves analysis idle, has zero JavaScript errors and no horizontal overflow at
390 pixels. Its screenshots contain saved real predictions and no mocked API
responses. The failed preceding attempt is retained under `failed_ui_attempt/`.
The [artificial UI controls](artificial_ui_controls/report.json) separately
verify all three partial class labels/filters, complete-grade display, Review
and 390-pixel mobile layout using mocked inputs; those screenshots are not actual
fruit predictions. The supplement
manifest verifies retained file hashes, and its ZIP is checked for CRC errors.

No human-labelled conveyor defect/grade truth is available. A partial grade
reports the observed area and cannot establish the condition of unseen skin.
The increased class count follows the requested policy; it is not an accuracy
result. The earlier 309,119,746-byte `evi_runtime_20261003.zip` and its folder
remain unchanged with their historical strict-coverage counts and tests.
The supplement records that archive's hash independently in [provenance.json](provenance.json).
