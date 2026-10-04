# Dashboard transport fix, 3 October 2026

The final dashboard contained 7 saved jobs and 2,535 inspection records. Its 3,774,048-byte JSON response reached the API client completely, but the original Vite proxy stalled before the advertised response length. The resulting incomplete response prevented the application from loading the saved grades.

## Controlled experiments

Direct Node fetch with default headers returned all 3,774,048 bytes in 1.529 seconds. Adding `Connection: close` reproduced the stall after 3,720,960 bytes; using `Connection: keep-alive` returned the complete response in 1.611 seconds. Switching a temporary Vite proxy to fetch alone also failed, because it retained the close header.

The installed Vite bundle's `http-proxy-3` implementation sets `outgoing.agent = options.agent || false` and forces `outgoing.headers.connection = 'close'` when no explicit agent is present. See [the captured installed-source excerpt](installed_proxy_excerpt.txt). This connects the proxy's original behavior to the observed header-dependent failure. These tests do not establish the precise underlying Windows, Python or TCP defect.

A temporary native HTTP proxy configured with `new Agent({ keepAlive: true })` and `headers: { connection: 'keep-alive' }` returned every byte to both a Node HTTP client and a fetch client. The clients received 2,535 records, and the response hashes matched the direct API exactly. Temporary servers were closed and their agents destroyed afterwards. See [captured output](captured_output.log) and [structured results](report.json).

## Production change

The application's `vite.config.js` now applies those two tested options to the existing `/api` proxy. This also covers the large report returned when a video analysis completes. The proxy continues to use native Node HTTP; no fetch transport or new active request/header timeout was added. The existing backend-control middleware still handles its route before proxying.

The response data, saved maps and backend grading algorithm were not changed by this transport fix. A byte-for-byte [configuration snapshot](vite.config.js.after.snapshot) records the resulting source.

| Source | SHA-256 after the transport fix |
| --- | --- |
| `vite.config.js` | `1b6582dca898de357a7b048a30489197d860509aa01c3c1803a03590079dec4e` |
| `backend/algorithm.py` — unchanged | `f10e8393f1af64f67023f9519fcbf1b117d91418c1955ec44c2bd329fa22e657` |
| `backend/main.py` — unchanged | `76a66ac90ad2549775bce28f0ecb66b4348a4a0829219c770eb08349230d5f89` |

## Final verification

The final GET-only check at 18:03:50 SAST compared the production API and Vite dashboard responses. Both returned HTTP 200, all 3,774,048 advertised bytes and all 2,535 records. Their raw bytes were identical, with SHA-256 `fc74391e044f80a27d30912a6c3793ba2a50536e8f751371da5999b46983ba2c`.

The latest job was `ed3aa02cca364812a145610aad627a83`: 474 records, comprising 293 Class 1, 1 Class 2 and 180 ungraded records. There were 292 provisional grades. See [the final raw check](final_checks/get_only_check.json) and [software-check summary](final_checks/summary.json). The final build and lint checks both exited with code 0. The actual application UI also passed its separate verification at approximately 18:02 SAST.

All transport checks used GET requests. No model inference was requested. The [reproduction helper](transport_probe.mjs) was prepared from the stdin commands after testing and passed a syntax check; it is not represented as the original executed filename.
