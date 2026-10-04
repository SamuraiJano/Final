# Exact original full-turn input replay

Exact archived synthetic development inputs and declared limits. Actual matcher and mapping; no corrected or extrapolated poses. Not field/model accuracy.

Source `6f2c56ac6edbdc3cc72fecd995055f01a6690113c54115c304b7e29595c20961`. Archived inputs copied byte-for-byte from `full_turn_hybrid_20261002`; original hashes and 5°/5px/full-pair/class acceptance retained.

| Case | Measured pairs | Maximum pose error (degrees) | Maximum visible landmark RMS (pixels) | Outcome |
|---|---:|---:|---:|---|
| constant_6deg_texture_a | 60/60 | 3.000478 | 2.036299 | PASS |
| variable_06_54deg_texture_b | 120/120 | 3.138168 | 2.125633 | PASS |

Perfect sphere masks and known-clear defect masks isolate geometry and mapping execution. These controls do not establish real conveyor grading or neural-model accuracy.
