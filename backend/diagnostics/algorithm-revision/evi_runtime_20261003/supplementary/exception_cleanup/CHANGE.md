# Exception cleanup ? 3 October 2026

A failed full-video run raised MemoryError while estimating rotation. This change makes track cleanup reliable when an unexpected error occurs; it does not establish or remove the original source of memory pressure.

`_finish_track` writes the track result and saved images through `_write_track_result`, then always releases that track in `finally`. Unexpected RuntimeError and MemoryError still propagate. Recoverable mapping failures retain their existing Review behavior and evidence. The local view references remain available until evidence writing finishes.

`analyze_video` now includes opening/cancellation in its resource cleanup block and releases all remaining known track states when processing stops, whether by completion, cancellation or error. It does not alter camera services, training, CUDA globals, matcher logic, capture limits or grading thresholds.

Twelve focused tests passed, including seven added cleanup tests. They exercise unexpected track/processing errors, end-of-video mapping failure, unopened video, cancellation immediately after pipeline creation, evidence-before-release ordering and normal completion. Tests use real NaartjiePipeline state with mocked model/video failures; they do not claim full-video execution or model accuracy. The initial test fixture reset bug is recorded in report.json.

Before/after source snapshots, exact hashes, the diff and focused test output are retained in this directory.
