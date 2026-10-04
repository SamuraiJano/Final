# Fixed conveyor input regression

Every variant receives identical frozen BGR crops and fruit masks. No detector, GrabCut, defect segmenter, or grading runs. These inputs have no labelled pose or defect truth, so improved coverage is not evidence of improved accuracy.

The baseline is the preserved production source from the preceding audit. The adjacent candidate breaks on rejected motion and unknown source-frame gaps. The native variant rechecks only accepted quarter-resolution estimates below 3 degrees at original crop resolution; a coarse residual failure is never rescued.

| Track | Variant | Result | Selected views | Rotation / longitude (deg) | Native rechecks |
|---|---|---|---:|---:|---:|
| 98 | adjacent_native | insufficient_longitude_coverage | 13 | 160.53 / 258.56 | 63 |
| 1 | adjacent_native | insufficient_longitude_coverage | 4 | 26.31 / 113.53 | 41 |
| 14 | adjacent_native | insufficient_longitude_coverage | 2 | 10.73 / 99.03 | 38 |
| 491 | adjacent_native | insufficient_longitude_coverage | 4 | 30.44 / 159.81 | 55 |

## Fragmentation and ordering

The JSON and per-pair logs retain every estimate and selection decision. A short retained segment can result from residual rejection, a missing source frame, or longitude ordering checks. The following counts expose these causes rather than treating a successful map as accuracy evidence.

### Track 98

- adjacent_native: {'accepted': 43, 'failed_coarse': 2, 'failed_native': 20}; selection reasons {'no_split_reason': 43, 'Unreliable pair 0: rotation 13.6 deg, error 0.603': 1, 'Native green refinement disagrees with coarse rotation: 14.84 vs 1.00 degrees': 1, 'Unreliable pair 0: rotation 15.5 deg, error 0.597': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 14, 'Unreliable pair 0: rotation 0.22 deg is too small': 1, 'Unreliable pair 0: rotation 0.05 deg is too small': 1, 'Unreliable pair 0: rotation 0.16 deg is too small': 1, 'Unreliable pair 0: rotation 0.12 deg is too small': 1, 'Unreliable pair 0: rotation 0.14 deg is too small': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 1

- adjacent_native: {'failed_coarse': 4, 'accepted': 21, 'failed_native': 20}; selection reasons {'Unreliable pair 0: rotation 5.5 deg, error 0.662': 1, 'Unreliable pair 0: rotation 1.6 deg, error 0.617': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.635': 1, 'Unreliable pair 0: rotation 11.0 deg, error 0.606': 1, 'no_split_reason': 21, 'Native green refinement disagrees with coarse rotation: 6.56 vs 2.63 degrees': 1, 'Native green refinement disagrees with coarse rotation: 16.00 vs 0.29 degrees': 1, 'Unreliable pair 0: rotation 0.24 deg is too small': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 14, 'Unreliable pair 0: rotation 0.07 deg is too small': 2, 'Unreliable pair 0: rotation 0.04 deg is too small': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 2}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 14

- adjacent_native: {'failed_coarse': 5, 'accepted': 9, 'failed_native': 29}; selection reasons {'Unreliable pair 0: rotation 13.1 deg, error 0.677': 1, 'no_split_reason': 9, 'Unreliable pair 0: rotation 14.5 deg, error 0.630': 1, 'Native green refinement disagrees with coarse rotation: 17.25 vs 3.65 degrees': 1, 'Unreliable pair 0: rotation 17.5 deg, error 0.627': 1, 'Native green refinement disagrees with coarse rotation: 16.38 vs 8.30 degrees': 1, 'Native green refinement disagrees with coarse rotation: 7.00 vs 3.50 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.50 vs 4.35 degrees': 1, 'Unreliable pair 0: rotation 4.5 deg, error 0.600': 1, 'Native green refinement disagrees with coarse rotation: 8.60 vs 4.81 degrees': 1, 'Unreliable pair 0: rotation 9.6 deg, error 0.599': 1, 'Native green refinement disagrees with coarse rotation: 0.16 vs 3.20 degrees': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 20, 'Unreliable pair 0: rotation 0.12 deg is too small': 1, 'Unreliable pair 0: rotation 0.23 deg is too small': 1, 'Unreliable pair 0: rotation 0.03 deg is too small': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 2}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 491

- adjacent_native: {'accepted': 21, 'failed_coarse': 2, 'failed_native': 34}; selection reasons {'no_split_reason': 21, 'Unreliable pair 0: rotation 11.5 deg, error 0.617': 1, 'Unreliable pair 0: rotation 19.0 deg, error 0.581': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 29, 'Native green refinement disagrees with coarse rotation: 9.21 vs 5.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 1.50 vs 7.79 degrees': 1, 'Native green refinement disagrees with coarse rotation: 8.09 vs 4.98 degrees': 1, 'Missing original frames between captured views': 1, 'Unreliable pair 0: rotation 0.22 deg is too small': 1, 'Unreliable pair 0: rotation 0.04 deg is too small': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Unique boundaries that split each candidate

The counts below concern original source-frame pairs. Repeated checks of a pair after a reference-frame change count once. Backwards longitude is a subset of longitude below 0.25 degrees.

| Track | Variant | Failed motion | Missing frame | Rolling rotation <0.25 deg | Total rotation <0.25 deg | Longitude <0.25 deg | Backwards longitude |
|---|---|---:|---:|---:|---:|---:|---:|
| 98 | adjacent_native | 3 | 0 | 19 | 0 | 0 | 0 |
| 1 | adjacent_native | 6 | 0 | 18 | 0 | 2 | 1 |
| 14 | adjacent_native | 11 | 0 | 23 | 0 | 2 | 0 |
| 491 | adjacent_native | 5 | 1 | 31 | 0 | 1 | 1 |
## Reproduction

```powershell
.\backend\venv\Scripts\python.exe -B "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_log_pattern20_20261002\sources\validate_algorithm_revision.py" --candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_log_pattern20_20261002\sources\adjacent_candidate.py" --native-candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_log_pattern20_20261002\sources\adjacent_native.py" --baseline "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_log_pattern20_20261002\sources\baseline.py" --label <new-label> --source-frame-gap 1 --native-only --native-matching-cost aligned_mad --native-recheck-angle 20.0 --transverse-angle 20.0 --max-pair-angle 20.0
```

Source files, settings, script, and input hashes are frozen beside this report. The report was generated from actual saved images; the evidence images are not synthetic.
