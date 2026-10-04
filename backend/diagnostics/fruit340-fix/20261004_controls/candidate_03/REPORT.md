# Fruit 340 correction: independent motion controls

Replay pre-existing frozen images, exact masks and independent analytical pose/landmark truth through both frozen estimator sources. Native aligned_mad, quarter-resolution coarse search, bidirectional matching and rolling/transverse bounds 20 degrees. Existing helper acceptance thresholds remain fixed. Failed chains are never interpolated; per-pair truth errors are additionally scored independently after chain failure.

Baseline measurements reused from `backend\diagnostics\fruit340-fix\20261004_controls\candidate_01\report.json` after verifying the exact source, analytical validators, pixels and acceptance references. Candidate measurements rerun for every listed case.

Synthetic development software controls only: perfect sphere masks and known orthographic projection, no real fruit ground truth, no detector or defect segmentation inference, no occlusion or glare. Full-turn maps have explicitly known all-clear labels to test map execution. A pass does not establish real fruit pose, surface or grading accuracy.

| Known scene | Baseline measured | Candidate measured | Baseline control | Candidate control | Changed pairs |
| --- | --- | --- | --- | --- | --- |
| full_turn_x12_linear_additive_texture_a | 30/30 | 30/30 | PASS | PASS | 0 |
| full_turn_x12_linear_additive_texture_b | 30/30 | 30/30 | PASS | PASS | 0 |
| full_turn_x12_lambertian_multiplicative_texture_a | 30/30 | 30/30 | PASS | PASS | 0 |
| full_turn_x12_lambertian_multiplicative_texture_b | 30/30 | 30/30 | PASS | PASS | 0 |
| short_xy_linear_additive_texture_a | 10/10 | 10/10 | PASS | PASS | 0 |
| short_xy_linear_additive_texture_b | 10/10 | 10/10 | PASS | PASS | 0 |
| short_xy_lambertian_multiplicative_texture_a | 10/10 | 10/10 | PASS | PASS | 0 |
| short_xy_lambertian_multiplicative_texture_b | 10/10 | 10/10 | PASS | PASS | 0 |
| stationary_120_linear_additive_texture_a | 0/119 | 0/119 | PASS | PASS | 0 |
| stationary_120_linear_additive_texture_b | 0/119 | 0/119 | PASS | PASS | 0 |
| stationary_120_lambertian_multiplicative_texture_a | 0/119 | 0/119 | PASS | PASS | 0 |
| stationary_120_lambertian_multiplicative_texture_b | 0/119 | 0/119 | PASS | PASS | 0 |
| variable_xy_texture_a | 10/10 | 10/10 | PASS | PASS | 0 |
| variable_xy_texture_b | 10/10 | 10/10 | PASS | PASS | 0 |
| stationary_120_texture_a | 0/119 | 0/119 | PASS | PASS | 0 |
| stationary_120_texture_b | 0/119 | 0/119 | PASS | PASS | 0 |
| variable_small_motion | 10/10 | 10/10 | PASS | PASS | 0 |
| stationary_pixel_noise | 0/19 | 0/19 | PASS | PASS | 0 |
| uniform_stationary | 0/19 | 0/19 | PASS | PASS | 0 |
