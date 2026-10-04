# Prepared tracking test

Open [annotate.html](annotate.html) in a browser. It contains 181 consecutive
original frames, 0 through 180, from your conveyor video. Tracker predictions
are hidden; manual physical-fruit labels start empty.

1. Assign each physical fruit a permanent manual ID. Draw its visible box,
   including partially visible fruit at the image edges. Keep that ID as it
   moves and rotates.
2. Review every frame. Copied boxes must be moved and resized; add entering
   fruit and remove departed fruit. Review the whole image before marking the
   frame reviewed. Record identity uncertainty rather than guessing.
3. Enter your name or initials and export `annotation_bundle.json`. Save backups
   regularly. Have a second reviewer check identities independently. Put the
   final bundle beside `manifest.json`.

Run from the project root:

```powershell
$trackingTestDataset = 'backend/diagnostics/tracking-test/20261004_pilot'
./backend/venv/Scripts/python.exe backend/import_tracking_annotations.py --dataset $trackingTestDataset --annotations "$trackingTestDataset/annotation_bundle.json"
./backend/venv/Scripts/python.exe backend/evaluate_tracking_test.py --ground-truth "$trackingTestDataset/ground_truth.csv" --predictions "$trackingTestDataset/predictions_current_raw.csv" --manifest "$trackingTestDataset/manifest.json" --output-dir "$trackingTestDataset/evaluation_current_raw_iou50"
```

The report lists missed detections, false detections, ID switches, split IDs,
duplicate candidates, IDs shared by different fruit, IDF1 and per-fruit results.
The proposed window gate requires at least **95% precision, recall, IDF1 and
stable fruit identities**. Incomplete review or unresolved uncertainty prevents
scoring. These thresholds are proposed requirements, not achieved results.

The command above scores the current tracker, freshly replayed on the saved
real detections. `predictions_current_capture.csv` scores the identity guard's
capture IDs; `predictions.csv` contains the historical tracker output. Use
separate evaluation output directories for each comparison. The source video,
frame interval and dimensions of the current exports were checked against this
pilot; provenance is in `candidate_predictions.json`. The detector was not
rerun in this comparison. The pilot is development footage.
[The full method](../../../TRACKING_TEST_METHOD.md) explains comparisons,
independent review and held-out testing. Use the supplied
`physical_cohorts.csv` to record complete entry-to-exit paths and paths cut off
by the window boundaries; window stability alone does not establish full paths.

Independent annotation remains pending, so real tracking accuracy is **not yet
measured**. [tool_validation.json](tool_validation.json) records software checks.
