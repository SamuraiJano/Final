# Camera-fixed illumination: independent motion controls

Source SHA256 `bf25b9d4a9ed261d1d94ced7e89d557a8972fced65174c410743885c95529e7b`. Exact input manifest SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.

All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run with quarter-resolution paper MAD, native aligned_mad rechecks below 20 degrees, transverse bound 20 degrees, rolling search bound 20 degrees, unchanged 0.58 residual and 3-degree consensus gates. No models or production edits.

| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 3.6552084563818843 | 2.479798826154783 | PASS |
| full_turn_x12_linear_additive_texture_b | 30/30 | 2.809834911498793 | 1.9066710236214353 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 11.16272949394714 | 7.539925869354936 | FAIL |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 6.8647325425300485 | 4.651398643542173 | FAIL |
| short_xy_linear_additive_texture_a | 10/10 | 0.20217499293037502 | 0.18450704702654605 | PASS |
| short_xy_linear_additive_texture_b | 10/10 | 0.09890117488311409 | 0.09078595950920791 | PASS |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 1.1096309622428722 | 1.0113067108770644 | FAIL |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 0.19599852215981536 | 0.17859006867603816 | PASS |
| stationary_120_linear_additive_texture_a | 1/119 | unavailable | unavailable | FAIL |
| stationary_120_linear_additive_texture_b | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_a | 4/119 | unavailable | unavailable | FAIL |
| stationary_120_lambertian_multiplicative_texture_b | 0/119 | unavailable | unavailable | PASS |

Full turns require all 30 measurements and 5-degree/5-pixel errors. Short x/y chains require all 10 measurements, endpoint 1-degree and maximum 1-pixel landmark errors. Stationary controls require all 119 pairs unavailable, null endpoints and no map/grade. Helper stationary zero maxima include only frame 0 scaffolding and are not scored zero motion.

Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.
