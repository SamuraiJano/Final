# Citrusvision naartjie monitor

The dashboard shows the conveyor camera, assigned quality classes, detection and segmentation signals, and recent fruit surface maps. It reads results from either a recorded video or a live camera inspection. Empty states represent actual missing data; the dashboard does not generate sample results.

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

Results are saved under `backend/results/<job_id>/`. The dashboard aggregates saved reports and lets its class and search filters examine all saved records. It displays six rows at a time; **Show more inspections** reveals further matches. Earlier Review records remain in the totals after a new run. Fruit without sufficient observed surface remain ungraded with a reason. To match the real camera and rollers, configure `FRUIT_ROTATION_AXIS` (`x` or `y`) and `FRUIT_ROTATION_DIRECTION` (`1` or `-1`). The current grade rules require at least 350 degrees of **observed map longitude** and 65% observed surface. Physical rotation is reported separately: the visible surface before and after a turn adds coverage. Class 1 and Class 2 defect limits are currently 10% and 20% of the observed surface; these are engineering settings, not validated commercial grading rules.

Open an inspection and expand **Source views and model masks** to see representative input crops, fruit silhouettes and predicted-defect overlays. Partial and failed tracks retain input evidence too. Defect inference is deferred until geometry and rotation select the views used in a map. Those views are segmented before the final coverage check, so some partial maps also contain defect predictions. Green outlines indicate the extracted fruit boundary; red indicates model predictions, not manually verified defects. The downloaded report retains the selected/discarded frame numbers, pair rotations, matching errors and rejection reasons.

`main.py` serves the API and camera, `dfine_segmenter.py` loads the models and TrackTrack, and `algorithm.py` constructs surface maps. Tests cover geometry and the installed TrackTrack interface. `backend/venv` is installed package code, and `__pycache__` is generated Python cache.

The current camera default is horizontal rollers (`FRUIT_ROTATION_AXIS=x`, direction `1`). This is a geometry assumption, not a completed calibration. The real-video audit in [INFERENCE_AUDIT.md](backend/diagnostics/INFERENCE_AUDIT.md) found reconstruction failures even after correcting input and mathematical defects. Synthetic tests do not establish grading accuracy on this conveyor. The historical failed report is preserved.

## Validation evidence, 2 October 2026

The revised algorithm measures connected adjacent views, rechecks successful turns
below 8 degrees using native smoothed green values and a brightness correction,
and checks the same
fruit longitude coordinates before selection and fusion. Missing, failed or
unobservable transitions split a sequence. The [plain-language code walkthrough](backend/ALGORITHM_EXPLAINED.md)
explains detection, tracking, fruit masks, rotation, surface fusion and grading in
six steps. Failed sequences now retain their motion diagnostics in the report.

The conveyor searches up to 20 degrees sideways, instead of the paper's typical
10 degrees. Fruit 98's frames 85–86 hit the old bound; the wider search finds
about −13.2 degrees sideways and passes the unchanged residual limit. The
[interactive fruit walkthrough](backend/diagnostics/algorithm-revision/debug_fruit_98_wobble_20261002/index.html)
shows every captured pair, the tracking entry/exit, the accepted and rejected
matches, and the actual defect predictions. On these frozen crops the model
integration now assigns fruit 98 Class 1 with 360 degrees observed longitude;
the other three debugging examples remain partial. This is our setup adaptation,
not a reconstruction accuracy measurement.

The [current author-data results](backend/diagnostics/authors-benchmark/runs/hybrid_wobble_profile_20261002/report.json)
record 36 maps and 462/497 independently predicted labelled points, with 5.399-pixel
conditional RMS error versus baseline 5.103 pixels for 458 predictions. Of all 497
labels, 373 are within 5 pixels versus baseline 367. The preceding 10-degree
hybrid profile returned 455 points at 5.110 pixels. These conditional RMS values
use different returned subsets; the
[same-label comparison](backend/diagnostics/algorithm-revision/transverse_author_comparison_20261002/SAME_LABEL_COMPARISON.md)
preserves both improvements and regressions. Unavailable labels remain in the
497-label denominator. The retained-map subset also contains a 39.56-pixel error;
map availability does not guarantee a correct pose.

The [known full-turn controls](backend/diagnostics/algorithm-revision/full_turn_hybrid_wobble_20261002/FULL_TURN_CONTROLS.md)
and [fixed conveyor regression](backend/diagnostics/algorithm-revision/fixed_hybrid_wobble_conveyor_20261002/REGRESSION.md)
retain both successful controls and rejected alternatives. The actual segmentation
model was tested on these crops in
[real-model integration](backend/diagnostics/algorithm-revision/real_segmenter_wobble_20261002/report.json).
Execution and coverage do not establish grading accuracy.

The earlier refinement was needed because the preceding matcher accumulated more
than 20 degrees of error on known full turns despite producing maps. It passes
the tested six-degree/subdegree 5-degree / 5-pixel full-turn controls, the 1-degree /
1-pixel short wobble controls, and stationary-noise and exposure-offset checks.
These are limited synthetic development tests; actual conveyor grading still
requires labelled evaluation. The stricter known large-sideways test passes
three of four pairs at 1 degree / 1 pixel; one pair still has 3.27 degrees pose
error and 2.88-pixel landmark RMS. Both successful and failed sources are preserved.

A later horizontal-axis 360-degree control at 12 degrees per view exposed
another failure of the 8-degree recheck profile: maximum pose errors 11.092 and
6.189 degrees despite Class 1 clear maps. It is now a development profile, not
the final validated configuration. A settings-only candidate extends native
rechecking to 20 degrees; it passes the same 12-degree controls at 2.063 and
0.936 degrees, but its author predictions drop from 462 to 416 of 497 labels,
both common-label RMS comparisons worsen, and frozen track 98 drops to 188.39
degrees coverage. It is not an accepted solution. See `full_turn_x12_wobble_20261002` and
`full_turn_x12_refine20_20261002` for the frozen failures and candidate results.

Later camera-fixed illumination controls also expose unresolved matching errors.
The best of these unadopted local-contrast trials passes 11 of 12 frozen scenes;
one full turn still has 8.39-degree / 5.68-pixel error despite a Class 1 map.
The [continued testing report](backend/diagnostics/algorithm-revision/development_followup_20261002/DEVELOPMENT_TEST_REPORT.md)
and [actual failure-image gallery](backend/diagnostics/algorithm-revision/development_followup_20261002/index.html)
keep the exact inputs, source hashes, successful controls and failures. The fast
aligned author's-data trial covers only 15 mandarin sequences, not all 36.
The subsequent full nine-sample pattern trial passes 10 of those 12 scenes;
texture A still fails under curved illumination, even though a separately
rendered fresh texture C passes both full-turn lighting controls. These outcomes
remain tied to their exact source snapshots.

The `full_hybrid_wobble_20261002` original-video API attempt is incomplete at the
recovery checkpoint: 515 frames were saved, but the service was absent and no
final report existed. Its cause is unconfirmed; recovery outcomes require separate
provenance. The previous `full_observable_20261002` run finished
with 474 tracked records, 7 graded and 467 Review; that matcher later failed the
known full-turn test and is retained as a development result. Historical saved
records remain in the dashboard totals.

Windows backend refresh now stops the managed process tree directly through
`scripts/stop_process_tree.py`: this setup denied `taskkill` process enumeration.
The actual refresh test returned 200 and verified both old Python processes
exited before the new service started. Refresh remains blocked during inference.

The later [algorithm decision report](backend/diagnostics/algorithm-audit/decision_20261002/ALGORITHM_DECISION.md) identifies accepted bad skipped-frame matches and a conveyor longitude-ordering failure. Its [figure gallery](backend/diagnostics/algorithm-audit/decision_20261002/index.html) and [evidence ZIP](backend/diagnostics/algorithm-audit/decision_20261002/algorithm_audit_evidence.zip) retain the actual images, labels, geometry controls, rejected candidate fixes and source snapshots. These findings support correcting motion matching and view selection; the tested safeguards remain experimental, and production code was not changed during this audit.

Start with the [validation report](backend/diagnostics/authors-benchmark/evidence_20261002/VALIDATION_REPORT.md), [figure gallery](backend/diagnostics/authors-benchmark/evidence_20261002/index.html), or [PDF figures](backend/diagnostics/authors-benchmark/evidence_20261002/validation_figures.pdf). The [evidence ZIP](backend/diagnostics/authors-benchmark/evidence_20261002/report_evidence.zip) includes the report, 300-dpi figures, test outputs, frozen source, raw result JSON and selected image evidence. Full datasets, experimental outputs and model weights remain in their workspace locations; they are not all duplicated into the ZIP.

The independent implementation was tested against all 36 public author sequences and 497 labelled feature correspondences, analytical geometry, synthetic known-defect masks, and the exact original 515-frame conveyor video with the user's own detector and segmenter. Reference reconstruction improved, but many conveyor records still fail or have insufficient coverage. Pipeline execution and numerical grade output do not establish reliable grading accuracy. Successful and unsuccessful trials are documented in [DEVELOPMENT_LOG.md](backend/diagnostics/authors-benchmark/DEVELOPMENT_LOG.md). The authors' public repositories supplied data and labels; a reusable reconstruction implementation was not found in the inspected repositories.

Run the existing algorithm checks with:

```powershell
./backend/venv/Scripts/python.exe -B -m unittest discover -s backend -p 'test_*.py'
```
