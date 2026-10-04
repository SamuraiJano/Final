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
The paper searches up to 10 degrees of sideways movement. Our conveyor setting
searches up to 20 degrees: one real transition hit the old limit, while a wider
search measured about 13 degrees sideways with a lower matching residual.
This is our setup adaptation. The error limit remains unchanged. It helps that
transition, but the synthetic large-sideways test still fails a strict accuracy
limit in one case; a low residual alone does not prove the measured pose.

Our normal search uses images reduced four times. The video profile repeats a
successful estimate below **8 degrees** on the original pixels. Small movements
can disappear after shrinking an image.

The coarse calculation compares high-pass image values, following the paper.
Our full-turn test showed that filtering each camera image can shift the best
rotation: a known 360-degree turn accumulated more than 20 degrees of error.
This was a reconstruction problem even when a full-looking map was produced.

For the native recheck we still select the paper's strong high-pass texture
points, but compare **smoothed original green values** at their projected
locations. A two-pixel Gaussian suppresses pixel noise. We subtract the median
brightness difference between the sampled source and target values, then minimize
their mean absolute difference. This removes a constant exposure change without
assuming a rotation speed. The reported residual is divided by the sampled
intensity contrast; it remains a rejection signal, not an accuracy score.

Native feature selection keeps the physical filter width: 1.25 pixels in a
quarter-size image becomes 5 pixels in the original image. The image supplied to
your detection and segmentation models is unchanged. A failed coarse match is
not rescued. A failed native recheck is not replaced with the coarse result.
If the native rolling angle differs from the coarse angle by more than 3 degrees,
we reject that transition rather than choose one of the conflicting estimates.

The native green comparison, 8-degree trigger and 3-degree disagreement limit
are our engineering adaptations. The original high-pass MAD mode remains in the
code for comparison with the paper. Globally replacing it with original-green
matching performed badly on the authors' larger turns, so the application uses
the adaptation only for successful small-turn estimates.

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

This follows the [2022 paper's fruit coordinates and view fusion, section 2](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
Its CNN classification experiment is separate from our use of your defect model.

Code: `_map_trajectory()`, `_sample_view()` and `build_surface_map()`.

## 6. Measure observed area, then assign a class

A flat map pixel does not represent the same physical area at every latitude.
We weight pixels using the spheroid surface-area formula. Then:

`defect percentage = observed defect area / observed fruit area * 100`

The application currently requires at least 65% observed surface and 350 degrees
of observed map longitude. If those requirements fail, the fruit stays **Review**
with a reason. Estimated rotation and actually observed map coverage are different
measurements.

With sufficient evidence, the current rules are Class 1 below 10% defect,
Class 2 from 10% through 20%, and Class 3 above 20%. These are our engineering
thresholds; neither paper validates them for this conveyor.

Code: the surface-area calculation in `build_surface_map()` and `_grade()`.

## Follow one fruit while debugging

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
