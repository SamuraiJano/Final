# Fresh texture C motion control

Limited fresh synthetic control after candidate design; not a formally held-out dataset or neural-model/field-grade accuracy test. One new texture, two lighting scenes, ideal sphere/masks, no translation/perspective/occlusion/specular glare. No tuning based on this control's outputs.

Seed `20261002771` and both scenes' waveform, known motion, images, truth and 5°/5px acceptance were frozen before candidate loading. Source `6f2c56ac6edbdc3cc72fecd995055f01a6690113c54115c304b7e29595c20961`; no subsequent tuning.

| Camera-fixed lighting | Measured pairs | Maximum pose error (degrees) | Maximum visible landmark RMS (pixels) | Outcome |
|---|---:|---:|---:|---|
| lambertian_multiplicative | 30/30 | 2.507859 | 1.701989 | PASS |
| linear_additive | 30/30 | 1.525655 | 1.035497 | PASS |

All-clear maps exercise mapping/class arithmetic only; they do not prove segmentation or real fruit grade accuracy. Complete measured coverage does not itself prove correct pose.
