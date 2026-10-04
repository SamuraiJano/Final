# Complete pipeline rerun — 4 October 2026

The complete production pipeline processed `WIN_20260818_13_05_49_Pro.mp4` with the new conveyor identity manager enabled. The 80% mapping target was not achieved: 381 of 556 capture segments produced a surface map (68.53%), and none met the production requirements of at least 80% estimated surface coverage and 350° longitude coverage.

The run called the unchanged `main.analyze_video` on the complete original video, using fresh detection, TrackTrack, stable fruit identity assignment, silhouette capture, rotation estimation, deferred defect segmentation, mapping and grading. No track subset, cached detections, geometry changes or threshold changes were used. Runtime was 8,461.6 seconds, approximately 141 minutes.

| Measurement | Result |
| --- | ---: |
| Decoded and processed frames | 795 / 795 |
| Fresh detector calls | 795 |
| Defect segmentation calls | 2,248 |
| Raw tracker IDs | 542 |
| Stable capture segments | 556 |
| Saved tracking observations | 40,334 |
| Any surface map | 381 / 556 (68.53%) |
| Segments with at least two usable views | 406 |
| Any map among segments with at least two usable views | 381 / 406 (93.84%) |
| Maps meeting complete coverage requirements | 0 |
| Provisional grades | 380, all Class 1 |
| Mapped segments withheld for uncertain identity | 1 |
| Mapping failures | 175 |
| Median estimated surface coverage of maps | 29.40% |
| Mean estimated surface coverage of maps | 30.15% |
| Maximum estimated surface coverage | 49.22% |
| Maximum observed longitude coverage | 203.54° |

The 93.84% rate counts partial maps and uses only segments with at least two usable views as its denominator. It does not establish that 80% of physical fruit were mapped successfully or fully assessed. All 380 grades apply provisionally to the observed surface; unseen surface was not assessed. No independent manual identity, rotation or grade labels are available.

## Why mapping failed or remained incomplete

Of the 175 mapping failures, 149 had no complete usable silhouettes, one had only one usable view, and 25 had no reliable rotating sequence. Of all 556 segments, 145 never had a bounding box fully inside the video frame. The capture stage rejected 15,393 observations because fruit was cut off by the frame; these are observations across frames, not distinct fruit.

Even where mapping produced an image, estimated surface coverage remained below 50%. The results therefore point to usable silhouette capture and reliable rotation/view coverage as the remaining mapping bottlenecks. Stable identity assignment alone did not achieve complete maps on this video. The black regions in the saved maps are unobserved areas.

## Tracking and output integrity

All 15 integrity checks passed. Every frame received fresh detection, segmentation executed, stable IDs remained unique in each frame, saved histories used the correct capture ID, uncertain identities were never graded, frozen sources matched the launch fingerprints, individual result files matched the final report, and all map assets existed. The original input video remained unchanged.

All 40,334 saved capture observations exactly match the previously verified tracking-only export: no missing or additional observation keys, and maximum bounding-box difference of zero pixels. This verifies reproducibility and integration; it does not prove physical identity accuracy.

The manager recorded 95 same-raw-ID gap recoveries and four motion-supported raw-ID reconnections, alongside 34 ambiguous associations and eight motion/size discontinuities. It marked 57 capture segments uncertain. The earlier visual review found that all four reconnections occurred at the right frame edge; independent labels are needed to determine whether they represent the same physical fruit. Conservative splits explain why capture segments can outnumber raw tracker IDs.

## Evidence

- [Final production report](report.json), an unchanged copy of the application report including histories, mapping diagnostics and local evidence image paths. The original remains in `backend/results/b23fe12db90e41dbae9928e3fbcf55cf/report.json`; generated media remains local.
- [Audit and checks](audit.json), including exact counts, failure reasons, coverage distributions and tracking comparison.
- [Run summary](summary.json), including production geometry, identity settings and inference metrics.
- [Launch request](request.json), including original video, model and source SHA-256 fingerprints.
- [Raw runtime log](runtime.log).
- [Highest-coverage map](../../../results/b23fe12db90e41dbae9928e3fbcf55cf/393/surface_map_overlay.png), estimated coverage 49.22%.

The shell tool reported exit code 1 despite the completed analysis. Its log contains a PowerShell `NativeCommandError` for an informational Loguru CUDA message on stderr, followed by the completed summary and no Python traceback or failure report. A [separate stderr probe](stderr_probe.json) reproduced PowerShell reporting failure while Python exited zero. Completion is supported by the final report and the independently passing audit; the shell status anomaly is retained here for transparency.
