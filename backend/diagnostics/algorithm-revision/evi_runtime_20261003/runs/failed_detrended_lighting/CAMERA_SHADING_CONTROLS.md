# Camera-fixed illumination: independent motion controls

Source SHA256 `6f2c56ac6edbdc3cc72fecd995055f01a6690113c54115c304b7e29595c20961`. Exact input manifest SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.

All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run with quarter-resolution paper MAD, native aligned_mad rechecks below 20 degrees, transverse bound 20 degrees, rolling search bound 20 degrees, unchanged 0.58 residual and 3-degree consensus gates. No models or production edits.

| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 3.6554174131934785 | 2.4799572455985492 | PASS |
| full_turn_x12_linear_additive_texture_b | 30/30 | 3.271786626471521 | 2.219969744959767 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 6.676572983862286 | 4.524457051949303 | FAIL |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 5.25311365114571 | 3.561941131658298 | FAIL |
| short_xy_linear_additive_texture_a | 10/10 | 0.24361620727738906 | 0.22227726706471373 | PASS |
| short_xy_linear_additive_texture_b | 10/10 | 0.10527296123724268 | 0.09607653809474202 | PASS |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 1.3879754252226268 | 1.2649296230642981 | FAIL |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 0.13600869165584697 | 0.12404471397408462 | PASS |
| stationary_120_linear_additive_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_linear_additive_texture_b | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_b | 0/119 | unavailable | unavailable | PASS |

Full turns require all 30 measurements and 5-degree/5-pixel errors. Short x/y chains require all 10 measurements, endpoint 1-degree and maximum 1-pixel landmark errors. Stationary controls require all 119 pairs unavailable, null endpoints and no map/grade. Helper stationary zero maxima include only frame 0 scaffolding and are not scored zero motion.

Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.
