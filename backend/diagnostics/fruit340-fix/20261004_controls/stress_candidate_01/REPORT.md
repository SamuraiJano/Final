# Fruit 340 correction: independent motion controls

Replay pre-existing frozen images, exact masks and independent analytical pose/landmark truth through both frozen estimator sources. Native aligned_mad, quarter-resolution coarse search, bidirectional matching and rolling/transverse bounds 20 degrees. Existing helper acceptance thresholds remain fixed. Failed chains are never interpolated; per-pair truth errors are additionally scored independently after chain failure.

Synthetic development software controls only: perfect sphere masks and known orthographic projection, no real fruit ground truth, no detector or defect segmentation inference, no occlusion or glare. Full-turn maps have explicitly known all-clear labels to test map execution. A pass does not establish real fruit pose, surface or grading accuracy.

| Known scene | Baseline measured | Candidate measured | Baseline control | Candidate control | Changed pairs |
| --- | --- | --- | --- | --- | --- |
| moving_x6_log_light_reversal_g0.006_texture_a | 2/2 | 2/2 | PASS | PASS | 0 |
| moving_x6_log_light_reversal_g0.012_texture_a | 2/2 | 2/2 | PASS | PASS | 0 |
| stationary_log_light_reversal_g0.006_texture_a | 0/2 | 0/2 | PASS | PASS | 0 |
| stationary_log_light_reversal_g0.012_texture_a | 0/2 | 0/2 | PASS | PASS | 0 |
| moving_x6_log_light_reversal_g0.006_texture_b | 2/2 | 2/2 | PASS | PASS | 0 |
| moving_x6_log_light_reversal_g0.012_texture_b | 2/2 | 2/2 | PASS | PASS | 0 |
| stationary_log_light_reversal_g0.006_texture_b | 0/2 | 0/2 | PASS | PASS | 0 |
| stationary_log_light_reversal_g0.012_texture_b | 1/2 | 1/2 | FAIL | FAIL | 0 |
