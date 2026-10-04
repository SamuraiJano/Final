# Native recheck trigger: same-label audit

Only the native recheck trigger changes from8 to20degrees. Exact source951, transverse20, residual0.58 and all other settings stay fixed. Both sources score the same original497labels.

| Evaluation | Common returned labels | Native8 RMS, px | Native20 RMS, px | Newly returned | Lost |
| --- | --- | --- | --- | --- | --- |
| independent_pairs | 416 | 5.30578 | 5.37020 | 0 | 46 |
| retained_segment | 285 | 5.64601 | 5.74345 | 2 | 83 |

Native20 independent availability drops462→416, within5 drops373→338; overall conditional RMS5.39868→5.37020 conceals the smaller returned subset. Retained availability drops368→287, within5 drops296→230 and conditional RMS5.60733→5.72502. Both common-label RMS comparisons worsen. Development data, not held-out or conveyor-grade accuracy. Failures remain counted.
