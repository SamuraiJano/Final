# Continued algorithm tests: development supplement

Built 2026-10-02T20:19:22.297891+02:00. **No final algorithm is declared operational or accuracy validated by this supplement.**
It preserves later experiments alongside the earlier sealed evidence. The source 951/native8
profile is known to fail horizontal full turns; extending rechecks to 20 improves that
synthetic case but regresses author availability and the fixed real conveyor examples.
Any earlier description of that phase as stable or final is superseded by these failures.
Paper geometry, actual models and historical results remain separate from this control evidence.

## What was tested, and why

1. Freeze inputs, true body rotations, projected landmarks and acceptance limits before estimating motion.
2. Run the actual sphere fit, two-axis matcher, pose propagation, adjacent selector and map fusion.
3. Score prediction availability together with errors. Rejected motion is unavailable, never zero-error.
4. Compare all author labels and common returned labels before adopting a setting.
5. Replay the same real crops/masks across candidates. Such replays check behavior; they have no field pose truth.
6. Preserve each source snapshot, parameters, inputs, measurements and exported images, including failures.

The original horizontal twelve-degree full-turn profile returns all 60 pairs yet
accumulates 11.092/6.189 degrees error and produces Class 1 maps. The native20 profile
passes that ideal full-turn control at 2.063/0.936 degrees, but author predictions
fall 462→416 and retained predictions 368→287. Common-label RMS worsens in both
audits. Fixed real track 98 coverage falls 360→188.390 degrees. This settings-only
trial is not an accepted solution. [Exact unchanged comparison](algorithm-revision/native_recheck_author_comparison_20261002/NATIVE_RECHECK_COMPARISON.md).

## Fixed-camera illumination: the same twelve independent scenes

Two analytical textures use additive linear lighting and multiplicative Lambertian
lighting, both fixed in camera coordinates. Each has one complete 360-degree turn,
one short known x/y chain and one 120-frame noisy stationary sequence. Perfect
masks and known geometry isolate matching from detection/segmentation. These
are development controls, not held-out real fruit or a full camera simulation.

The input manifest was frozen at 2026-10-02T15:55:37.863214+02:00, SHA256 `7f52fcc044edcfd741e62bba5dbbcb2746456f13329dab602f0cbafbacc14e1f`.
No saturation is introduced. Full turns require all 30 pairs and errors ≤5 degrees/5 pixels.
Short chains require all 10 pairs, endpoint ≤1 degree and maximum landmark RMS ≤1 pixel.
Stationary controls require 119 unavailable pairs, a null endpoint and no map or grade.
These original limits are unchanged for all five profiles.

| Exact source/profile | Passing scenes | False stationary returns /476pairs | Failed scenes that still produce a class | Source SHA256 prefix |
| --- | --- | --- | --- | --- |
| Green 951 / native20 | 10/12 | 0 | 2 | 951b55a4912d |
| Additive plane f03 | 9/12 | 1 | 2 | f03b2ec019d7 |
| Aligned fast bf25 | 7/12 | 5 | 2 | bf25b9d4a9ed |
| Aligned contrast d3bf | 11/12 | 0 | 1 | d3bf284a5013 |
| Aligned full pattern 9a5a | 10/12 | 0 | 1 | 9a5a3e13c8b9 |

![All independently rendered scene outcomes](camera_shading_comparison.png)
[300-dpi PDF](camera_shading_comparison.pdf), [exact comparison](shading_comparison.json).

No profile passes all twelve controls. Contrast d3bf passes 11/12, but the Lambertian
texture A complete turn remains incorrect at 8.387 degrees/5.676 pixels while returning
all 30 pairs, 360 degrees observed longitude and Class 1. Plane f03 and fast bf25 also
produce false stationary maps. The stationary helper's reference-scaffold zero
maxima are not estimated zero motion and are not used to claim accuracy.

![Actual maps that pass coverage but fail known motion](false_eligible_maps.png)
[Exportable map comparison](false_eligible_maps.pdf), [image provenance](figure_provenance.json).
These Class 1 outputs use supplied all-clear defect observations to test arithmetic.
They are not predictions from the user's segmentation model or verified fruit grades.

The aligned f4 and fast bf25 variants pass their ideal twelve-degree turns. The frozen
f4 runs have no separate twelve-scene shading suite; the fast bf25 results cannot be
silently assigned to f4. The full nine-sample pattern source 9a5a passes 10/12:
Lambertian texture A fails both the complete turn (7.257 degrees /4.915 pixels)
and short chain (1.114-degree endpoint /1.402-pixel maximum landmark RMS).
It returns no stationary motion in all 476 pairs. Its numerical equivalence
controls pass; numerical invariance is not ground-truth motion accuracy.

An independently rendered fresh texture C was prepared with frozen acceptance
before estimation. Source 9a5a passes both twelve-degree turns under linear and
Lambertian lighting, maximum 0.606/0.581 degrees and 0.411/0.351 pixels. These two
passes remain separate from its texture-A failures. [Fresh-texture record](algorithm-revision/fresh_texture_pattern20_20261002/FRESH_TEXTURE_CONTROL.md).

The detrended nine-sample source 6f2c passes numerical equivalence and local
affine-gradient invariance checks. Its motion, real-crop and author trials are
still being evaluated outside this bounded supplement. Those numerical results
do not establish reconstruction accuracy or production adoption.

## Same real crops, selected development cases

| Frozen trial | Track | Retained views | Observed longitude, deg | Status |
| --- | --- | --- | --- | --- |
| fixed_refine20_conveyor | 98 | 8 | 188.390 | insufficient_longitude_coverage |
| fixed_refine20_conveyor | 1 | 7 | 127.186 | insufficient_longitude_coverage |
| fixed_refine20_conveyor | 14 | 4 | 103.717 | insufficient_longitude_coverage |
| fixed_refine20_conveyor | 491 | 3 | 133.174 | insufficient_longitude_coverage |
| fixed_plane | 98 | 7 | 184.576 | insufficient_longitude_coverage |
| fixed_plane | 1 | 7 | 130.778 | insufficient_longitude_coverage |
| fixed_plane | 14 | 3 | 101.710 | insufficient_longitude_coverage |
| fixed_plane | 491 | 3 | 133.174 | insufficient_longitude_coverage |
| fixed_aligned | 98 | 7 | 183.051 | insufficient_longitude_coverage |
| fixed_aligned | 1 | 7 | 130.060 | insufficient_longitude_coverage |
| fixed_aligned | 14 | 3 | 102.379 | insufficient_longitude_coverage |
| fixed_aligned | 491 | 4 | 158.091 | insufficient_longitude_coverage |
| fixed_aligned_bound20 | 98 | 24 | 360.000 | missing_defect_masks |
| fixed_aligned_bound20 | 1 | 7 | 130.060 | insufficient_longitude_coverage |
| fixed_aligned_bound20 | 14 | 2 | 109.071 | insufficient_longitude_coverage |
| fixed_aligned_bound20 | 491 | 4 | 158.091 | insufficient_longitude_coverage |
| fixed_aligned_fast_bound20 | 98 | 24 | 360.000 | missing_defect_masks |
| fixed_aligned_fast_bound20 | 1 | 7 | 130.060 | insufficient_longitude_coverage |
| fixed_aligned_fast_bound20 | 14 | 2 | 109.071 | insufficient_longitude_coverage |
| fixed_aligned_fast_bound20 | 491 | 4 | 158.091 | insufficient_longitude_coverage |
| fixed_aligned_contrast20 | 98 | 24 | 360.000 | missing_defect_masks |
| fixed_aligned_contrast20 | 1 | 5 | 114.251 | insufficient_longitude_coverage |
| fixed_aligned_contrast20 | 14 | 2 | 109.071 | insufficient_longitude_coverage |
| fixed_aligned_contrast20 | 491 | 2 | 122.005 | insufficient_longitude_coverage |
| fixed_pattern20_conveyor | 98 | 13 | 257.797 | insufficient_longitude_coverage |
| fixed_pattern20_conveyor | 1 | 4 | 113.533 | insufficient_longitude_coverage |
| fixed_pattern20_conveyor | 14 | 2 | 99.033 | insufficient_longitude_coverage |
| fixed_pattern20_conveyor | 491 | 4 | 160.668 | insufficient_longitude_coverage |

The four tracks contain 215 original detector/tracker crops and extracted fruit masks.
No detector, tracker, GrabCut or defect-model call is repeated in these geometric
replays. A 360-degree map with missing_defect_masks receives no grade. A larger
connected segment does not establish accurate poses. No independently labelled
field rotation, surface map or grade truth is available for these cases.

## Author-data scope must stay explicit

The native20 comparison includes all 36 author sequences and 497 labels. The fast bf25
trial includes **only 15 mandarin sequences and 132 labels**. It returns
120/132 at conditional RMS
5.10574 pixels, with
102/132 within 5 pixels.
The 39.55996-pixel error remains included. This is not an all-36-sequence benchmark;
no orange/tomato outcome is claimed for bf25. Source/profile differences prevent
using these partial author results as contrast d3bf or pattern 9a5a validation.
All development images have been inspected and are not held-out evaluation.

## Original video and incomplete API execution

Archived full_hybrid_wobble_20261002 state: **interrupted_incomplete**.
No completed video outcome is claimed unless its completed summary and saved
execution snapshots exist. Saved frame counts or individual track results are not
a final report. The service was absent when work resumed after the credit interruption;
this supplement does not infer a cause. [Archived API state](api_run_state.json).
Recovery and any resumed/replayed job must be recorded under its own provenance.

## Report evidence and reproduction

Every copied payload has a SHA256 manifest. The 12 scene input NPZ files, original
renderers, frozen candidate sources, actual map PNGs, 300-dpi charts/PDFs, author
point overlays, unchanged reports and parameter records are retained. Duplicate
NPZ files are stored once by SHA256; [input_references.json](input_references.json)
resolves historical aliases. Original model checkpoints and full datasets are not
duplicated. [Frozen source records](source_records.json) identify every trial.

```powershell
./backend/venv/Scripts/python.exe -B backend/build_algorithm_development_evidence.py --label development_followup_20261002 --refresh
```

This script copies evidence; it does not rerun inference. Individual frozen scripts
and their recorded commands supply reproduction. This package documents both
successful controls and failed hypotheses. It is a development supplement rather
than a certificate of real conveyor grading accuracy.
