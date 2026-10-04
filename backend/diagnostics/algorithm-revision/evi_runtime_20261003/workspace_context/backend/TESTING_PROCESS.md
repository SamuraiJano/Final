# Algorithm testing process and report evidence

This record describes the October 2–3, 2026 development tests. The frozen rotation
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

The current source passes these declared development controls. All **714 noisy
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
