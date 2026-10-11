# How the naartjie algorithm works

The application makes one measured surface map for each guarded fruit identity,
then measures the defect union on that map. It preserves unknown skin and makes
partial grades explicit. Coverage is estimated under a spheroid model; it is
not independently measured physical area.

The current mathematical audit, exact settings, paired before/after results,
failed calibration trials, reproduction commands and acquisition limitations
are in [SURFACE_MAPPING_AUDIT.md](SURFACE_MAPPING_AUDIT.md). The frozen current
experiment is [the paired comparison](diagnostics/mapping80/20261006_final/COMPARISON.md).
Earlier diagnostics retain their original source hashes and observations.

## 1. Detection and guarded identity

D-FINE detects fruit boxes in every video frame. TrackTrack associates detections.
ConveyorIdentityManager and the fruit identity guard check motion, size, local
ordering, competing matches and bounded missed detections before views enter a
reconstruction identity. Uncertain associations form independent identity records
before shape fitting; uncertain identities remain ungraded.

These guards are active. They cannot establish real identity accuracy without
manual labels; smooth switches and fragmented records remain possible. The
number of tracker identities is therefore different from the true number of
physical fruit. Translation is used for tracking, never as fruit rotation.

Code: the DfineDetector adapter in `dfine_segmenter.py`, `conveyor_identity.py`, `fruit_identity.py`, and
`NaartjiePipeline.record_tracked_detection()` in `algorithm.py`.

## 2. Complete silhouettes and deferred defects

GrabCut extracts fruit masks from padded detector crops. Cut-off, collapsed or
strongly concave silhouettes are rejected. Captured views retain original frame
numbers, images, masks and boxes. A tracked partial fruit can have no usable
mapping silhouette.

Uploaded video retains dense candidate views (capture stride 1). It still tracks
every frame, including frames whose crops are unusable. D-FINE defect segmentation
is deferred until geometry selects the views used by the map. This avoids running
segmentation on all redundant captures while ensuring every selected view is
segmented. Fruit masks and defect masks serve different purposes.

Code: `_validate_capture_mask()`, `NaartjiePipeline.add_tracked_detection()`,
`NaartjiePipeline.finish_track()`.

## 3. Fit the shape and lift image points

Silhouette covariance supplies the projected ellipse center, axes and semiaxes:
`a = 2 sqrt(lambda_max)`, `b = 2 sqrt(lambda_min)`. A shared sphere or oblate
spheroid supplies the height of visible surface points. The larger quadratic
root of `p.T @ M @ p = 1` is the camera-facing surface. Visibility uses the
surface normal `(M @ p).z > 0`; a tilted visible surface can include negative z.

This follows [Albiol 2021, section 3.1](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/).
Real irregular fruit and imperfect silhouettes introduce model error. The oblate
minor radius can also be biased if the collection never shows the necessary
projection. Dense geometry follows the signed projected pole vector. For the two searched
rotation components, the orthogonal projected component determines depth sign
from the configured rolling direction, including transverse motion. A local
fit uses at most seven samples and shrinks for rapid curvature. It estimates
geometry and supplies no measured rotation. The full audit derives the sign
law and preserves earlier minor-axis-trend trials that failed mixed-turn truth
controls. Camera-axis tumbling is excluded from this profile's pose assumption.

Code: `_ellipse()`, `fit_spheroid()`, `_silhouette_slopes()`, `_oblate_poles()`, `_height()`.

## 4. Directly measured rotation and keyframes

The coarse matcher uses green-channel high-pass texture and mean absolute
intensity difference, following the 2021 paper. A separate normalized residual
rejects unreliable hypotheses. Dense video uses half-size images, sigma 2.5,
40-degree rolling and 10-degree transverse limits. This preserves the original
five-pixel filter scale while retaining more peel detail. Points must lie inside
a conservative ellipsoid-normal visibility cone; bright low-saturation glare
is excluded from feature selection.

Native remeasurement uses the existing original-green comparison for subpixel
hypotheses, or surface-aligned nine-sample patterns for observable movement.
A failed coarse estimate can be remeasured from the original pixels. Rolling
boundary optima, residuals over 0.58 and inconsistent estimates remain rejected.
Native aligned-pattern search uses its existing 2-degree initial grid and then
finer local/parabolic refinement; the coarse high-pass search uses 1 degree.

Dense keyframe selection keeps the last accepted view as an anchor and examines
later candidates directly. Failed or redundant pair hypotheses are recorded but
never composed. Acceptance requires at least 3 degrees of measured dominant
rolling, independent forward/reverse inverse agreement and agreement with the
joint estimate within 3 degrees. A failed eight-frame anchor window splits the
sequence. One missing silhouette can be crossed only by a newly measured pair,
within that window; larger capture gaps split. Identity guards remain active.

Sparse live capture retains its adjacent-selection profile. Hardware accuracy
has not been tested in this audit. These dense scheduling, native descriptors,
confidence and feature-support rules are engineering adaptations. A failed pair
means unavailable motion evidence; it does not mean the fruit did not rotate.

Code: `_relevant()`, `_search_rotation()`, `estimate_rotation()`,
`_verify_keyframe_rotation()`, `_select_keyframes()`, `_select_rotating_views()`.

## 5. A common fruit-coordinate map

Only accepted relative rotations propagate pose:
`next_orientation = measured_rotation @ previous_orientation`.
Selection and fusion share the same fruit coordinate trajectory and longitude
order checks. The largest supported ordered segment is selected; disconnected
segments are not stitched with assumed turns.

Each physical map cell receives actual visible samples from one or two neighboring
measured views, with nonnegative interpolation weights. Endpoint views extend
at most 45 degrees before/after their centers, still requiring valid projections.
Later measured revolutions can contribute new image and defect samples to the
same physical cell. Each cell's area is counted once. Unknown regions receive
no support, texture or inferred clean skin.

This uses [Albiol 2022, section 2](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/)
for fruit coordinates, neighboring-view fusion, endpoint support, the latitude
band and angular scale. Unique-cell revisit accumulation is our adaptation.
The angular step is approximately one original equatorial pixel (`1/A` radians).

D-FINE class masks are projected onto the same valid surface cells. Overlapping
classes and repeated observations form a union. Existing colored defect overlays
are display layers; they do not change measured areas, grades or original texture.

Code: `_map_trajectory()`, `_sample_view()`, `build_surface_map()`.

## 6. Full-surface coverage and provisional grading

The ellipsoid Jacobian weights map cells by modeled physical surface area:

`coverage = observed modeled area / full modeled fruit area * 100`

The denominator includes the full +/-90-degree latitude range. Mapping only the
+/-60-degree band leaves pole caps unknown; a fully observed spherical band is
86.602540%, not 100%. No dilation or canvas filling increases the observed mask.

Defect percentage for grading is observed defect union area divided by observed
fruit area. A separate value divides the observed defect union by the full
modeled area; it cannot estimate defects on unseen skin. Absent segmentation
evidence yields no defect estimate or grade.

Production requires at least 80% surface and 350 degrees of supported longitude
for coverage completeness, plus the configured rotation/pair-gap checks. A
partial map can receive an explicitly provisional observed-area class:
`status: graded_partial`, `grade_provisional: true`, `coverage_complete: false`.
Uncertain identities and implausible motion remain ungraded. Class 1 is below
10% observed defect, Class 2 is 10% through 20%, Class 3 is above 20%. These
thresholds are application policy; neither paper validates classification for
this conveyor. Standalone settings retain historical benchmark defaults;
`main._mapping_settings()` supplies the production profile.

Code: `_ellipsoid_jacobian()`, `_grade()`, `_grade_map()`, `build_surface_map()`.

## Inspect a result

Use the first/last tracked crops, original frame numbers, identity diagnostics,
captured and selected views, every accepted/rejected rotation, the residuals,
surface map, observed mask, longitude support, defect masks and provisional flag.
A plausible occupied map is not sufficient evidence of accurate reconstruction.

The full audit provides representative real success/partial/failure evidence as
available and explicitly labelled known-truth synthetic controls. A synthetic
full turn must never be presented as a successful real fruit. Saved reports keep
the source hashes and settings that actually generated them; changing source does
not retroactively recompute existing runs. The API must import the updated code
before future analyses use these changes.
