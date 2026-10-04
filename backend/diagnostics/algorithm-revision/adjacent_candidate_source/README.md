# Isolated adjacent-motion candidate

This folder is an experimental algorithm snapshot. It does not change the running
backend or historical results. The original paper's geometry, texture search,
MAD objective and surface fusion equations remain unchanged.

The candidate measures each adjacent input pair once, with zero motion allowed
in the pair search. A failed estimate, a source-frame gap larger than
`maximum_view_index_gap`, or a total three-dimensional angle below 0.25 degrees
ends the connected sequence. Set `maximum_view_index_gap=1` when the source views
are consecutive video frames. Unlike the earlier setting, this limit applies to
source frame numbers, rather than positions in the list of surviving crops.

The candidate retains valid motion below the old three-degree selection threshold.
It does not sum sub-quarter-degree changes into apparent full-turn coverage, and
does not reconnect across rejected pairs. This is deliberately conservative: real
motion smaller than the resolution gate may exist, so splitting it reduces
availability and does not prove the fruit was stationary.

Selection and fusion share `_map_trajectory`, an extraction of the original
pose propagation and fruit-fixed longitude computation. After fitting the exact
subset model, longitude changes outside the existing 0.25 to `max_pair_angle_deg+12`
degree fusion bounds split the segment. Each child is checked again because its
reference ellipse can change. The longest ordered longitude span wins. This span
is not observed pixel coverage; the final map still measures coverage from actual
supported pixels and applies the existing grade gates.

This candidate is a conservative reference, not an accuracy claim. The current
residual gate can still accept wrong adjacent matches. Longitude consistency
tests suitability for fusion and does not supply motion truth. A complete-looking
map or larger longitude span alone cannot validate geometric accuracy.

Run its focused controls from the project root:

```powershell
./backend/venv/Scripts/python.exe -B backend/diagnostics/algorithm-revision/adjacent_candidate_source/test_candidate.py
```

The controls cover valid two-degree motion, failed-pair separation, missing
source-frame gaps, positive stationary jitter, ordered noncommuting matrix
composition, and an oblate fruit where positive rolling-axis motion plus transverse
motion makes the surface longitude go backwards. Motion is mocked in selector
controls; this does not measure texture estimator or field grading accuracy.
