# Exact original full-turn input replay

Exact archived synthetic development inputs and declared limits. Actual matcher and mapping; no corrected or extrapolated poses. Not field/model accuracy.

Source `c5c7e7292af1ef67eeca476ed99389b96f8aa17fd2d3814cbe7934934be2b911`. Archived inputs copied byte-for-byte from `full_turn_hybrid_20261002`; original hashes and 5°/5px/full-pair/class acceptance retained.

| Case | Measured pairs | Maximum pose error (degrees) | Maximum visible landmark RMS (pixels) | Outcome |
|---|---:|---:|---:|---|
| constant_6deg_texture_a | 60/60 | 0.030699 | 0.020780 | PASS |
| variable_06_54deg_texture_b | 120/120 | 0.104460 | 0.070915 | PASS |

Perfect sphere masks and known-clear defect masks isolate geometry and mapping execution. These controls do not establish real conveyor grading or neural-model accuracy.
