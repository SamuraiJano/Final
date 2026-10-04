# Final adjacent-motion revision on the authors' data

The exact tested source is `863fd09cfa629c5b5b8ba7c73963fbe993441b3e3dd989f1e451d0a5f62c9db1`.
The datasets contain 578 images in 36 sequences and 497 published feature
correspondences. These are development data already examined during debugging,
not a held-out evaluation. No defect-area or quality-class ground truth is present.

| Measurement | Baseline | Final revision |
| --- | --- | --- |
| Independent adjacent predictions, all 497 labels | 458 | 458 |
| Conditional prediction RMS, original pixels | 5.102881442 | 5.102953939 |
| Labels within 5 pixels, all 497 labels | 367 | 367 |
| Labels available on retained map poses | 305 | 348 |
| Produced maps, 36 sequences | 34 | 36 |
| Maps meeting configured coverage, no defect truth | 17 | 14 |
| Partial maps | 17 | 22 |
| Mapping failures | 2 | 0 |

Independent adjacent-pair accuracy is essentially unchanged, with slightly higher
RMS. The paired comparison found five changed predictions: three improved and two
worsened. An unavailable prediction remains in the denominator and is never
counted as correct. Retained-pose RMS is 4.997927057 pixels for 348 returned labels;
its different availability prevents interpreting it as an unconditional accuracy
improvement over the baseline.

All four previously identified bad skipped-frame chains are excluded. Exclusion
does not mean their endpoint was correctly reconstructed. The final selector uses
adjacent original frames, native rechecks for small motion, and common longitude
coordinates for selection and fusion. Rejecting missing or unobservable motion
increases partial maps in some sequences.

![Accuracy and availability](author_accuracy_availability.png)

The complete [independent results](../../authors-benchmark/runs/adjacent_observable_profile_20261002/report.json),
[retained-pose results](../../authors-benchmark/bridge_runs/adjacent_observable_retained_20261002/report.json),
[paired predictions](paired_prediction_comparison.json), and
[fixed-chain audit](fixed_chain_report.json) preserve settings, labels, errors and
source hashes. The frozen source and command records are in this directory.

The authors' repositories provide data and labels. This is an independent
implementation of their [2021 rotation method](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 surface mapping method](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/),
with documented engineering adaptations for this conveyor.
