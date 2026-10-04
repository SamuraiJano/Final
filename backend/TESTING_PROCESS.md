# Algorithm testing process and report evidence

This record describes the October 2–3, 2026 development tests and the later
partial-map grading and defect-display updates. The frozen rotation
algorithm has SHA256
`50bdd78eafcc5581d0368353c9996c2f95823c69f734dac6f778dc82f22c815d`.
The October 3 runtime uses `main.py` SHA256
`4c0b69d815164c9e4745af72a69880a417ee6b940cc1792027be4b31e775cfdb`.

## 1. Check what the papers and public repositories provide

We compared our shape fitting, texture-point rotation search and surface fusion
with the [2021 rotation paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 mapping paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
The public repositories provide images and point annotations; we did not find
the reconstruction implementation to reuse. Our code is an independent
implementation with documented adaptations. The supplied detector and defect
segmenter replace the image-processing inputs; their accuracy is a separate
question from whether the surface calculations work.

## 2. Test movement against the authors' labelled image points

We used all 36 sequences: 15 mandarins, 10 oranges and 11 tomatoes, containing
578 images and 497 published point correspondences. A correspondence specifies
where one visible fruit feature appears in two images. We estimate rotation
without those labels, project the source point into the target image, and measure
the Euclidean distance from its published target position, in pixels.
Fruit silhouettes are derived from the images' black backgrounds; they are not
hand-labelled silhouette ground truth.

The current direct-pair test returned 457 predictions out of 497. RMS error on
those predictions was **5.225 pixels**; 372 of all 497 labels were within five
pixels. Forty unavailable predictions remain in the availability denominator.
The retained-map test returned 348 of 497 predictions, with **5.360 pixels** RMS
error on returned predictions and 286 of all 497 labels within five pixels.
It used no nonadjacent bridges.

The data were inspected repeatedly during development. The original report's
calibration/evaluation names do not make these final results held-out accuracy.
The paper's published error table uses a different annotation denominator, so
these numbers do not demonstrate reproduction or improvement of that table.
Author images use a 55-degree rolling search; the recorded conveyor video uses
20 degrees because it supplies every consecutive frame. Both settings are saved.

## 3. Test known motion, lighting and stationary noise

Analytically rendered fruit textures provide exact rotations and projected point
positions. Twelve frozen scenes cover full turns, short noncommuting movements
and stationary noisy fruit under additive or multiplicative camera lighting.
We also retained the original short-motion and vertical full-turn controls,
tested a fresh third texture, and tested sideways motion of plus/minus 13 degrees.
Acceptance limits and the original input arrays were preserved across revisions.

That frozen benchmark source passes these declared development controls. All **714 noisy
stationary pairs** remain unavailable and produce no map. Unavailable motion is
not scored as an accurate zero rotation. Numerical checks separately confirm
that scalar and batched comparisons agree and that the two native matching
branches are selected as documented.

Earlier versions could produce a complete-looking Class 1 map while estimating
the wrong turn. Those failed tests and images remain in the evidence history.
A complete-looking map alone was therefore never our accuracy acceptance test.

## 4. Test defect fusion and class arithmetic with known answers

We supplied true rotations and known defect masks covering 5%, 15% and 30% of a
rendered sphere. The measured areas were 5.144%, 15.179% and 30.093%, respectively,
and produced the intended Classes 1, 2 and 3. Maximum absolute area error was
0.179 percentage points against a one-percentage-point acceptance limit.
Separate tests checked that incomplete coverage stays ungraded.
Those checks used the original strict grading policy; the user later requested
provisional grades for partial maps, as documented below.

These controls bypass motion estimation and neural models. They test projection,
overlap handling, area weights and class logic. They do not validate the 10% and
20% class thresholds against commercial or human conveyor grades.

## 5. Join the mapper to the actual local segmentation model

The October 3 integration test used 215 archived real conveyor crops and fruit
masks across four tracks. It made 42 actual segmentation calls and returned 80
defect instances. The detector was loaded but made zero calls because its crops
were already frozen. Fruit 98 met the coverage rules; three other tracks remained
partial. These records prove this integration executes, without supplying human
motion, defect-mask or grade truth.

## 6. Run the original video through the complete application

The final runtime check submits
`WIN_20260818_13_29_43_Pro.mp4` through `POST /api/analyze-video`, without a track
subset. It uses the actual detector, tracker, fruit-mask extraction, rotation
matcher, defect model, mapping and report writer on all 515 original frames.
The video SHA256 is
`dc25964bf6052972cad761b0246f79906e768c6737bf4228ba44711d7272429c`.
The retry ran October 3 from 12:32:32 to 13:09:55 SAST. It completed all 515
distinct frames with zero duplicates, using the exact frozen algorithm and
runtime snapshots. The request took 2,242.5 seconds (37.4 minutes) for a
17.3-second clip. Its outcome is recorded in
`diagnostics/api-runs/full_pixel_switch_runtime_20261003/summary.json`.

It returned 474 inspection records: **2 Class 1 and 472 Review**. Those records
are not a manually verified count of distinct physical fruit. Review reasons
were 292 insufficient map-longitude coverage, 164 without complete usable
silhouettes, six with fewer than two views, and ten without a reliable rotating
sequence. The grading yield was only 0.42%; successful execution has not solved
grading for this whole conveyor clip. Insufficient estimated map coverage does
not prove insufficient true physical rotation, because shape or matching failures
can also limit the retained sequence.

Fruit 98 was tracked from frame 51 to 138, with 88 observations. Its fresh
full-run map reached 360 degrees of computed longitude and reported 4.512%
predicted defect area, giving Class 1 under the current rules. This actual-run
result is separate from the archived-crop integration result. The full run made
515 detector calls and 3,004 defect-segmentation calls. Model confidence is not
measured accuracy.

The earlier attempt failed with a memory allocation error after its last
published progress of 330/515 frames. Its exact error frame/time was not logged. Model
training was concurrent, but its exact contribution to the failure is unknown.
We added track cleanup on errors and excluded backend data from the frontend
file watcher. The rotation algorithm and class requirements stayed unchanged.
The retry records RAM, GPU usage and frame progress every 25 seconds. All 51
software tests, frontend build and lint passed before this retry. Actual-browser
checks use real API reports and preserve screenshots without mocked responses.

## Evidence to use in the report

The fresh bundle is configured by
`current_profile_evidence_runtime_20261003.json`. It retains source snapshots,
parameters, input hashes, raw reports, successful and failed examples, and
300-dpi PNG/PDF figures. Figure captions distinguish rendered controls from real
fruit images. The bundle is sealed only after the full-video summary exists.

For a simple explanation, read [ALGORITHM_EXPLAINED.md](ALGORITHM_EXPLAINED.md).
The saved [fruit 98 walkthrough](diagnostics/algorithm-revision/debug_fruit_98_pixel_switch_runtime_20261003/index.html)
shows all 65 archived motion decisions, first/last tracking observations, extracted
boundaries and actual model overlays. Its archived-crop replay remains separately
labelled from the fresh full-video result.

Full-video completion proves execution for this clip and recorded resources.
Human-labelled conveyor identities, rotations, defect masks and grades are still
needed to measure field accuracy. Offline completion also does not establish
real-time sorting speed or capacity while model training runs simultaneously.

## Subsequent partial-map grading update

The user explicitly requested grades even when a map is partial. The app now
grades the observed defect percentage using the same 10% and 20% thresholds,
labels incomplete maps as provisional, and retains their surface and longitude
coverage. Missing maps or invalid/missing defect estimates remain ungraded.

New source `f10e8393...` changes grading eligibility; the rotation search and map
rendering are unchanged. Thirteen added tests verify partial grading, class
boundaries, an observed-area denominator, unchanged map pixels/masks/percentages,
missing evidence and invalid-motion refusal. All 64 backend tests, frontend build
and lint passed in `diagnostics/software-checks/partial_grades_20261003/`.

The new saved job is `ed3aa02cca364812a145610aad627a83`. It derives from original
job `ea6e595b8f3f45f2b5edfda8dafff3f2` and returns **293 Class 1, 1 Class 2 and
180 ungraded records**. Of the 294 grades, 292 are provisional partial-map grades;
the two previously complete grades remain unchanged. All 5,691 copied PNGs match
their original hashes, and the original report remains unchanged. This update
made zero model calls. The report records original mapping source `50bdd78e...`
separately from grading-policy source `f10e8393...`.

The original sealed evidence bundle retains the strict-policy results. The
partial-grading supplement is under `diagnostics/algorithm-revision/partial_grades_20261003/`.
The greater number of assigned grades is a policy change, not new evidence of
accuracy. Unseen portions of a fruit are not assessed by its partial grade.

The final running-app check also exposed a dashboard delivery failure: the
default development proxy's forced `Connection: close` truncated the large JSON
response on this setup. A keep-alive HTTP agent and header fixed that transfer.
Direct API and actual Vite responses then contained the same 3,774,048 bytes,
with identical SHA256 and all 2,535 saved records. The latest run displayed the
counts and provisional notes above in the actual browser. This delivery change
only affects `vite.config.js`; the algorithm, API and UI sources tested by the
64-test record are unchanged. Fresh build and lint passed. The separate
[transport record](diagnostics/algorithm-revision/dashboard_transport_20261003/TRANSPORT_FIX.md)
retains the failed controls and final GET-only comparison.

## Defect-category colours and the 80% surface target

The visualization shows the whole observed naartjie texture with defects highlighted,
rather than a map showing only defect pixels, and proposed at least 80%
coverage. The new display is a separate translucent overlay. The original map,
observed mask and all five predicted-defect masks are retained. Normal skin and
unobserved pixels are unchanged; overlapping categories use stripes. Category
colours are cyan (dark marking), yellow (light brown discolouration), red (open
skin), purple (wrinkling) and green (wind scarring). Defect categories are
different from the overall fruit quality Classes 1, 2 and 3.

The application source now explicitly selects 80% observed surface, retaining
350 degrees observed longitude as the other completeness criterion. The earlier
request for provisional grades on partial maps remains enabled. A map below 80%
is labelled partial and does not claim a coverage-complete whole-fruit grade.
Standalone `Settings()` keeps the historical 65% default so frozen benchmarks
retain their original criteria. Neither changing the target nor colouring a map
creates observations of unseen skin.

Derived display job `d0cb7e25b5e14d76a7ebf03c111e259b` reuses the saved maps in
`ed3aa02cca364812a145610aad627a83` and makes zero model, tracker or reconstruction
calls. It saves 294 overlay PNGs. The helper verifies hashes of 2,058 original
map and mask files and preserves the source report. Raw original asset URLs
remain in the source job; new overlays belong to the display job. Counts remain
293 Class 1, one Class 2 and 180 Review, including 292 provisional grades.
The earlier 65% grading policy is retained as `previous_grading_policy`; current
grading metadata explicitly records 80%. Original model timings and mapping
geometry settings remain the original execution's measurements, not a new run.

Seven additional software checks verify that tinting preserves all input
arrays and every clean/unobserved pixel; five categories have distinct colours;
overlapping labels stay visible without mask changes; empty observations invent
no defects; invalid shapes are rejected; the regular-grade boundary is exactly
80%; and the app constructs settings with 80% while partial grading stays
enabled. These tests do not load either neural model. All **71 Python tests**,
frontend build and lint pass in
`diagnostics/software-checks/defect_maps_80_20261003/summary.json`.

The [new proof report](diagnostics/algorithm-revision/defect_maps_80_20261003/REPORT.md)
and [map gallery](diagnostics/algorithm-revision/defect_maps_80_20261003/index.html)
retain selected raw maps, coloured maps, masks, JSON measurements and 300-dpi
PNG/PDF figures. This is verification of saved predictions and display,
not a new end-to-end inference or an accuracy validation. Earlier sealed bundles
retain their original sources and policies.

Runtime activation is separate from source and saved-display verification.
At 20:46 SAST, the guarded restart refused to stop an ongoing user analysis;
the running API retained its earlier source and 65% settings for that run.
The final proof report records whether the new source was activated later.
No training or analysis was cancelled to apply this display update.

## Tracking identity checks and remaining validation

The [read-only tracking audit](diagnostics/algorithm-revision/tracking_identity_20261003/REPORT.md)
compares 32,875 saved boxes over all 515 frames with their retained replay; all
coordinates match exactly. This is data consistency, not physical identity
ground truth. The seven earlier association disagreements involve 15 IDs, all
without usable maps. Broad complete-box discontinuity flags occurred only at
the clip-start frame 0-to-1 transition; smooth swaps can still evade them.

A CPU replay of the same cached detector outputs, changing only camera-motion
compensation to none, produced 506 IDs and 82 IDs with at most two observations,
compared with the existing 474 and 54. This gives no support for disabling the
current compensation as an immediate fix. No production tracker change or
neural inference was made. A synthetic A-to-gap-to-different-B sequence at
identical coordinates makes the installed tracker reuse an ID, demonstrating
an ambiguity the available real labels cannot confirm or rule out.

The next accuracy test needs manually labelled paths for 20–30 physical fruit,
including gaps, occlusion and close neighbours. Proposed motion, size, real-lane
and competing-match guards should separate uncertain map segments **before
spheroid fitting**, then be replayed on those same detections. Measure actual
ID switches, fragmentation and wrong-fruit map merges on reserved labelled
paths. Missing-frame rotation rejection already splits some map sequences;
it does not certify identity. These added identity guards are proposed, not
active production safeguards. A single-fruit chamber or encoder-labelled pockets
could replace visual tracking; detection alone cannot associate the many fruit
in this video across time.
