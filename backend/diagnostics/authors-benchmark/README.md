# Reconstruction testing evidence

The subsequent [algorithm decision audit](../algorithm-audit/decision_20261002/ALGORITHM_DECISION.md)
finds errors in accepted skipped-frame matches and reproduces an actual conveyor
ordering failure. Its [gallery](../algorithm-audit/decision_20261002/index.html) and
[evidence ZIP](../algorithm-audit/decision_20261002/algorithm_audit_evidence.zip)
retain controls and experimental safeguards. The independent adjacent-point
benchmark alone does not validate the added view-selection stage.

The latest results are in [the 2 October validation report](evidence_20261002/VALIDATION_REPORT.md).
Open the [figure gallery](evidence_20261002/index.html), [PDF figures](evidence_20261002/validation_figures.pdf),
or [complete report evidence ZIP](evidence_20261002/report_evidence.zip).

**The root `REPORT.md` is the frozen initial failure audit.** Its statement that no
maps were produced describes the original algorithm, not the revised implementation.
It remains unchanged to preserve the before/after evidence.

- `DEVELOPMENT_LOG.md`: successful and rejected experiments, limits and decisions.
- `source_manifest.json` and `data/`: pinned author files, checksums and licenses.
- `runs/`: each reference-data experiment, with source, settings, labels and results.
- `mapping_runs/`: analytical coordinate controls and author-map comparisons.
- `synthetic_runs/`: known defect areas and coverage controls.
- `optimization_runs/`: batched/scalar search parity and timing.
- Sibling `pipeline-runs/`, `replay-runs/`, `api-runs/`, `software-checks/`, `ui-checks/`:
  real models, failed trials, full application runs and software/UI evidence.

Results are development evidence, not a claim of production grading accuracy.
Use a new label for each experiment; do not overwrite historical runs.

The later [entry-to-exit tracking follow-up](../entry-tracking/entry_full_20261002/TRACKING_FOLLOWUP.md)
tests the revised tracker on all 515 original frames. Its [video gallery](../entry-tracking/entry_full_20261002/index.html)
shows actual first-entry/last-seen observations. The earlier report and sealed ZIP
remain the evidence for the old tracker's full grading run and author reconstruction tests.
The [tracking evidence ZIP](../entry-tracking/entry_full_20261002/tracking_evidence.zip)
retains the new report, original image evidence, annotated videos, predictions and checks.
