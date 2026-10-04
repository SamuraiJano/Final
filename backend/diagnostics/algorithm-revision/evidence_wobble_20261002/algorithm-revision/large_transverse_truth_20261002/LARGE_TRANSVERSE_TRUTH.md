# Large transverse motion: independent geometry probe

Four independently rendered two-frame sphere scenes. Both texture patterns and both signs of a 13-degree transverse plus 11-degree rolling axis-angle vector. Analytical pose and projected landmarks score the actual estimator, never initialize it. The same scenes are compared at transverse bounds 10 and 20 with unchanged residual .58 and all other settings.

Criteria were fixed before execution: returned measurement, at most one degree pose error and one pixel projected landmark RMS. A rejected measurement remains unavailable, rather than being assigned zero error.

| Scene | Bound, deg | Returned pair | Pose error, deg | Landmark RMS, px | Control |
| --- | --- | --- | --- | --- | --- |
| texture_a_transverse_-13 | 10 | 1/1 | 3.353413836896729 | 2.9621093662153037 | FAIL |
| texture_a_transverse_-13 | 20 | 1/1 | 3.2655090826465263 | 2.8835658439986047 | FAIL |
| texture_a_transverse_+13 | 10 | 1/1 | 3.353413836896729 | 2.9621093662153046 | FAIL |
| texture_a_transverse_+13 | 20 | 1/1 | 0.7997139415929869 | 0.704140020987357 | PASS |
| texture_b_transverse_-13 | 10 | 1/1 | 3.038456364768792 | 2.697885879505305 | FAIL |
| texture_b_transverse_-13 | 20 | 1/1 | 0.27804433052117505 | 0.2510345118810975 | PASS |
| texture_b_transverse_+13 | 10 | 1/1 | 2.995400653219356 | 2.6707479825062843 | FAIL |
| texture_b_transverse_+13 | 20 | 1/1 | 0.9515723342577864 | 0.8370330303338178 | PASS |

A new diagnostic probe for larger transverse motion. Ideal sphere, perfect masks, no exposure change. Does not establish field accuracy or change the prior accepted controls.

![Independent geometry errors](large_transverse_truth.png)
