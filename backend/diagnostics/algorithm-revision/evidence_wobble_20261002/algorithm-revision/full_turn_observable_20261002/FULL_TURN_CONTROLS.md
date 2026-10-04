# Full-turn reconstruction controls

Analytical body-to-camera y rotations, independent body textures and 36 spherical landmarks. Actual spheroid fit, MAD matcher, pose composition, selector and fusion. Perfect sphere masks and explicit zero defect labels. No mocked rotations.

Development synthetic controls selected after small-motion diagnosis. Perfect masks/camera and no glare, translation, perspective or occlusion. All-clear labels test area/class execution, not either model accuracy.

Motion passes require every pair and maximum errors below the predeclared 5° / 5 px limits. A broken chain remains unavailable; later pairs do not repair its score. Clear map execution is scored separately.

| Case | Measured pairs | Max pose ° | Max RMS px | Map status | Grade | Motion / clear map pass |
| --- | --- | --- | --- | --- | --- | --- |
| constant_6deg_texture_a | 60/60 | 25.744 | 17.029 | graded | Class 1 | False / True |
| variable_06_54deg_texture_b | 120/120 | 21.415 | 14.371 | graded | Class 1 | False / True |

![Pose and landmark errors](full_turn_accuracy.png)
