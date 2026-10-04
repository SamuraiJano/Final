# Camera-fixed illumination: independent motion controls

Source SHA256 `c5c7e7292af1ef67eeca476ed99389b96f8aa17fd2d3814cbe7934934be2b911`. Exact input manifest SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.

All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run with quarter-resolution paper MAD, native aligned_mad rechecks below 20 degrees, transverse bound 20 degrees, rolling search bound 20 degrees, unchanged 0.58 residual and 3-degree consensus gates. No models or production edits.

| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 0.1733328850704081 | 0.11764248848931078 | PASS |
| full_turn_x12_linear_additive_texture_b | 30/30 | 0.03484564759322293 | 0.02125731812658928 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 5.254898973886953 | 3.562256292993178 | FAIL |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 2.3490161757591066 | 1.5941175211337073 | PASS |
| short_xy_linear_additive_texture_a | 10/10 | 0.6537836852414117 | 0.5960233077460217 | PASS |
| short_xy_linear_additive_texture_b | 10/10 | 0.1663696116908372 | 0.15179771047854645 | PASS |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 1.505871723053788 | 1.3725149077507037 | FAIL |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 0.06789051472132179 | 0.062073313927137504 | PASS |
| stationary_120_linear_additive_texture_a | 29/119 | unavailable | unavailable | FAIL |
| stationary_120_linear_additive_texture_b | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_a | 119/119 | 69.83099237637076 | 49.680531863067195 | FAIL |
| stationary_120_lambertian_multiplicative_texture_b | 0/119 | unavailable | unavailable | PASS |

Full turns require all 30 measurements and 5-degree/5-pixel errors. Short x/y chains require all 10 measurements, endpoint 1-degree and maximum 1-pixel landmark errors. Stationary controls require all 119 pairs unavailable, null endpoints and no map/grade. Helper stationary zero maxima include only frame 0 scaffolding and are not scored zero motion.

Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.
