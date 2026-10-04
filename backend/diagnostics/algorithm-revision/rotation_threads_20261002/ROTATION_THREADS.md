# OpenCV thread timing on real rotation pairs

Three real adjacent pairs selected from previous frozen replay: two native rechecks and one coarse-only match. Exact full-track spheroid is fitted once outside timing; each pair uses the production selector subset helper. Each mode gets one untimed warm-up. Three paired estimator repetitions alternate mode order. Captured actual remap arrays are timed separately in three groups of 50 calls, after warm-up; setup, hashing and thread switching are excluded. No production change.

Frozen algorithm SHA256: `863fd09cfa629c5b5b8ba7c73963fbe993441b3e3dd989f1e451d0a5f62c9db1`.

| Fruit / frames | Search path | Mean 16 threads, ms | Mean 1 thread, ms |
| --- | --- | ---: | ---: |
| 98 / 99–100 | Coarse plus native | 205.732 | 202.419 |
| 1 / 4–5 | Coarse plus native | 186.001 | 190.721 |
| 14 / 1–2 | Coarse only | 46.466 | 47.140 |

All nine paired estimator outputs are bit-identical: True; residuals and path details also match exactly. All captured remap output pairs are bit-identical.

Estimator overall means: 16 threads 146.067 ms; 1 thread 146.760 ms. Captured remap means: 16 threads 0.1575 ms; 1 thread 0.5635 ms.

A short single-process microbenchmark under other machine load. These crops have no pose ground truth. Equality between thread modes establishes numerical agreement, not geometric accuracy or full-video throughput.

Run from the project root: `backend/venv/Scripts/python.exe -B backend/diagnostics/algorithm-revision/rotation_threads_20261002/validate_rotation_threads.py`. Source, six unchanged NPZ crops, their hashes, complete settings, all timings, matrices and exact comparison results are retained in this folder. Full-track fit inputs remain in the referenced frozen replay.
