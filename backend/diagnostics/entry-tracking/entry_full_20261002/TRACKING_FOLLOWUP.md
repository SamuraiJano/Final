# Entry-to-exit tracking validation — 2 October 2026

The detector must start a fruit identity on its first accepted visible entry detection.
That identity must continue while the fruit moves through the frame, including partial
entry and exit views. The revised tracker was tested on all 515 frames
of the original conveyor video, using the user's actual D-FINE detection checkpoint.

## Direct before/after evidence

| Same physical fruit | First published frame (zero-based) | Last seen | Observations |
| --- | ---: | ---: | ---: |
| Original configuration, ID 125 | 55 | 138 | 84 |
| Revised configuration, ID 98 | 51 | 138 | 88 |

The reference fruit was matched to the earlier full application's fruit 125 at
frame 62 by box IoU (0.995268) and inspected in the saved
contact sheet. ID numbers are local to each run; a different number between runs
does not imply an identity switch within a run. The revised ID has an observation
on every frame from 51 through 138.

![Entry, movement and last-seen observations](entry_tracking_comparison.png)

- [Selected-fruit annotated video](entry_to_exit.mp4)
- [All-fruit annotated video, complete original clip](all_fruit_tracking.mp4)
- [300-dpi contact sheet](entry_tracking_comparison.png) and [PDF figure](entry_tracking_comparison.pdf)
- Six full-resolution frame PNGs and original first/last crops in `application_evidence/`.

## What happened, step by step

1. Decode each original video frame; call the trained detector on every frame.
2. Keep the actual predicted boxes, confidence scores and classes at confidence ≥ 0.25.
3. Suppress overlapping same-class duplicate predictions at box IoU > 0.7.
4. Publish accepted new edge detections immediately (`min_track_len=1`), including
   low-confidence partial entries. The stronger 0.7 initialization threshold remains
   for previously unseen interior detections.
5. Use an estimated full-size box for association of clipped observations. A growing
   visible arc otherwise has little overlap with its own earlier detection. The prior
   comes from complete interior fruit sizes, or a circular-cap bootstrap at startup.
6. At an edge transition, recover an existing lost identity only when consecutive
   actual detected boxes have IoU ≥ 0.5 and the best candidate exceeds other eligible
   identities by ≥ 0.15. This addresses a smaller fruit's change from the virtual
   edge box to its complete detected box. It uses the official track's reactivation.
7. Return and retain the actual detector coordinates. Virtual extents never become
   observed pixels, inferred silhouettes or reconstruction inputs.
8. Record first/last seen, frame-by-frame boxes, and first/last source crops BEFORE
   any capture stride, view budget, or silhouette suitability check.
9. Complete-outline views from that same identity may enter reconstruction. Partial
   entry/exit detections still preserve tracking and evidence when unsuitable for
   the paper's spheroid fitting.
10. Save tracking evidence even if reconstruction fails. Future application reports
    expose first/last tracked frame, observed frame count and entry/last-seen crops.
11. Evaluate tracking separately before making any new surface-map or grade claim.

The target entry predictions were inspected in the top-edge region:

| Frame | Actual detector confidence |
| ---: | --- |
| 48 | No accepted target detection in the inspected entry region |
| 49 | No accepted target detection in the inspected entry region |
| 50 | No accepted target detection in the inspected entry region |
| 51 | 0.378 |
| 52 | 0.788 |
| 53 | 0.868 |
| 54 | 0.917 |
| 55 | 0.888 |

This proves tracking from the first accepted detection in this example; it does
not prove detection from the first visible pixel for every fruit. A tracker cannot
assign a measured box before the model produces an accepted detection.

## Full-clip checks

Both configurations received the same cached actual boxes/scores/classes and the
same original image frames. The final diagnostic recomputed detection on all
515 frames; earlier exploratory trials reused a 160-frame cache.

| Tracking consistency indicator | Original | Revised |
| --- | ---: | ---: |
| Published track IDs | 402 | 474 |
| IDs with at most two observations | 11 | 54 |
| Median observations per ID | 84.0 | 86.0 |
| Concurrent output box pairs with IoU > 0.7 | 5 | 0 |

Cross-replay matching considered 379 baseline IDs
with at least 10 matched frames. 7
matched multiple revised IDs substantially; details and thresholds are retained in
`all_frame_tracking_checks.json`. The old tracker is not ground truth. These
numbers can flag fragmentation or disagreement, but do not measure true identity
accuracy, false detections, or unique physical fruit counts. Earlier starts and
weak edge candidates can increase the revised ID count. Full-clip identity
reliability remains unverified without manually labelled tracks.

## Software checks and source provenance

All 30 Python tests passed, including immediate publication, thin low-confidence
entries, mixed fruit size at entry, nearby separate fruit, strong replacement
reactivation, duplicate suppression, and evidence retention despite mapping failure.
The frontend production build and ESLint passed. Exact commands, stdout,
timestamps and source SHA-256 hashes are in `software_checks/`.

The reconstruction/geometry code preceding `class NaartjiePipeline` is byte-identical
to the earlier validated algorithm snapshot. Changes inside the pipeline record
tracking observations and evidence; the tracker adapter and inspection UI changed.
The earlier full grading run and author-data results remain historical evidence,
not tests of the new tracker. No new reconstruction or commercial grading accuracy
result is claimed by this tracking-only diagnostic. The supplied segmentation model
and its weights were not changed or tested in this follow-up.

Original input: `C:\Users\USER\Pictures\Camera Roll\WIN_20260818_13_29_43_Pro.mp4`

Video SHA-256: `dc25964bf6052972cad761b0246f79906e768c6737bf4228ba44711d7272429c`

Detection checkpoint SHA-256: `06f2675d12ec200b4a0419b1bd505c4aa113674c69ab6894684867bd194048b1`

The final replay's frozen source/settings/hashes are in `report.json` and the Python
snapshots alongside it. `trial_decisions.json` retains the successful and rejected
development decisions; all exploratory runs remain in sibling directories.

## Reproduce

From the project root in PowerShell, choose new labels each time:

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_entry_tracking.py --label new_tracking_run --frames 515
./backend/venv/Scripts/python.exe -B backend/audit_entry_tracking.py backend/diagnostics/entry-tracking/new_tracking_run
```

To compare tracking again without rerunning the neural network, add
`--replay-from backend/diagnostics/entry-tracking/entry_full_20261002` to the first
command. Reconstruction and defect grading require separate full-pipeline tests.

Recorded diagnostic time: 2026-10-02T09:12:16.248342+02:00.

## Evidence delivery checks

Both H.264 videos loaded and the selected-fruit video played in a separate headless
Microsoft Edge browser. All three gallery images loaded; no page errors occurred.
`browser_qa.json`, the gallery screenshot, `VIDEO_ENCODING.json` and retained raw
MPEG-4 encodes document rendering and encoding. ffprobe counted exactly 88 selected
frames and 515 full-clip frames at 1920 ? 1080. The two raw `.mpeg4.mp4` encodes remain
in the workspace but are omitted from the ZIP to avoid duplicate movies.

Live-camera timing and identity accuracy were not tested in this follow-up. The
application's live worker processes the latest available camera image, so this
recorded-video test does not establish detection of every live sensor frame. The
earlier full-pipeline throughput was not real-time; the tracking fix does not
change that measurement. Original video and trained weights remain at their
recorded paths and are not duplicated into the evidence ZIP.
