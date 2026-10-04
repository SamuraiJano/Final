# Longitude-order failure audit — 2 October 2026

This geometry-only test reproduced one failure from the original full conveyor
run, and isolated the exact transition that caused rejection. It used actual
recorded detector boxes and images, with no detector or defect-model inference.
No defect masks or quality grades were fabricated.

## Inputs and controls

- Video: `WIN_20260818_13_29_43_Pro.mp4`, 515 frames, original 1920 × 1080 source.
- Historical run: `f2276fe89ce24fe1a155c228a00e3f17`, fruit ID 491.
- Cached boxes: `entry_full_20261002/baseline_three_detections.json`.
- All 75 cached observations for ID 491 have exactly the same box coordinates as
  the earlier `original_video_symmetric_v1/tracking.json` cache. Maximum coordinate
  difference: 0 pixels. See `cached_box_identity_check.json`.
- Geometry settings reproduce the historical API settings: automatic spheroid,
  image-x rotation, direction +1, bidirectional matching, rotating-view selection,
  350° longitude coverage requirement. The sole override is
  `defect_observations_complete=False`, because this audit supplies no defect evidence.
- Fresh GrabCut masks were extracted with RNG seed 0. This yielded 59 usable views,
  frames 305–364, with frame 330 rejected for silhouette irregularity. The historical
  run captured all 60 views. Masks at the three saved historical checkpoints have
  IoU 0.998622 (frame 305), 0.995312 (335), and 0.999698 (364). This is a fresh-mask
  reproduction, not an exact replay of every original silhouette.

All extracted source crops, binary masks, and compressed arrays are in
`captured_views/`. Video/input/source hashes, rejected-view counts and original
metrics are retained in the JSON reports. Source snapshots freeze the code used.

## Exact failure

The automatic oblate fit has A = 66.560930 pixels and B = 58.215144 pixels
(B/A = 0.874614). The selected sequence is frames 305, 306, 307, 308, 314, 316, 319.

The first selected transition, 305 → 306, has estimated Rodrigues components
x = +3.005253°, y = −5.261839°, z ≈ 0°, with normalized pair error 0.348344.
It passes the current selector's minimum 3° image-x change, while its transverse
component is larger than the configured roller-axis component. Propagating the
tilted fruit frame gives a longitude progress step of **−1.781701°**. The production
ordering check rejects this sequence.

`auto/longitude_trace.json` preserves every selected rotation, error, fruit basis,
propagated axis, camera ray, longitude, delta and selection diagnostic. The
instrumented wrapper observes the production computation; it does not alter it.

![Source crops and exact estimated longitude failure](longitude_failure_comparison.png)

The report figure is available as a 300-dpi PNG and vector PDF. Its source crops
are real observations. Motion curves show algorithm estimates, not manually
labelled rotation truth.

## Isolated shape and rejection experiments

| Same 59 frozen views | Outcome | Estimated rotation | Observed longitude |
| --- | --- | ---: | ---: |
| Automatic oblate baseline | Longitude-order failure | Not returned | Not returned |
| Sphere shape control | Partial map | 123.60° | 214.58° |
| Automatic oblate + experimental axis-dominance rejection | Partial map | 50.40° | 124.58° |

The sphere control avoids this ordering failure but remains below the unchanged
350° longitude requirement. This does not establish that the fruit is spherical.

The experimental rejection wrapper discards a pair if any transverse Rodrigues
component exceeds the configured roller-axis component. It preserves the estimated
rotation for accepted pairs. Thirty pairs were rejected for ID 491. Its outputs
are retained separately under `../rotation_dominance_20261002/legacy491/`.

The same experimental wrapper was also tested on three frozen corrected-tracker
sequences:

| Corrected track | Baseline observed longitude | Experimental observed longitude |
| --- | ---: | ---: |
| 98 | 335.59° | 335.59° |
| 1 | 110.66° | 147.31° |
| 14 | 151.90° | 118.44° |

None becomes coverage eligible. One sequence loses retained extent. Therefore the
guard is an isolated development candidate, not an adopted production fix. No
manually labelled motion is available to establish whether its rejected transverse
rotation is real fruit wobble or a false photometric match. An ordered or larger map
does not prove reconstruction accuracy.

## Decision supported by this audit

The rotating-view selector and map-ordering assumptions need further validation:
positive image-x motion does not ensure forward fruit longitude for this tilted
oblate estimate. The failure is reproducible from the recorded inputs and does
not require changing either trained model.

This test supports investigating the accepted transitions and fitted pose. It does
not support disabling the ordering/coverage gates, forcing every fruit to a sphere,
or adopting the axis-dominance candidate without labelled rotation checks. No
production algorithm or API code was changed in these experiments.

## Reproduce

From the project root, use new labels to preserve existing evidence:

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_longitude_failure.py --label new_longitude_audit --track 491
./backend/venv/Scripts/python.exe -B backend/build_longitude_failure_figure.py backend/diagnostics/algorithm-audit/new_longitude_audit
./backend/venv/Scripts/python.exe -B backend/validate_rotation_dominance.py --label new_dominance_audit --longitude-run new_longitude_audit
```

The dominance test additionally uses the retained frozen corrected-track crops in
`corrected_tracks_20261002/{98,1,14}`. The source video and cached-box paths are
recorded in the script and JSON report; trained checkpoints are not loaded.
