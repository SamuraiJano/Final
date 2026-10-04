# Memory audit ? 3 October 2026

The full API run failed while allocating a small 1.26 MiB array. Source review found bounded crop retention and no unbounded retention of completed tracks. This is consistent with host memory pressure, but source review cannot establish the exact cause. The user confirmed active model training and requested waiting until it finishes.

The matcher batch remains unchanged. Normal track completion releases all six state dictionaries. MemoryError bypasses track cleanup, and run cleanup releases only VideoCapture; exception cleanup can be improved in a separately tested change. The older completed real-video donor suggests roughly 476 MiB of crops/evidence around frame 330 and a 706 MiB peak at frame 514; these are estimates, not measurements of the failed run, and exclude model/runtime memory.

No production edits or heavy model tests were performed for this audit. See report.json for source hashes, line references and limitations.
