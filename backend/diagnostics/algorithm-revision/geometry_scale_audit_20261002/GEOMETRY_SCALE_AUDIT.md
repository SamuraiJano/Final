# Fixed-size spheroid setup audit

This diagnostic uses the same frozen 215 conveyor crops and fruit masks as the fixed-input reconstruction comparisons. It estimates only ellipse radii and shared spheroid dimensions. No motion estimator, detector, GrabCut, defect segmenter, image normalization, or grading runs.

The source is frozen production revision `52c13a0452875653fb054053fcc0bdbb4a6ed9cb4227c697be32b62fbe811327`. Selected segments are read from that revision's existing results; a later algorithm revision does not change this historical audit.

The [2021 paper, sections 3.1 and 3.1.2](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) approximates the camera as a parallel projection and fits one shared spheroid size per fruit. For an ideal oblate spheroid, the projected major radius stays approximately equal to its equatorial radius A while the minor radius changes with pose. Thus major-radius variation is a useful consistency check. The paper allows real fruit and silhouettes to depart from the ideal shape.

CV = 100 × population standard deviation / mean major radius. Relative range = 100 × (maximum − minimum) / mean major radius. Values below use original image pixels, not rescaled thumbnails.

| Real track | Views | A / B (px) | Major radius min..max (px) | CV (%) | Range / mean (%) | First-to-last change (%) |
|---|---:|---:|---:|---:|---:|---:|
| 98 | 66 | 75.00 / 61.55 | 70.66..77.18 | 2.28 | 8.70 | +3.92 |
| 1 | 46 | 79.59 / 62.64 | 76.68..81.07 | 1.34 | 5.52 | +1.63 |
| 14 | 44 | 85.52 / 62.55 | 84.36..87.25 | 0.81 | 3.37 | +1.81 |
| 491 | 59 | 66.56 / 58.22 | 64.08..70.94 | 2.35 | 10.31 | -6.75 |

Across all 36 author sequences, the median major-radius CV is 0.92% and maximum is 1.89%. Median relative range is 3.39% and maximum is 7.22%.

Conveyor tracks 98 and 491 exceed the maximum CV in this author sample. Tracks 1 and 14 overlap the author range. This is a discrepancy in two sample tracks, not evidence that every conveyor track violates the model.

| Real track | Selected source frames | Selected CV (%) | Selected range / mean (%) | Maximum major deviation from shared A (%) |
|---|---|---:|---:|---:|
| 98 | 66..85 | 1.69 | 5.85 | 5.79 |
| 1 | 5..16 | 1.32 | 4.92 | 3.66 |
| 14 | 5..9 | 0.62 | 1.79 | 2.02 |
| 491 | 305..308 | 2.43 | 6.69 | 6.58 |

## Interpretation and limits

A changing pixel radius can arise from perspective and distance changes, silhouette extraction error, fruit shape departing from a spheroid, or a combination. This audit has no calibrated camera depth, manual silhouette truth, or known fruit orientation, so it cannot identify which cause dominates. Minor-radius variation alone is expected when an oblate fruit rotates.

The author comparison uses frozen silhouette statistics from the complete 36-sequence benchmark, originally derived from their isolated black-background images. The conveyor comparison uses preserved GrabCut masks. These mask methods and sequence lengths differ. The authors' measurements are a reference distribution, not a ground-truth tolerance or a universal acceptance cutoff.

No geometry change is justified solely by these measurements. A normalization trial would need a known-pose control and manual correspondence evaluation before treating scale variation as the cause of a reconstruction failure.

## Evidence

- `conveyor_radius_traces.png/pdf`: all major/minor radii and selected frame intervals.
- `author_conveyor_scale_comparison.png/pdf`: all 36 author sequences and four real tracks.
- `scale_mask_examples.png/pdf`: actual first/minimum/maximum/last crops with masks and fitted ellipses.
- `report.json`: per-view radii, models, settings, input hashes, and grouped author statistics.
- `sources/`: exact frozen algorithm, author report, paper text, and diagnostic script.

All plots are saved at 300 dpi; source data and source hashes are retained.
