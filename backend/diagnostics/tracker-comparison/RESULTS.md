# Real-video tracker comparison verification

Completed six installed trackers in both full and cached modes on **795 source frames**.

Run: `20261008T093801Z_52984b81e03c`. Started `2026-10-08T09:38:01.874235+00:00` (UTC).

[Open offline report](real-video/20261008T093801Z_52984b81e03c/report.html). [Comparison CSV](real-video/20261008T093801Z_52984b81e03c/comparison_summary.csv).

| Tracker | Detection + tracking FPS | Tracker-only FPS | Unique raw IDs | Mean lifetime (s) | Mean consistency (%) | Suspected ID Fragmentations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ByteTrack | 10.70 | 158.08 | 634 | 2.053 | 98.37 | 11 |
| BoT-SORT | 8.71 | 40.16 | 509 | 2.544 | 99.48 | 5 |
| OC-SORT | 10.03 | 88.35 | 524 | 2.507 | 98.82 | 4 |
| Deep OC-SORT | 10.27 | 89.16 | 522 | 2.515 | 98.79 | 4 |
| FastTracker | 10.25 | 119.69 | 625 | 2.111 | 97.74 | 11 |
| TrackTrack | 8.64 | 34.81 | 488 | 2.557 | 99.89 | 1 |

The detector is the final D-FINE `best_stg1.pth`, confidence 0.25, NMS IoU 0.7, input 640 ? 640. The source is `WIN_20260818_13_05_49_Pro.mp4`, 29.9308 FPS, decoded at 1920 ? 1080. Hardware: NVIDIA GeForce RTX 4060 Laptop GPU; Ultralytics 8.4.170, PyTorch 2.6.0+cu124, CUDA 12.4.

Timing measures detector + tracker or tracker-only as labelled. Encoding, decoding, overlays, metrics and file writing are excluded. Three detector warm-up frames and three disposable tracker warm-up frames per run are excluded, then each measured run starts fresh at frame zero and processes the complete video.

Another GPU workload was present at the start: the recorded snapshot showed 4,073 MiB used and 33% utilization. These are one-pass timings on shared hardware. Repeat on idle hardware before a final speed decision. Full detection + tracking measured 8.64?10.70 FPS here, below the 29.93 FPS source rate; cached replay FPS alone does not establish conveyor throughput.

All full-pass detection arrays exactly matched the cache; the six cached detection sequence hashes match. Each tracker produced equal ID/lifetime/consistency/fragmentation results in both modes. Independent reaggregation of 466,746 raw observations verifies every per-ID count, lifetime, consistency, mean box dimension and reported aggregate. All twelve annotated files have 795 frames at the source resolution.

Raw-ID lifetime and suspected fragmentation are observational diagnostics. Short lifetimes can include legitimate entries/exits and video-boundary censoring. No physical fruit identity was manually verified. The lower unique-ID count must be considered alongside active counts, returned observations, videos and the installed confirmation rules. No combined score or automatic winner is used.

Validation: **257 backend tests passed**, build/lint passed, seven offline browser checks passed, exact YAML hashes verified, all nine protected application/inference/UI source hashes unchanged. See [FINAL_VERIFICATION.json](FINAL_VERIFICATION.json), [independent reconciliation](real-video-validation.json), [backend test log](backend-tests.log), and [browser checks](ui/checks.json).

The exact experiment source used for the real run is retained in its `source_snapshot/` directory. The final report renderer snapshot and hash are recorded separately in run metadata. Current tool source hashes are retained in FINAL_VERIFICATION.json. The existing regional journal and production TrackTrack configuration remain unchanged.
