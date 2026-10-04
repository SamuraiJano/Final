# Camera-fixed illumination: independent motion controls

Source SHA256 `9a5a3e13c8b9200958c678110640153022dbe8e59d4e3559ea1743ef579b5067`. Exact input manifest SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.

All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run with quarter-resolution paper MAD, native aligned_mad rechecks below 20 degrees, transverse bound 20 degrees, rolling search bound 20 degrees, unchanged 0.58 residual and 3-degree consensus gates. No models or production edits.

| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 1.0153340628868919 | 0.6891495523482721 | PASS |
| full_turn_x12_linear_additive_texture_b | 30/30 | 0.7566987699828218 | 0.5136189433121439 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 7.257497657845601 | 4.914972645626398 | FAIL |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 3.7762077332786332 | 2.561796365344053 | PASS |
| short_xy_linear_additive_texture_a | 10/10 | 0.6918075012654437 | 0.6306597712285794 | PASS |
| short_xy_linear_additive_texture_b | 10/10 | 0.17048493596845293 | 0.15555397035310672 | PASS |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 1.53861777322 | 1.402352108819089 | FAIL |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 0.07025736160188303 | 0.06419911659523998 | PASS |
| stationary_120_linear_additive_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_linear_additive_texture_b | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_b | 0/119 | unavailable | unavailable | PASS |

Full turns require all 30 measurements and 5-degree/5-pixel errors. Short x/y chains require all 10 measurements, endpoint 1-degree and maximum 1-pixel landmark errors. Stationary controls require all 119 pairs unavailable, null endpoints and no map/grade. Helper stationary zero maxima include only frame 0 scaffolding and are not scored zero motion.

Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.
