# Dashboard transport verification

See [the production fix and final checks](TRANSPORT_FIX.md) for the completed application change, source hashes and verification after the fix.

The completed dashboard contained 2,535 inspection records and 3,774,048 JSON bytes. Requests using `Connection: close` stalled before the advertised response length, while otherwise identical direct fetch requests using keep-alive completed.

The installed Vite proxy forcibly uses `Connection: close` without an explicit HTTP agent. A temporary native HTTP proxy with a keep-alive agent and upstream keep-alive header delivered all 3,774,048 bytes to both a native Node HTTP client and a fetch client. Their SHA-256 hashes matched the direct API response exactly. The temporary proxies were closed and their owned agents destroyed after testing.

`report.json` records the results; `captured_output.log` preserves the terminal observations; `installed_proxy_excerpt.txt` records the relevant installed implementation. `transport_probe.mjs` is a reproduction helper prepared from the commands after the captured tests. It was not the filename used for the original stdin-based experiments. Run it only with the local API already running and without an analysis in progress.

No model inference, saved-map modification or production source mutation was performed by the reviewer. This establishes the observed header dependence and a byte-preserving proxy fix. It does not prove the precise lower-level Windows, Python or TCP defect. Final verification in the actual application browser is separate.

Version correction before sealing: the first structured report recorded Vite 8.3.0 from the declared `^8.3.0` dependency range. The installed package and the service's startup banner both identify Vite 8.3.1, so `report.json` was corrected and records that provenance. Raw experiment output remains unchanged.
