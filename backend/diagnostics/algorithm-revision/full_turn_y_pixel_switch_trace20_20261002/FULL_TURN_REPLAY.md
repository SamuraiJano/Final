# Exact original full-turn input replay

Exact archived synthetic development inputs and declared limits. Actual matcher and mapping; no corrected or extrapolated poses. Not field/model accuracy.

Source `50bdd78eafcc5581d0368353c9996c2f95823c69f734dac6f778dc82f22c815d`. Archived inputs copied byte-for-byte from `full_turn_hybrid_20261002`; original hashes and 5°/5px/full-pair/class acceptance retained.

| Case | Measured pairs | Maximum pose error (degrees) | Maximum visible landmark RMS (pixels) | Outcome |
|---|---:|---:|---:|---|
| constant_6deg_texture_a | 60/60 | 0.024543 | 0.016318 | PASS |
| variable_06_54deg_texture_b | 120/120 | 0.589330 | 0.402015 | PASS |

Perfect sphere masks and known-clear defect masks isolate geometry and mapping execution. These controls do not establish real conveyor grading or neural-model accuracy.
