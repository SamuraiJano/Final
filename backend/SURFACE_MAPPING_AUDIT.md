# Final surface-mapping audit, 6 October 2026

The production changes address geometry and measurement-handling defects. They do not
establish that this footage meets the 80% requirement. Read the measured results
and verdict below before making that claim in the skripsie. A map's occupied
area is an estimate under a fitted shape and measured poses, not independently
verified physical surface area.

The source of truth at the start was local `main` and `origin/main`, commit
`0e9f3c7437ea3a92761d1774c48c8388c0a45884`. The tracked working tree was clean.
The initial `algorithm.py` SHA-256 was
`21e8eb0b924d153c5bbc979c9202330b1621283c33444d132b7da51cddfbe3b4`.
Remote branch verification encountered Windows Git TLS failures, so the local
branch was audited without fetching or replacing it. The pre-existing untracked
`MAIN_FUNCTIONS.md` was preserved.

## Evidence and denominator

All artifacts in this report are relative to
`diagnostics/mapping80/20261006_final/`. `baseline_source/` preserves the active
initial sources; `inputs.json` freezes the full cohort, original tracker IDs,
identity statuses, frame numbers, boxes, crop hashes and silhouette hashes.

The matching current-source saved full run was
`results/b23fe12db90e41dbae9928e3fbcf55cf/report.json`, on
`WIN_20260818_13_05_49_Pro.mp4`: 795 frames, 29.9308014929 fps, SHA-256
`ae12db73e219a666b639725e9c729e9d3f79e80c4fc6c369795187f67acf8198`.
There are 556 tracker records, 407 with at least one usable view and 406 with
at least two. These are eligible **identity records**, not a manually counted
denominator of distinct physical fruit. Fragmentation can count one fruit more
than once; undetected fruit are absent. The user's historical 17,220-view
figures belong to another run and are not the current baseline.

The original saved run had 24,049 accepted captures and 381 maps. The paired
replay re-extracted the same accepted-frame crops from the original video, using
a fixed per-frame GrabCut seed. It obtained 23,946 usable captures; 103 previously
accepted silhouettes were rejected on re-extraction. Both replay variants use
these exact same immutable NPZ files, including their rejections, and all 556
records. The baseline therefore has 383 maps rather than 381. This is a
controlled remeasurement, not a byte-identical rerun of the old stochastic
GrabCut masks. No favorable tracks were filtered into the headline comparison.

The separate 32-record `pilot/` contains all saved records from a different,
earlier diagnostic video. Its 29 eligible records and 938 views supported
calibration and ablations. Its results never enter the full-cohort numerator.

Geometry replay disables defect inference and grading in **both** variants.
It tests mapping on unchanged identities/crops. Fresh production integration
uses the actual D-FINE detector, TrackTrack, identity guards, GrabCut, deferred
D-FINE segmentation, mapping and report/grading path. These have separate
denominators. Neither experiment has manual real pose, identity or defect truth.

Tracking history remains separate from selected mapping views. The recorded-video
capture buffer retains up to 120 usable views per identity; the frozen cohort's
largest record has 74 usable views, so this limit does not truncate its inputs.

## Causes isolated and changes

1. **Adjacent sampling caused repeated sequence destruction.** In the paired
   baseline, 18,794 transitions split for motion below the minimum; 17,128
   hypotheses returned exactly zero. This means unavailable measurement, not
   proof that a fruit was stationary. Most tiny apparent movements disappear
   at quarter resolution. Dense keyframe selection now keeps the last accepted
   anchor and directly measures later candidates. Unaccepted angles are never
   composed into a pose. The anchor window is eight original frames; a failed
   window splits. Independent forward, reverse and joint estimates must agree.

2. **Blindly sampling every fourth frame did not solve the problem.** Pilot
   `adaptive_only` produced four maps; `adaptive_40_10` produced two, versus
   25 baseline maps. Four-frame displacement can already exceed the search
   bounds for some pairs. Final scheduling examines every candidate, then
   accepts only measured rolling increments of at least 3 degrees. This 3-degree
   spacing is distinct from the historical 20-degree native-recheck trigger.

3. **Coarse and native texture selection needed separate calibration.** The
   final dense profile uses half-size images and sigma 2.5, retaining the same
   physical five-pixel high-pass scale as quarter-size sigma 1.25. Native feature
   selection removes the additional two-pixel preblur, preserving peel detail.
   It retains the existing original-green comparison for subpixel hypotheses
   and surface-aligned nine-sample patterns for measurable displacement.
   A failed coarse hypothesis can be remeasured at native resolution within
   40/10-degree two-axis limits. No residual or disagreement gate is relaxed.

4. **A hard-coded central ellipse was an undocumented engineering choice.**
   Dense matching now selects points by the fitted surface normal and the
   configured rotation cone. It excludes glare from feature selection and
   retains actual target foreground, visibility and point-count checks. The
   glare mask is not used to manufacture map support. It remains a heuristic
   without manually labelled glare validation.

5. **Pole depth disambiguation was a geometric bottleneck.** Raw minor-axis
   differentiation produced 241/906 pilot pole jumps beyond the 41.23-degree
   searched vector bound; in the full cohort there were 7,297/23,539. A fixed
   seven-frame fit reduced jumps but failed rapid known turns by over 80 degrees.
   An adaptive window fixed the rapid single-axis case, then failed valid mixed
   rolling/transverse controls by 46..75 degrees. All sources and outcomes are
   preserved: `final_v2/` is the fixed window; `final_v3/` is the adaptive
   minor-axis derivative. They are intermediate experiments.

   The final `projected_trend` method follows the projected pole vector, choosing
   equivalent eigenvector signs continuously in the image plane. With no
   camera-axis rotation, dp_y/dt=-omega_x*p_z and dp_x/dt=omega_y*p_z. Thus the
   orthogonal projected component resolves depth using only the configured
   rolling sign, even with transverse motion. It uses a residual-adaptive
   maximum-seven-sample fit, shrinking to five/three for genuine curvature;
   its noise floor is measured major-radius noise divided by A. Ambiguous signs
   use the nearest geometric branch. This supplies no rotation magnitude or
   mapping increment. Only direct texture estimates enter the map.

   Both axes/directions, rapid pure turns through 40 degrees and 24 mixed
   component controls pass. Worst fitted pole error is below 4.5 degrees,
   including finite-view bias in B=min(projected minor). The projected law
   assumes a zero camera-axis component, so that mode also disables the older
   optional camera-axis native retry. The matcher supplies no camera-axis component in this profile. Actual
   camera-axis tumbling remains unmodeled and can impair real accuracy; the
   confidence gates do not certify that it is absent.

   The final full-silhouette audit still has 5,956/23,539 adjacent jumps beyond
   that cone (median adjacent axis change 6.97 degrees). The adaptive minor-axis
   intermediate had fewer jumps (1,671), but that statistic cannot justify a
   method that fails correct mixed-axis truth. Projected geometry passes those
   controls while remaining noisy on actual masks. The derivative noise floor
   from major-radius variation is an engineering proxy; it does not quantify
   all eigenvector/minor-radius uncertainty or irregular fruit shape. These
   counts describe fitted geometry, not accepted texture rotations or physical
   turns. Native/inverse verification still rejects unsupported transitions.

6. **Measured revisits were previously excluded by the unique chart.** Later
   supported revolutions now contribute their actual image/defect samples to
   existing physical cells. Area is counted once. Every revisit retains the
   two-neighbor fusion rule. Missing samples contribute zero weight.

7. **Projection and completeness accounting needed small corrections.**
   Surface sampling now rejects continuous coordinates beyond image bounds
   before bilinear interpolation; rounded coordinates cannot admit half-pixels
   outside the image. `coverage_complete` includes the same maximum-pair gate
   as grading. The full Jacobian denominator and 80%/350-degree targets were
   already correct and are preserved.

Two final frozen pilot checks were also rejected. `native_green_fallback`
retries the surface-pattern objective after an unavailable smoothed-green
hypothesis; all 32 records produced exactly the same selected maps and coverage
as `stable_geometry`. `fine_peel_scale` halves the physical high-pass/patch
scale; its full pilot metrics are retained in `ablation_summary.json` and it
gave mixed results: 19 maps, median 27.30% versus 26.88%, but upper quartile
33.19% versus 36.42% and maximum 56.05% versus 62.43%. It did not solve the
coverage problem and was not adopted. Neither trial changes the headline cohort.

Remaining failures are predominantly unavailable or inconsistent skin
registration. A low residual and inverse consistency are necessary checks;
they do not prove a unique correct correspondence on repetitive or changing
texture. A local silhouette fit does not remove real fruit irregularity.
The code returns partial maps or explicit failures when direct evidence ends.

A diagnostic depth-branch continuity bound was also tested on real record 393
without changing production code. It reduced that record from 51.945% to
51.272% and shortened its selected chain, so it was not adopted. This one-record
probe is not a full-cohort ablation and does not enter headline results.
`pole_branch_probe.json` preserves both measurements and the diagnostic wrapper.

## Mathematical audit

References are Albiol et al., [2021, DOI 10.3390/s21062232](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022, DOI 10.3390/s22145452](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
Authentic full-text copies already in `diagnostics/authors-benchmark/papers/`
were read alongside the active source. Pole trend estimation, dense selection, native
patterns, glare exclusion, confidence gates, unique-cell revisits, identity
validation and grading policy are application adaptations.

| Check | Derivation / implemented meaning |
|---|---|
| 1. Silhouette covariance | Foreground pixel centroid; covariance is mean centered outer product (population normalization). For a uniformly filled ellipse, principal variances are a^2/4, b^2/4. Raster and GrabCut errors remain. |
| 2. Semiaxes | `2 sqrt(lambda_max)` and `2 sqrt(lambda_min)`, not diameters; eigenvectors give projected principal directions. Independently rasterized controls recover center/radii. |
| 3. Shared shape | Sphere radius mean of per-view major/minor; oblate A = mean major, B = minimum minor. Auto-sphere tolerance 0.06 is engineering. B assumes the collection includes a sufficiently equatorial projection; a partial collection can bias B. |
| 4. Oblate pole | Projected length^2 = (A^2-b^2)/(A^2-B^2); depth^2 = (b^2-B^2)/(A^2-B^2). Silhouettes leave the depth sign ambiguous. The final dense method uses the signed orthogonal projected-pole derivative, configured rolling sign and nearest ambiguous branch. Minor-radius trend is preserved for sparse callers; it is insufficient for mixed rolling/transverse motion. |
| 5. Lift | Solve Mzz z^2 + 2(Mxz x+Myz y)z + Mxx x^2+2Mxy xy+Myy y^2-1 = 0. The larger root has camera-facing normal; negative discriminant is invalid. A visible point can have negative z on a tilted oblate. |
| 6. Rodrigues | Rotation vector components are radians. `cv2.Rodrigues(v)` gives an active right-hand matrix R; vectors with two components are exponential-coordinate rotations, not successive Euler rotations. |
| 7. Axis | Camera coordinates x right, y down, z toward visible side. `x` default follows the configured roller orientation. Map y is chosen near the roller axis with radii permuted alongside the basis. |
| 8. Direction | +1 is right-hand about configured image axis; reverse controls test -1. Axis/direction are mechanical setup assumptions, not inferred from conveyor translation. |
| 9. Matrix order | Column point maps as R p; row arrays as `points @ R.T`. Relative rotations compose on the left: P[i+1] = R[i] P[i]. Reverse agreement compares Rback Rforward with identity. |
| 10. Visibility | For implicit p^T M p = 1, outward normal is proportional to M p; valid camera-facing samples have (M p)z > 0. Also require finite projection, continuous image bounds and actual fruit foreground. |
| 11. Photometry | Coarse minimizer is unnormalized high-pass MAD over valid points; normalized residual is a separate rejection quantity. Native aligned MAD uses warped neighborhoods with local log-brightness detrending and contrast normalization. These native descriptors are adaptations. |
| 12. Limits | Dense rolling 0..40 deg in configured direction, transverse +/-10 deg; search-edge optima rejected. Wider native retry keeps two components, not an unbounded third axis. |
| 13. Refinement | Paper-style coarse search 1 deg, local 5 x 5 half-step and parabolic refinement. Existing native aligned-pattern search starts at 2 deg for cost control, then refines; it is not falsely described as an everywhere-1 deg grid. |
| 14. Native retry | Remeasure original pixels after unavailable coarse result; same residual gate, minimum observable displacement and independent joint/forward/backward agreement. Failed retry remains failed. |
| 15. Bidirectional | Joint photometric objective uses both directions. Adaptive keyframes also run independent directional minima, checking inverse and joint discrepancies within 3 deg. These are confidence adaptations, not proof of ground truth. |
| 16. Fruit pose | Find the selected reference basis and carry it through composed measured matrices. Selection and fusion use the same `_map_trajectory`; unmeasured increments are never added. Per-frame fitted ellipsoids approximate shape in matching; fusion uses rigid propagated geometry. |
| 17. Chart | X(lambda,phi) = (rx cos(lambda)cos(phi), ry sin(lambda), rz cos(lambda)sin(phi)); camera-ray longitude uses atan2(z/rz,x/rx), retaining anisotropic radii. |
| 18. Interpolation | At a supported longitude use two neighboring measured views with nonnegative linear weights. Normalize only valid color contributions. Interpolation chooses image sources; it supplies no rotation between them. |
| 19. Endpoints | First/last view support extends at most +/-45 deg in longitude, still subject to front-facing, image bounds and silhouette checks. This is not assumed extra rolling motion. |
| 20. Resolution | Default angular step 1/A radians, approximately one equatorial original-image pixel; round full 2pi width and pi height upward, then use uniform cell centers. |
| 21. Longitude | Sum widths of columns with at least one valid observed cell. Longitude occupancy is not full surface percentage. Unknown columns remain unknown. |
| 22. Rotation | Sum absolute measured dominant Rodrigues components over the selected chain; report fruit-chart longitudinal span separately. Neither equals physical unseen motion or area. |
| 23. Defect projection | Sample supplied per-view class masks at the same valid physical projection; segmentation masks are intersected with fruit foreground. |
| 24. Union | OR valid positive-weight class observations into each physical map cell, then OR classes for total defect area. Multiple labels/revisits cannot count a physical cell twice. |
| 25. Area | Full ellipsoid Jacobian derived below, including correct radii when the pole/map axes are exchanged. Independent numerical cross products and quadrature verify it. |
| 26. Surface coverage | 100  x  sum(observed  x  J)/sum(J) over the entire +/-90 deg  x  360 deg modeled surface. Restricting observed latitude to +/-60 deg does not restrict the denominator. |
| 27. Defect percentage | Observed defect union / observed area; separately report observed defect / full modeled area. The latter is not an estimate of all unseen defects. No segmentation evidence yields no defect percentage. |
| 28. Grade gates | Complete requires >=80% area, >=350 deg supported longitude, configured rotation gate and max pair gap. Partial observed-area classes remain explicitly provisional. Uncertain identity and bad motion are ungraded. Class 1 <10%, Class 2 10..20%, Class 3 >20%; application policy, not paper validation. |

### Jacobian checked from first principles

Let c = cos(lambda), s = sin(lambda), C = cos(phi), S = sin(phi).

```
X_lambda = (-rx s C, ry c, -rz s S)
X_phi    = (-rx c S, 0, rz c C)
X_lambda  x  X_phi = (ry rz c^2 C, rx rz s c, rx ry c^2 S)
J = c sqrt((ry rz c C)^2 + (rx rz s)^2 + (rx ry c S)^2)
```

On -pi/2..pi/2, c >= 0. For a sphere all radii equal r, J = r^2 cos(lambda).
The full area is 4pi r^2. The +/-60 deg band contains sin(60 deg) = 0.866025403784
of that full surface, not 100%. The discretized sum includes all latitudes;
observed and defect sums apply masks to the same weights. Constant cell-angle
factors cancel in ratios. For the fitted cohort, independent quadrature gives
median band capacity 87.1653%, range 84.3482..88.0028%. Thus 80% is geometrically
possible for the ideal fitted band, while 85% is impossible for some shapes.

For the normal-cone feature selection, let theta be the source normal's angle
to camera +z and beta bound the norm of any searched rotation vector.
theta + beta < 90 deg guarantees a facing normal after every searched rotation.
Equivalent condition: nz/|n| > sin(beta). Dense beta is hypot(40,10) + 2 deg;
for a sphere the projected-radius bound is cos(beta), approximately 0.728.
Using the actual ellipsoid normal handles tilt. This is a conservative support
condition, not a photometric correctness certificate.

### Depth sign with the two searched rotation components

For camera pole p and angular velocity omega, dp/dt = omega cross p. With
omega_z=0, dp_y/dt=-omega_x p_z and dp_x/dt=omega_y p_z. The known rolling sign
therefore determines the depth sign from the derivative of the orthogonal
projected component. The projection is measured from ellipse eigenvectors and
sqrt((A^2-b^2)/(A^2-B^2)); its equivalent vector signs are kept continuous.

In contrast, b^2=B^2+(A^2-B^2)p_z^2 has derivative proportional to
p_z*(omega_x*p_y-omega_y*p_x). Using its sign as if only one component existed
can reverse the inferred depth even when the transverse rotation is inside the
configured limit. The new sign rule follows the actual searched domain. Camera
rotation around z would add another term, so it is explicitly excluded in this
profile. Finite silhouette sampling, irregular shape, covariance noise and
local derivative approximation remain uncertainties; this is not a proof of
accurate real pose. Synthetic mixed-component controls and the full real replay
quantify its behavior. Physical turns remain independently image-measured.

### Physical travel calculation

`calibration.json` integrates longitude-dependent area density using all fitted
shapes, with the full surface denominator. In an ideal aligned roller motion,
two endpoint views can add 90 deg supported longitude. Required measured travel
for 65/70/75/80/85% area has cohort medians 182.25/202.25/221.75/241.25/261.25 deg.
These are idealized area upper bounds, not recovered real rotation.

Median representative captured-view diameter is 174.56 pixels (IQR 157.36..190.17). Median continuous
fully-visible capture interval is 2.205 s (IQR 2.038..2.305). Ideal 80% area
needs median 18.47 rpm over each record's visible interval. Independently,
350 deg longitude needs at least 260 deg measured travel under the ideal +/-45 deg endpoint
assumption, approximately 19.65 rpm over a 2.205 s median interval.
Both assumptions require clean actual projections over the relevant latitudes.

Timing in these diagnostic travel/rpm calculations uses original frame-index
intervals and the reported average FPS. Rates are approximate; shutter/exposure
is not inferred from frame rate. No angular speed is assumed between images.

`physical_rotation.json` reports rpm only on accepted source/target intervals
and selected supported chains. Never extrapolate those rates across failed
windows. Registration failures cannot distinguish slow/stalled fruit from
missing texture evidence, nonrigid fruit shape, blur, lighting change or bounds
violations. No encoder, calibrated roller slip or manually tracked landmark
ground truth is available. This footage does not establish a defensible physical
upper bound on unobserved turning. A successful synthetic turn establishes
mathematical capability, not acquisition success on real fruit.

An acquisition check can be derived without guessing the recorded exposure:
central projected skin speed is approximately A*omega pixels/s. At the median
A=87.28 px and an ideal 20 rpm, one pixel of exposure smear corresponds to
about 5.47 ms (roughly 1/183 s). This is a prospective exposure target, not a
measurement of this video's shutter or proof that blur caused its failures.
The actual shutter, roller slip and independently measured physical rotation
are unavailable. Those measurements are needed to distinguish acquisition
blur/lighting, genuinely insufficient spin and the remaining shape/registration
error. Camera translation and failed matches cannot substitute for them.

Additional independent quadric rendering checks the hard perpendicular-pole
case, including nearly circular camera-facing projections. It recovers 356.631
of 360 degrees, worst pair geodesic error 0.07555 degrees, full longitude, and
87.4914% modeled area. The fitted map radii are approximately (65.074, 82.020,
82.020): the short axis lies on map x rather than map y, so the same Jacobian
predicts 87.4914% band capacity. This is a geometry-dependent limit, not a
change of denominator. The mixed-axis control gives 84.8862% area against
84.8863% fitted band capacity and worst pair error 0.09327 degrees. Both input
NPZ hashes, true matrices, renderer hash and exact active algorithm hash are
saved. These synthetic results do not enter real success counts.

## Quantitative scale and shape calibration

Across 406 eligible records, 388 fit oblate and 18 fit sphere under the existing
0.06 auto cutoff. Median flattening (A-B)/A is 0.1423 (IQR 0.0981..0.1920).
These silhouette statistics support retaining auto; the covariance masks are
not independent caliper measurements, so forcing an oblate model is unjustified.

For three representative captured views per record (first/middle/last), the
original central-ellipse selection at equivalent five-original-pixel Gaussian
scale gives the following medians. This isolates sampling scale; it is not a
claim that every final normal-cone feature survives target projection.

| Image scale | Candidate pixels | Top-3-percent points | Selected after 12-point floor / 160-point cap |
|---|---:|---:|---:|
| /4 | 585 | 18 | 18 |
| /3 | 1,044 | 32 | 32 |
| /2 | 2,365 | 71 | 71 |
| /1 | 9,499 | 285 | 160 |

The three sampled major diameters within each identity have a median relative
range of 5.820% (IQR 4.295..7.795%, maximum 17.614%). A rigid orthographic oblate
has a constant projected major semiaxis. These measured silhouettes depart from
that ideal; segmentation error, irregular shape, perspective and identity error
are confounded. `shape_stability.json` preserves every sampled frame/value.
This does not prove a perspective cause or justify inventing scale/pose motion.
It supports the explicit limitation on real fitted geometry and native warp
consistency. Only three samples were measured per record, so it is not an
estimate of every per-frame variation.

Quarter-size selected-point IQR is 15..21, versus 58..85 at half size.
More points do not establish correct matches; the real ablations and preserved
residual/inverse gates are required alongside this spatial calculation.

## Final active calibration

Values below are the production dense-upload profile; standalone defaults and
sparse live settings are kept for existing callers. `final_v4/settings.json`
stores **every** dataclass value. Axis/direction can be overridden by the
existing `FRUIT_ROTATION_AXIS`/`FRUIT_ROTATION_DIRECTION` environment variables.

| Setting | Dense uploaded video | Reason / limitation |
|---|---:|---|
| spheroid_type | auto | Preserve sphere/oblate model selection. |
| spherical_tolerance | 0.06 | Existing engineering ambiguity cutoff; not a paper constant. |
| rotation_axis | x | Existing image-axis mechanical setup; controls test both axes. |
| rotation_direction | +1 | Existing right-hand setup; controls test both signs. |
| max_pair_angle_deg | 40 | Test 20 deg/40 deg known turns and real pilot pair displacement; avoids extending rolling search beyond bounded overlap. Boundary remains rejection. |
| transverse_angle_deg | 10 | Narrower nuisance search follows expected roller-dominant motion and pilot accepted displacement. Out-of-range motion remains unavailable. |
| search_step_deg | 1 | Paper-style coarse high-pass grid. Native patterns use existing 2 deg initial grid and finer refinement. |
| image_downsample | 2 | Retain approximately 79..95 median-IQR fruit diameter pixels rather than 39..48; pilot evidence favors original texture detail. |
| highpass_sigma | 2.5 | Same original-image scale 5 px as 4 x 1.25. |
| native_point_preblur_sigma | 0 | Dense native feature-selection ablation preserved more peel detail; high-pass scale remains 5 px. Sparse stays 2. |
| point_percentile | 97 | Paper top 3% high-pass texture rule; preserve. |
| min_pair_points | 12 | Existing engineering floor; fallback picks 12 strongest valid points, cap 160. No lowering for low success. |
| min_pair_angle_deg | 1 | Existing direct estimator floor; final mapping keyframe uses stricter 3 deg dominant rolling threshold. |
| max_pair_error | 0.58 | Existing normalized residual gate preserved. Not calibrated real angular-error probability. |
| min_texture | 0.006 | Existing normalized green selected-RMS floor preserved. |
| minimum_view_rotation_deg | 20 | Trigger for successful coarse native recheck; not the mapping keyframe spacing. |
| maximum_view_index_gap | 2 | Permit one missing silhouette only if a new direct, independently verified image pair succeeds within bounded anchor window. Identity guards still run on every tracked frame. |
| max_latitude_deg | 60 | Paper fusion band; unseen pole caps remain in full denominator. |
| map_angle_step_deg | null -> 1/A rad | Paper-style equatorial pixel scale, not a coverage control. |
| minimum_surface_coverage | 0.80 | User requirement preserved. |
| minimum_rotation_coverage_deg | 0 | Existing setting; no assumption of a revolution. Independent area and longitude gates provide requirements. |
| minimum_longitude_coverage_deg | 350 | User requirement preserved. |
| maximum_pair_gap_deg | 40 | Consistent with dense rolling-search bound; bad pair remains ungraded. |
| relevant_ellipse_fraction | null | Use ellipsoid normal cone instead of undocumented fixed 0.66 ellipse. |
| relevant_visibility_margin_deg | 2 | Additional geometric overlap allowance for raster/silhouette uncertainty; not photometric confidence. |
| grabcut_iterations | 3 | Existing extraction cost/quality setting preserved. |
| select_rotating_views | true | Choose a supported ordered segment rather than combine disconnected failures. |
| adaptive_keyframes | true | Directly remeasure later candidate from accepted anchor, skipping unavailable tiny increments. |
| keyframe_candidate_spacing | 1 | Every frame is a candidate; fourth-frame-only pilots often overshot usable overlap. |
| keyframe_minimum_rotation_deg | 3 | Retain observable motion above stationary controls while avoiding the unsuccessful 8 deg pilot sparsification. Engineering spacing; not presumed exact angular accuracy. |
| maximum_keyframe_index_gap | 8 | Bound unknown interval to 0.267 s at this fps; fail rather than bridge distant images. Pilot-derived engineering limit, not universal camera calibration. |
| keyframe_inverse_tolerance_deg | 3 | Preserve strict existing native agreement tolerance, add independent checks to direct keyframes. |
| pole_pose_method | projected_trend | Orthogonal projected-pole derivative matches the searched two-component kinematics, including transverse motion; uses no spin magnitude. |
| pole_trend_window | 7 maximum | Up to 0.234 s; shrink to 5/3 samples when fit residual exceeds measured-noise tolerance. Slow and rapid turning-point controls pass. |
| pole_trend_sigma_multiple | 2 | Window-fit residual tolerance and derivative-sign uncertainty multiplier; ambiguous geometry uses nearest branch. |
| pole_pose_tolerance_deg | 5 | Existing constrained solver parameter; unused by active projected-trend path. |
| refine_small_motion | true | Preserve original-pixel remeasurement rather than accept coarse disappearance. |
| native_matching_cost | aligned_mad | Existing warped pattern matcher; original-green subpixel branch retained. |
| matching_cost | mad | Paper unnormalized objective for hypothesis selection. |
| batch_rotation_search | true | Vectorized equivalent objective; no search approximation. |
| bidirectional_matching | true | Joint direction objective plus independent consistency for keyframes. |
| texture_metric | selected_rms | Existing signed high-pass selected texture energy. |
| exclude_specular_texture | true | Existing HSV low-saturation/bright glare heuristic, expanded one local pixel; excludes features, not fills coverage. |
| enforce_uniform_pair_rotation | false | Variable observed rotations allowed; no constant-speed prior. |
| minimum_mask_box_fraction | 0.4 | Existing collapsed extraction guard, preserved. |
| minimum_silhouette_solidity | 0.95 | Existing occlusion/concavity guard, preserved. |
| class_1_max_defect_pct | 10 | Existing policy, exclusive upper boundary. |
| class_2_max_defect_pct | 20 | Existing policy, inclusive upper boundary. |
| defect_observations_complete | true in production | Deferred segmentation must execute for every selected mapping view; false in geometry replay. |
| grade_partial_maps | true in production | Preserve requested provisional observed-area grading; false in geometry replay. |

Important internal constants also remain explicit. Feature selection falls
back to 12 strongest valid points and caps at 160, limiting the search workload.
The native green comparison uses a two-original-pixel smoothing width; the
aligned descriptor has nine surface-warped samples at the preserved physical
filter scale. These are engineering descriptors, not exact paper formulas.
The HSV glare rule uses saturation <102 and value >90 on OpenCV's 0..255
channels, then a 3x3 feature-exclusion dilation; it can also exclude other
less-saturated skin and has no labelled glare truth. It never dilates coverage.
Fruit-chart ordering retains the existing 0.25-degree minimum and
max_pair_angle_deg+12 upper guard (52 degrees in dense mode). This is a
conservative chart-order plausibility guard, not a measured angular-speed bound
or a guarantee for every tilted fruit. Sparse adjacent selection retains its
historical 0.25-degree measurable increment floor; dense accepted keyframes
require 3 degrees. Identity and detector confidence settings remain unchanged.

Sparse live capture retains quarter-size/sigma 1.25, preblur 2, central ellipse
0.66, raw silhouette trend, adjacent selection, glare exclusion off,
rolling/transverse 55/20 deg and original-frame gap equal to capture stride (default
3). It retains 80%/350 deg requirements and provisional grading. No camera hardware
was available for a live acquisition accuracy test. Changes are activated when
the API imports the new sources; existing saved runs keep their recorded hashes.

The known 40-degree pair control uses a 45-degree search domain so truth is an
interior hypothesis. A true 40-degree turn at the active 40-degree rolling bound
is deliberately unavailable as a boundary optimum; it is not claimed accepted.
Transverse-edge estimates remain a calibration limitation: independent inverse
agreement does not certify that actual sideways motion stays inside the bound.

## Changed files and reproduction

Production: `algorithm.py` (selection, native remeasurement, pole derivative,
feature support, valid image sampling, revisits, completeness, diagnostics),
`main.py` (centralized dense/sparse settings). No detector, segmenter, identity,
TrackTrack model/configuration or frontend source was edited.

Controls/evidence: `test_dense_mapping.py`, `validate_dense_mapping.py`,
`analyze_dense_mapping.py`, `validate_dense_pipeline.py`,
`benchmark_dense_runtime.py`, `validation_resources.py`, `probe_dense_pairs.py`,
`probe_skin_registration.py`; the independent mixed-axis quadric renderer is
`diagnostics/mapping80/20261006_final/mixed_axis_control.py`. The independent KLT/3D reprojection probe was
less successful and was not adopted into production. All earlier trials are
preserved under distinct variant names, including stopped costly explorations.
Documentation: this file and `ALGORITHM_EXPLAINED.md`.

From the repository root, PowerShell (uses the existing local virtualenv):

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'backend/runtime/ultralytics-validation'
New-Item -ItemType Directory -Force -Path $env:YOLO_CONFIG_DIR | Out-Null
backend/venv/Scripts/python.exe -B backend/validate_dense_mapping.py prepare
backend/venv/Scripts/python.exe -B backend/validate_dense_mapping.py replay --variant baseline --source backend/diagnostics/mapping80/20261006_final/baseline_source/algorithm.py --workers 6
backend/venv/Scripts/python.exe -B backend/validate_dense_mapping.py replay --variant final_v4 --source backend/algorithm.py --settings backend/diagnostics/mapping80/20261006_final/final_v4_settings.json --workers 6
backend/venv/Scripts/python.exe -B backend/validate_dense_mapping.py compare --variants baseline final_v4
backend/venv/Scripts/python.exe -B backend/analyze_dense_mapping.py calibration
backend/venv/Scripts/python.exe -B backend/analyze_dense_mapping.py pose --variant final_v4
backend/venv/Scripts/python.exe -B backend/analyze_dense_mapping.py panels --variant final_v4
backend/venv/Scripts/python.exe -B backend/analyze_dense_mapping.py physical --variant final_v4
backend/venv/Scripts/python.exe -B backend/analyze_dense_mapping.py synthetic --variant final_v4
backend/venv/Scripts/python.exe -B backend/analyze_dense_mapping.py pole-control --variant final_v4
backend/venv/Scripts/python.exe -B backend/benchmark_dense_runtime.py --variant final_v4
backend/venv/Scripts/python.exe -B backend/validate_dense_pipeline.py --output backend/diagnostics/mapping80/20261006_final/integration_reproduce --full-video
Set-Location backend
venv/Scripts/python.exe -B -m unittest discover -s . -p 'test_*.py'
```

Variant source/settings mismatches are rejected; completed per-record results
resume from their cache. Use a new variant label to force a fresh replay. Inputs
and generated media are local; `.gitignore` excludes large NPZ/video/PNG files,
not the numerical JSON reports or source snapshots. The original video and model
weights must remain available at their recorded paths for fresh extraction and
full model integration. No synthetic defect/grade is issued for real replay.
Run model integration separately from CPU replay and other memory-heavy model
jobs. Earlier overlapped attempts exhausted machine memory; their failure JSON
and logs remain saved. Unit controls passed, and completed replay records were
retained and resumed with lower concurrency. A failed attempt is not counted as
completed end-to-end validation.

The unguarded `integration_complete/` attempt failed after 3364 s, with the last
saved progress at 520 frames: Windows could not commit a further 1.26 MiB NumPy array. Physical
RAM alone did not predict this failure. The fresh `integration_commit_guard/`
attempt requires 8 GiB physical and 12 GiB commit headroom and 2 GiB free disk before loading models,
and pauses before each frame, finished track, and rotation-cost allocation if
commit headroom falls below 4 GiB or free disk below 0.25 GiB. These are validation scheduling controls,
not calibration constants or production changes. They alter no input or numeric
decision. Wait durations and the guard source hash are recorded. Other user
processes and system paging settings are untouched.

<!-- FINAL_RESULTS -->

## Complete same-cohort before/after results

All 556 identity records remain in both runs; 406 have at least two usable views. Map statistics below are conditional on each variant producing a map. Unavailable maps remain in success-rate denominators.

| Metric | Baseline | Final |
|---|---:|---:|
| Tracker records | 556 | 556 |
| At least one usable view | 407 | 407 |
| Eligible (at least two usable views) | 406 | 406 |
| Generated maps | 383 | 330 |
| Observed area %, median (p25, p75) | 29.407 (25.857, 33.734) | 30.417 (25.908, 34.313) |
| Observed longitude deg, median (p25, p75) | 122.101 (107.831, 140.233) | 126.598 (108.889, 142.682) |
| Measured rolling deg, median (p25, p75) | 31.335 (17.277, 48.697) | 36.668 (18.047, 50.729) |
| Fruit-chart span deg, median (p25, p75) | 31.955 (17.780, 49.969) | 36.420 (18.837, 52.563) |
| Selected views, median (p25, p75) | 6.000 (4.000, 8.000) | 5.000 (3.000, 7.000) |
| Accepted residual, median (p25, p75) | 0.330 (0.215, 0.421) | 0.380 (0.288, 0.470) |
| Maps with at least 65% area | 0 | 0 |
| Maps with at least 70% area | 0 | 0 |
| Maps with at least 75% area | 0 | 0 |
| Maps with at least 80% area | 0 | 0 |
| Maps with at least 85% area | 0 | 0 |
| Maps with at least 350 deg longitude | 0 | 0 |
| Maps satisfying both 80% area and 350 deg longitude | 0 | 0 |
| 80% area success / all eligible, % | 0.000 | 0.000 |
| Both-target success / all eligible, % | 0.000 | 0.000 |

Maximum final modeled coverage is 51.945%. Of 329 common mapped records, 157 improved, 166 worsened and 6 were unchanged. Median paired change is -0.002 percentage points. There are 54 baseline-only maps and 1 final-only maps. This exposes regressions as well as gains; increased occupancy is not ground-truth accuracy.

[Machine-readable comparison](diagnostics/mapping80/20261006_final/comparison.json) and [full comparison](diagnostics/mapping80/20261006_final/COMPARISON.md) preserve IDs and distributions.

### Failure distributions

Baseline failures split adjacent sequences. Final candidate skips/rejections and final window splits are different events, so their raw totals cannot be interpreted as a direct percentage reduction in the same failure population. Residual/boundary messages that cannot be distinguished remain combined.

| Sequence-split reason | Baseline | Final |
|---|---:|---:|
| coarse_native_or_inverse_disagreement | 498 | 0 |
| direct_measurement_window_exceeded | 0 | 19 |
| direct_measurement_window_exhausted | 0 | 2356 |
| longitude_order_failure | 182 | 3 |
| missing_original_frames | 363 | 140 |
| motion_below_minimum | 18794 | 0 |
| pair_residual_or_boundary | 98 | 0 |

Final candidate rejection/skip counts:

```json
{
  "motion_below_minimum": 12154,
  "pair_residual_or_boundary": 7460,
  "coarse_native_or_inverse_disagreement": 1509,
  "measured_below_keyframe_minimum": 624
}
```

Window-ending candidate causes:

```json
{
  "pair_residual_or_boundary": 1616,
  "coarse_native_or_inverse_disagreement": 223,
  "motion_below_minimum": 464,
  "measured_below_keyframe_minimum": 53
}
```

Accepted-pair original-frame gap median 1.0, maximum 8.0; 1462 selected pairs. Complete raw diagnostics remain per record.

### Physical evidence

Accepted-chain rpm median 32.926, accepted-pair rpm median 37.788; median supported-chain interval 0.200 s. These are conditioned on accepted measurements. They cannot establish rpm during the rest of the visible interval or an upper bound on physical turning. The ideal geometry requires about 18.47 rpm for 80% area over the median fully-visible interval.

### Tests, full production integration and timing

All 202 backend tests passed in 243.678 s. Frontend build and lint passed; frontend sources were unchanged. Known 20/40-degree pairs, zero/noisy motion, full turns, mixed-axis pole geometry, Jacobian, visibility, seam/revisit fusion, defects, identity withholding and cancellation controls are included.

The frozen final textured full-turn sphere/oblate controls recovered 357.085/357.222 degrees with maximum pair rolling errors 0.0534/0.0516 degrees. Area is 86.6025/84.8985%, longitude 360 degrees, and a known 15% defect wedge gives 15.756/15.726% and Class 2. The independent changing-pole mixed-axis quadric renderer gave 84.8862% area, 360 deg longitude and maximum pair geodesic error 0.0933 deg. A perpendicular-pole control recovered 356.631 deg with worst pair error 0.0755 deg and 87.4914% area. Its short radius lies on map x, so the same Jacobian gives a different band capacity, 87.4914%. These are synthetic controls, separate from real success counts.

The full unmodified 795-frame original video completed through the actual production pipeline in 35189.2 s: 795 detector calls, 1757 deferred segmenter calls for 1757 selected views. Validation-only memory waits totaled 30454.2 s; this runtime is not a throughput benchmark. The scheduling guard changes no numerical decisions. Every integration check passed: per-frame detection, selected-view segmentation, deferred inference, active identity guards, uncertain identities ungraded, explicit provisional partial grades, unchanged weights and exact final algorithm source.

Full model rerun has a separate stochastic-mask/tracking denominator:

```json
{
  "tracker_records": 556,
  "records_with_one_usable_view": 407,
  "eligible_records": 406,
  "generated_maps": 327,
  "maps_surface80": 0,
  "maps_longitude350": 0,
  "complete_maps": 0,
  "observed_surface_pct": {
    "min": 20.25831513079842,
    "p25": 25.925515064753277,
    "median": 30.302290689481854,
    "p75": 34.210571955011716,
    "max": 55.25856023802789
  },
  "provisional_grades": 326,
  "uncertain_identities": 57
}
```

Model checks prove the execution contracts, not real detection, tracking, defect or grade accuracy.

Serial five-record seed-817 mapping benchmark, alternating order on identical loaded inputs: median baseline 7.529 s/record, final 9.652 s/record. This is mapping only; concurrent replay wall times are not used as a speedup claim.

Earlier source-mismatched and memory-exhausted integration attempts remain preserved and are excluded from successful validation. No live camera hardware test was possible.

### Visual evidence

[Representative real panels and IDs](diagnostics/mapping80/20261006_final/visuals.json), [paired distributions](diagnostics/mapping80/20261006_final/comparison_distribution.png), [ideal capture capacity](diagnostics/mapping80/20261006_final/coverage_capacity.png), [sphere control](diagnostics/mapping80/20261006_final/synthetic_final_v4/sphere/diagnostic_panel.png), [oblate control](diagnostics/mapping80/20261006_final/synthetic_final_v4/oblate/diagnostic_panel.png). [Actual full-model source masks and projected defect union](diagnostics/mapping80/20261006_final/integration_commit_guard/diagnostic_panel.png). Real panels show best, median, low and failed records. If no real map passes 80%, no high-coverage successful real panel is claimed.

## Final verdict

**A. Mathematics:** Jacobian, full denominator, lifting, normal visibility, matrix order, fusion and defect union pass independent controls. The projected-pole sign rule matches the two-component motion model. This does not establish exact real-fruit geometry.

**B. Camera/video calibration:** Spatial scale and temporal selection are now explicitly derived and tested. Overall real pose/registration accuracy is still unverified; persistent mask/pole instability and failed matching prevent declaring the camera pipeline fully calibrated.

**C. Physical feasibility:** The fitted band has enough modeled area for 80%; ideal median required travel is 241.25 deg and minimum speed about 18.47 rpm over the available interval. Typical fruit actually attaining that physical travel is not established by this footage.

**D. Actual 80% area success:** 0/406 eligible identity records = 0.000%.

**E. Both targets:** 0/406 = 0.000%.

**F. Remaining limitation:** Continuous reliable skin registration and stable real silhouette pose are not available for enough travel. The existing evidence cannot isolate actual spin/slip, exposure blur, changing illumination, irregular shape, perspective or camera-axis tumbling as the physical cause. No honest physical upper bound follows from failed registration. Independent landmark/encoder rotation, shutter/lighting measurements and pose labels are needed to separate those causes. The 80% operational target has not been achieved; the application preserves partial results and failures instead of reporting unseen skin.

[Consolidated exact-source evidence](diagnostics/mapping80/20261006_final/FINAL_EVIDENCE.json).
