# Fixed conveyor input regression

Every variant receives identical frozen BGR crops and fruit masks. No detector, GrabCut, defect segmenter, or grading runs. These inputs have no labelled pose or defect truth, so improved coverage is not evidence of improved accuracy.

The baseline is the preserved production source from the preceding audit. The adjacent candidate breaks on rejected motion and unknown source-frame gaps. The native variant rechecks only accepted quarter-resolution estimates below 3 degrees at original crop resolution; a coarse residual failure is never rescued.

| Track | Variant | Result | Selected views | Rotation / longitude (deg) | Native rechecks |
|---|---|---|---:|---:|---:|
| 98 | native_all | insufficient_longitude_coverage | 22 | 257.50 / 349.32 | 0 |
| 1 | native_all | missing_defect_masks | 12 | 300.65 / 360.00 | 0 |
| 14 | native_all | insufficient_longitude_coverage | 17 | 238.04 / 314.50 | 0 |
| 491 | native_all | insufficient_longitude_coverage | 6 | 60.44 / 151.22 | 0 |

## Fragmentation and ordering

The JSON and per-pair logs retain every estimate and selection decision. A short retained segment can result from residual rejection, a missing source frame, or longitude ordering checks. The following counts expose these causes rather than treating a successful map as accuracy evidence.

### Track 98

- native_all: {'accepted': 46, 'failed_coarse': 19}; selection reasons {'no_split_reason': 46, 'Unreliable pair 0: rotation 0.00 deg is too small': 16, 'Unreliable pair 0: rotation 0.01 deg is too small': 1, 'Unreliable pair 0: rotation 0.22 deg is too small': 1, 'Unreliable pair 0: rotation 0.04 deg is too small': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 1

- native_all: {'accepted': 26, 'failed_coarse': 19}; selection reasons {'no_split_reason': 26, 'Unreliable pair 0: rotation 0.00 deg is too small': 16, 'Unreliable pair 0: rotation 0.14 deg is too small': 1, 'Unreliable pair 0: rotation 0.04 deg is too small': 1, 'Unreliable pair 0: rotation 0.18 deg is too small': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 2}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 14

- native_all: {'accepted': 19, 'failed_coarse': 24}; selection reasons {'no_split_reason': 19, 'Unreliable pair 0: rotation 55.0 deg, error 0.496': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 23, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 1}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Track 491

- native_all: {'accepted': 29, 'failed_coarse': 28}; selection reasons {'no_split_reason': 29, 'Unreliable pair 0: rotation 55.0 deg, error 0.497': 1, 'Unreliable pair 0: rotation 0.00 deg is too small': 25, 'Missing original frames between captured views': 1, 'Unreliable pair 0: rotation 0.09 deg is too small': 1, 'Unreliable pair 0: rotation 0.10 deg is too small': 1, 'Longitude increment outside fusion bounds 0.25..max_pair+12 degrees': 4}; final steps below 0.25 degrees: 0; backwards steps: 0.

### Unique boundaries that split each candidate

The counts below concern original source-frame pairs. Repeated checks of a pair after a reference-frame change count once. Backwards longitude is a subset of longitude below 0.25 degrees.

| Track | Variant | Failed motion | Missing frame | Rolling rotation <0.25 deg | Total rotation <0.25 deg | Longitude <0.25 deg | Backwards longitude |
|---|---|---:|---:|---:|---:|---:|---:|
| 98 | native_all | 0 | 0 | 19 | 0 | 0 | 0 |
| 1 | native_all | 0 | 0 | 19 | 0 | 2 | 0 |
| 14 | native_all | 1 | 0 | 23 | 0 | 1 | 0 |
| 491 | native_all | 1 | 1 | 27 | 0 | 4 | 1 |
## Reproduction

```powershell
.\backend\venv\Scripts\python.exe -B "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_green_conveyor_20261002\sources\validate_algorithm_revision.py" --candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_green_conveyor_20261002\sources\adjacent_candidate.py" --native-candidate "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_green_conveyor_20261002\sources\adjacent_native.py" --baseline "C:\Users\USER\Desktop\1Skripsie\VS Code\final\backend\diagnostics\algorithm-revision\fixed_green_conveyor_20261002\sources\baseline.py" --label <new-label> --source-frame-gap 1 --native-only --image-downsample 1 --highpass-sigma 5.0 --matching-cost green_mad
```

Source files, settings, script, and input hashes are frozen beside this report. The report was generated from actual saved images; the evidence images are not synthetic.
