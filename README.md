# Citrusvision naartjie monitor

The dashboard shows the conveyor camera, assigned quality classes, detection and segmentation signals, and recent fruit surface maps. It reads results from either a recorded video or a live camera inspection. Empty states represent actual missing data; the dashboard does not generate sample results.

## GitHub source and current validation

The `Final` repository contains the application, tracking and mapping tools,
tests, documentation, model metadata, and text validation records. Installed
dependencies, generated results, diagnostic images/videos/cache archives,
uploaded videos, local runtime state, secrets and trained checkpoint binaries
remain local and are excluded by `.gitignore`. Evidence links to those generated
files refer to the original local validation archive. A fresh clone needs the
two checkpoint files and the sibling inference/training dependencies described
below before running real-video inference.

The current identity implementation is documented in
[CONVEYOR_IDENTITY.md](backend/CONVEYOR_IDENTITY.md), and the independent
annotation method is in [TRACKING_TEST_METHOD.md](backend/TRACKING_TEST_METHOD.md).
The latest [complete pipeline rerun](backend/diagnostics/pipeline-runs/identity_full_20261004/RESULTS.md)
processed all 795 frames and retained 40,334 tracking observations. It produced
381 maps from 556 capture segments, including 380 provisional grades and one
identity review case. All 15 integrity checks passed, but no map met both the
80% surface and 350-degree longitude requirements. These execution results do
not establish physical identity or grade accuracy without independent labels.

## Run locally

From this directory in PowerShell, set up the backend once:

```powershell
python -m venv backend/venv
./backend/venv/Scripts/python.exe -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
./backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt
./backend/venv/Scripts/python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

The CUDA check should print `True`. Stop the backend before changing PyTorch on Windows because loaded DLLs prevent replacement.

Start the dashboard and inference API together:

```powershell
npm install
npm run dev
```

`npm run dev` waits for the API to become ready before opening the dashboard. It reuses an API already running on port 8000. If the API stops unexpectedly, the dashboard process also stops so a broken inference service is not shown as ready.

Open the URL printed by Vite. Upload an MP4, AVI, MOV, or MKV file and choose **Analyze**. The selected video is previewed locally; analysis finishes before the full report appears. Recent inspections can be searched, filtered by class, and opened to view the surface map and masks.

While a video is being analyzed, choose **Stop analysis** to cancel that run. The current model or mapping operation finishes before cancellation takes effect. A stopped run does not save a report, and you can start another run once its status clears.

Use **Refresh backend** before a new run when you need to restart the Python inference service, such as after updating its code or model files. The button is available when `npm run dev` started the API and no video or live inspection is running. Saved reports remain available. If the API was started separately and reused by `npm run dev`, restart it in its own terminal.

Recorded video tracking checks every frame. Masked views are captured when image content changes (up to 120 per fruit), so repeated encoded frames do not consume the view budget. Frame-edge truncation, collapsed masks, and strongly concave silhouettes are rejected before fitting a spheroid. Reports include rejected-view reasons, sampled frame counts, and rotation settings. The dashboard shows frame progress and explicitly labels failed reconstruction as **Mapping failed**.

Tracking now publishes an ID on the first accepted frame-edge detection and retains partial entry/exit observations before checking whether a view can be reconstructed. Future inspection reports expose first/last tracked frames and entry/last-seen crops. The [entry-to-exit tracking report](backend/diagnostics/entry-tracking/entry_full_20261002/TRACKING_FOLLOWUP.md) and [annotated video gallery](backend/diagnostics/entry-tracking/entry_full_20261002/index.html) document the complete 515-frame test with the actual detector. The example fruit remains one ID from frame 51 through 138; other identity-consistency flags remain documented. This tracking test does not establish new reconstruction or grading accuracy.

The [tracking evidence ZIP](backend/diagnostics/entry-tracking/entry_full_20261002/tracking_evidence.zip) contains the report, videos, 300-dpi figure, source images, predictions, settings, source snapshots and software/browser checks.

## Live camera

Set `FRUIT_CAMERA_SOURCE` before starting the API. Use a USB camera index or a network stream URL:

```powershell
$env:FRUIT_CAMERA_SOURCE = '0'
# or: $env:FRUIT_CAMERA_SOURCE = 'rtsp://camera-host/stream'
npm run dev
```

The camera preview connects automatically. Select **Start live** to process the feed; **Stop live** finalizes fruit still being tracked. Completed fruit appear in the class mix and inspection history as the conveyor runs. The live camera, its position, and roller motion still need calibration with actual conveyor footage.

## Models, GPU, and results

The local weights are `backend/models/D-FINE/detection/best_stg1.pth` and `backend/models/D-FINE/segmentation/model.pt`, with `model.dfineseg.json` beside the segmentation checkpoint. The D-FINE checkpoint loader comes from the sibling `Inference Runner/backend/python` project, and D-FINE-seg code comes from `New Model Trainer/model_training/third_party/D-FINE-seg`. Set `FRUIT_DETECTOR_WEIGHTS`, `DFINE_SEG_WEIGHTS`, or `DFINE_SEG_SOURCE` if those locations change. The installed Ultralytics TrackTrack implementation receives the detector's boxes and maintains fruit IDs.

CUDA is the default inference device. Set `$env:FRUIT_DEVICE = 'cpu'` to run deliberately on CPU. GPU activity appears during detector and segmenter calls; OpenCV capture and decoding, tracking, GrabCut, and surface mapping use CPU. `/api/health` reports the requested device, CUDA availability, and checkpoint presence. Dashboard model figures are average processing time and prediction confidence for the latest run. Confidence is not validated accuracy; that requires labelled evaluation footage.

Results are saved under `backend/results/<job_id>/`. The dashboard defaults to the latest saved report; **All saved runs** includes earlier development and regrading records. It displays six rows at a time; **Show more inspections** reveals further matches. At the user's request, usable partial maps receive a provisional class from their **observed surface**. The dashboard labels these **Class 1 (partial)**, **Class 2 (partial)** or **Class 3 (partial)** and shows their coverage. Unseen areas are unassessed. Fruit without a usable map or completed defect observations remain Review. To match the camera and rollers, configure `FRUIT_ROTATION_AXIS` (`x` or `y`) and `FRUIT_ROTATION_DIRECTION` (`1` or `-1`). At least 350 degrees of observed map longitude and **80% observed surface** now mark coverage as complete in the app. Maps below the target retain provisional classes. The standalone settings retain the historical 65% default for reproducible benchmarks. Physical rotation is reported separately: the visible surface before and after a turn adds coverage. Class 1 means less than 10% predicted defects, Class 2 means 10% through 20%, and Class 3 means more than 20%, using the observed surface as denominator. These are engineering settings, not validated commercial grading rules.

Open an inspection to compare **Original** and **Defects** views of the surface map. The original texture includes blemishes; a separate translucent overlay highlights each predicted defect category with its own colour and legend. Dark marking is cyan, light brown discolouration yellow, open skin red, wrinkling purple and wind scarring green. These categories are separate from the overall fruit quality Classes 1, 2 and 3. Overlapping categories remain visible as stripes. The full surface canvas is retained; unobserved regions stay unknown. Display colouring changes no masks, coverage or defect arithmetic.

Expand **Source views and model masks** to see representative input crops, fruit silhouettes and predicted-defect overlays. Partial and failed tracks retain input evidence too. Defect inference is deferred until geometry and rotation select the views used in a map. Those views are segmented before the final coverage check, so some partial maps also contain defect predictions. Future source-view overlays use the same category colours; archived source overlays retain their original red display. These are model predictions, not manually verified defects. The downloaded report retains the selected/discarded frame numbers, pair rotations, matching errors and rejection reasons.

`main.py` serves the API and camera, `dfine_segmenter.py` loads the models and TrackTrack, `algorithm.py` constructs surface maps, and `map_visualization.py` creates the separate defect-colour display. Tests cover geometry and the installed TrackTrack interface. `backend/venv` is installed package code, and `__pycache__` is generated Python cache.

The current camera default is horizontal rollers (`FRUIT_ROTATION_AXIS=x`, direction `1`). This is a geometry assumption, not a completed calibration. The real-video audit in [INFERENCE_AUDIT.md](backend/diagnostics/INFERENCE_AUDIT.md) found reconstruction failures even after correcting input and mathematical defects. Synthetic tests do not establish grading accuracy on this conveyor. The historical failed report is preserved.

## Validation evidence: current checkpoint, 3 October 2026

### Defect-colour display and 80% coverage target

The latest saved display job is `d0cb7e25b5e14d76a7ebf03c111e259b`. It adds
294 coloured defect overlays and the requested 80% surface target to the
preceding saved observations. Its counts remain **293 Class 1, 1 Class 2 and
180 Review**, including **292 provisional partial-map classes**. It performs
no new detection, tracking, segmentation or reconstruction. All 2,058 original
map and binary-mask files checked by the helper retain their hashes; original
job reports remain intact. The full canvas is shown with unknown surface left
unknown. The [new proof supplement](backend/diagnostics/algorithm-revision/defect_maps_80_20261003/REPORT.md)
records selected original/coloured maps, source snapshots and software checks.

Source settings and runtime activation are checked separately. A guarded restart
at 20:46 SAST refused to interrupt an ongoing user analysis, so that run continued
under the earlier API's 65% settings. The new proof report records later
activation status. The saved display job already has explicit 80% metadata;
it is not a claim that an in-flight inference run changed its settings.

The [tracking identity audit](backend/diagnostics/algorithm-revision/tracking_identity_20261003/REPORT.md)
explains why multi-fruit mapping needs association, how a switch can mix fruit,
and which safeguards need labelled validation. None of the 15 IDs involved in
the seven earlier association disagreements produced a usable map. Disabling
camera-motion compensation increased short fragments in a cached replay, so
the production tracker remains unchanged. Smooth identity switches have not
been ruled out. The original audit proposed checks before shape fitting. The
[4 October identity guard](backend/IDENTITY_GUARD.md) now implements capture-ID
continuity, one-to-one motion recovery, separation at gaps/discontinuities, and
withholding grades for uncertain segments. Its 515-frame replay reconnects one
raw-ID transition and separates 192 uncertain transitions. It produces 665
capture segments from 474 raw IDs; segments are not unique physical fruit counts.
This is a mapping safeguard, not proof that ID switches caused the map defects
or that physical identity accuracy has improved. Existing reports are unchanged.

The [mapping attribution and rerun](backend/diagnostics/identity-mapping-check/20261004_scene_motion_v3/REPORT.md)
corrects the guard's initial zero-motion assumption with shared conveyor motion.
Version 3 avoids 19 clip-start flags and preserves all seven compared captures.
The actual defect model remapped 215 saved views: fruit 98 reaches 85.074%
observed surface; fruit 1, fruit 14 and raw fruit 340 (legacy fixture 491) remain
at 39.144%, 25.962% and 26.413%. The known ID change contributes no completed
map. Rotation/view selection remains the immediate coverage limitation in
these examples. All 88 Python tests and known-area controls pass; physical
identity, motion and grading accuracy still lack labelled conveyor validation.

### Earlier partial-map grading update

The preceding saved result is a separate regrading job,
`ed3aa02cca364812a145610aad627a83`: **293 Class 1, 1 Class 2 and 180 Review**.
Of the 294 assigned classes, **292 are provisional partial-map grades**. The
two maps meeting the original coverage requirements retain their regular Class 1.
This update reuses the completed original-video maps and defect percentages;
it performs no new detection, segmentation or rotation estimation. All 5,691
copied PNG files were verified byte-identical, and the original report remains
unchanged. Fruit 340 is now Class 2 (partial), from 17.842% predicted defects on
26.516% observed surface. Fruit 32 is Class 1 (partial), from 1.242% predicted
defects on 22.430% observed surface.

The [policy change and proof supplement](backend/diagnostics/algorithm-revision/partial_grades_20261003/POLICY_CHANGE.md)
records the observed-area calculation, source separation and tests. The current
grading source is `f10e8393` and API source is `76a66ac9`; the saved maps were
created by motion/mapping source `50bdd78e`. The 13 added policy tests check class
boundaries, invalid/missing observations, the observed-area denominator and
unchanged map pixels. All 64 Python tests, build and lint pass in the
[policy software record](backend/diagnostics/software-checks/partial_grades_20261003/summary.json).
This change increases assigned classes by allowing partial observations; it is
not evidence of improved model accuracy or reconstructed coverage. The original
sealed evidence pack below retains its earlier strict coverage policy.
The [partial-grade image gallery](backend/diagnostics/algorithm-revision/partial_grades_20261003/index.html)
and [small evidence ZIP](backend/diagnostics/algorithm-revision/partial_grades_20261003.zip)
retain three actual fruit examples, 300-dpi figures, all 474 before/after decisions,
source snapshots and separate actual/artificial UI checks.
The [dashboard transfer diagnostic](backend/diagnostics/algorithm-revision/dashboard_transport_20261003/TRANSPORT_FIX.md)
separately records a frontend proxy fix needed to deliver the saved report in
full. It does not change the models, maps or grading decisions. Its final Vite
configuration and fresh build/lint evidence are included with the supplement.

### Completed original-video test under the earlier strict policy

The tested mapping algorithm is frozen as source `50bdd78e` (full SHA256 in its
[source record](backend/diagnostics/algorithm-revision/aligned_pixel_switch_trace_source/metadata.json)).
The complete original-video pipeline now executes: the
[3 October replay](backend/diagnostics/api-runs/full_pixel_switch_runtime_20261003/summary.json)
processed all 515 distinct frames and returned **474 records: 2 Class 1 and 472 Review**.
Grading remains very limited (0.42% of saved records), and field accuracy is unmeasured.
The 17.3-second clip took 37.4 minutes, so this setup is not running in real time.
Its controlled development tests pass; those tests do not establish conveyor-wide
grading accuracy. **The requested midnight verification target was missed.**
The earlier attempt failed with last published progress 330/515 and a NumPy memory
allocation error.
The [failed-run evidence](backend/diagnostics/api-runs/full_pixel_switch_trace_failure_capture_20261003/README.md)
preserves the request, HTTP 500 response, error state, tracebacks, exact execution
sources and partial outputs. A healthy API response does not mean that analysis
completed. The successful retry has separate source and execution provenance.

Testing resumed at the user's request on 3 October at 12:19 SAST. The separate
full-video replay ran from 12:32:32 to 13:09:55 SAST. The earlier pause stopped
only the owned API/dashboard at
01:05:09 SAST; [pause evidence](backend/diagnostics/algorithm-revision/service_20261002/pixel_switch_trace_services/paused_for_training_20261003.json)
records those processes. Training was running concurrently when the failed
attempt occurred, but its precise memory-failure cause has not been established.
Sources, report images and failed results remain saved.

Runtime cleanup now releases model/pipeline references after successful or failed
analysis, and Vite ignores backend/evidence writes. These changes retain exact
motion source50; the new runtime main.py is source `4c0b69d8`. Its 51 Python tests,
build and lint pass. The retry completed without an allocation failure; this does
not establish the original failure's cause or eliminate all future memory risks.
The [current fruit 98 walkthrough](backend/diagnostics/algorithm-revision/debug_fruit_98_pixel_switch_runtime_20261003/index.html)
shows all 65 captured pair diagnostics, actual model masks and the separately
identified tracking entry/exit donor images. Its
[browser checks](backend/diagnostics/ui-checks/walkthrough_pixel_switch_runtime_20261003/report.json)
verify rendering and interaction; they do not measure field accuracy.

The algorithm retains the papers' spheroid geometry, lifted surface points,
two-axis rotation search and surface fusion. For rechecked adjacent turns it
uses a local log-pattern comparison when predicted texture displacement is at
least one pixel; smaller displacements use smoothed native green values. This
choice handles the tested camera lighting while retaining small-motion detail.
The current recorded-video bounds are 20 degrees rolling and 20 degrees sideways;
live/author rolling search is 55 degrees. The frozen benchmark used
65% observed surface, 350 degrees observed longitude, and 10%/20% defect limits.
The later app coverage target is 80%; the benchmark evidence retains its
original settings.
The [fruit 340 correction](backend/diagnostics/fruit340-fix/20261004_final/REPORT.md)
adds a conservative native three-component retry for failed coarse matches in
the dense 20-degree recorded-video profile. Independent inverse checks and a
one-pixel rolling floor recover frame 309, raising estimated coverage from
26.41% to 32.22%. The map remains partial; documented reflection, backward-motion
and successful-coarse model failures remain. Wider sparse/live profiles keep
their existing behavior. The report separates final software/model checks from
component accuracy, preserved failed controls and historical benchmarks.
The [plain-language walkthrough](backend/ALGORITHM_EXPLAINED.md) explains the
pipeline and these engineering adaptations. The
[testing process](backend/TESTING_PROCESS.md) explains the datasets, measurements,
denominators, failure preservation and remaining limits for the report.

The exact adopted source passes all twelve
[camera-lighting controls](backend/diagnostics/algorithm-revision/camera_shading_pixel_switch_trace20_20261002/report.json),
the [short-motion and brightness-offset controls](backend/diagnostics/algorithm-revision/short_pixel_switch_trace20_20261002/report.json),
four [strict large-sideways pairs at the 20-degree bound](backend/diagnostics/algorithm-revision/large_transverse_pixel_switch_trace20_20261002/report.json),
two [fresh-texture turns](backend/diagnostics/algorithm-revision/fresh_texture_pixel_switch_trace20_20261002/report.json),
two [complete vertical-axis turns](backend/diagnostics/algorithm-revision/full_turn_y_pixel_switch_trace20_20261002/report.json),
and [numerical equivalence checks](backend/diagnostics/algorithm-revision/pixel_switch_trace_equivalence_20261002/report.json).
All 714 noisy stationary pairs remain unavailable and produce no map or grade;
this is the expected observability result, not measured zero motion error.
Inputs, criteria, failed predecessors and actual misleading maps are preserved.
These repeatedly inspected synthetic scenes are development tests.
The [known-area controls](backend/diagnostics/authors-benchmark/synthetic_runs/pixel_switch_trace_20261002/report.json)
separately test supplied 5%/15%/30% defect masks and known rotations, plus four
coverage thresholds. They verify area/class arithmetic while bypassing motion
estimation; they do not measure learned defect-mask accuracy.

On [all 36 public author sequences and 497 labels](backend/diagnostics/authors-benchmark/runs/pixel_switch_trace_author_profile_20261002/report.json),
the adopted source produces 36 maps and returns 457 point predictions, with
5.225-pixel conditional RMS error; 372 of all 497 labels are within five pixels.
The earlier operational reference returned 458 at 5.103 pixels, with 367 within
five pixels. There is no overall author-accuracy improvement claim. The
[same-label comparison](backend/diagnostics/algorithm-revision/pixel_switch_author_comparison_20261002/SAME_LABEL_COMPARISON.md)
retains gains, regressions and unavailable predictions. The
[retained-map subset](backend/diagnostics/authors-benchmark/bridge_runs/retained_pixel_switch_trace_author_20261002/report.json)
returns 348/497 at 5.360 pixels, with 286/497 within five pixels and no
nonadjacent bridges. A 39.56-pixel worst returned error remains documented.
Map availability alone does not establish correct pose.

The [current actual GPU model integration](backend/diagnostics/algorithm-revision/real_segmenter_pixel_switch_runtime_20261003/report.json)
uses 215 frozen detector/tracker crops and fruit masks. It performs 42 actual
segmentation calls, returning 80 instances at 62.1 ms mean call time. The detector
is loaded but performs zero calls in this isolated replay. Fruit 98 reaches 360 degrees observed
longitude and 85.074% observed surface; predicted defects cover 4.544% of observed
surface and the configured arithmetic assigns Class 1. Three other examples
remain partial. This isolated replay repeats no detector inference and has no
human pose, defect or grade truth. All 51 Python tests, frontend build and lint
pass in the [current software record](backend/diagnostics/software-checks/pixel_switch_runtime_20261003/summary.json).
The original 43-test checkpoint and two preceding failed attempts are retained separately.

The completed full original-video replay includes
[actual track 98](backend/results/ea6e595b8f3f45f2b5edfda8dafff3f2/98/result.json):
one ID is observed from frames 51 through 138, with 360 degrees computed map longitude,
85.150% observed surface and 4.512% predicted defect area, producing Class 1
arithmetic. These are fresh detector/tracker/model outputs, distinct from the
frozen-crop result above. Neither example establishes verified grading accuracy.
Of the 472 Review records, 292 lack sufficient computed map longitude, 164 lack
complete usable silhouettes, six have fewer than two views, and ten have no
reliable rotating sequence. Capture-rejection and motion-pair events are counted
separately; automatic edge/silhouette labels and estimated coverage are not manual
proof of physical truncation or true fruit rotation.

The dashboard defaults to the latest saved report. **All saved runs** includes
earlier development results. The screenshot's 711 Review records match the
138 + 171 + 402 records in the earliest saved reports; association with that
screenshot is an inference because it shows no report IDs. The
[history and display audit](backend/diagnostics/ui-checks/dashboard_scope_20261002/README.md)
separates actual saved reports from artificial UI fixtures. Existing-history
screenshots taken before the new run finished are not evidence of grading by
the adopted algorithm. The
[current real-browser evidence](backend/diagnostics/algorithm-revision/service_20261003/runtime_retry/ui_completed/report.json)
matches the final job and its 2/474 Class 1 outputs. All history contains 2,061
records (17 Class 1 and 2,044 Review), including earlier development runs.

Earlier source `951b55` passed some controls but failed later horizontal turns.
Its native20 setting and subsequent plane/pattern candidates also had documented
motion, author-availability or stationary failures. Those historical profiles
are not the current validated control configuration. See the
[continued-testing report](backend/diagnostics/algorithm-revision/development_followup_20261002/DEVELOPMENT_TEST_REPORT.md),
[failure-image gallery](backend/diagnostics/algorithm-revision/development_followup_20261002/index.html)
and [development log](backend/diagnostics/authors-benchmark/DEVELOPMENT_LOG.md).
The earlier `full_observable_20261002` video completed with 474 records, 7 graded
and 467 Review, using a matcher later found to fail known-turn controls.
`full_hybrid_wobble_20261002` remained incomplete after a service interruption
of unconfirmed cause. Neither supplies a completed full-video result for source50.

The authors' repositories supplied images and annotations; no reusable
reconstruction implementation was found in the inspected repositories. This is
an independent implementation tested against published labels and controlled
geometry. Author-label error, model execution, coverage arithmetic and complete
video execution are different measurements. Reliable field grading and real-time
throughput remain unverified. Original evidence packs and failed trials remain
intact. The current-source pack retains the completed retry alongside the failed
attempt and the source-specific development controls.
Its [explicit evidence configuration](backend/current_profile_evidence_runtime_20261003.json)
and [read-only preflight](backend/current_profile_evidence_runtime_20261003.preflight.json)
verify all 27 named reports and 348 referenced input files. The fresh
[testing report](backend/diagnostics/algorithm-revision/evi_runtime_20261003/VALIDATION_REPORT.md)
and [figure gallery](backend/diagnostics/algorithm-revision/evi_runtime_20261003/index.html)
retain actual author labels, controlled inputs, fresh/frozen model examples and
historical failures. The [evidence ZIP](backend/diagnostics/algorithm-revision/evi_runtime_20261003.zip)
includes 300-dpi PNG/PDF figures, raw reports, input hashes and frozen sources.

Run the existing algorithm checks with:

```powershell
./backend/venv/Scripts/python.exe -B -m unittest discover -s backend -p 'test_*.py'
```
