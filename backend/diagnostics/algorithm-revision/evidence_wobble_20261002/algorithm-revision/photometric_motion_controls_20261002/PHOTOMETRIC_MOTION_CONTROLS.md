# Isolated original-green photometric controls

Completed 2026-10-02T14:28:37.830963+02:00. Source SHA256 `46a46f9aac7c2f8f57114786f11df62e2833142f352e0c2a49eac2bdb1cd6b89`.

Overall control result: **FAIL**.

The unchanged four archived NPZ scenes are replayed using the actual fitted sphere, matcher, pose propagation and map selector. Original-resolution images, high-pass sigma 5, green_mad, bidirectional matching and a quarter-degree observable rolling minimum are recorded with each result. No production code is edited and no neural model is executed. High-pass texture selection stays in place; image matching samples the original green channel and subtracts the median brightness difference.

| Scene | Returned / attempted pairs | Endpoint pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| variable_xy_texture_a | 10/10 | 0.04097183589098934 | 0.06792409961133793 | PASS |
| variable_xy_texture_b | 10/10 | 0.04836583560188879 | 0.07909542545249987 | PASS |
| stationary_120_texture_a | 83/119 | unavailable | unavailable | FAIL |
| stationary_120_texture_b | 0/119 | unavailable | unavailable | PASS |

Moving criteria are unchanged: all ten pairs measured, endpoint pose error at most one degree and every landmark RMS at most one pixel. Each stationary scene contains 120 independently noisy images; its 119 dominant-turn measurements must all be unavailable, with no propagated endpoint and no map or grade. A helper maximum of zero refers only to the initial reference frame and does not score rejected motion as exactly zero.

The exposure control adds ten gray levels to every pixel of the second image of one known moving pair per texture, including the background. It verifies that no pixel saturates; silhouettes, poses and landmarks are unchanged. Before execution, rotation invariance is bounded by 0.01 degrees and residual invariance by 0.00001. Both original and shifted pairs must still satisfy one-degree/one-pixel known geometry.

| Exposure scene | Rotation change, deg | Residual change | Control |
| --- | --- | --- | --- |
| variable_xy_texture_a | 0.0 | 0.0 | PASS |
| variable_xy_texture_b | 0.0 | 1.7214244639116028e-09 | PASS |

Synthetic development results cover two ideal textures, perfect masks, a fixed analytical camera and short motion. They do not establish field, real segmentation, defect-grade or general complete-turn accuracy. Previous failed sources and controls remain frozen. Every input, settings record, execution source, figure and result is hashed.

![Moving geometry](observable_moving_accuracy.png)
![Stationary availability](stationary_observability.png)
![Exposure invariance](brightness_offset_invariance.png)
