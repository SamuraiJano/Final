# Architecture review for an 80% fruit mapping success target

No production source was changed. The only executable experiment in this folder
is an exact-pose rendering control; it does not estimate recorded-video poses.

The provisional target is **80% of distinct physical fruit passing through the
inspection region receive a reliable map meeting the existing 80% surface
coverage requirement**. The current app also requires 350 degrees of observed
longitude. Producing any partial image or provisional grade is not success under
that definition. A raw track ID is not an independently counted physical fruit.

## Largest software opportunity

Replace the coupled assumption of positive, two-component adjacent rotations
and monotonically ordered longitude strips with **measured, signed three-axis
poses, a graph of directly verified view matches, and all-view visibility
fusion**. Changing only the rotation search cannot fix the downstream selection
and fusion, which reject genuine reversals and nonmonotonic tumbling.

Current code evidence in `backend/algorithm.py`:

- `estimate_rotation`: coarse successful two-axis estimates are kept. The new
  native three-axis retry handles coarse failure only; it cannot repair an
  accepted but physically wrong coarse estimate.
- `_select_rotating_views`: any missing crop, unobservable adjacent motion or
  rejected pair starts a new segment. It then splits negative or very small
  fruit-fixed longitude increments and keeps one segment.
- `_map_trajectory`: relative poses are accumulated in a chain. There are no
  redundant edges or loop constraints to expose accumulated drift.
- `build_surface_map`: each longitude column is sourced from two chronological
  neighboring views. This does not use every view that can geometrically observe
  that surface point and requires a monotonic longitude trajectory.
- `_relevant`: the central sampling ellipse and strongest-response percentile
  can concentrate samples on a highlight. `exclude_specular_texture` is false
  in the app profile. The black freckle on fruit 340 moves outside the central
  sampling region while still visibly belonging to the fruit.

Independent image checks already document accepted poses that miss fruit 340's
freckle by 7.33, 5.19 and 11.69 native pixels. Conversely, the recovered 308 to
309 pair is supported by distributed SIFT and ORB matches requiring nonzero
camera-axis rotation. See the earlier [image investigation](../../fruit340-fix/20261004_motion/REPORT.md).
Those correspondences are approximate image evidence, not calibrated pose truth.

## An inexpensive experiment that isolates fusion

`oracle_visibility.py` renders a radius-55 textured sphere with exact input
poses, fruit masks and a known 15% longitude-wedge defect. It compares production
strip fusion with a diagnostic projection of all views onto the surface grid.
The diagnostic keeps the existing 60-degree latitude limit. It only counts
points inside the original fruit masks, facing the camera and satisfying a
chosen surface-normal cosine cutoff. Color weights are squared normal cosines.
Neither pose estimation nor neural models nor physical identities are tested.

At a conservative normal cosine of at least 0.5 (within 60 degrees of the camera
direction), the results are:

| Exact pose sequence | Production strip fusion | Diagnostic all-view fusion |
| --- | --- | --- |
| 100-degree forward turn | 45.72% surface / 190.40-degree longitude; partial | 49.02% / 219.54 degrees; partial |
| 250-degree forward turn | 81.70% / 340.23 degrees; fails the existing longitude gate | 84.08% / 360 degrees; meets both gates |
| 270-degree forward turn | 86.45% / 360 degrees | 85.45% / 360 degrees |
| 375-degree forward turn | 86.45% / 360 degrees | 86.39% / 360 degrees |
| Rocking with a 275-degree unique pose span | Rejected: longitude centers not consistently ordered | 85.60% / 360 degrees; meets both gates |
| 16 duplicate stationary views | Rejected: no consistent progress | 25.01% / 119.65 degrees; partial |

This provides a concrete reason to redesign fusion without lowering coverage
requirements. It also shows that fewer useful views or repeated views cannot be
turned into a full map by fusion alone. The 60-degree latitude band caps the
ideal sphere result near sin(60 degrees), about 86.6% of total surface; the
actual discrete grid yields 86.4508%. There is little margin above the 80% gate.

Blindly applying defect-mask OR to every visible image is a risk. In the full
375-degree example, counting near-limb pixels gives 16.0834% for the true 15%
defect. A normal cosine floor of 0.5 gives 15.2479%. Even with exact poses,
projection rounding and binary-mask aliasing require validation. General fusion
should choose a best reliable source view or combine mask evidence using a
documented confidence rule; adding more noisy masks is not proof of more defects.

Raw results, exact pose schedules and generated maps are saved in
`oracle_visibility.json` and the accompanying PNGs. The rocking all-view map
was visually inspected. This is not a candidate deployed mapper or proof that
80% of the recorded fruit can pass.

## Reviewable implementation phases

1. **Freeze a representative corpus and define the denominator.** Reconstruct
   full captures from the original video, raw cached tracker boxes and one
   reproducible mask extraction pass. Hash those inputs and separate complete
   inspection passages from clip-start and clip-end truncations, while reporting
   both. Use reviewed physical-fruit IDs for the success denominator. Establish
   a failure breakdown: capture/occlusion, low texture, pose error, graph
   disconnection and truly insufficient observed area. Reserve a held-out clip.

2. **Validate signed 3D measurements independently.** Start with existing OpenCV
   SIFT/ORB and SciPy; no extra model or library is necessary for a first
   prototype. Sample features across multiple spatial cells inside an eroded
   foreground, excluding glare and weak/blurred texture. Fit bounded signed
   three-axis rotation using lifted surface points and robust reprojection
   residuals, then refine surface-aligned photometric patterns. Compare forward
   and independently fitted inverse estimates. Require adequate spatial support,
   a well-conditioned solution and held-out correspondence checks; a low
   brightness residual alone is insufficient. Evaluate this alternative for
   successful coarse pairs too. Use an abstention for genuinely ambiguous pairs.

3. **Use directly measured keyframe edges.** A low-motion adjacent pair can be
   skipped while retaining the last reliable keyframe; match a later crop
   directly against that keyframe when displacement becomes observable.
   Additional short-window edges provide redundancy. A missing usable mask is
   not necessarily a missing identity observation. If the existing guard proves
   continuous capture identity, endpoints across a missing crop may be aligned
   directly, with no pose assigned to the missing view. Do not connect across a
   guard boundary or unsupported identity gap. Do not infer rotation from
   conveyor speed, elapsed frames or accumulated subpixel jitter.

4. **Optimize consistent pose components and fuse all valid observations.** Use
   robust SO(3) graph residuals over independently measured edges, with a fixed
   reference pose and outlier edges removed. Reprojection residuals and cycle
   consistency should determine whether a component is usable. Fuse projected
   observations by foreground validity, viewing angle, blur, glare and pose
   confidence, independent of chronological order. Track supported area as a
   union of actual valid observations. Preserve 80% surface/350-degree longitude
   gates initially. Rotational travel is a diagnostic, not observed-area proof.

5. **Run the complete pipeline and inspect failures.** Require unchanged
   stationary/noise/shading controls, fixed accuracy limits for independent
   synthetic poses, author-provided point correspondence accuracy, known defect
   area controls and held-out physical-fruit checks. Compare processing cost and
   segmentation call counts; all-view fusion may retain more views and invoke
   more real defect-model predictions. A better pose component alone does not
   show that the complete estimator chooses it correctly.

## Tests that should remain and tests whose mechanism would change

Keep the identity guard, ambiguity tests, stationary/noise abstention, model
profile scope checks, inverse consistency, residual limits, masks, area
normalization, grade completeness and end-to-end inference tests. Add independent
known backward/tumbling/rocking pose schedules and graph outlier/cycle tests.

The current exact-call-list tests `test_failed_motion_ends_sequence_without_a_replacement_bridge`
and `test_original_frame_gap_splits_even_when_crop_list_is_consecutive` encode
the adjacency-only design. They should remain for the legacy profile. The graph
profile needs tests distinguishing a directly measured safe edge across rejected
usable crops from an unmeasured bridge or identity gap. Likewise,
`test_deferred_segmentation_runs_on_retained_views_and_preserves_area` would have
different retained-view counts under general fusion; preserve the guarantee that
every used view has real defect inference, rather than a fixed legacy count.

The known 250-degree sphere coverage control currently expects rejection because
strip fusion only observes 340 degrees. An all-view implementation can support
360 degrees at that exact known pose sequence. Any changed expectation must be
justified by independent visibility and area evidence, as above, not by changing
the 350-degree gate. Existing forward legacy controls should stay reproducible.

## Assets available now

- NumPy, OpenCV including SIFT/ORB, and SciPy are already installed. Existing
  diagnostic feature fitting uses `scipy.optimize.least_squares`.
- Four primary frozen fruit fixtures contain 215 complete image/mask views,
  tied by source pixels to raw IDs 1, 14, 98 and 340. Additional original-video
  onset crops have already been recaptured. They are a small development set,
  not a representative success-rate dataset.
- The completed original job contains tracking history and capture frame lists
  for all 474 raw records, but usually only three selected evidence crop/mask
  images per mapped fruit. It does not freeze all original captured masks. The
  original video and 515-frame tracker cache allow one consistent recapture.
- The downloaded FruitRot3D data supplies author-annotated point correspondences
  for 36 sequences, and the benchmark can measure image projection error.
  These sparse controlled sequences are useful accuracy regressions but differ
  from the dense conveyor profile and cannot establish its fruit success rate.
- The existing 19 motion/shading controls contain 190 moving pairs and 752
  stationary/uniform pairs. Later stress controls already expose cases where a
  successful coarse estimate chooses the wrong motion model. Known-area controls
  freeze 5%, 15% and 30% defect scenes and coverage cases with supplied exact poses.

## Could software alone get this clip to 80%?

It is plausible that the redesign recovers substantially more usable fruit than
the bounded retry, because it removes several known incorrect assumptions. The
available evidence does not justify predicting an 80% physical-fruit success
rate. On fruit 340, current SIFT/ORB matching does not provide enough robust
inliers for 309 to 310 and 310 to 311, optical flow fails fast movement, and late
views contain little surface change. More freedom can produce confident-looking
false poses when texture is ambiguous. Shape and silhouette uncertainty compound
that problem on nearly spherical fruit.

If a reviewed visibility/capture audit finds more than 20% of complete fruit
have insufficient observable surface or unreliable image texture, an 80% true
success target also requires capture changes: stable diffuse illumination and
glare reduction, sharper exposure, fruit separation, longer reliable rolling
time, and/or an additional calibrated camera viewpoint. Increasing frame count
alone does not expose missing surface. Those are interventions to evaluate with
the conveyor, not settings guaranteed to fix the existing video.

## Primary research and the limits of applying it here

[Albiol et al. 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) supports
spheroid fitting and texture-based rotation estimation and explicitly limits
applicability to adequately textured fruit whose shape is reasonably modeled
by a spheroid. Its controlled research data does not validate an arbitrary
80% success rate on this clip.

[Albiol et al. 2022](https://www.mdpi.com/1424-8220/22/14/5452) maps fruit-fixed
surface coordinates through measured poses to camera views. The proposed
general all-view confidence fusion is an engineering extension to the current
strip implementation, not a reported result from that paper.

[Choi, Zhou and Koltun, CVPR 2015](https://openaccess.thecvf.com/content_cvpr_2015/html/Choi_Robust_Reconstruction_of_2015_CVPR_paper.html)
uses robust global optimization to reject erroneous pairwise alignments in
RGB-D reconstruction. It supports the design principle of redundant verified
edges and robust global consistency. Applying that principle to a monocular
rotating spheroid is an inference and needs separate validation.
