# Fixed conveyor input regression

Every variant receives identical frozen BGR crops and fruit masks. No detector, GrabCut, defect segmenter, or grading runs. These inputs have no labelled pose or defect truth, so improved coverage is not evidence of improved accuracy.

The baseline is the preserved production source from the preceding audit. The adjacent candidate breaks on rejected motion and unknown source-frame gaps. The native variant rechecks only accepted quarter-resolution estimates below 3 degrees at original crop resolution; a coarse residual failure is never rescued.

| Track | Variant | Result | Selected views | Rotation / longitude (deg) | Native rechecks |
|---|---|---|---:|---:|---:|
| 98 | adjacent_native | insufficient_longitude_coverage | 8 | 93.88 / 188.39 | 63 |
| 1 | adjacent_native | insufficient_longitude_coverage | 7 | 15.17 / 127.19 | 41 |
| 14 | adjacent_native | insufficient_longitude_coverage | 4 | 14.44 / 103.72 | 38 |
| 491 | adjacent_native | insufficient_longitude_coverage | 3 | 14.34 / 133.17 | 55 |

## Fragmentation and ordering

The JSON and per-pair logs retain every estimate and selection decision. A short retained segment can result from residual rejection, a missing source frame, or longitude ordering checks. The following counts expose these causes rather than treating a successful map as accuracy evidence.

### Track 98

- adjacent_native: {'accepted': 38, 'failed_native': 25, 'failed_coarse': 2}; selection reasons {'no_split_reason': 38, 'Native green refinement disagrees with coarse rotation: 12.68 vs 0.00 degrees': 1, 'Unreliable pair 0: rotation 13.6 deg, error 0.603': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.323': 1, 'Native green refinement disagrees with coarse rotation: 14.84 vs 0.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 13.94 vs 10.10 degrees': 1, 'Native green refinement disagrees with coarse rotation: 13.57 vs 3.50 degrees': 1, 'Unreliable pair 0: rotation 15.5 deg, error 0.597': 1, 'Native green refinement disagrees with coarse rotation: 16.42 vs 4.14 degrees': 1, 'Native green refinement disagrees with coarse rotation: 15.43 vs 2.78 degrees': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 16, 'Unreliable pair 0: rotation 0.17 deg is too small': 1, 'Unreliable pair 0: rotation 0.22 deg is too small': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 1

- adjacent_native: {'failed_coarse': 4, 'failed_native': 24, 'accepted': 17}; selection reasons {'Unreliable pair 0: rotation 5.5 deg, error 0.662': 1, 'Unreliable pair 0: rotation 1.6 deg, error 0.617': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.635': 1, 'Unreliable pair 0: rotation 11.0 deg, error 0.606': 1, 'Native green refinement disagrees with coarse rotation: 0.67 vs 22.21 degrees': 1, 'no_split_reason': 17, 'Native green refinement disagrees with coarse rotation: 4.50 vs 53.50 degrees': 1, 'Native green refinement disagrees with coarse rotation: 1.50 vs 49.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 6.56 vs 52.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 1.00 vs 9.66 degrees': 1, 'Native green refinement disagrees with coarse rotation: 16.00 vs 0.00 degrees': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 14, 'Native green refinement disagrees with coarse rotation: 9.68 vs 13.45 degrees': 1, 'Unreliable pair 0: rotation 0.06 deg is too small': 1, 'Unreliable pair 0: rotation 0.05 deg is too small': 1, 'Unreliable pair 0: rotation 0.12 deg is too small': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 14

- adjacent_native: {'failed_coarse': 5, 'failed_native': 31, 'accepted': 7}; selection reasons {'Unreliable pair 0: rotation 40.6 deg, error 0.593': 1, 'Native green refinement disagrees with coarse rotation: 10.91 vs 2.26 degrees': 1, 'Unreliable pair 0: rotation 14.5 deg, error 0.630': 1, 'Native green refinement disagrees with coarse rotation: 17.25 vs 0.69 degrees': 1, 'Unreliable pair 0: rotation 17.5 deg, error 0.627': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.311': 1, 'Native green refinement disagrees with coarse rotation: 16.38 vs 8.81 degrees': 1, 'no_split_reason': 7, 'Unreliable pair 0: rotation 4.5 deg, error 0.600': 1, 'Native green refinement disagrees with coarse rotation: 8.04 vs 5.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 8.60 vs 1.35 degrees': 1, 'Unreliable pair 0: rotation 9.6 deg, error 0.599': 1, 'Native green refinement disagrees with coarse rotation: 3.50 vs 0.00 degrees': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 21, 'Unreliable pair 0: rotation 0.25 deg is too small': 2, 'Unreliable pair 0: rotation 0.18 deg is too small': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 491

- adjacent_native: {'accepted': 22, 'failed_native': 33, 'failed_coarse': 2}; selection reasons {'no_split_reason': 22, 'Native green refinement disagrees with coarse rotation: 16.96 vs 13.47 degrees': 1, 'Unreliable pair 0: rotation 11.5 deg, error 0.617': 1, 'Unreliable pair 0: rotation 19.0 deg, error 0.581': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.424': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 25, 'Native green refinement disagrees with coarse rotation: 5.46 vs 0.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 3.61 degrees': 1, 'Native green refinement disagrees with coarse rotation: 9.21 vs 17.13 degrees': 1, 'Unreliable pair 0: rotation 0.15 deg is too small': 1, 'Missing original frames between captured views': 1, 'Unreliable pair 0: rotation 0.22 deg is too small': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 20.15 degrees': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Unique boundaries that split each candidate

The counts below concern original source-frame pairs. Repeated checks of a pair after a reference-frame change count once. Backwards longitude is a subset of longitude below 0.25 degrees.

| Track | Variant | Failed motion | Missing frame | Rolling rotation <0.25 deg | Total rotation <0.25 deg | Longitude <0.25 deg | Backwards longitude |
|---|---|---:|---:|---:|---:|---:|---:|
| 98 | adjacent_native | 9 | 0 | 18 | 0 | 0 | 0 |
| 1 | adjacent_native | 11 | 0 | 17 | 0 | 1 | 0 |
| 14 | adjacent_native | 12 | 0 | 24 | 0 | 1 | 0 |
| 491 | adjacent_native | 8 | 1 | 27 | 0 | 1 | 1 |
## Reproduction

```powershell
.\backend\venv\Scripts\python.exe -B "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_refine20_conveyor_20261002\sources\validate_algorithm_revision.py" --candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_refine20_conveyor_20261002\sources\adjacent_candidate.py" --native-candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_refine20_conveyor_20261002\sources\adjacent_native.py" --baseline "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_refine20_conveyor_20261002\sources\baseline.py" --label <new-label> --source-frame-gap 1 --native-only --native-matching-cost green_mad --native-recheck-angle 20.0 --transverse-angle 20.0
```

Source files, settings, script, and input hashes are frozen beside this report. The report was generated from actual saved images; the evidence images are not synthetic.
