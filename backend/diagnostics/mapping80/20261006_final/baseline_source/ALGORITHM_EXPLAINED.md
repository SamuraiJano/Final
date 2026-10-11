# How the naartjie algorithm works

The goal is to make **one surface map for one fruit**, then measure the defect
area on that map. Counting defects separately in every camera frame would count
the same blemish repeatedly.

This is our independent implementation of the authors' method. Their public
repositories supply images and point labels; they do not supply the reconstruction
code used here.

## 1. Find the fruit and keep its identity

Your D-FINE object detector returns a box around each fruit. TrackTrack associates
the boxes between frames and gives each fruit an ID. The same ID must belong to
the same naartjie throughout its passage.

Detection supplies a box in one image; association supplies the identity across
images. With many fruit in this video, reconstruction needs that association.
A one-fruit capture station or encoder-labelled conveyor pockets could replace
visual tracking. Removing association altogether would mix unrelated views.

An ID switch can join two different fruit into an invalid map. Fragmentation
gives one fruit several IDs and usually loses coverage. The read-only
[identity audit](diagnostics/algorithm-revision/tracking_identity_20261003/REPORT.md)
checks the saved boxes and a cached-detection experiment. It does not establish
real identity accuracy without manually labelled physical fruit. The seven old
association disagreements involve only tracks without usable maps; they do not
explain the current mapped examples. A smooth switch remains possible.

The proposed safeguard is to check predicted motion, size, genuine lane
constraints and competing matches before views enter a map segment. An uncertain
match must start an independent segment **before spheroid fitting**. Those guards
still need implementation and validation on labelled fruit; they are not active
in the current tracker. Disabling camera-motion compensation increased short
fragments in the cached replay, so its production setting is unchanged.

Tracking starts at the first accepted detection, including a partial fruit at the
edge. We save the first and last tracked crops. A partial fruit is still tracked,
but cannot yet provide a complete silhouette for reconstruction.

Code: `dfine_segmenter.py` and `NaartjiePipeline.record_tracked_detection()` in
`algorithm.py`.

## 2. Collect complete views of that fruit

We crop the detected fruit and use GrabCut to separate it from the rollers.
This produces a **fruit mask**, distinct from your model's **defect masks**.
A cut-off, collapsed or strongly concave silhouette is rejected. We retain the
original frame number, image and mask for every accepted view.

Code: `NaartjiePipeline.add_tracked_detection()` and `_validate_capture_mask()`.

## 3. Fit a simple 3D shape

We fit an ellipse to each silhouette. Their major and minor radii define a
spheroid: a sphere, or a slightly flattened sphere. The shape model supplies the
height of visible surface points, so a 2D image location can become a 3D point.

This follows the [2021 paper, section 3.1](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/).
The model is an approximation of a real fruit.

Code: `fit_spheroid()`, `_oblate_poles()` and `_height()`.

## 4. Measure movement between adjacent usable frames

The matcher takes the green channel, removes slowly varying brightness, and
selects strong texture points. It tries candidate 3D rotations, projects the
points into the next image, and chooses the rotation with the smallest **mean
absolute intensity difference (MAD)**. A separate normalized error rejects poor
matches; that error is not an accuracy score.

This keeps the [2021 paper's rotation search and MAD objective, sections 3.2–3.3](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/).
The paper describes 10 degrees as typical sideways movement. Our conveyor setting
searches up to 20 degrees: one real transition hit the old limit, while a wider
search measured about 13 degrees sideways with a lower matching residual.
The recorded-video search allows up to 20 degrees of rolling between consecutive
frames. Live capture retains 55 degrees because it skips frames. These are setup
assumptions; live performance and mechanical calibration still need testing.

Our normal search uses images reduced four times. The current profile repeats a
successful estimate below **20 degrees** on the original pixels. Small movements
can disappear after shrinking an image. A failed coarse match now has a separate,
strict native retry described below.

The coarse calculation compares high-pass image values, following the paper.
Our full-turn test showed that filtering each camera image can shift the best
rotation: a known 360-degree turn accumulated more than 20 degrees of error.
This was a reconstruction problem even when a full-looking map was produced.

The native recheck uses two comparisons. It first estimates how many original
image pixels the coarse rolling angle would move, using the fitted fruit radius:

`estimated pixel movement = 2 * radius * sin(rolling angle / 2)`

For movement below one pixel, it compares **smoothed original green values**.
A two-pixel Gaussian suppresses noise. Subtracting the median brightness difference
allows a constant exposure change. This branch is needed because raw texture
patterns incorrectly interpreted noise as rotation on stationary fruit.

For larger movement, it compares **nine samples around each texture point**.
The whole neighborhood is lifted onto the spheroid and projected by each trial
rotation before comparison. The samples use log green intensity, remove local
mean and linear brightness slope, and divide by local contrast. Logarithms turn
multiplicative darkening into an additive change; local subtraction reduces smooth
lighting variation. The matcher minimizes the weighted mean absolute difference
of the two patterns. It avoids blurring camera images before this projection,
which biased the tested larger turns. This branch does not promise exact
invariance to every exposure change.

The one-pixel switch comes from image resolution, rather than an assumed fruit
speed. Both branches retain the paper's fitted 3D shape, texture points, candidate
rotation search and MAD comparison. The normalized residual remains a rejection
signal, not an accuracy score.

Native feature selection keeps the physical filter width: 1.25 pixels in a
quarter-size image becomes 5 pixels in the original image. The image supplied to
your detection and segmentation models is unchanged. A failed native recheck is
not replaced with the coarse result.
If the native rolling angle differs from the coarse angle by more than 3 degrees,
we reject that transition rather than choose one of the conflicting estimates.

For a failed coarse match in the dense recorded-video profile (rolling search
bound at most 20 degrees), the configured bidirectional surface-pattern matcher
can make a new measurement at native resolution. This retry also searches
rotation around the camera axis within **10 degrees**: fruit 340 visibly tumbles,
and its distributed texture correspondences cannot be fitted well by only two
components. The rolling and sideways bounds, minimum rolling movement and 0.58
residual limit remain unchanged. A solution at either the rolling or camera-axis
boundary is rejected. Independently fitted forward and backward rotations must
agree as inverses within 3 degrees; each must also agree with the joint estimate
within 3 degrees. Failure still ends the sequence.
The pattern retry also requires at least one native pixel of rolling displacement;
independent inverse agreement alone admitted small false fits on stationary noise.
Wider sparse-view/live search profiles retain their established behavior.
This extension does not change
the normal successful-coarse path or permit missing-frame bridges, backward
rolling or extrapolated turns. It is our engineering adaptation, not a method
claimed by the papers.

The [fruit 340 investigation](diagnostics/fruit340-fix/20261004_final/REPORT.md)
preserves the rejected two-component attempt, image correspondences, new controls
and the remaining failures. A successful retry does not establish complete
surface coverage or generally accurate tumbling sequences.

The native comparisons, one-pixel switch, 20-degree trigger, 2-degree initial
pattern-search grid and 3-degree disagreement limit are our engineering
adaptations. The finer search then uses half-degree samples and a quadratic
refinement. The original high-pass MAD mode remains available for comparison with
the paper. Globally replacing it with original-green matching performed badly on
the authors' larger turns, so larger sparse author-image turns retain that mode.

We use only adjacent captured views within the configured original-frame gap.
A failed match, a missing frame or rolling movement below 0.25 degrees ends the current
sequence. We do not retry against a distant frame or fill in an assumed speed.
The minimum applies to the rolling-axis component. Sideways jitter alone cannot
establish that the fruit rolled. Rejected motion is unknown, not assumed to be zero.
We keep small, observable movements rather than dropping everything below the
old 3-degree keyframe threshold.

Code: `_search_rotation()` is the paper matcher; `estimate_rotation()` adds the
resolution recheck; `_select_rotating_views()` separates connected sequences.
These capture, refinement and rejection rules are our adaptations, not rules
claimed by the paper. Extremely slow movement can produce only partial maps.

The frozen mapping benchmark source is `50bdd78e...`. It passes the twelve fixed illumination
scenes, original full-turn and short-motion controls, strict sideways-motion
controls, fresh texture C, and numerical consistency checks. All 714 tested noisy
stationary frame pairs remain unavailable and produce no map. Those are ideal
synthetic development controls; they do not establish real conveyor accuracy.
Earlier failed sources and images are preserved separately.
The current source `f10e8393...` adds the partial-map grading policy described
below. This policy leaves the rotation search and map construction unchanged;
the earlier benchmark remains labelled with the source it actually tested.

## 5. Put the views onto one surface map

Each measured rotation carries the previous fruit orientation into the next
view: `next_orientation = measured_rotation @ previous_orientation`.
We express the visible view centers in the same fruit coordinates and check their
longitude order. Backward or implausibly large steps split a sequence. Selection
and mapping call the same `_map_trajectory()` helper, including the same reference
view, so they check the same coordinates.

We use the connected, ordered sequence with the largest measured longitude span.
For each map location, we sample one or two nearby views and blend their colors.
Your D-FINE segmentation model runs on the selected views; its masks are projected
onto the same map. Overlapping defect masks form a union, so one surface location
is counted once.

The original textured map retains the predicted defect areas. A separate
`surface_map_overlay.png` tints those areas over the texture: cyan for dark
marking, yellow for light brown discolouration, red for open skin, purple for
wrinkling and green for wind scarring. Overlapping labels use small stripes so
each label stays visible. These are **defect categories**, separate from the
fruit's overall quality Classes 1, 2 and 3. The original map and all binary masks
remain available. The overlay changes no measured area or grade.

The canvas represents the whole surface, but unseen regions remain unknown.
The mapper does not fill them with invented clean skin. Coverage measures the
observed surface area, not the fraction of the canvas that happens to be bright.

This follows the [2022 paper's fruit coordinates and view fusion, section 2](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
Its CNN classification experiment is separate from our use of your defect model.

Code: `_map_trajectory()`, `_sample_view()` and `build_surface_map()`.

## 6. Measure observed area, then assign a class

A flat map pixel does not represent the same physical area at every latitude.
We weight pixels using the spheroid surface-area formula. Then:

`defect percentage = observed defect area / observed fruit area * 100`

The application now assigns a class to partial maps too, as requested. The class
uses defects as a percentage of the **observed surface**. It does not treat unseen
surface as defect-free or guess what that surface contains.

At least 80% observed surface and 350 degrees of observed map longitude now
mark a map as having sufficient coverage. A map below those requirements can
receive **Class 1 (partial)**, **Class 2 (partial)** or **Class 3 (partial)**. Its
report records `status: graded_partial` and `grade_provisional: true`, while the
app keeps the measured coverage visible. Estimated rotation and observed map
coverage remain different measurements.

The 80% target is the requested application setting, not a paper-derived
accuracy threshold. Standalone `Settings()` retains its historical 65% default
for reproducible benchmarks; `main.py` explicitly selects 80% in the app.
The earlier request to grade partial maps remains enabled, so a map below 80%
can receive a clearly provisional observed-area class. It is not presented as
a coverage-complete whole-fruit grade.

These are the new source settings. A running API activates them only after it
can be restarted while idle. The guarded restart at 20:46 SAST preserved an
ongoing user analysis under its earlier 65% settings. Its result must retain
that execution's provenance, even if the newer display uses an 80% target.

For a usable defect estimate, the current rules are Class 1 below 10% defect,
Class 2 from 10% through 20%, and Class 3 above 20%. These are our engineering
thresholds; neither paper validates them for this conveyor.

A fruit with no usable map, no observed area or no valid defect estimate remains
ungraded. Implausible motion steps also remain ungraded. For example, fruit 340
has 26.5% observed surface and 17.8% predicted defects within that observed area:
it receives **Class 2 (partial)**. The unseen surface was not assessed.

The app enables `Settings.grade_partial_maps`. Its default is false so the earlier
strict benchmark and comparisons remain reproducible. Partial grading changes
the class decision; it does not relax silhouette checks or reconstruct missing
surface.

Code: the surface-area calculation in `build_surface_map()`, `_grade()` and
`_grade_map()`.

## Follow one fruit while debugging

Choose **Latest run** to inspect one completed analysis. **All saved runs** adds
inspection records from every saved report, including repeat analyses of the same
video. Earlier Review results stay saved. The new latest run applies the partial
grading rule to the saved original maps, preserving the original report and all
image bytes. The report names the original mapping source separately from the
new grading-policy source; the models were not rerun for this update.

The newer defect-display job `d0cb7e25b5e14d76a7ebf03c111e259b` adds the
coloured overlays and the 80% coverage target to those saved observations. Its
original map URLs still refer to the preceding job; new overlay URLs refer to
the display job. It makes no detector, tracker, segmenter or motion calls.
The saved coverage and defect percentages are unchanged. Its inherited model
metrics describe the original full-video execution, rather than a new run.

Open its inspection and inspect the first/last tracked crops. Then download the
report and find the matching `track_id`. The saved `result.json` records captured
frames, mapped frames, discarded frames, mask rejections and `view_selection`.
Each motion record gives source/target frame numbers, rotation, match error and
the reason for a split. Successful measurements also record the coarse angle and
the image resolution used. A failed sequence retains its motion diagnostics too.

Check these stages in order: identity, fruit silhouette, motion matches,
longitude order, observed coverage, then defect masks. A detected fruit or a
successful map alone does not prove the final grade is accurate.

The original reports and algorithm snapshots are preserved. Tests use author
feature labels, synthetic motion with known answers, and fixed real conveyor
images. Current experiments are under `diagnostics/algorithm-revision/`; their
reports distinguish accuracy measurements from coverage and software execution.

## Memory and interrupted runs

The mapper keeps cropped images and masks while a fruit is being tracked. When
that fruit finishes, the app writes its report and evidence, then releases the
stored track data. The release now also happens if writing or mapping raises an
exception. When a video run stops or fails, the app releases the video capture
and any remaining track data. Errors still reach the API; cleanup does not turn
an interrupted fruit into a successful result.

The frontend file watcher ignores the backend folder, which contains model
weights, the Python environment and thousands of evidence images. This reduces
unnecessary frontend work while those files are created. Neither cleanup change
alters the measured rotations, coverage requirements or class thresholds.

The previous full-video attempt failed with a memory allocation error after its
last published progress of 330/515 frames while model training was running. The
exact error frame/time was not logged. Its records remain separate from the
retry. Passing the retry establishes that this saved video can complete with the
recorded resources; it does not establish simultaneous training capacity or
real-time conveyor throughput.
