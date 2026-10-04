# Known-area mapping controls

Exact algorithm SHA `6c592861d9318456856f6a05c780f6a8fdd77c4c50286cc0b748ff094f397371`.

Analytically rendered radius-55 sphere, exact 25-degree y rotations, 16 views, true longitude-wedge defect masks. Geometry and motion estimators bypassed only in this control.
No neural models; validates projection, repeated-defect fusion, area normalization and grading arithmetic, not field accuracy.

These controls deliberately substitute known geometry and rotations. They test projection, repeated-defect union, area weighting, coverage gates and grade arithmetic. They do not test rotation estimation, detection, segmentation or field grading accuracy. All 112 rendered input views, truth masks and poses are frozen as hashed NPZ files.

| True defect percentage | Measured percentage | Absolute error, percentage points | Expected / returned grade | Outcome |
|---:|---:|---:|---|---|
| 5 | 5.143654 | 0.143654 | Class 1 / Class 1 | PASS |
| 15 | 15.178671 | 0.178671 | Class 2 / Class 2 | PASS |
| 30 | 30.092759 | 0.092759 | Class 3 / Class 3 | PASS |

Area tolerance: 1 percentage point, declared before execution. Coverage cases retain the existing 375°/270° eligible and 250°/100° partial expectations.
