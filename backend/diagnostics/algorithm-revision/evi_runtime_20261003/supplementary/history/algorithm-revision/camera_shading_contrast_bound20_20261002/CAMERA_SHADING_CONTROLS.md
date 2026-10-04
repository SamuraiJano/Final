# Camera-fixed illumination: independent motion controls

Source SHA256 `d3bf284a501351cf98a101a13f588f0b7d1ea02cb72774b2a9bb49397730d651`. Exact input manifest SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.

All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run with quarter-resolution paper MAD, native aligned_mad rechecks below 20 degrees, transverse bound 20 degrees, rolling search bound 20 degrees, unchanged 0.58 residual and 3-degree consensus gates. No models or production edits.

| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 1.0265330611157373 | 0.69673244005266 | PASS |
| full_turn_x12_linear_additive_texture_b | 30/30 | 0.8361441652692336 | 0.567535460166587 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 8.387329098743892 | 5.676123194085582 | FAIL |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 3.670025934499673 | 2.4898367254643596 | PASS |
| short_xy_linear_additive_texture_a | 10/10 | 0.20804572106528552 | 0.18984725299530084 | PASS |
| short_xy_linear_additive_texture_b | 10/10 | 0.1321135040547784 | 0.12058560069687882 | PASS |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 0.36403597658170134 | 0.33205354924010316 | PASS |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 0.10849329369630713 | 0.09901745132625428 | PASS |
| stationary_120_linear_additive_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_linear_additive_texture_b | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_b | 0/119 | unavailable | unavailable | PASS |

Full turns require all 30 measurements and 5-degree/5-pixel errors. Short x/y chains require all 10 measurements, endpoint 1-degree and maximum 1-pixel landmark errors. Stationary controls require all 119 pairs unavailable, null endpoints and no map/grade. Helper stationary zero maxima include only frame 0 scaffolding and are not scored zero motion.

Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.
