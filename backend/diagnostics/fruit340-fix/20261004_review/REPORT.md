# Fruit 340 rotation review and optional search patch

The frozen fixture is legacy 491, physically matched to raw 340 in the original video. The diagnostic review uses the saved algorithm from the most recent identity/mapping rerun. After the review, an optional bounded three-axis branch was added only to the production `_search_rotation` function at the root agent's request. The ordinary two-axis path remains unchanged. Coverage, grading, angle and residual gates were not relaxed. Signed searches below are diagnostic hypotheses, not accepted maps.

## Findings

1. **Coarse validation prevents a useful native check.** The four-times-shrunk MAD search rejects308→309 at residual0.617 before native aligned patches can run. Native aligned search at unchanged0.58 residual bound gives `[11.59,-8.22,0]` degrees, residual0.480, and independent forward/reverse inverse disagreement2.392°. This is a supportable rescue. Across13 coarse-rejected pairs in four fixtures, six pass the same angle/residual gates plus a3° inverse check:98 at65→66 and89→90;14 at2→3,10→11,13→14;340 at308→309. None of four coarse-rejected startup pairs for fruit1 pass. See `coarse_retry_review.json`.

2. **The assumed positive rolling direction clips measured backward motion to zero.** Forcing aligned patches in the same positive-only search domain does not fix most sampled zero cases. Allowing the opposite direction diagnostically gives consistent inverses and lower residuals:312→313 x=-1.157°, inverse disagreement0.362°;313→314 x=-1.320°, disagreement0.235°;316→317 x=-4°, disagreement0.568°. The same phenomenon appears at337,350 and360. This supports backward rocking or a remaining image/shape alignment error. It is not complete3D pose ground truth. Accumulating such absolute angles would falsely manufacture a full rotation. Keep signed pose and actual observed pixels when testing any future change.

3. **Missing rotation about the camera axis matters.** The production search fixes z=0. A diagnostic three-component native aligned search on308→309 gives `[12.5,-8.5,-6.5]` degrees, residual0.372 and inverse disagreement1.346°. It projects the manually identified freckle within1.081px of its target label, whose uncertainty is±2px. The visual-motion agent independently found SIFT/ORB consensus around z=-6..-7°. This is evidence for real tumbling outside the two-component model. It does not justify enabling an untested3D search globally.

4. **309→310 and310→311 are still unsupported by the current matcher.** The2D native aligned joint optimum for309→310 fails the0.58 gate at0.581; independent forward/reverse also disagree4.519°. A3D joint solution projects the freckle within1.129px, but its rolling component reaches the20° bound and inverse disagreement is17.725°. It remains unsafe to accept. For310→311, the currently accepted2D estimate has a manually measured11.69px freckle error; the3D joint estimate still has11.701px error. A low descriptor residual alone does not establish correct surface motion.

5. **Sample selection becomes dominated by glare when the useful feature leaves the central ROI.** At308/309/310,39/33/34 native points lie within5px of the identified freckle. At311 there are none within10px; the closest selected point is18.739px away. The freckle's normalized ellipse radius is0.715, outside the hard-coded0.66 texture ROI. Nearly all selected points in311 cluster on the central specular highlight. All sampled patches pass the mask/visibility checks, so those checks cannot reject this photometric distractor. The native sample visualization is `native_selected_points.png`.

6. **Aligned patch normalization cannot identify reflections as surface texture.** `_patch_response` removes a constant brightness offset and a local linear slope in the nine-sample patch coordinates, then scales by local contrast. These operations help illumination changes but cannot distinguish a camera-facing highlight from a physical fruit mark. The HSV glare rule marks none of the selected points in308–311, despite visible highlights: saturated orange reflections evade that rule. A spatially diverse, independently matched feature set is a better validation target than simply changing the residual threshold or patch contrast floor.

## Implementation recommendations

The narrowly supported production change is an optional native aligned retry after failed coarse validation, retaining the existing residual, nonzero motion and angle bounds and requiring separate forward/reverse estimates to agree. This improves observable pairs without claiming a complete340 map. A separate validation should reject already accepted glare fits when independent surface feature evidence contradicts them.

Before changing the full motion model, retain the two-sided and feature evidence above as regression controls. A future3D signed search needs known-pose stationary, reversal, wobble and brightness controls; coverage must continue to come from observed surface pixels. More accepted frames or greater summed rotation are not reconstruction accuracy.

## Reproduction

Run the three diagnostic scripts with `backend/venv/Scripts/python.exe -B`. They save only to this directory and load the frozen source at `backend/diagnostics/identity-mapping-check/20261004_scene_motion_v3/source/algorithm.py`.

- `review_rotation.py`: direct coarse/native, independent reverse, signed-direction probe.
- `review_coarse_failures.py`: all coarse-rejected pairs from four frozen fixtures.
- `review_three_axis.py`:3D search with2° coarse grid and1°,0.5°,0.25° local refinements, manual freckle reprojection.
- `review_points.py`: selected native samples and true-feature ROI check.

The manual labels are diagnostic image correspondences with±2px uncertainty. They were not used to tune or guide the search, and they do not supply full3D pose ground truth.

## Optional production branch verification

`_search_rotation(..., inplane_angle_deg=10.0)` enables a bounded camera-axis rotation search. The default value is 0 and executes the original two-component search. The branch reuses the exact existing scalar/batched objectives, bidirectional averaging, residual and dominant-axis gates. It rejects the new z boundary, uses a 2-degree coarse grid and three half-step local refinements, and permits a positive-Hessian sub-grid correction only within the local neighborhood and all configured bounds.

`check_search_patch.py` compares sixteen frozen native pair searches: every ordinary two-axis rotation array, residual or rejection message is bit-identical. The new three-axis branch returns308→309 `[12.5235,-8.6043,-6.6061]`, residual0.371253, independent inverse disagreement1.393492°. It refuses309→310 at the20-degree rolling boundary. Independent inverse disagreement for310→311 is3.361306° and for311→312 is13.943508°, so a caller requiring at most3° must reject them.

The search change compiled successfully. These local pair checks do not establish full-fruit coverage or final mapping accuracy. Evidence is saved in `search_patch_check.json`. The root agent subsequently completed the separate final validation: 94 software tests, fresh four-fixture mapping with CUDA defect inference, and known-area controls. Those integration results are recorded in the main fix report; this report preserves the isolated rotation and scope evidence.

## Public-author scope and performance assessment

An exploratory **55-degree** public-author profile run used frozen candidate2 source `d2a49090d0c8abc9d9d2785da05664e3ee677f70eb812994e86617cac927b164`. It was planned for 36 sequences and 497 labels but was **intentionally stopped at 24 completed sequences** after the root agent limited the final fix to dense recorded-video searches of at most 20 degrees. The partial run includes 15 mandarin and 9 orange sequences; no tomato sequence completed. A full 36-sequence/497-label accuracy result is not claimed, and the benchmark's aggregate label-prediction report was not persisted.

The partial wide search took 758.82 seconds for the completed sequences, versus 226.78 seconds for those same historical sequences, or **3.35 times the runtime**. An earlier measurement at 20 completed sequences was 3.19 times the historical runtime. Historical and current runs occurred at different times and the current run had concurrent workloads, so this is not an isolated timing benchmark. The additional wide three-axis work is nevertheless substantial and outside the validated recorded-video domain.

The partial experiment preserved 314 previously accepted pair results exactly and added 10 direct rescues. Their arrays and changed maps are retained in `partial_author_scope_assessment.json`. These experimental rescues are outside final production scope. The run directory has an explicit `PARTIAL_STATUS.json`, and no final `report.json`.

The **final scoped source** is `cf6c2dd19968f0c159a7e2ecb8d781eee0206a88d0bab104df8d087023706745`, frozen as `algorithm.final_scoped_author.snapshot.py`. Its caller requires `max_pair_angle_deg <= 20` before attempting the new retry. Every original public-profile setting matches, with only the added `grade_partial_maps=False` default. A 16-pair comparison against the original historical source `50bdd78e...` includes all 10 experimental rescues and 6 previously accepted pairs: fitted geometry and rotations/residuals or exact rejection messages are bit-identical, and instrumented calls observe **zero three-axis native retries** at the 55-degree setting. This documents the scope guard and samples the preserved paths; it is not a fresh final-source 497-label benchmark.

Evidence: `scoped_author_path_parity.json`, `partial_author_scope_assessment.json`, `author_profile_progress.json`, and the saved per-track results under `backend/diagnostics/authors-benchmark/runs/fruit340_native_3d_retry_author_profile_20261004`.
