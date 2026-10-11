# Complete frozen pilot ablations

Separate earlier video; all 32 saved identity records, 29 eligible, 938 frozen crops. These results do not enter the 556-record headline cohort.

| Variant | Maps | Median area % | P75 area % | Max area % | Area >=80% |
|---|---:|---:|---:|---:|---:|
| baseline | 25 | 26.334 | 32.426 | 47.669 | 0 |
| adaptive_only | 4 | 24.044 | 24.588 | 26.003 | 0 |
| adaptive_40_10 | 2 | 22.536 | 23.081 | 23.625 | 0 |
| early_hybrid | 13 | 26.169 | 30.998 | 43.334 | 0 |
| early_native | 17 | 28.801 | 35.081 | 48.780 | 0 |
| early_retry | 17 | 31.017 | 35.081 | 48.780 | 0 |
| unblurred_points | 19 | 26.883 | 36.563 | 62.434 | 0 |
| bounded_missing | 19 | 26.883 | 36.563 | 62.434 | 0 |
| stable_geometry | 19 | 26.883 | 36.415 | 62.434 | 0 |
| native_green_fallback | 19 | 26.883 | 36.415 | 62.434 | 0 |
| fine_peel_scale | 19 | 27.296 | 33.188 | 56.049 | 0 |
| projected_pole | 19 | 26.883 | 35.360 | 62.434 | 0 |

Every variant directory contains algorithm.py, settings.json, report.json and individual record diagnostics. The two interrupted scale/normal exploratory jobs remain separately labelled incomplete and are excluded from this complete table.
