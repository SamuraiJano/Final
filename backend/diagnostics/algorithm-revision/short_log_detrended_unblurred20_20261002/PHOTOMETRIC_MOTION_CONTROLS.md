# Photometric motion and observability controls

Completed 2026-10-02T20:30:46.343371+02:00. Source SHA256 `25d14c1be4321bc6d031eee948d48bd32785a4528d3f45a2eb078fef72a1be04`.

Overall control result: **FAIL**.

The unchanged four archived NPZ scenes are replayed using the actual fitted sphere, matcher, pose propagation and map selector. Settings profile: Quarter resolution4 paper MAD; native aligned_mad recheck below 20 degrees. Transverse bound 20.0 and rolling bound 20.0; all accuracy and exposure comparison limits unchanged. Full settings and a quarter-degree observable rolling minimum are recorded with each result. No production code is edited and no neural model is executed. Where green_mad is used, high-pass texture selection stays in place; matching samples green intensities and subtracts the median brightness difference.

| Scene | Returned / attempted pairs | Endpoint pose error, deg | Maximum landmark RMS, px | Control |
| --- | --- | --- | --- | --- |
| variable_xy_texture_a | 10/10 | 0.29238492590364257 | 0.32529177931573233 | PASS |
| variable_xy_texture_b | 10/10 | 0.06195867351812958 | 0.09120417726248173 | PASS |
| stationary_120_texture_a | 87/119 | unavailable | unavailable | FAIL |
| stationary_120_texture_b | 0/119 | unavailable | unavailable | PASS |

Moving criteria are unchanged: all ten pairs measured, endpoint pose error at most one degree and every landmark RMS at most one pixel. Each stationary scene contains 120 independently noisy images; its 119 dominant-turn measurements must all be unavailable, with no propagated endpoint and no map or grade. A helper maximum of zero refers only to the initial reference frame and does not score rejected motion as exactly zero.

The exposure control adds ten gray levels to every pixel of the second image of one known moving pair per texture, including the background. It verifies that no pixel saturates; silhouettes, poses and landmarks are unchanged. Before execution, rotation invariance is bounded by 0.01 degrees and residual invariance by 0.00001. Both original and shifted pairs must still satisfy one-degree/one-pixel known geometry.

| Exposure scene | Rotation change, deg | Residual change | Control |
| --- | --- | --- | --- |
| variable_xy_texture_a | 0.0876351985098503 | 0.0009276816054143945 | FAIL |
| variable_xy_texture_b | 0.00725105379237671 | 0.0029400498309268453 | FAIL |

Synthetic development results cover two ideal textures, perfect masks, a fixed analytical camera and short motion. They do not establish field, real segmentation, defect-grade or general complete-turn accuracy. Previous failed sources and controls remain frozen. Every input, settings record, execution source, figure and result is hashed.

![Moving geometry](observable_moving_accuracy.png)
![Stationary availability](stationary_observability.png)
![Exposure invariance](brightness_offset_invariance.png)
