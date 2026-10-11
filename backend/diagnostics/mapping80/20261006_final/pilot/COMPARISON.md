# Paired full-video mapping comparison

All records use identical frozen crops, masks, frame numbers and tracker identities. Geometry replay contains no defect inference or grades. Coverage is model-estimated; there are no independent real rotation labels.

| Metric | baseline | adaptive_only | adaptive_40_10 | early_hybrid |
|---|---:|---:|---:|---:|
| total_tracker_records | 32 | 32 | 32 | 32 |
| records_with_at_least_one_view | 32 | 32 | 32 | 32 |
| eligible_tracks | 29 | 29 | 29 | 29 |
| generated_maps | 25 | 4 | 2 | 13 |
| failure_reasons | {"pair_residual_or_boundary": 27, "motion_below_minimum": 429, "longitude_order_failure": 13, "coarse_native_or_inverse_disagreement": 77, "missing_original_frames": 29} | {"direct keyframe measurement window exhausted; no bridge assumed": 54, "missing_original_frames": 29} | {"direct keyframe measurement window exhausted; no bridge assumed": 57, "missing_original_frames": 29} | {"direct keyframe measurement window exhausted; no bridge assumed": 79, "missing_original_frames": 29} |
| candidate_rejections_or_skips | {} | {"waiting for candidate spacing; no rotation inferred": 265, "pair_residual_or_boundary": 161, "motion_below_minimum": 247, "coarse_native_or_inverse_disagreement": 130, "measured rotation below mapping keyframe minimum; not accumulated": 70} | {"waiting for candidate spacing; no rotation inferred": 265, "pair_residual_or_boundary": 439, "measured rotation below mapping keyframe minimum; not accumulated": 59, "motion_below_minimum": 98, "coarse_native_or_inverse_disagreement": 14} | {"pair_residual_or_boundary": 422, "measured rotation below mapping keyframe minimum; not accumulated": 72, "coarse_native_or_inverse_disagreement": 41, "motion_below_minimum": 275} |
| selected_views | 4.0000 (2.0000, 7.0000) | 2.0000 (2.0000, 2.0000) | 2.0000 (2.0000, 2.0000) | 4.0000 (2.0000, 6.0000) |
| observed_surface_pct | 26.3344 (21.9296, 32.4264) | 24.0442 (23.8909, 24.5876) | 22.5361 (21.9916, 23.0806) | 26.1687 (23.9953, 30.9978) |
| observed_longitude_deg | 114.2569 (92.0000, 142.6829) | 100.2505 (98.6203, 103.1669) | 102.1735 (102.0602, 102.2867) | 109.8656 (102.4000, 125.9341) |
| cumulative_rotation_deg | 19.6455 (2.1486, 47.1535) | 10.2660 (8.8990, 12.9797) | 12.4353 (12.3767, 12.4940) | 22.3117 (11.4768, 39.4678) |
| map_span_deg | 24.6852 (1.9679, 53.0365) | 10.1814 (8.8353, 12.8641) | 12.1725 (12.1221, 12.2229) | 19.7459 (12.2734, 35.8110) |
| pair_residual | 0.2971 (0.2005, 0.4107) | 0.3622 (0.3542, 0.3917) | 0.5112 (0.5046, 0.5177) | 0.2604 (0.1954, 0.3581) |
| seconds_per_eligible_track | 22.2911 (7.5930, 54.9386) | 68.5277 (11.0723, 188.5695) | 4.4836 (1.6223, 7.3231) | 11.1675 (3.8479, 26.5270) |
| maps_surface_at_least_65 | 0 | 0 | 0 | 0 |
| maps_surface_at_least_70 | 0 | 0 | 0 | 0 |
| maps_surface_at_least_75 | 0 | 0 | 0 | 0 |
| maps_surface_at_least_80 | 0 | 0 | 0 | 0 |
| maps_surface_at_least_85 | 0 | 0 | 0 | 0 |
| maps_longitude_at_least_350 | 0 | 0 | 0 | 0 |
| complete_maps | 0 | 0 | 0 | 0 |
| surface80_success_pct_of_eligible | 0.0 | 0.0 | 0.0 | 0.0 |
| complete_success_pct_of_eligible | 0.0 | 0.0 | 0.0 | 0.0 |
