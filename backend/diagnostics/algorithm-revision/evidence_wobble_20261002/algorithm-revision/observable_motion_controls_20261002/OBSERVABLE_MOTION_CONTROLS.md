# Explicit observable-motion controls

The isolated candidate passes these defined observability controls: it returns all
ten real moving transitions in each of two synthetic textures, while declaring
all 119 stationary turns unavailable in each 120-frame noisy sequence. It returns
no stationary map, grade or extrapolated endpoint pose.

The earlier raw-motion accuracy failures remain failures. In particular, forcing
the minimum rolling angle to zero and propagating every sigma-2 estimate produces
1.973-degree / 1.799-pixel stationary-A drift. This report does not relabel that
result as accurate stationary motion.

## Isolated changes and reason

The frozen candidate combines native-only float-green prefilter sigma 2 pixels,
the existing physical-width sigma-5 high-pass, and a **0.25-degree minimum dominant
rolling component** at both direct measurement and selector measurement. The
selector no longer requests a zero minimum that permits subresolution motion.
The numerical quarter-degree bound already existed in map fusion; applying it
consistently to dominant rolling is an engineering adaptation, not an independently
calibrated confidence threshold from the paper.

This candidate never treats an unavailable measurement as zero. It breaks the
motion chain and leaves later propagated poses unavailable. Coarse failures are
not rescued, and no direct bridge replaces a missing intermediate measurement.

Before testing, the preserved sigma-2 stationary estimates were audited:

| Stationary input | Largest raw dominant y component | Raw dominant components at least 0.25 deg |
| --- | ---: | ---: |
| Texture A, 119 adjacent pairs | 0.128745 deg | 0 / 119 |
| Texture B, 119 adjacent pairs | 0.039667 deg | 0 / 119 |

Texture A's largest total rotation-vector magnitude was 0.370886 degrees despite
its smaller rolling component. A total-vector threshold can therefore admit
transverse noise that supplies no observable rolling motion.

## Results on identical preserved pixels and truth

| Input | Observable measurements | Endpoint pose error | Endpoint landmark RMS | Mapping |
| --- | ---: | ---: | ---: | --- |
| Known variable x/y motion, texture A | 10 / 10 | 0.773 deg | 0.701 px | Partial; no grade |
| Known variable x/y motion, texture B | 10 / 10 | 0.272 deg | 0.248 px | Partial; no grade |
| Stationary with independent pixel noise, texture A | **0 / 119** | Unavailable | Unavailable | No reliable map or grade |
| Stationary with independent pixel noise, texture B | **0 / 119** | Unavailable | Unavailable | No reliable map or grade |

All 119 stationary native rechecks are executed in each texture; all are explicitly
rejected by the dominant rolling minimum. Moving accuracy retains the existing
one-degree endpoint-pose and one-pixel maximum-landmark RMS acceptance limits.
All ten moving transitions remain available, so the result does not obtain lower
error by excluding difficult moving examples.

The stationary test's criterion is unavailability of every dominant-turn estimate,
not numerical pose accuracy on an extrapolated chain. Endpoint errors are null.
The shared measurement helper's summary maxima of zero refer only to the initial
reference frame, not 119 scored stationary transitions; no subsequent stationary
landmark prediction exists. Raw errors from the previous zero-minimum tests are
retained in `unchanged_raw_stationary_audit` and linked to their frozen report.

![Moving accuracy with unchanged limits](observable_moving_accuracy.png)

![All stationary transitions are unavailable](stationary_observability.png)

## Evidence, scope and limits

The candidate algorithm SHA-256 is
`863fd09cfa629c5b5b8ba7c73963fbe993441b3e3dd989f1e451d0a5f62c9db1`.
The source snapshot, exact candidate-construction code, settings/input hashes,
all rejection details, analytical truth and raw predictions are preserved.
The four NPZs are reused without modification from the extended controls.
Production files were not edited by this test.

This is development evidence after failure inspection. It uses perfect spherical
silhouettes, fixed camera, two textures, one size and short visible moving sequences.
Declaring motion unobservable does not measure exact zero motion. These controls
do not establish performance on oblate fruit, full turns, glare, changing crops,
conveyor motion, defects or commercial grades. Author-label and frozen-conveyor
regressions are still required before retaining the candidate in production.

Reproduce with a fresh label:

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_observable_motion.py --label NEW_OBSERVABLE_MOTION
```
