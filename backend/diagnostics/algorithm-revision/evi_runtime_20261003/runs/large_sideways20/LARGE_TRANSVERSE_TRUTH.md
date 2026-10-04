# Large transverse motion: independent geometry probe

Four independently rendered two-frame sphere scenes. Both texture patterns and both signs of a 13-degree transverse plus 11-degree rolling axis-angle vector. Analytical pose and projected landmarks score the actual estimator, never initialize it. The same scenes are compared at transverse bounds 10 and 20 with unchanged residual .58 and all other settings.

Criteria recorded before this replay: returned measurement, at most 1 degrees pose error and 1 pixels projected landmark RMS. A rejected measurement remains unavailable, rather than being assigned zero error.

The original one-degree/one-pixel limits remain fixed; any replay preserves them.

| Scene | Bound, deg | Returned pair | Pose error, deg | Landmark RMS, px | Control |
| --- | --- | --- | --- | --- | --- |
| texture_a_transverse_-13 | 10 | 0/1 | unavailable | unavailable | FAIL |
| texture_a_transverse_-13 | 20 | 1/1 | 0.0 | 0.003070045416960688 | PASS |
| texture_a_transverse_+13 | 10 | 1/1 | 3.353413836896729 | 2.9621093662153046 | FAIL |
| texture_a_transverse_+13 | 20 | 1/1 | 0.007290541693372202 | 0.00943384735666366 | PASS |
| texture_b_transverse_-13 | 10 | 1/1 | 3.038456364768792 | 2.697885879505305 | FAIL |
| texture_b_transverse_-13 | 20 | 1/1 | 0.0028689680939879077 | 0.005374462832144966 | PASS |
| texture_b_transverse_+13 | 10 | 1/1 | 3.0348796608517223 | 2.7177458721567147 | FAIL |
| texture_b_transverse_+13 | 20 | 1/1 | 0.005105042265145527 | 0.007087492643223005 | PASS |

A new diagnostic probe for larger transverse motion. Ideal sphere, perfect masks, no exposure change. Does not establish field accuracy or change the prior accepted controls.

![Independent geometry errors](large_transverse_truth.png)
