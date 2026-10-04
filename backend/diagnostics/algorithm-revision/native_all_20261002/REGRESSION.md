# Fixed conveyor input regression

Every variant receives identical frozen BGR crops and fruit masks. No detector, GrabCut, defect segmenter, or grading runs. These inputs have no labelled pose or defect truth, so improved coverage is not evidence of improved accuracy.

The baseline is the preserved production source from the preceding audit. The adjacent candidate breaks on rejected motion and unknown source-frame gaps. The native variant rechecks only accepted quarter-resolution estimates below 3 degrees at original crop resolution; a coarse residual failure is never rescued.

| Track | Variant | Result | Selected views | Rotation / longitude (deg) | Native rechecks |
|---|---|---|---:|---:|---:|
| 98 | native_all | insufficient_longitude_coverage | 3 | 27.51 / 117.46 | 0 |
| 1 | native_all | insufficient_longitude_coverage | 5 | 25.60 / 112.81 | 0 |
| 14 | native_all | insufficient_longitude_coverage | 3 | 27.50 / 113.75 | 0 |
| 491 | native_all | insufficient_longitude_coverage | 7 | 7.22 / 103.96 | 0 |

## Fragmentation and ordering

The JSON and per-pair logs retain every estimate and selection decision. A short retained segment can result from residual rejection, a missing source frame, or longitude ordering checks. The following counts expose these causes rather than treating a successful map as accuracy evidence.

### Track 98

- native_all: {'failed_coarse': 33, 'accepted': 32}; selection reasons {'Unreliable pair 0: rotation 13.5 deg, error 0.693': 1, 'Unreliable pair 0: rotation 13.7 deg, error 0.619': 1, 'Unreliable pair 0: rotation 12.2 deg, error 0.621': 1, 'Unreliable pair 0: rotation 12.5 deg, error 0.684': 1, 'Unreliable pair 0: rotation 13.4 deg, error 0.638': 1, 'Unreliable pair 0: rotation 13.1 deg, error 0.634': 1, 'Unreliable pair 0: rotation 13.1 deg, error 0.586': 1, 'Unreliable pair 0: rotation 14.4 deg, error 0.667': 1, 'Unreliable pair 0: rotation 13.2 deg, error 0.616': 1, 'Unreliable pair 0: rotation 13.8 deg, error 0.657': 1, 'Unreliable pair 0: rotation 11.6 deg, error 0.636': 1, 'Unreliable pair 0: rotation 5.1 deg, error 0.756': 1, 'Unreliable pair 0: rotation 13.2 deg, error 0.669': 1, 'Unreliable pair 0: rotation 13.4 deg, error 0.685': 1, 'Unreliable pair 0: rotation 5.2 deg, error 0.616': 1, 'Unreliable pair 0: rotation 14.2 deg, error 0.642': 1, 'Unreliable pair 0: rotation 3.5 deg, error 0.652': 1, 'Unreliable pair 0: rotation 12.6 deg, error 0.673': 1, 'accepted': 26, 'Unreliable pair 0: rotation 54.2 deg, error 0.714': 1, 'Unreliable pair 0: rotation 13.0 deg, error 0.751': 1, 'Unreliable pair 0: rotation 0.5 deg, error 0.675': 1, 'Unreliable pair 0: rotation 2.0 deg, error 0.782': 1, 'Unreliable pair 0: rotation 22.0 deg, error 0.798': 1, 'Unreliable pair 0: rotation 7.0 deg, error 0.791': 1, 'Unreliable pair 0: rotation 14.0 deg, error 0.661': 1, 'Unreliable pair 0: rotation 16.5 deg, error 0.673': 1, 'Unreliable pair 0: rotation 13.9 deg, error 0.718': 1, 'Unreliable pair 0: rotation 14.9 deg, error 0.717': 1, 'Unreliable pair 0: rotation 16.0 deg, error 0.664': 1, 'Unreliable pair 0: rotation 1.6 deg, error 0.652': 1, 'Unreliable pair 0: rotation 12.6 deg, error 0.719': 1, 'Unreliable pair 0: rotation 9.0 deg, error 0.603': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 6, 'Unreliable pair 0: rotation 0.0 deg, error 0.643': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 11}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 1

- native_all: {'failed_coarse': 13, 'accepted': 32}; selection reasons {'Unreliable pair 0: rotation 5.0 deg, error 0.654': 1, 'Unreliable pair 0: rotation 8.4 deg, error 0.651': 1, 'Unreliable pair 0: rotation 9.0 deg, error 0.668': 1, 'Unreliable pair 0: rotation 9.9 deg, error 0.716': 1, 'Unreliable pair 0: rotation 10.0 deg, error 0.625': 1, 'accepted': 22, 'Unreliable pair 0: rotation 3.1 deg, error 0.638': 1, 'Unreliable pair 0: rotation 52.5 deg, error 0.714': 1, 'Unreliable pair 0: rotation 2.3 deg, error 0.660': 1, 'Unreliable pair 0: rotation 1.0 deg, error 0.629': 1, 'Unreliable pair 0: rotation 2.4 deg, error 0.659': 1, 'Unreliable pair 0: rotation 15.1 deg, error 0.782': 1, 'Unreliable pair 0: rotation 8.6 deg, error 0.663': 1, 'Unreliable pair 0: rotation 8.6 deg, error 0.613': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 10, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 5}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 14

- native_all: {'failed_coarse': 14, 'accepted': 29}; selection reasons {'Unreliable pair 0: rotation 16.4 deg, error 0.702': 1, 'accepted': 17, 'Unreliable pair 0: rotation 15.9 deg, error 0.667': 1, 'Unreliable pair 0: rotation 54.0 deg, error 0.588': 1, 'Unreliable pair 0: rotation 1.7 deg, error 0.646': 1, 'Unreliable pair 0: rotation 9.0 deg, error 0.625': 1, 'Unreliable pair 0: rotation 11.5 deg, error 0.697': 1, 'Unreliable pair 0: rotation 4.9 deg, error 0.663': 1, 'Unreliable pair 0: rotation 11.0 deg, error 0.778': 1, 'Unreliable pair 0: rotation 9.8 deg, error 0.741': 1, 'Unreliable pair 0: rotation 8.9 deg, error 0.662': 1, 'Unreliable pair 0: rotation 8.9 deg, error 0.680': 1, 'Unreliable pair 0: rotation 7.9 deg, error 0.696': 1, 'Unreliable pair 0: rotation 0.3 deg, error 0.647': 1, 'Unreliable pair 0: rotation 1.0 deg, error 0.592': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 12, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 13}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 491

- native_all: {'failed_coarse': 18, 'accepted': 39}; selection reasons {'Unreliable pair 0: rotation 3.2 deg, error 0.717': 1, 'Unreliable pair 0: rotation 8.0 deg, error 0.688': 1, 'Unreliable pair 0: rotation 10.2 deg, error 0.752': 1, 'Unreliable pair 0: rotation 12.0 deg, error 0.715': 1, 'Unreliable pair 0: rotation 18.2 deg, error 0.639': 1, 'Unreliable pair 0: rotation 7.8 deg, error 0.704': 1, 'Unreliable pair 0: rotation 9.1 deg, error 0.704': 1, 'accepted': 29, 'Unreliable pair 0: rotation 5.0 deg, error 0.698': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.651': 1, 'Unreliable pair 0: rotation 0.0 deg, error 0.663': 1, 'Unreliable pair 0: rotation 9.3 deg, error 0.637': 1, 'Unreliable pair 0: rotation 2.9 deg, error 0.652': 1, 'Unreliable pair 0: rotation 3.8 deg, error 0.647': 1, 'Unreliable pair 0: rotation 8.5 deg, error 0.658': 1, 'Unreliable pair 0: rotation 11.1 deg, error 0.653': 1, 'Unreliable pair 0: rotation 1.1 deg, error 0.681': 1, 'Unreliable pair 0: rotation 4.9 deg, error 0.631': 1, 'Missing original frames between captured views': 1, 'Unreliable pair 0: rotation 16.4 deg, error 0.827': 1, 'Unobservable change below 0.25 degrees; motion is not accumulated': 10, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 11}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Unique boundaries that split each candidate

The counts below concern original source-frame pairs. Repeated checks of a pair after a reference-frame change count once. Backwards longitude is a subset of longitude below 0.25 degrees.

| Track | Variant | Failed motion | Missing frame | Total rotation <0.25 deg | Longitude <0.25 deg | Backwards longitude |
|---|---|---:|---:|---:|---:|---:|
| 98 | native_all | 33 | 0 | 6 | 11 | 1 |
| 1 | native_all | 13 | 0 | 10 | 5 | 3 |
| 14 | native_all | 14 | 0 | 12 | 13 | 3 |
| 491 | native_all | 18 | 1 | 10 | 11 | 5 |
## Reproduction

```powershell
.\backend\venv\Scripts\python.exe -B backend/validate_algorithm_revision.py --candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\adjacent_candidate_source\algorithm_snapshot.py" --label <new-label> --source-frame-gap 1 --native-only --image-downsample 1
```

Source files, settings, script, and input hashes are frozen beside this report. The report was generated from actual saved images; the evidence images are not synthetic.
