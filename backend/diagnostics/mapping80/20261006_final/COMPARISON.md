# Paired full-video mapping comparison

All records use identical frozen crops, masks, frame numbers and tracker identities. Geometry replay contains no defect inference or grades. Coverage is model-estimated; there are no independent real rotation labels.

| Metric | baseline | final_v4 |
|---|---:|---:|
| total_tracker_records | 556 | 556 |
| records_with_at_least_one_view | 407 | 407 |
| eligible_tracks | 406 | 406 |
| generated_maps | 383 | 330 |
| failure_reasons | {"motion_below_minimum": 18794, "longitude_order_failure": 182, "missing_original_frames": 363, "pair_residual_or_boundary": 98, "coarse_native_or_inverse_disagreement": 498} | {"direct_measurement_window_exhausted": 2356, "direct_measurement_window_exceeded": 19, "missing_original_frames": 140, "longitude_order_failure": 3} |
| candidate_rejections_or_skips | {} | {"motion_below_minimum": 12154, "pair_residual_or_boundary": 7460, "coarse_native_or_inverse_disagreement": 1509, "measured_below_keyframe_minimum": 624} |
| selected_views | 6.0000 (4.0000, 8.0000) | 5.0000 (3.0000, 7.0000) |
| observed_surface_pct | 29.4072 (25.8568, 33.7338) | 30.4166 (25.9077, 34.3129) |
| observed_longitude_deg | 122.1007 (107.8310, 140.2328) | 126.5984 (108.8891, 142.6823) |
| cumulative_rotation_deg | 31.3351 (17.2765, 48.6967) | 36.6685 (18.0467, 50.7290) |
| map_span_deg | 31.9548 (17.7803, 49.9694) | 36.4203 (18.8373, 52.5634) |
| pair_residual | 0.3298 (0.2154, 0.4205) | 0.3797 (0.2879, 0.4703) |
| seconds_per_eligible_track | 30.1547 (21.6198, 43.1649) | 13.9023 (11.5794, 17.5180) |
| failed_track_reasons | {"no reliable rotating sequence; inspect motion, reflections and fruit masks": 23} | {"no reliable rotating sequence; inspect motion, reflections and fruit masks": 76} |
| measured_zero_hypotheses | 17128 | 11292 |
| selected_pair_count | 1875 | 1462 |
| pair_measurement_attempts | 1875 | 23209 |
| accepted_pair_frame_gap | 1.0000 (1.0000, 1.0000) | 1.0000 (1.0000, 1.0000) |
| window_ending_candidate_failures | {} | {"pair_residual_or_boundary": 1616, "coarse_native_or_inverse_disagreement": 223, "motion_below_minimum": 464, "measured_below_keyframe_minimum": 53} |
| maps_surface_at_least_65 | 0 | 0 |
| maps_surface_at_least_70 | 0 | 0 |
| maps_surface_at_least_75 | 0 | 0 |
| maps_surface_at_least_80 | 0 | 0 |
| maps_surface_at_least_85 | 0 | 0 |
| maps_longitude_at_least_350 | 0 | 0 |
| complete_maps | 0 | 0 |
| surface80_success_pct_of_eligible | 0.0 | 0.0 |
| complete_success_pct_of_eligible | 0.0 | 0.0 |

## Common mapped records

The above conditional map medians have different map denominators. The common-record comparison below exposes improvements and regressions; unmapped identities remain in each variant's eligible success denominator.

```json
{
  "common_mapped_records": 329,
  "before_surface": {
    "min": 17.521852296336874,
    "p25": 27.166751777490006,
    "median": 30.211702083847825,
    "p75": 34.64678743973376,
    "max": 49.40415823270592
  },
  "after_surface": {
    "min": 17.72670120670681,
    "p25": 25.923890824885863,
    "median": 30.438475248045098,
    "p75": 34.31815953737695,
    "max": 51.945271990872264
  },
  "surface_change_percentage_points": {
    "min": -22.77350319823505,
    "p25": -2.305594559109675,
    "median": -0.0023936351876550077,
    "p75": 2.4310352703237044,
    "max": 23.014212666388723
  },
  "improved": 157,
  "worse": 166,
  "unchanged": 6,
  "baseline_only_mapped_records": [
    1,
    4,
    7,
    8,
    11,
    14,
    16,
    17,
    18,
    20,
    21,
    24,
    25,
    27,
    30,
    37,
    38,
    43,
    44,
    73,
    86,
    90,
    107,
    126,
    133,
    142,
    157,
    180,
    236,
    242,
    243,
    275,
    276,
    286,
    311,
    313,
    335,
    336,
    350,
    358,
    364,
    397,
    407,
    418,
    420,
    441,
    447,
    459,
    473,
    498,
    517,
    525,
    536,
    539
  ],
  "final_only_mapped_records": [
    96
  ]
}
```

Recorded replay durations reflect different worker concurrency and machine load. They are not a fair speed comparison. The separate serial_runtime.json benchmark uses the same loaded inputs, alternating order and no saved-result cache.
