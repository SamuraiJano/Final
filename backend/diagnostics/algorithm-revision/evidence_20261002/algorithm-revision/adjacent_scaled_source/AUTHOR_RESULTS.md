# Revised algorithm: author-data regression evidence

This test uses the complete 578-image public author dataset: 36 fruit sequences,
comprising 15 mandarins, 10 oranges and 11 tomatoes, and all 497 published point
correspondences. Silhouettes are derived from the black backgrounds, rather than
ground-truth silhouettes. Labels are used only for scoring predictions. These
datasets were inspected during development, so this is development evidence,
including the historical calibration/evaluation partition, rather than held-out
accuracy.

The revised snapshot is byte-identical to the production algorithm at 13:00:55
on 2 October 2026, with SHA256
`52c13a0452875653fb054053fcc0bdbb4a6ed9cb4227c697be32b62fbe811327`.
It keeps the paper's spheroid fitting and MAD texture search, checks small
successful coarse movements again at native image resolution, uses consecutive
source-frame measurements, and checks the exact map longitude trajectory before
fusion. Failed and unobservable transitions end the connected sequence. The
source snapshot stays frozen if production changes later.

The saved operational author profile remains the same: automatic sphere/oblate,
x rolling axis, negative direction, bidirectional MAD, downsample factor four,
selection enabled, no minimum rolling-angle sum, and at least 350 degrees of
observed longitude for coverage eligibility. The revised profile adds the native
small-motion recheck and changes the maximum source-frame gap to one.

| Measured indicator | Earlier operational algorithm | Revised snapshot |
| --- | ---: | ---: |
| Images / sequences / labels | 578 / 36 / 497 | 578 / 36 / 497 |
| Geometry fits | 36 | 36 |
| Maps produced, including partial | 34 | 36 |
| Independent adjacent predictions / labels | 458 / 497 | 458 / 497 |
| Independent conditional RMS, px | 5.10288 | 5.10106 |
| Predictions within 5 px / all labels | 367 / 497 | 367 / 497 |
| Labels measurable on retained map poses | 305 / 497 | 348 / 497 |
| Retained-pose conditional RMS, px | 4.80594 | 4.99775 |
| Selected nonadjacent bridges | 20 | 0 |
| Maps passing coverage gates; defect truth absent | 17 | 14 |
| Partial maps / mapping failures | 17 / 2 | 22 / 0 |

![Availability and error counts on the fixed author dataset](author_accuracy_availability.png)

The independent comparison now uses exactly the same 458 returned labels in both
algorithms: none is gained or lost. Five predictions change, all small-motion
cases, and all five improve on these development labels. Their individual values
are retained in [paired_prediction_comparison.json](paired_prediction_comparison.json).
Overall RMS changes only from 5.10288 to 5.10106 px, and the count within five pixels
stays 367/497. This supports preservation of author-data performance; it is not
an independently demonstrated general accuracy improvement. Maximum returned error
remains 35.93046 px, so bad adjacent estimates are not eliminated by the revision.

The retained-map-pose conditional RMS values use different returned subsets
(305 versus 348). The revised map supports more published labels, but its conditional
RMS is 4.99775 versus 4.80594 px. These are availability and error measurements,
not equivalent fixed-subset accuracy comparisons. Maps passing coverage gates
also decrease from 17 to 14, while numerical mapping failures decrease from two
to zero. Additional partial maps do not demonstrate accurate complete reconstruction.

### Native filtering correction and rejected candidate

At quarter image size, a high-pass Gaussian sigma of 1.25 corresponds to five
original image pixels. The final native-resolution recheck therefore uses sigma
five, preserving the physical texture scale. The first native candidate incorrectly
kept sigma 1.25 at full image size, changed the selected texture, and failed the
known-motion/landmark controls. It also lost four low-error author predictions.
That candidate remains frozen in `../adjacent_native_source` as rejected development
evidence. The final physical-width correction restores all four predictions. Its
known-motion results are documented separately in
[the scaled synthetic controls](../motion_resolution_scaled_20261002/report.json).
This author report measures only author correspondence and map availability.

## The same four historical failed chains

The earlier audit identified four accepted nonadjacent bridges with errors
34.05832, 41.37993, 17.03898 and 16.41084 px. The revised selector creates no
replacement bridges and excludes all four historical endpoint connections from
its chosen connected segments. The check explicitly tries those same endpoints
even when intermediate views might have survived. None returns a prediction.

This establishes that these false connections are no longer used in the chosen
maps. It does **not** establish accurate reconstructed motion for the excluded
fruit surfaces, nor zero remaining geometric error. The four chains are correlated
with original adjacent annotations and are not an independent accuracy sample.
Original annotation line provenance and both endpoint coordinates remain in
[fixed_chain_report.json](fixed_chain_report.json).

## Reproduce and inspect the retained artifacts

The full benchmark completed in 101.47 seconds. It retains actual source-mask
previews, feature projection images, all 36 surface maps, observed masks,
per-fruit results, all label predictions and failure reasons, source snapshots,
and settings. No detector, segmentation checkpoint or user's conveyor data was
used in this author-data run. There are no author defect masks in this evaluation,
so map coverage eligibility is not measured grade accuracy.

From the project root, use fresh labels to preserve the recorded runs:

```powershell
./backend/venv/Scripts/python.exe -B backend/benchmark_authors.py run --label NEW_AUTHOR_RUN --groups mandarins oranges tomatoes --direction -1 --bidirectional --select-views --minimum-rotation 0 --minimum-longitude 350 --algorithm-snapshot backend/diagnostics/algorithm-revision/adjacent_scaled_source/algorithm_snapshot.py
./backend/venv/Scripts/python.exe -B backend/validate_author_bridges.py --label NEW_RETAINED_RUN --algorithm-snapshot backend/diagnostics/algorithm-revision/adjacent_scaled_source/algorithm_snapshot.py --reference-report backend/diagnostics/algorithm-revision/adjacent_scaled_source/operational_profile_with_native_and_gap1.json
```

The frozen run outputs are:

- [Full benchmark](../../authors-benchmark/runs/adjacent_scaled_profile_20261002/report.json).
- [Retained-pose audit](../../authors-benchmark/bridge_runs/adjacent_scaled_retained_20261002/report.json).
- [Matched-label comparison](paired_prediction_comparison.json).
- [Same four historical chain checks](fixed_chain_report.json).
- [Exportable comparison figure](author_accuracy_availability.pdf).
- Exact command text and stdout are stored beside this report.

The method stays based on the [2021 rotation paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 map paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/). It is an
independent implementation. The unavailable author software cannot be claimed to
have been reproduced byte-for-byte or to share the earlier selection defect.
