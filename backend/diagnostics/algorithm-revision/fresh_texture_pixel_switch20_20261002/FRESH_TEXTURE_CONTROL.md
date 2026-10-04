# Fresh texture C motion control

Limited fresh synthetic control after candidate design; not a formally held-out dataset or neural-model/field-grade accuracy test. One new texture, two lighting scenes, ideal sphere/masks, no translation/perspective/occlusion/specular glare. No tuning based on this control's outputs.

Seed `20261002771` and both scenes' waveform, known motion, images, truth and 5°/5px acceptance were frozen before candidate loading. Source `d57078ace090cd6aedaad97a614d0a3bb9d8045c2896141400c052e8aa7ce12c`; no subsequent tuning.

| Camera-fixed lighting | Measured pairs | Maximum pose error (degrees) | Maximum visible landmark RMS (pixels) | Outcome |
|---|---:|---:|---:|---|
| lambertian_multiplicative | 30/30 | 0.039618 | 0.026891 | PASS |
| linear_additive | 30/30 | 0.021738 | 0.013280 | PASS |

All-clear maps exercise mapping/class arithmetic only; they do not prove segmentation or real fruit grade accuracy. Complete measured coverage does not itself prove correct pose.
