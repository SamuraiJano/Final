# Fixed conveyor input regression

Every variant receives identical frozen BGR crops and fruit masks. No detector, GrabCut, defect segmenter, or grading runs. These inputs have no labelled pose or defect truth, so improved coverage is not evidence of improved accuracy.

The baseline is the preserved production source from the preceding audit. The adjacent candidate breaks on rejected motion and unknown source-frame gaps. The native variant rechecks only accepted quarter-resolution estimates below 3 degrees at original crop resolution; a coarse residual failure is never rescued.

| Track | Variant | Result | Selected views | Rotation / longitude (deg) | Native rechecks |
|---|---|---|---:|---:|---:|
| 98 | adjacent_native | insufficient_longitude_coverage | 7 | 81.84 / 183.05 | 63 |
| 1 | adjacent_native | insufficient_longitude_coverage | 7 | 16.50 / 130.06 | 41 |
| 14 | adjacent_native | insufficient_longitude_coverage | 3 | 15.19 / 102.38 | 38 |
| 491 | adjacent_native | insufficient_longitude_coverage | 4 | 33.25 / 158.09 | 55 |

## Fragmentation and ordering

The JSON and per-pair logs retain every estimate and selection decision. A short retained segment can result from residual rejection, a missing source frame, or longitude ordering checks. The following counts expose these causes rather than treating a successful map as accuracy evidence.

### Track 98

- adjacent_native: {'accepted': 37, 'failed_native': 26, 'failed_coarse': 2}; selection reasons {'no_split_reason': 37, 'Unreliable pair 0: rotation 55.0 deg, error 0.583': 1, 'Unreliable pair 0: rotation 13.6 deg, error 0.603': 1, 'Native green refinement disagrees with coarse rotation: 13.34 vs 54.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 12.50 vs 49.50 degrees': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.556': 1, 'Native green refinement disagrees with coarse rotation: 13.35 vs 54.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 13.45 vs 50.17 degrees': 1, 'Native green refinement disagrees with coarse rotation: 12.26 vs 48.00 degrees': 1, 'Unreliable pair 0: rotation 15.5 deg, error 0.597': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 15, 'Unreliable pair 0: rotation 0.05 deg is too small': 1, 'Unreliable pair 0: rotation 0.16 deg is too small': 1, 'Unreliable pair 0: rotation 0.04 deg is too small': 1, 'Unreliable pair 0: rotation 0.09 deg is too small': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 1

- adjacent_native: {'failed_coarse': 4, 'failed_native': 28, 'accepted': 13}; selection reasons {'Unreliable pair 0: rotation 5.5 deg, error 0.662': 1, 'Unreliable pair 0: rotation 1.6 deg, error 0.617': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.635': 1, 'Unreliable pair 0: rotation 11.0 deg, error 0.606': 1, 'Native green refinement disagrees with coarse rotation: 0.67 vs 35.97 degrees': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.648': 1, 'Native green refinement disagrees with coarse rotation: 4.50 vs 36.30 degrees': 1, 'Native green refinement disagrees with coarse rotation: 4.50 vs 49.50 degrees': 1, 'Unreliable pair 0: rotation 39.0 deg, error 0.633': 1, 'Native green refinement disagrees with coarse rotation: 6.56 vs 39.00 degrees': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.617': 1, 'Native green refinement disagrees with coarse rotation: 16.00 vs 42.95 degrees': 1, 'no_split_reason': 13, 'Unreliable pair 0: rotation 0.00 deg is too small': 14, 'Native green refinement disagrees with coarse rotation: 9.68 vs 41.23 degrees': 1, 'Native green refinement disagrees with coarse rotation: 5.68 vs 50.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 3.50 vs 53.98 degrees': 1, 'Unreliable pair 0: rotation 0.24 deg is too small': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 52.00 degrees': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.478': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 14

- adjacent_native: {'failed_coarse': 5, 'failed_native': 32, 'accepted': 6}; selection reasons {'Unreliable pair 0: rotation 40.6 deg, error 0.593': 1, 'Native green refinement disagrees with coarse rotation: 10.91 vs 50.73 degrees': 1, 'Unreliable pair 0: rotation 14.5 deg, error 0.630': 1, 'Native green refinement disagrees with coarse rotation: 17.25 vs 39.00 degrees': 1, 'Unreliable pair 0: rotation 17.5 deg, error 0.627': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.420': 1, 'Native green refinement disagrees with coarse rotation: 16.38 vs 50.50 degrees': 1, 'Native green refinement disagrees with coarse rotation: 7.32 vs 27.61 degrees': 1, 'Native green refinement disagrees with coarse rotation: 7.00 vs 53.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.50 vs 37.09 degrees': 1, 'Unreliable pair 0: rotation 4.5 deg, error 0.600': 1, 'no_split_reason': 6, 'Unreliable pair 0: rotation 9.6 deg, error 0.599': 1, 'Native green refinement disagrees with coarse rotation: 0.16 vs 53.86 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.04 vs 53.00 degrees': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 22, 'Unreliable pair 0: rotation 0.15 deg is too small': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 491

- adjacent_native: {'accepted': 14, 'failed_coarse': 2, 'failed_native': 41}; selection reasons {'no_split_reason': 14, 'Unreliable pair 0: rotation 11.5 deg, error 0.617': 1, 'Unreliable pair 0: rotation 19.0 deg, error 0.581': 1, 'Native green refinement disagrees with coarse rotation: 1.64 vs 53.50 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 35.18 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.46 vs 46.55 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 51.50 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 51.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 5.46 vs 34.90 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 54.00 degrees': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.481': 1, 'Native green refinement disagrees with coarse rotation: 9.21 vs 41.68 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.63 vs 42.50 degrees': 1, 'Native green refinement disagrees with coarse rotation: 2.34 vs 45.57 degrees': 1, 'Native green refinement disagrees with coarse rotation: 1.50 vs 42.43 degrees': 1, 'Unreliable pair 0: rotation 55.0 deg, error 0.470': 1, 'Native green refinement disagrees with coarse rotation: 8.09 vs 42.00 degrees': 1, 'Unreliable pair 0: rotation 0.24 deg is too small': 1, 'Missing original frames between captured views': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 19, 'Native green refinement disagrees with coarse rotation: 0.00 vs 45.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 23.35 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 34.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 49.50 degrees': 1, 'Unreliable pair 0: rotation 0.18 deg is too small': 1, 'Native green refinement disagrees with coarse rotation: 2.03 vs 32.00 degrees': 1, 'Native green refinement disagrees with coarse rotation: 0.00 vs 14.50 degrees': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Unique boundaries that split each candidate

The counts below concern original source-frame pairs. Repeated checks of a pair after a reference-frame change count once. Backwards longitude is a subset of longitude below 0.25 degrees.

| Track | Variant | Failed motion | Missing frame | Rolling rotation <0.25 deg | Total rotation <0.25 deg | Longitude <0.25 deg | Backwards longitude |
|---|---|---:|---:|---:|---:|---:|---:|
| 98 | adjacent_native | 9 | 0 | 19 | 0 | 0 | 0 |
| 1 | adjacent_native | 17 | 0 | 15 | 0 | 0 | 0 |
| 14 | adjacent_native | 14 | 0 | 23 | 0 | 1 | 0 |
| 491 | adjacent_native | 22 | 1 | 21 | 0 | 0 | 0 |
## Reproduction

```powershell
.\backend\venv\Scripts\python.exe -B "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_aligned_20261002\sources\validate_algorithm_revision.py" --candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_aligned_20261002\sources\adjacent_candidate.py" --native-candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_aligned_20261002\sources\adjacent_native.py" --baseline "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_aligned_20261002\sources\baseline.py" --label <new-label> --source-frame-gap 1 --native-only --native-matching-cost aligned_mad --native-recheck-angle 20.0 --transverse-angle 20.0
```

Source files, settings, script, and input hashes are frozen beside this report. The report was generated from actual saved images; the evidence images are not synthetic.
