# Preserved fruit texture, coloured defects and an 80% coverage target

The visualization shows the full naartjie map with each defect category highlighted,
and proposed at least 80% coverage. The app now offers **Defects** and
**Original** views of the same map. Defects are tinted over the original texture;
they are not removed or replaced with clean skin. All original maps and binary
masks remain available. The full map canvas is retained. Unobserved regions
remain unknown, rather than fabricated surface.

| Predicted defect category | Display colour |
| --- | --- |
| Dark marking | Cyan `#38bdf8` |
| Light brown discolouration | Yellow `#facc15` |
| Open skin | Red `#ef4444` |
| Skin wrinkling | Purple `#a78bfa` |
| Wind scarring | Green `#4ade80` |

The overlay uses 45% colour and 55% original texture on observed defect pixels.
Normal skin and unobserved pixels stay byte-identical. Small diagonal stripes
retain each category where masks overlap. These are the model's **defect
categories**, distinct from overall fruit quality Classes 1, 2 and 3. The area
calculation continues to use the binary union of defect masks and spheroid
surface-area weights. Display colours do not enter grading arithmetic.

## Coverage and grading policy

The new application source selects **80% observed surface** plus **350 degrees
observed map longitude** for a regular coverage-complete grade. The user's prior
request to grade partial maps remains enabled. A map below a target may receive
an observed-area class marked **partial**, with the note that unseen areas were
not assessed. Maps without usable observations or valid predicted defect areas
remain Review. Raising the target does not manufacture additional coverage.

The class thresholds remain below 10% predicted defects for Class 1, 10% through
20% for Class 2 and above 20% for Class 3. The denominator is observed surface
area, excluding unseen surface. Neither these grade boundaries nor the new
80% target is validated here as a commercial grading standard. The standalone
settings preserve the historical 65% default for old benchmark reproduction;
`main.py` explicitly selects 80% for new application pipelines.

## Exact saved examples and provenance

Display job: `d0cb7e25b5e14d76a7ebf03c111e259b`.
Source saved-map job: `ed3aa02cca364812a145610aad627a83`.
Original full-video execution: `ea6e595b8f3f45f2b5edfda8dafff3f2`.

The display helper makes **zero detector, tracker, segmentation or motion
calls**. It creates 294 new overlay images and reuses original asset URLs for
the maps and masks. The source report and 2,058 original map/mask file hashes
were checked unchanged. Counts remain **293 Class 1, 1 Class 2 and 180 Review**,
including **292 provisional partial grades**. The two regular Class 1 maps also
meet the new 80% surface target. This increased coverage target therefore does
not change these saved class counts.

| Actual fruit | Assigned class | Observed surface | Observed longitude | Predicted defects / observed area |
| --- | --- | ---: | ---: | ---: |
| 98 | Class 1, coverage complete | 85.150% | 360.000° | 4.512% |
| 340 | Class 2 (partial) | 26.516% | 157.232° | 17.842% |
| 32 | Class 1 (partial) | 22.430% | 93.455° | 1.242% |

The [300-dpi PNG](figures/actual_defect_maps_300dpi.png),
[PDF](figures/actual_defect_maps.pdf) and [gallery](index.html) compare original
texture, the new category overlay and the observed-area mask. They use saved
actual conveyor predictions, not generated fruit images or human-labelled
defect truth. White in the observed mask means an observed location; the
reported surface percentage uses area weights, rather than a flat pixel count.
Each [selected result](examples.json) includes original URLs and copied-asset
hashes. The [474-row display ledger](all_474_display_records.json) records every
assigned class, target, measured area and map URL.

The original mapping geometry and model timing metrics retain the full-video
execution's source and 65% setting. The display report separately records the
80% current `grading_policy` and retains the former policy as
`previous_grading_policy`. Inherited metrics are not new model calls.
`metadata_finalization.json` records making those policies explicit. The helper
snapshot ending `.executed` identifies the version used to render the assets;
the adjacent `.py` snapshot includes later metadata handling. The original
surface map images were produced by mapping source `50bdd78e…`; grading source
`f10e8393…` is unchanged by this display update. Exact sources and complete
SHA-256 values are retained in [checks/summary.json](checks/summary.json),
[provenance.json](provenance.json) and `source/`.

## Software and actual browser checks

All **71 Python tests**, frontend build and lint pass. Seven new tests check
unchanged input arrays and clean/unobserved pixels, five distinct colours,
overlapping categories, absence of invented predictions, invalid-shape rejection,
the exact 80% regular-grade boundary and app settings construction without
loading either neural model. Their logs are retained in `checks/`.

The root's independent check re-verifies all 2,058 original hashes and compares
the saved example image arrays outside the observed-defect union. Original and
coloured images match at every normal or unseen location in fruit 98, 340 and
32. That separately retained result is copied into `checks/` without changing
its independent original file. The report figure was visually inspected for
legible labels, retained texture, correct colours and unchanged unknown regions.

The [actual browser check](actual_ui/report.json) passed at **20:49 SAST on
3 October 2026**, using the actual local Vite/API in isolated headless Edge.
It verifies the exact saved job, 293/1/180 counts and 292 provisional records.
Fruit 340 and 98 load both original and defect-coloured maps, the five exact
metadata colours and labels, and separate 80% target and measured coverage.
No-map fruit 47 stays Review. The 390-pixel mobile view has no horizontal
overflow and there are zero JavaScript errors. All API requests are GET.
The separate `artificial_ui_controls/` check uses mocked inputs and is labelled
as such; those screenshots are not actual conveyor predictions.

The guarded API restart refused to interrupt an ongoing user analysis at
20:46 SAST. The running API retained its earlier source and 65% pipeline setting.
That same run remained processing at 250/797 frames before and after this
GET-only browser check. No API restart, cancellation, training interruption or
new inference occurred. The browser result proves the saved overlays and 80%
metadata render correctly; it does **not** claim the new backend pipeline
default was loaded into the active process. Runtime activation is tracked
separately by the root service process after the API becomes idle.

## Tracker findings and the concrete next validation

Surface reconstruction needs views associated with one physical fruit. In this
multi-fruit video, the detector alone cannot provide that identity. A visual
tracker is replaceable by a single-fruit chamber or encoder-labelled conveyor
pockets. Some form of identity association remains necessary.

An ID switch may mix texture and defects from different fruit in one map.
Fragmentation gives one fruit multiple IDs, reducing the views available to
each map. The [tracking audit](tracking_identity/REPORT.md) checks all 32,875
saved boxes on all 515 frames; every coordinate matches the retained replay.
That is consistency, not identity ground truth. The seven earlier association
disagreements involve 15 revised IDs; none produced a usable map. Those known
disagreements therefore do not explain the current mapped examples. Smooth
exchanges remain possible without physical identity labels.

Disabling camera-motion compensation on cached actual detector outputs yielded
506 IDs and 82 very short IDs, compared with the current 474 and 54. This does
not support disabling it as an immediate fix. Production tracking is unchanged.
A synthetic A-to-gap-to-different-B sequence at an identical box reuses the
same installed-tracker ID. It demonstrates ambiguity, not a confirmed switch
in the real clip.

The next test is to label 20–30 physical fruit from entry to exit, preserving
ambiguous occlusions as unknown and reserving some paths for final validation.
Motion prediction, travel direction, plausible size, real lane or pocket
constraints and competing-match checks should flag uncertain associations.
At uncertainty, start a separate map-capture segment **before fitting the
spheroid**. Existing failed-motion and missing-frame rules do not certify
identity; a late split would leave the shape fit exposed to mixed fruit views.
Replay the same cached detections to measure true ID switches, fragmentation
and wrong-fruit map merges, then reconstruct the labelled paths. These guards
are proposed work, not currently active protection. An 80% coverage score also
does not prove identity or correct rotation.

## Reproducibility and evidence boundaries

From the workspace root:

```powershell
./backend/venv/Scripts/python.exe -B backend/diagnostics/algorithm-revision/defect_maps_80_20261003/build_evidence.py
```

This copies only selected new proof and draws the figures. It runs no learned
inference or reconstruction. `--seal` additionally creates this supplement's
manifest and ZIP after QA. Original job folders and earlier sealed packs are
read only. Their complete ZIP hashes are rechecked and recorded in
`provenance.json`. `seal.json` is an external verification receipt, so it is
excluded from the manifest and archive; the manifest excludes itself.

The earlier runtime and partial-grade archives remain unchanged. This bounded
supplement records a display change and a higher coverage target. It does not
establish detector, segmenter, tracking, reconstruction or whole-fruit grade
accuracy, and it makes no real-time throughput claim.
