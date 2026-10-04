# Fresh texture C motion control

Limited fresh synthetic control after candidate design; not a formally held-out dataset or neural-model/field-grade accuracy test. One new texture, two lighting scenes, ideal sphere/masks, no translation/perspective/occlusion/specular glare. No tuning based on this control's outputs.

Seed `20261002771` and both scenes' waveform, known motion, images, truth and 5°/5px acceptance were frozen before candidate loading. Source `9a5a3e13c8b9200958c678110640153022dbe8e59d4e3559ea1743ef579b5067`; no subsequent tuning.

| Camera-fixed lighting | Measured pairs | Maximum pose error (degrees) | Maximum visible landmark RMS (pixels) | Outcome |
|---|---:|---:|---:|---|
| lambertian_multiplicative | 30/30 | 0.580875 | 0.351225 | PASS |
| linear_additive | 30/30 | 0.605694 | 0.411123 | PASS |

All-clear maps exercise mapping/class arithmetic only; they do not prove segmentation or real fruit grade accuracy. Complete measured coverage does not itself prove correct pose.
