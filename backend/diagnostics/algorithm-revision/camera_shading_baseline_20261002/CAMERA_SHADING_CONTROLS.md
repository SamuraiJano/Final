# Camera-fixed illumination: independent motion controls

Source SHA256 `951b55a4912d3147d349282846e2e02d20159a410b6bb2e8fdd4ab4dd3abea2d`. Exact input manifest SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.

All scenes and limits were frozen before estimation. The actual estimator, spheroid fit, pose composition and mapper run with quarter-resolution paper MAD, native green rechecks below20degrees, transverse bound20degrees, unchanged .58 residual and3degree consensus gates. No models or production edits.

| Known scene | Returned / attempted | Maximum pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 2.097712162819 | 1.4234512223842275 | PASS |
| full_turn_x12_linear_additive_texture_b | 30/30 | 0.7923990659770532 | 0.5378486337613464 | PASS |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 14.03161977758782 | 9.460680061667947 | FAIL |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 9.694349244620325 | 6.555355106394605 | FAIL |
| short_xy_linear_additive_texture_a | 10/10 | 0.25548400913118 | 0.23268830415208092 | PASS |
| short_xy_linear_additive_texture_b | 10/10 | 0.09538561088667188 | 0.08709994842609695 | PASS |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 0.26537988050653943 | 0.24210865630791742 | PASS |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 0.3018905973763493 | 0.2743792744240039 | PASS |
| stationary_120_linear_additive_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_linear_additive_texture_b | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_a | 0/119 | unavailable | unavailable | PASS |
| stationary_120_lambertian_multiplicative_texture_b | 0/119 | unavailable | unavailable | PASS |

Full turns require all30measurements and5degree/5pixel errors. Short x/y chains require all10measurements, endpoint1degree and maximum1pixel landmark errors. Stationary controls require all119pairs unavailable, null endpoints and no map/grade. Helper stationary zero maxima include only frame0 scaffolding and are not scored zero motion.

Independent ideal synthetic development controls, not held-out real fruit. Perfect masks, fixed sphere/camera, no occlusion/specular glare/perspective/translation. The plane is additive and exact; Lambertian illumination is multiplicative and curved, deliberately outside that compensation model. Complete-turn scoring uses36 independent body landmarks only when front visible; short motion uses6 always-visible landmarks.
