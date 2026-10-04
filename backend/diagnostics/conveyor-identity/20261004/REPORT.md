# Conveyor identity implementation verification

TrackTrack remains unchanged. The new manager is between raw TrackTrack
observations and capture storage, using stable fruit IDs, timestamps, robust
image velocity, global one-to-one association and local order validation.
See [implementation and configuration](../../../CONVEYOR_IDENTITY.md).

## Completed checks

- [Software check summary](../../software-checks/conveyor_identity_20261004_final/summary.json):
  174 Python tests pass (27 new identity tests), frontend build and lint pass.
- [Scope verification](scope_verification.json): all pre-existing module-level
  mapping definitions and the model-loading function are unchanged; the
  detector/segmentation adapter, old identity guard and map visualizer are
  byte-for-byte unchanged.
- [Actual representative run](representative/report.json): 795 decoded frames,
  795 actual D-FINE detector calls, 40,334 observations; no defect, mapping or
  grading execution. Source input is WIN_20260818_13_05_49_Pro.mp4, with FPS
  29.9308014929, source SHA256
  ae12db73e219a666b639725e9c729e9d3f79e80c4fc6c369795187f67acf8198.
- [Initial exact replay](replay_verification.json) and
  [optimized replay](replay_verification_batched.json): one-to-one decisions and
  untouched boxes, scores and classes over every observation. Final replay
  matches all decisions and numeric predictions exactly; 13.2 seconds versus
  the initial 96.2-second manager replay. Timing is development evidence only.

## Diagnostic results and their limits

542 raw IDs became 556 stable segments; 57 were flagged uncertain. There were
95 same-ID recoveries after missed observations and four raw-ID reconnections
at frames 726, 763, 765 and 783. All four are clipped right-edge views, with
little visible fruit. They are plausible-motion links, not independently
verified physical ID switches. Extra segments can result from conservative
abstention rather than additional physical fruit. No accuracy or map-success
percentage is claimed.

The [debug video](representative/identity_debug.mp4) and
[CSV](representative/identity_debug.csv) show the complete original run.
Original source and configuration are frozen beside them. This run predates
the batching optimisation and final text-placement improvement; association
parity was checked against the frozen output afterward. Four short correction
mosaics are also present in this directory. Source timestamps were used for
all 40,334 observations.

The first test run exposed two outdated raw-ID-equals-capture-ID expectations;
the integration assertions now check independent stable IDs and legacy-mode
tests still exercise the unchanged old guard. A new edge test caught scene
learning with insufficient complete history; learning now requires three
complete observations. All checks pass after those fixes.

Per-fruit source views remain chronological. Missing images are not synthesized,
and the mapper's existing frame-gap and measured-rotation checks remain active.
Complete mapping/identity accuracy still requires independent physical-fruit
labels using [the tracking test method](../../../TRACKING_TEST_METHOD.md).
