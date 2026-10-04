# Isolated native noise-filter trials

**Neither tested smoothing-only candidate passes all unchanged accuracy controls.**
Both improve long stationary drift while preserving the two tested moving sequences.
Failures are retained; production code was not edited by this validator.

The base algorithm is frozen source
`52c13a0452875653fb054053fcc0bdbb4a6ed9cb4227c697be32b62fbe811327`.
The tested module's `_preprocess` function is replaced at runtime **only for native
resolution**. Float green pixels are Gaussian filtered before the existing sigma-5
high-pass operation. Coarse d4 preprocessing is unchanged.

Two native prefilter widths were specified before running these trials:
sigma `sqrt((4^2-1)/12) = 1.118034` pixels, derived from the variance of four-pixel
box averaging, and sigma 2 pixels. This is an engineering extension, not a filter
prescribed for native resolution by the research paper.

All four exact pixel/pose/landmark NPZs are reused from the frozen extended controls.
The relative path, SHA-256 and full evaluation results are recorded in `report.json`.
Each moving sequence has ten known noncommuting x/y transitions; each stationary
sequence has 120 fixed-pose frames with independently sampled pixel noise.

| Input | Sigma 1.118034 endpoint pose / landmark RMS | Sigma 2 endpoint pose / landmark RMS |
| --- | ---: | ---: |
| Moving texture A | 0.795 deg / 0.721 px | 0.773 deg / 0.701 px |
| Moving texture B | 0.292 deg / 0.266 px | 0.272 deg / 0.248 px |
| Stationary texture A | **6.154 deg / 5.601 px** | **1.973 deg / 1.799 px** |
| Stationary texture B | **1.541 deg / 1.405 px** | 0.742 deg / 0.677 px |

All adjacent measurements return in every trial. Both moving cases pass the same
1-degree endpoint pose and 1-pixel maximum landmark RMS controls. Sigma 1.118034
fails both stationary accuracy controls; sigma 2 fails stationary texture A.
The largest sigma-2 stationary-A errors are 1.989 degrees and 1.814 pixels.
The script exits with status 1 because neither candidate passes all four cases.

Whole-chain motion drift is scored independently of the map selector. Sigma 2
produces no reliable rotating sequence for either stationary texture. Sigma 1.118034
returns a 90.520-degree partial map for stationary A and no reliable rotating map
for B. All stationary grades remain null. These safeguards prevent a grade in
these examples, but do not convert failed raw-motion accuracy into a passing result.

![Prefilter comparisons on identical inputs](native_prefilter_comparison.png)

This is development evidence after observing a failure. The fixed sphere and perfect
silhouettes do not establish conveyor, oblate-fruit, defect or grading accuracy.
The two moving textures alone do not establish general correctness. No failed
transition is rescued, and no threshold or denominator was relaxed to report a pass.

Reproduce while preserving this folder:

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_native_prefilter.py --label NEW_NATIVE_PREFILTER
```
