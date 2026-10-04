# Camera-fixed illumination: independent motion controls

Source SHA256 `f03b2ec019d7e3e5f366333d0c5cf2830ad56c57dd508fc0f866cc0e347e2bc7`. Exact input manifest SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.

All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run with quarter-resolution paper MAD, native green rechecks below 20 degrees, transverse bound 20 degrees, unchanged 0.58 residual and 3-degree consensus gates. No models or production edits.

| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 1.5218295478848676 | 1.0328100960851352 | PASS |
| full_turn_x12_linear_additive_texture_b | 30/30 | 1.2161170813907876 | 0.8254268821676705 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 11.163741635643094 | 7.547075980253173 | FAIL |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 7.212724151641872 | 4.821931083125981 | FAIL |
| short_xy_linear_additive_texture_a | 10/10 | 0.2317136479586416 | 0.2113958497472709 | PASS |
| short_xy_linear_additive_texture_b | 10/10 | 0.08605498909829747 | 0.07858836648426974 | PASS |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 0.6653071141574409 | 0.6052653246708473 | PASS |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 0.2671594952721944 | 0.24290235280532316 | PASS |
| stationary_120_linear_additive_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_linear_additive_texture_b | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_a | 1/119 | unavailable | unavailable | FAIL |
| stationary_120_lambertian_multiplicative_texture_b | 0/119 | unavailable | unavailable | PASS |

Full turns require all 30 measurements and 5-degree/5-pixel errors. Short x/y chains require all 10 measurements, endpoint 1-degree and maximum 1-pixel landmark errors. Stationary controls require all 119 pairs unavailable, null endpoints and no map/grade. Helper stationary zero maxima include only frame 0 scaffolding and are not scored zero motion.

Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.
