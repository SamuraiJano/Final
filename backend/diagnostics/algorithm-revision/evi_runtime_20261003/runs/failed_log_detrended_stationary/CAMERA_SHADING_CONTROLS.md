# Camera-fixed illumination: independent motion controls

Source SHA256 `25d14c1be4321bc6d031eee948d48bd32785a4528d3f45a2eb078fef72a1be04`. Exact input manifest SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.

All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run with quarter-resolution paper MAD, native aligned_mad rechecks below 20 degrees, transverse bound 20 degrees, rolling search bound 20 degrees, unchanged 0.58 residual and 3-degree consensus gates. No models or production edits.

| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 0.0636240357474335 | 0.04318710849884259 | PASS |
| full_turn_x12_linear_additive_texture_b | 30/30 | 0.050216759812404914 | 0.030826290395896176 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 0.0914016421485477 | 0.056605141845908154 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 0.04145797309272411 | 0.020009233560720388 | PASS |
| short_xy_linear_additive_texture_a | 10/10 | 0.4291111080002986 | 0.39135309640683275 | PASS |
| short_xy_linear_additive_texture_b | 10/10 | 0.09841238993818949 | 0.08988736871401626 | PASS |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 0.6510887742633208 | 0.5936246745109888 | PASS |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 0.07263597617755535 | 0.06621322909771925 | PASS |
| stationary_120_linear_additive_texture_a | 117/119 | unavailable | unavailable | FAIL |
| stationary_120_linear_additive_texture_b | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_a | 119/119 | 90.5545031596014 | 53.655332926514085 | FAIL |
| stationary_120_lambertian_multiplicative_texture_b | 27/119 | unavailable | unavailable | FAIL |

Full turns require all 30 measurements and 5-degree/5-pixel errors. Short x/y chains require all 10 measurements, endpoint 1-degree and maximum 1-pixel landmark errors. Stationary controls require all 119 pairs unavailable, null endpoints and no map/grade. Helper stationary zero maxima include only frame 0 scaffolding and are not scored zero motion.

Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.
