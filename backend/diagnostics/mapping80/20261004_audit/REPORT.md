# Mapping success target: saved full-run audit

The saved complete 515-frame run produces **294 maps from 474 raw tracker
records (62.03%)**. Only **two** satisfy both **80% estimated surface coverage
and 350 degrees of observed circumference**. Producing a partial map and
completing a map are different outcomes.

Considering the **80% area criterion alone gives three maps**, or 0.63% of
all raw records and 0.91% of ever-full records. The additional longitude gate
therefore accounts for only one record in this baseline. It does not explain
the large shortfall; these figures do not recommend changing that policy.

This is a read-only audit of run `ea6e595b8f3f45f2b5edfda8dafff3f2`, whose
algorithm SHA256 is
`50bdd78eafcc5581d0368353c9996c2f95823c69f734dac6f778dc82f22c815d`.
The run predates the identity guard and the fruit-340 retry. It is **not** a
complete rerun of current production. Current source at audit is
`cf6c2dd19968f0c159a7e2ecb8d781eee0206a88d0bab104df8d087023706745`.
Exact report/source hashes, settings and counters are in [audit.json](audit.json).

## Denominators must be explicit

| Descriptive raw-record denominator | Records | Any map | Map with surface >=80% and longitude >=350 degrees | Maps required for an 80% completion rate |
| --- | ---: | ---: | ---: | ---: |
| All tracker records | 474 | 294 (62.03%) | 2 (0.42%) | 380 |
| Ever fully inside the image | 328 | 294 (89.63%) | 2 (0.61%) | 263 |
| Observed edge/full/edge transit entirely within clip | 228 | 213 (93.42%) | 2 (0.88%) | 183 |
| At least one accepted usable view | 310 | 294 (94.84%) | 2 (0.65%) | 248 |
| At least two accepted usable views | 304 | 294 (96.71%) | 2 (0.66%) | 244 |

These are **tracker-record counts, not labelled unique physical fruit counts**.
The transit proxy requires an edge observation at both ends, at least one full
observation, and neither endpoint at the clip boundary. It remains vulnerable
to ID fragmentation and false detections. It cannot establish the actual
production pass rate or substitute for a defined inspection ROI and labelled
fruit entries. Removing difficult fruits after inspection would inflate the
metric; every fruit entering the defined inspection process must remain in
its denominator.

Current app settings require 80% surface coverage and 350 degrees of longitude
for completion, but also allow a **provisional observed-area grade** on partial
maps. The saved historical run used a 65% area target and strict grading.
Changing the partial-grade status does not make unseen skin observed or
increase the rate of complete maps.

## How long the fruit is visible

The original cached video metadata supplies **29.745917878 frames/second**.
Durations below are frame-index intervals divided by that frame rate. Full-box
spans include any intervening gaps; the uninterrupted interval column avoids
counting those gaps as continuously observed fruit.

| Raw-record set / measurement | Median seconds | Maximum seconds | Records >=1 second | Records >=2 seconds |
| --- | ---: | ---: | ---: | ---: |
| 328 ever-full records: tracking lifetime | 2.992 | 5.076 | 313 | 292 |
| 328 ever-full records: first-to-last full-box span | 2.168 | 4.135 | 289 | 242 |
| 328 ever-full records: longest uninterrupted full-box interval | 2.135 | 4.135 | 279 | 207 |
| 328 ever-full records: accepted-view first-to-last span | 2.135 | 4.034 | 274 | 215 |
| 228 transit proxies: tracking lifetime | 3.026 | 3.362 | 227 | 225 |
| 228 transit proxies: first-to-last full-box span | 2.185 | 2.488 | 213 | 183 |
| 228 transit proxies: longest uninterrupted full-box interval | 2.135 | 2.488 | 205 | 153 |
| 228 transit proxies: accepted-view first-to-last span | 2.118 | 2.454 | 203 | 159 |

Thus the typical complete image-transit record has about **2.2 seconds of
fully inside observations**. Duration by itself does not establish the number
of exposed turns or the visibility of the poles.

## Capture failures

There are **164 records with zero usable views**, **six with one view**, and
**ten with two or more views that produce no map**. Of the 170 zero/one-view
records, **146 never have a fully in-frame bounding box**. The other 24 have
one or more fully inside observations:

| Full-box observations per zero/one-view record | Records |
| --- | ---: |
| Zero | 146 |
| One | 10 |
| Two to nine | 7 |
| Ten to 29 | 3 |
| 30 or more | 4 |

There are 32,875 tracking observations, of which 19,961 have fully in-frame
boxes. All per-view rejection counts across the saved run are:

| View rejection | Count |
| --- | ---: |
| Cut off by the image edge | 12,914 |
| Occluded or too irregular for the spheroid silhouette | 1,878 |
| Foreground smaller than 100 pixels | 647 |
| No foreground fruit in mask | 166 |
| Mask occupies too little of detection box | 47 |
| Crop too small for GrabCut | 2 |

The 304/474 = **64.14%** ceiling applies only if the existing saved accepted
view sets remain fixed and mapping still requires at least two views. It is
**not a fixed limit of the video or hardware**: better segmentation,
recapture, wider camera coverage, extra cameras, or correctly reconciled
identities can change the eligible sets and denominator.

Recovering all ten currently eligible failures plus all 24 unusable records
that ever have a full box would permit at most 328 maps from those same raw
records (69.20%). Reaching 380 would still require at least 52 currently
edge-only records to become eligible, or a properly measured physical-fruit
denominator. Neither is achieved by relaxing the matcher.

### Best mask-recovery candidates

The following records provide many fully inside boxes despite almost no
accepted silhouettes. [unusable_records.json](unusable_records.json) contains
every full-box frame, rejection counter, and original image evidence path.

| Raw ID | Accepted views | Full-box observations | Useful original-frame range | Main rejection evidence |
| --- | ---: | ---: | --- | --- |
| 248 | 1 | 70 | 212–281 | 69 irregular/occluded silhouettes |
| 286 | 0 | 62 | 253–314 | 47 irregular, eight empty masks, seven tiny foregrounds |
| 46 | 1 | 59 | 8–66 | 23 irregular, 17 empty, 15 tiny, three low box occupancy |
| 214 | 0 | 55 | 193–249 | 23 irregular, 22 tiny, five empty, five low box occupancy |
| 278 | 1 | 25 | 243–267 | Eight irregular, nine tiny, five low box occupancy, two empty |
| 50 | 1 | 16 | 7–22 | 11 tiny, three irregular, one empty |
| 91 | 0 | 11 | 80–98, with gaps | Nine tiny, two empty |

IDs 244 and 248 were previously identified as a likely single ID transition;
this is another reason not to interpret these record counts as physical fruit.
Image inspection and a controlled comparison of mask methods are needed to
distinguish true occlusion from segmentation errors in these candidates.

## Why maps remain partial

Across the 294 maps, the median surface estimate is **37.71%**, median observed
circumference **159.76 degrees**, median input count **63.5 views**, and median
selected count **nine views**. In aggregate, 3,004 of 17,220 accepted captured
views enter selected maps (17.44%); unselected views may be duplicates,
unreliable, or in independently valid segments. These counters alone do not
establish how much new surface the discarded views show.

| Minimum estimated surface observed | Maps at or above threshold |
| --- | ---: |
| 40% | 124 |
| 50% | 39 |
| 60% | 15 |
| 65% | 10 |
| 70% | 8 |
| 75% | 5 |
| 80% | 3 |

The two complete maps are raw IDs **98 and 368**. ID **369** has 82.80%
estimated area but only 340.33 degrees of circumference and fails the current
350-degree requirement.

Of 17,136 pair diagnostics, 9,693 are recorded splits:

| Split reason | Pair events |
| --- | ---: |
| Estimated motion below minimum | 6,399 |
| Matching residual above 0.58 | 1,475 |
| Coarse and native estimates disagree | 1,070 |
| Missing original frames | 459 |
| Longitude step outside fusion bounds | 226 |
| Rolling estimate at 20-degree search boundary | 53 |
| Other rotation rejection | 11 |

The strongest software opportunities are distinguishing confidently stationary
views from failed motion estimates, verifying connections between independently
valid segments, and supporting the actual three-dimensional tumbling motion.
Such connections must be measured from images and validated against stationary
and lighting controls. Summing disconnected rotations or assuming constant
conveyor speed can increase apparent coverage without supplying valid poses.
These historical pair counts predate the new guarded native 3D retry.

The guard-v3 audit found **zero detected identity boundaries inside the
selected sequences of the 294 maps**, and 37 boundaries elsewhere among their
captured views. That finding does not prove identity ground truth, and smooth
undetected swaps remain possible. It does show that the detected ID
discontinuities are not the primary recorded explanation for the current
selected maps' limited coverage.

## Acceptance measurement

A meaningful target is: **at least 80% of independently counted physical
fruits entering a predefined inspection ROI yield a verified map meeting a
predefined surface-observation requirement**. If the retained requirement is
80% observed area, report it separately from the existing 350-degree
circumference gate. Report capture
failures, pose failures, insufficient coverage, uncertain identity, and defect
grading separately, with every ROI entrant retained in the denominator.

Validate correspondence/reprojection accuracy as well as geometric occupancy.
Capture labelled rolling sequences and controlled stationary/lighting cases,
then run the same full clip through each candidate with frozen detections or
documented detector changes. If a fruit never exposes enough surface, improved
pose estimation cannot reconstruct that unseen skin; acquisition must provide
more rotation, a longer observation interval, fewer occlusions, or additional
camera views.

## Reproduction

From the repository root:

```powershell
./backend/venv/Scripts/python.exe -B backend/diagnostics/mapping80/20261004_audit/audit.py
```

This regenerates only audit outputs in this directory and leaves production,
the saved report, source images and maps untouched. No model inference or
fresh video mapping was performed for this audit.
