# Extended known-motion controls

The frozen adaptive algorithm improves the two tested moving sequences but fails
the stationary-noise accuracy controls. These failures remain part of the evidence.
No production algorithm or threshold was changed by this validator.

The tested algorithm SHA-256 is
`52c13a0452875653fb054053fcc0bdbb4a6ed9cb4227c697be32b62fbe811327`.
`report.json` retains exact settings, rendered input hashes, measurement details,
predicted landmarks and independently calculated truth.

## Method

Two different analytic body textures are rendered on a radius-55 sphere with a
perfect silhouette. Moving sequences contain 11 images and ten known, variable
increments: forward y rotation from 0.5 to 1.5 degrees per image, combined with
transverse x wobble from -0.45 to +0.40 degrees. Each true incremental matrix is
calculated independently from the axis-angle formula. True poses are the ordered
product of those matrices, rather than the output of the image matcher.

Six body landmarks stay on the visible surface. Their image coordinates are
calculated directly from the true 3D poses. Estimated landmarks are lifted using
the fitted sphere and propagated using the measured rotations. The resulting
3D pose error and six-landmark pixel RMS compare predictions with independent
truth. Failed measurements would make a chain unavailable; no gap is interpolated.

Each stationary sequence contains **120 frames**, matching the configured maximum
captured views per fruit. The underlying body and camera remain fixed, with
independent Gaussian pixel noise of standard deviation 2 grey levels. Texture A
uses random seed 391 and texture B seed 923. Actual inputs and truth are preserved
in the four `*_inputs.npz` files.

Both coarse d4 and adaptive d4-to-d1 matching receive identical rendered pixels
and perfect silhouettes. Native refinement preserves the physical high-pass filter
width, as implemented in this frozen source. Defect inference is absent, and all
grades must remain null. The 1-degree pose and 1-pixel landmark tolerances are
development engineering controls, not accuracy specifications from the paper.

## Results

All ten moving pairs and all 119 stationary pairs return measurements in both
variants. This availability does not establish their correctness.

| Input | Coarse endpoint pose error | Adaptive endpoint pose error | Coarse endpoint landmark RMS | Adaptive endpoint landmark RMS |
| --- | ---: | ---: | ---: | ---: |
| Moving with x/y wobble, texture A | 4.994 deg | 0.762 deg | 4.538 px | 0.691 px |
| Moving with x/y wobble, texture B | 4.959 deg | 0.278 deg | 4.503 px | 0.254 px |
| Stationary with noise, texture A | 2.089 deg | **59.768 deg** | 1.905 px | **45.540 px** |
| Stationary with noise, texture B | 0.636 deg | **7.388 deg** | 0.580 px | **6.718 px** |

The largest intermediate adaptive error for stationary B is 9.041 degrees and
8.212 pixels. Both moving controls meet the declared accuracy limits; both
stationary accuracy controls fail. Therefore `all_controls_passed` is false and
the validator exits with status 1.

The false whole-chain motion above is an independent matcher test, **not the
rotation span of the final selected map**. The map selector splits the noisy
chains and retains shorter segments. Adaptive stationary A produces a partial map
covering 94.682 degrees of numerical observed longitude; B covers 90.520 degrees.
Neither reaches the 350-degree gate or receives a grade. Coarse stationary inputs
produce no reliable rotating sequence. Thus the grading gate prevents a full-turn
claim in these controls, while the matcher still returns incorrect stationary
motion and inaccurate partial reconstruction.

![Pose and landmark errors, including the failed stationary controls](extended_motion_accuracy.png)

Figure 1. Actual measured adjacent rotations are propagated through each complete
sequence. Ground truth is defined independently by the renderer. The third and
fourth rows expose stationary drift that the short moving examples do not reveal.

![Two different textures and independently projected endpoints](extended_landmark_comparison.png)

Figure 2. Green points are independently calculated landmark truth; red crosses
are predictions after the ten known x/y transitions. Errors use original pixel
coordinates, before figure resizing.

## Interpretation and limits

These controls show that native resolution can recover small real motion while
also interpreting pixel noise as motion. Fractional-coordinate interpolation
averages neighboring target noise, which may bias the native objective toward
small nonzero shifts; this is a possible mechanism, not a proved diagnosis.
Residual acceptance alone does not distinguish stationary noise from real rolling.

The results cover two synthetic textures, perfect silhouettes, one sphere size,
fixed camera and short visible motion. They do not establish performance under
conveyor lighting, glare, occlusion, full rotations, changing crops or oblate
geometry. A partial map and a withheld grade cannot prove geometric accuracy.
The existing running conveyor job uses its own frozen source snapshot and must
not be described as testing a later source change.

Reproduce with a new label to preserve this frozen evidence:

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_extended_motion_controls.py --label NEW_EXTENDED_CONTROLS --algorithm-snapshot backend/diagnostics/algorithm-revision/motion_resolution_scaled_20261002/algorithm_snapshot.py
```

The PNG and PDF figures were visually checked for readable labels, correct
legend-to-line assignments and visible analytical/predicted landmark markers.
