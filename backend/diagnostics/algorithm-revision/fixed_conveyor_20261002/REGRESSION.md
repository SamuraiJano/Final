# Fixed conveyor input regression

Every variant receives identical frozen BGR crops and fruit masks. No detector, GrabCut, defect segmenter, or grading runs. These inputs have no labelled pose or defect truth, so improved coverage is not evidence of improved accuracy.

The baseline is the preserved production source from the preceding audit. The adjacent candidate breaks on rejected motion and unknown source-frame gaps. The native variant rechecks only accepted quarter-resolution estimates below 3 degrees at original crop resolution; a coarse residual failure is never rescued.

| Track | Variant | Result | Selected views | Rotation / longitude (deg) | Native rechecks |
|---|---|---|---:|---:|---:|
| 98 | baseline | insufficient_longitude_coverage | 23 | 241.03 / 335.59 | 0 |
| 98 | adjacent_only | insufficient_longitude_coverage | 20 | 254.37 / 343.98 | 0 |
| 98 | adjacent_native | insufficient_longitude_coverage | 20 | 254.37 / 343.98 | 28 |
| 1 | baseline | insufficient_longitude_coverage | 7 | 34.77 / 110.66 | 0 |
| 1 | adjacent_only | insufficient_longitude_coverage | 12 | 65.88 / 166.71 | 0 |
| 1 | adjacent_native | insufficient_longitude_coverage | 6 | 40.53 / 125.75 | 27 |
| 14 | baseline | insufficient_longitude_coverage | 7 | 50.86 / 151.90 | 0 |
| 14 | adjacent_only | insufficient_longitude_coverage | 6 | 31.70 / 129.81 | 0 |
| 14 | adjacent_native | insufficient_longitude_coverage | 4 | 30.70 / 121.12 | 29 |
| 491 | baseline | mapping_failed | 0 | 0.00 / 0.00 | 0 |
| 491 | adjacent_only | insufficient_longitude_coverage | 4 | 27.32 / 161.53 | 0 |
| 491 | adjacent_native | insufficient_longitude_coverage | 4 | 27.32 / 161.53 | 46 |

## Fragmentation and ordering

The JSON and per-pair logs retain every estimate and selection decision. A short retained segment can result from residual rejection, a missing source frame, or longitude ordering checks. The following counts expose these causes rather than treating a successful map as accuracy evidence.

### Track 98

- baseline: {'accepted': 51, 'failed_coarse': 14}; selection reasons {'accepted': 25, 'Unreliable pair 0: rotation 13.6 deg, error 0.603': 1, 'Unreliable pair 0: rotation 23.1 deg, error 0.593': 1, 'Unreliable pair 0: rotation 1.1 deg, error 0.631': 1, 'Unreliable pair 0: rotation 6.1 deg, error 0.608': 1, 'Unreliable pair 0: rotation 20.5 deg, error 0.711': 1, 'Unreliable pair 0: rotation 20.6 deg, error 0.653': 1, 'Unreliable pair 0: rotation 6.5 deg, error 0.658': 1, 'Unreliable pair 0: rotation 5.5 deg, error 0.706': 1, 'Unreliable pair 0: rotation 12.0 deg, error 0.617': 1, 'Unreliable pair 0: rotation 15.0 deg, error 0.640': 1, 'Unreliable pair 0: rotation 28.0 deg, error 0.630': 1, 'Unreliable pair 0: rotation 44.1 deg, error 0.583': 1, 'Unreliable pair 0: rotation 19.4 deg, error 0.622': 1, 'Unreliable pair 0: rotation 18.0 deg, error 0.637': 1, 'insufficient_angular_change': 26}; final steps below 0.25 degrees: 0; backwards steps: 0.
- adjacent_only: {'accepted': 62, 'failed_coarse': 3}; selection reasons {'accepted': 59, 'Unreliable pair 0: rotation 13.6 deg, error 0.603': 1, 'Unreliable pair 0: rotation 12.0 deg, error 0.617': 1, 'Unreliable pair 0: rotation 15.5 deg, error 0.597': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 3, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 13}; final steps below 0.25 degrees: 0; backwards steps: 0.
- adjacent_native: {'accepted': 61, 'failed_coarse': 3, 'failed_native': 1}; selection reasons {'accepted': 55, 'Unreliable pair 0: rotation 13.6 deg, error 0.603': 1, 'Unreliable pair 0: rotation 12.0 deg, error 0.617': 1, 'Unreliable pair 0: rotation 15.5 deg, error 0.597': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 6, 'Unreliable pair 0: rotation 0.0 deg, error 0.643': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 10}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 1

- baseline: {'failed_coarse': 15, 'accepted': 30}; selection reasons {'Unreliable pair 0: rotation 5.5 deg, error 0.662': 1, 'Unreliable pair 0: rotation 5.9 deg, error 0.737': 1, 'Unreliable pair 0: rotation 11.5 deg, error 0.719': 1, 'Unreliable pair 0: rotation 14.0 deg, error 0.699': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.745': 1, 'Unreliable pair 0: rotation 3.6 deg, error 0.682': 1, 'Unreliable pair 0: rotation 8.0 deg, error 0.714': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.624': 1, 'insufficient_angular_change': 19, 'accepted': 11, 'Unreliable pair 0: rotation 0.0 deg, error 0.706': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.634': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.667': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.637': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.593': 1, 'Unreliable pair 0: rotation 42.5 deg, error 0.714': 1, 'Unreliable pair 0: rotation 20.8 deg, error 0.665': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.
- adjacent_only: {'failed_coarse': 4, 'accepted': 41}; selection reasons {'Unreliable pair 0: rotation 5.5 deg, error 0.662': 1, 'Unreliable pair 0: rotation 1.6 deg, error 0.617': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.635': 1, 'Unreliable pair 0: rotation 11.0 deg, error 0.606': 1, 'accepted': 33, 'Unobservable change below 0.25 degrees; motion is not accumulated': 8, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 7}; final steps below 0.25 degrees: 0; backwards steps: 0.
- adjacent_native: {'failed_coarse': 4, 'failed_native': 3, 'accepted': 38}; selection reasons {'Unreliable pair 0: rotation 5.5 deg, error 0.662': 1, 'Unreliable pair 0: rotation 1.6 deg, error 0.617': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.635': 1, 'Unreliable pair 0: rotation 11.0 deg, error 0.606': 1, 'Unreliable pair 0: rotation 10.0 deg, error 0.625': 1, 'accepted': 28, 'Unreliable pair 0: rotation 2.3 deg, error 0.660': 1, 'Unreliable pair 0: rotation 2.4 deg, error 0.659': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 10, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 6}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 14

- baseline: {'failed_coarse': 15, 'accepted': 28}; selection reasons {'Unreliable pair 0: rotation 40.6 deg, error 0.593': 1, 'Unreliable pair 0: rotation 18.2 deg, error 0.653': 1, 'Unreliable pair 0: rotation 30.5 deg, error 0.678': 1, 'Unreliable pair 0: rotation 17.5 deg, error 0.626': 1, 'accepted': 6, 'insufficient_angular_change': 22, 'Unreliable pair 0: rotation 8.2 deg, error 0.585': 1, 'Unreliable pair 0: rotation 9.6 deg, error 0.599': 1, 'Unreliable pair 0: rotation 4.0 deg, error 0.695': 1, 'Unreliable pair 0: rotation 2.5 deg, error 0.761': 1, 'Unreliable pair 0: rotation 12.6 deg, error 0.767': 1, 'Unreliable pair 0: rotation 18.5 deg, error 0.760': 1, 'Unreliable pair 0: rotation 14.9 deg, error 0.763': 1, 'Unreliable pair 0: rotation 20.0 deg, error 0.786': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.702': 1, 'Unreliable pair 0: rotation 1.8 deg, error 0.618': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.589': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.
- adjacent_only: {'failed_coarse': 5, 'accepted': 38}; selection reasons {'Unreliable pair 0: rotation 40.6 deg, error 0.593': 1, 'accepted': 30, 'Unreliable pair 0: rotation 14.5 deg, error 0.630': 1, 'Unreliable pair 0: rotation 17.5 deg, error 0.627': 1, 'Unreliable pair 0: rotation 4.5 deg, error 0.600': 1, 'Unreliable pair 0: rotation 9.6 deg, error 0.599': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 8, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 11}; final steps below 0.25 degrees: 0; backwards steps: 0.
- adjacent_native: {'failed_coarse': 5, 'accepted': 34, 'failed_native': 4}; selection reasons {'Unreliable pair 0: rotation 40.6 deg, error 0.593': 1, 'accepted': 22, 'Unreliable pair 0: rotation 14.5 deg, error 0.630': 1, 'Unreliable pair 0: rotation 17.5 deg, error 0.627': 1, 'Unreliable pair 0: rotation 1.7 deg, error 0.646': 1, 'Unreliable pair 0: rotation 4.9 deg, error 0.663': 1, 'Unreliable pair 0: rotation 4.5 deg, error 0.600': 1, 'Unreliable pair 0: rotation 9.6 deg, error 0.599': 1, 'Unreliable pair 0: rotation 7.9 deg, error 0.696': 1, 'Unreliable pair 0: rotation 1.0 deg, error 0.592': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 12, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 13}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 491

- baseline: {'accepted': 44, 'failed_coarse': 14}; selection reasons {'accepted': 7, 'Unreliable pair 0: rotation 11.5 deg, error 0.600': 1, 'Unreliable pair 0: rotation 15.5 deg, error 0.619': 1, 'Unreliable pair 0: rotation 15.1 deg, error 0.596': 1, 'Unreliable pair 0: rotation 10.6 deg, error 0.659': 1, 'Unreliable pair 0: rotation 11.1 deg, error 0.651': 1, 'insufficient_angular_change': 37, 'Unreliable pair 0: rotation 30.3 deg, error 0.702': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.619': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.622': 1, 'Unreliable pair 0: rotation 5.2 deg, error 0.594': 1, 'Unreliable pair 0: rotation 4.0 deg, error 0.595': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.626': 1, 'Unreliable pair 0: rotation 3.2 deg, error 0.622': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.651': 1, 'Unreliable pair 0: rotation 4.0 deg, error 0.683': 1}; final steps below 0.25 degrees: 1; backwards steps: 1.
- adjacent_only: {'accepted': 55, 'failed_coarse': 2}; selection reasons {'accepted': 48, 'Unreliable pair 0: rotation 11.5 deg, error 0.600': 1, 'Unreliable pair 0: rotation 19.0 deg, error 0.581': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 7, 'Missing original frames between captured views': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 20}; final steps below 0.25 degrees: 0; backwards steps: 0.
- adjacent_native: {'accepted': 46, 'failed_coarse': 2, 'failed_native': 9}; selection reasons {'accepted': 36, 'Unreliable pair 0: rotation 11.5 deg, error 0.600': 1, 'Unreliable pair 0: rotation 19.0 deg, error 0.581': 1, 'Unreliable pair 0: rotation 7.8 deg, error 0.704': 1, 'Unreliable pair 0: rotation 9.1 deg, error 0.704': 1, 'Unreliable pair 0: rotation 5.0 deg, error 0.698': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.663': 1, 'Unreliable pair 0: rotation 2.9 deg, error 0.652': 1, 'Unreliable pair 0: rotation 3.8 deg, error 0.647': 1, 'Unreliable pair 0: rotation 1.1 deg, error 0.681': 1, 'Unreliable pair 0: rotation 4.9 deg, error 0.631': 1, 'Missing original frames between captured views': 1, 'Unreliable pair 0: rotation 16.4 deg, error 0.827': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 10, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 12}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Unique boundaries that split each candidate

The counts below concern original source-frame pairs. Repeated checks of a pair after a reference-frame change count once. Backwards longitude is a subset of longitude below 0.25 degrees.

| Track | Variant | Failed motion | Missing frame | Total rotation <0.25 deg | Longitude <0.25 deg | Backwards longitude |
|---|---|---:|---:|---:|---:|---:|
| 98 | adjacent_only | 3 | 0 | 3 | 13 | 5 |
| 98 | adjacent_native | 4 | 0 | 6 | 10 | 1 |
| 1 | adjacent_only | 4 | 0 | 8 | 7 | 4 |
| 1 | adjacent_native | 7 | 0 | 10 | 6 | 3 |
| 14 | adjacent_only | 5 | 0 | 8 | 11 | 7 |
| 14 | adjacent_native | 9 | 0 | 12 | 13 | 3 |
| 491 | adjacent_only | 2 | 1 | 7 | 20 | 13 |
| 491 | adjacent_native | 11 | 1 | 10 | 12 | 6 |
## Reproduction

```powershell
.\backend\venv\Scripts\python.exe -B backend/validate_algorithm_revision.py --candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\adjacent_candidate_source\algorithm_snapshot.py" --label <new-label> --source-frame-gap 1
```

Source files, settings, script, and input hashes are frozen beside this report. The report was generated from actual saved images; the evidence images are not synthetic.
