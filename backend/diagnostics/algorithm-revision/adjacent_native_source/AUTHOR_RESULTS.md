# Revised algorithm: author-data regression evidence

This test uses the complete 578-image public author dataset: 36 fruit sequences,
comprising 15 mandarins, 10 oranges and 11 tomatoes, and all 497 published point
correspondences. Silhouettes are derived from the black backgrounds, rather than
ground-truth silhouettes. Labels are used only for scoring predictions. These
datasets were inspected during development, so this is development evidence,
including the historical calibration/evaluation partition, rather than held-out
accuracy.

The revised snapshot is byte-identical to the production algorithm at 12:23:22
on 2 October 2026, with SHA256
`9a0108a98440f3152c78445c9da25cb6747b4eb06478e1e6740cf67d4e82109b`.
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
| Independent adjacent predictions / labels | 458 / 497 | 454 / 497 |
| Independent conditional RMS, px | 5.10288 | 5.12153 |
| Predictions within 5 px / all labels | 367 / 497 | 363 / 497 |
| Labels measurable on retained map poses | 305 / 497 | 348 / 497 |
| Retained-pose conditional RMS, px | 4.80594 | 4.99757 |
| Selected nonadjacent bridges | 20 | 0 |
| Maps passing coverage gates; defect truth absent | 17 | 14 |
| Partial maps / mapping failures | 17 / 2 | 22 / 0 |

![Availability and error counts on the fixed author dataset](author_accuracy_availability.png)

The conditional RMS values use different returned subsets. On the same 454
independent labels for which both algorithms return predictions, RMS is 5.12196
versus 5.12153 px. Only one common prediction changes: tomato `obj0008`, annotation
line 140, improves from 1.80579 to 1.14050 px. Four previously returned low-error
predictions become unavailable, all on near-stationary tomato `obj0009` transitions
13↔14, 15→16 and 16→17. Their previous errors were 1.18896–2.62396 px. This is a
conservative loss of availability, not an overall author-data accuracy improvement.
Maximum returned error remains 35.93046 px, so bad adjacent estimates are not
eliminated by the selection revision.

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

The full benchmark completed in 91.22 seconds. It retains actual source-mask
previews, feature projection images, all 36 surface maps, observed masks,
per-fruit results, all label predictions and failure reasons, source snapshots,
and settings. No detector, segmentation checkpoint or user's conveyor data was
used in this author-data run. There are no author defect masks in this evaluation,
so map coverage eligibility is not measured grade accuracy.

From the project root, use fresh labels to preserve the recorded runs:

```powershell
./backend/venv/Scripts/python.exe -B backend/benchmark_authors.py run --label NEW_AUTHOR_RUN --groups mandarins oranges tomatoes --direction -1 --bidirectional --select-views --minimum-rotation 0 --minimum-longitude 350 --algorithm-snapshot backend/diagnostics/algorithm-revision/adjacent_native_source/algorithm_snapshot.py
./backend/venv/Scripts/python.exe -B backend/validate_author_bridges.py --label NEW_RETAINED_RUN --algorithm-snapshot backend/diagnostics/algorithm-revision/adjacent_native_source/algorithm_snapshot.py --reference-report backend/diagnostics/algorithm-revision/adjacent_native_source/operational_profile_with_native_and_gap1.json
```

The frozen run outputs are:

- [Full benchmark](../../authors-benchmark/runs/adjacent_native_profile_20261002/report.json).
- [Retained-pose audit](../../authors-benchmark/bridge_runs/adjacent_native_retained_20261002/report.json).
- [Matched-label comparison](paired_prediction_comparison.json).
- [Same four historical chain checks](fixed_chain_report.json).
- [Exportable comparison figure](author_accuracy_availability.pdf).
- Exact command text and stdout are stored beside this report.

The method stays based on the [2021 rotation paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 map paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/). It is an
independent implementation. The unavailable author software cannot be claimed to
have been reproduced byte-for-byte or to share the earlier selection defect.
