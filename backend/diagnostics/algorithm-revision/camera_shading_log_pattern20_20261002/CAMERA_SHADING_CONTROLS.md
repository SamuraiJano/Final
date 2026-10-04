# Camera-fixed illumination: independent motion controls

Source SHA256 `1cfbadc5627c57ba2a36f1319598272ec01bc542eac9b796239de45370627ee5`. Exact input manifest SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.

All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run with quarter-resolution paper MAD, native aligned_mad rechecks below 20 degrees, transverse bound 20 degrees, rolling search bound 20 degrees, unchanged 0.58 residual and 3-degree consensus gates. No models or production edits.

| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 1.044617015467678 | 0.7090333205027872 | PASS |
| full_turn_x12_linear_additive_texture_b | 30/30 | 0.819030665748483 | 0.5559222233744571 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 7.406101749368426 | 5.01533257214098 | FAIL |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 3.6916264989911243 | 2.5044705880070985 | PASS |
| short_xy_linear_additive_texture_a | 10/10 | 0.6988828402487601 | 0.6371107289189809 | PASS |
| short_xy_linear_additive_texture_b | 10/10 | 0.16017985018588915 | 0.14616435496367294 | PASS |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 1.5398340680285991 | 1.4034623560599766 | FAIL |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 0.07886892688159138 | 0.07221102454156432 | PASS |
| stationary_120_linear_additive_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_linear_additive_texture_b | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_b | 0/119 | unavailable | unavailable | PASS |

Full turns require all 30 measurements and 5-degree/5-pixel errors. Short x/y chains require all 10 measurements, endpoint 1-degree and maximum 1-pixel landmark errors. Stationary controls require all 119 pairs unavailable, null endpoints and no map/grade. Helper stationary zero maxima include only frame 0 scaffolding and are not scored zero motion.

Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.
