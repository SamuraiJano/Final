# Testing whether one tracker ID follows one physical fruit

This method tests detector coverage and physical identity independently of the
surface mapper. A track count, a smooth path, a clean-looking map, or a guard's
`trusted` flag is not identity ground truth. The existing saved-box consistency
audit in [TESTING_PROCESS.md](TESTING_PROCESS.md) does not establish tracking
accuracy. The earlier identity audit used informal terminology for switches and
fragmentation; the precise definitions below govern this test.

## What the test must answer

For every independently labelled physical naartjie, determine whether the
tracker detects it, follows it with the same identity, temporarily loses it,
assigns several identities to it, or assigns its identity to another fruit.
Evaluate raw tracker IDs and map-capture IDs separately. A conservative capture
guard can prevent wrong-fruit fusion while increasing the number of segments;
these are different outcomes and must both be reported.

Tracking passing this test does not prove correct rotation, surface coverage,
defect segmentation, or grading. The user's 80% mapping target remains a separate
test: accepted, correctly aligned maps divided by independently counted physical
fruit entering a predefined inspection region.

## Freeze the sample before examining predictions

1. Define the source video, original frame interval, image dimensions and region
   of interest (ROI). The prepared pilot uses the whole image as its fixed ROI;
   it does not select only fully visible fruit. Include every fruit and every
   original frame in that interval, including empty frames. Do not sample every
   fifth or tenth frame: a short identity exchange can happen between them.
2. Record hashes of the video, cached tracker observations, tracker configuration,
   detector weights and source code. Preserve the detector threshold, image
   resolution, frame rate, tracking implementation/version, camera-motion
   compensation, duplicate suppression, ID guard configuration and any frame
   skipping. A configuration comparison must change only its declared factors.
3. Prepare an annotation bundle before viewing tracker overlays. Annotators see
   original frames and their own physical labels, never the predicted IDs, map
   grades, failure flags or proposal boxes. Make the annotation copy read-only
   after review and hash it before evaluating predictions.
4. Use the existing clip for a development pilot. It has been examined during
   repeated tracker and mapper development and is not a held-out accuracy test.
   A final test requires new clips reserved before tuning, preferably covering
   several recordings or conveyor batches. Split whole clips or independent
   complete physical trajectories, never neighbouring frames from one fruit.
5. Keep a representative sample separate from a challenge sample. The
   representative sample should follow consecutive time intervals chosen without
   tracker outcomes. The challenge sample deliberately covers close neighbours,
   partial entry/exit, detection gaps, occlusion, glare, blur, similar appearance,
   different fruit sizes, tumbling and slow or irregular travel. Report both;
   do not combine a cherry-picked challenge set into a claimed natural yield.

The first prepared pilot covers original frames 0 through 180 inclusive, about
six seconds at this video's recorded frame rate. It contains many simultaneous
fruit; annotation is substantial work. Inspect all 181 frames, rather than
labelling a few tracker-selected paths. A final representative test should
contain at least 100 independently counted entrants across at least three
reserved clips. These sample sizes are proposed engineering requirements, not
thresholds prescribed by a research paper.

## Annotate physical fruit independently

Give each physical fruit a permanent positive integer manual label, for example
`1`, from its first visible appearance until its final visible
appearance. Manual labels need not equal tracker IDs. Different numeric IDs
between independent tracker runs are normal; evaluation compares associations,
not the literal ID numbers.

For every frame:

- Draw a tight axis-aligned box around every fruit's visible pixels. Include all
  visible pieces of a partly occluded fruit. Do not invent the hidden outline.
  The box convention is deliberately consistent with visible detector boxes,
  including entry/exit caps. It is a local fruit benchmark convention, so its
  scores should not be compared directly with pedestrian leaderboard scores.
- Keep the same manual label while position and neighbouring fruit establish
  continuity. Rotation changes the visible peel, so a changing surface mark
  alone does not indicate a different fruit. Inspect normal playback, slow
  playback and forward/backward frame stepping when fruit are close.
- If fruit is partly occluded but still identifiable, annotate its visible box
  and retain its manual ID. If completely hidden, create no detection box for
  that frame. Retain its ID on reappearance only when continuity can be
  independently established. Report such gaps separately from visible misses.
- If two fruit cannot be distinguished through an occlusion or contact, mark
  the interval unresolved. Do not choose an identity by reading the tracker's
  output, invent a box, silently omit difficult fruit, or connect uncertain
  pre/post trajectories. Record the frames, affected manual IDs/locations and
  reason. Unresolved identity prevents a final correctness gate, although a
  labelled visible subset may still support a clearly qualified diagnostic.
- Review the complete frame, then mark it reviewed. Reusing a previous frame's
  boxes is an editing aid only: inspect and correct every inherited box and
  every newly entering/leaving fruit before marking the frame reviewed. A blank
  frame can be reviewed as empty; an unreviewed frame cannot be treated as empty
  ground truth.

The current interface exports a JSON annotation bundle and the importer produces
`ground_truth.csv`. Local evaluation frames start at 1. The manifest records the
original zero-based start frame, so local frame 1 is original frame 0 for this
pilot. Box coordinates are zero-based pixel `x, y, width, height`; this is a
local CSV convention, not a claim to be a complete MOTChallenge file. Width and
height must be positive, IDs unique per frame, and all values finite. Only an
explicit MOTChallenge export should convert its required coordinate/indexing
conventions. [Official format reference](https://github.com/JonathonLuiten/TrackEval/blob/master/docs/MOTChallenge-format.txt).

The CSV has no header. Ground-truth rows contain ten fields:

```text
frame,physical_id,x,y,width,height,1,-1,-1,-1
```

The final four values declare an assessed GT box; ignored GT rows are prohibited.
Prediction rows use the same first six fields with the recorded prediction
confidence in field seven. Evaluation counts every prediction row without a
new confidence filter, including predictions on reviewed empty frames.

## Independent review and denominators

A second reviewer should inspect every identity ambiguity, close encounter,
gap/reappearance and clip boundary, plus a random sample of at least 20% of the
remaining trajectories. For final held-out evidence, obtain independent
annotation/review of the entire set if feasible. Resolve disagreements using
original pixels before showing either reviewer the predictions. Record reviewer
names or anonymous reviewer codes, dates and corrections.

Maintain three explicit denominators:

| Denominator | Use |
| --- | --- |
| Every annotated visible fruit-frame inside the frozen ROI | Detection precision/recall, localisation and identity metrics. |
| Every physical fruit first entering the frozen ROI during the counting interval | Mapping yield and physical counting; an ID change does not add another fruit. |
| Independently verified complete entry-to-exit physical trajectories | Full-path stability; clips beginning/ending midway through a path are censored and reported separately. |

For a future ROI, freeze a deterministic membership rule such as annotated box
centre inside a fixed rectangle, annotate a surrounding buffer for continuity,
and report the boundary policy. Count each physical entrant once at first
outside-to-inside crossing. Fruit already inside at the interval start form a
separate cohort. Retain entrants that later become difficult or disappear;
they remain in the mapping denominator. Capture enough preceding/following
footage to establish entry and exit. Do not retrospectively narrow the ROI or
remove edge fruit to improve the score.

The pilot's complete visible-frame metrics include start/end-censored fruit.
Those fruit do not demonstrate full entry-to-exit correctness. The annotation
interface currently records boxes and unresolved frames, rather than entry/exit
metadata. Keep a separate reviewed `physical_cohorts.csv` with these fields:

```text
physical_id,first_visible_frame,last_visible_frame,entry_frame,exit_frame,left_censored,right_censored,unresolved_identity,reviewer,notes
```

Use local 1-based frames, `true`/`false` flags and blank entry/exit when not
observed. `left_censored=true` means the fruit is already visible at the interval
start; `right_censored=true` means it remains visible at the interval end. A
known physical identity that temporarily leaves and re-enters is counted once.
Do not infer an exit from a tracker stopping output. This cohort sheet is a
manual review artifact, not an automatically inferred output of the current
evaluator. It must establish entrant and complete-trajectory denominators before
reporting those percentages. Do not interpret the count of raw records as
either physical-fruit denominator.

## Match boxes and calculate errors

Use IoU (intersection over union) of visible boxes with a fixed primary threshold
of 0.50. Match detections one-to-one within each frame: one prediction can match
at most one fruit and one fruit can match at most one prediction. Log each match
and unmatched box with its original frame number. Also report 0.30 and 0.70 IoU
as sensitivity checks; keep the primary threshold frozen and do not select the
most favourable result. A low IoU may reflect a box-size error rather than an
identity error, so inspect error clips before assigning the cause.

| Metric | Definition and interpretation |
| --- | --- |
| Detection recall | Matched visible GT boxes / all visible GT boxes. Missing visible fruit is a false negative. |
| Detection precision | Matched prediction boxes / all prediction boxes. Unmatched predictions, including surplus duplicates, are false positives. |
| Identity switches (IDSW) | A physical GT trajectory's currently matched predicted ID differs from its last previously matched predicted ID, including after a gap. Report events per 100 physical fruit as well as the absolute count. |
| Tracking interruptions / fragmentation | A physical trajectory is matched, becomes unmatched while assessable, then is matched again. Report visible missed frames and recovered gaps separately. Several successive IDs without a missed frame can be ID switches without this interruption. |
| Split identities per fruit | Number of distinct matched predicted IDs assigned to each physical fruit. This directly tests the concern that one naartjie receives several IDs. It is a custom diagnostic, not standard CLEAR fragmentation. |
| Simultaneous duplicate candidates | Surplus predictions overlapping the same annotated physical fruit above the fixed IoU threshold while it already has a one-to-one match. Review nearby-fruit cases; geometric overlap alone is only a duplicate candidate. |
| Same-ID mixing / transfer | A single predicted ID is matched to more than one independently labelled physical fruit over its lifetime. Report the affected IDs, physical fruit, frames and verified events. This is especially dangerous for map fusion. |
| IDF1 | Global identity F1 using an optimal one-to-one assignment of complete GT and predicted trajectories: `2*IDTP / (2*IDTP + IDFP + IDFN)`. Report ID precision and ID recall as well. |
| Per-fruit window stability | Fraction of independently labelled physical fruit that keep one exclusive predicted identity during the scored window with the declared observation recall, without a switch or mixed identity. Report duplicate and interruption counts separately. This is an observed-window diagnostic, including censored paths. |
| Complete-path stability | Apply the same definition only to the independently reviewed complete entry-to-exit cohort. Use the manual cohort sheet; a short clean observation does not prove a complete physical path. |

CLEAR matching gives continuity from the immediately preceding timestep priority
over IoU before assignment; its switch count remembers the last matched ID
across gaps. A simple nearest-centre matcher or an IoU-only assignment is useful
as a diagnostic but should not be labelled an exact official CLEAR score.
[Official CLEAR implementation](https://raw.githubusercontent.com/JonathonLuiten/TrackEval/master/trackeval/metrics/clear.py).

The provided evaluator maximises the number of valid frame-level matches and
then their total IoU. Its switches, interruptions, overlap duplicate candidates
and reused-ID checks are explicit local diagnostics. They are not presented as
official CLEAR, HOTA or MOTA scores. Its strict window-success check requires
at least 95% visible-frame recall, at least 90% dominant-ID coverage of the same
visible frames, and no switches, reused IDs or duplicate candidates. Inspect
candidate events, and keep the stricter proposed validation gate separate from
this per-fruit calculation.

Standard IDF1 first accumulates all valid GT/prediction detection overlaps at the
fixed threshold, then chooses a global one-to-one trajectory assignment. It is
not frame-level detection F1 and must not be calculated only from the local
matching table. Extra IDs for one fruit or one ID shared between fruit reduce
identity correctness. [Official Identity implementation](https://raw.githubusercontent.com/JonathonLuiten/TrackEval/master/trackeval/metrics/identity.py).

For publication or comparison, validate exports with the official TrackEval
implementation and include HOTA, DetA and AssA. HOTA jointly measures detection
and association; its standard score aggregates thresholds rather than being a
single IoU-0.50 score. ID switches alone can miss a predicted ID transferring to
another GT fruit, so they cannot replace the mixing check. MOTA alone is also
insufficient for this identity question. [HOTA paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC7881978/),
[official evaluator](https://github.com/JonathonLuiten/TrackEval).

## Proposed tracking acceptance gate

Freeze this proposed gate before the held-out run. These limits reflect the
application's need to avoid mixing fruit; they are not paper-derived guarantees.

- Complete, independently reviewed annotations for every declared frame; no
  unresolved identity event in the scored held-out set.
- At least 95% visible-frame detection recall, 95% detection precision and 95%
  IDF1 at the frozen primary box threshold.
- At least 95% stable physical identities during the observed window, each with
  at least 95% visible-frame recall. Publish the actual numerator and denominator,
  including each failure and each censored path. Repeat this calculation on the
  complete entry-to-exit cohort for final evidence; a dataset without that cohort
  supports only window stability.
- Zero verified wrong-fruit mixing in the map-capture sequences submitted to
  reconstruction. Raw tracker failures and rejected/cut capture segments remain
  visible in the report even if a guard prevents contaminated maps.
- At least 100 independent entrants across at least three reserved clips, with
  the representative and challenge results shown separately. Report uncertainty
  for the fruit-level proportions; even zero observed failures in 100 fruit does
  not prove a zero failure rate in operation.

Any gate failure has a specific next action: improve missing/duplicate boxes for
detection errors; revise association for verified switches; revise uncertainty
segmentation for mixed map inputs; improve capture or ground truth for
unresolvable occlusion. Do not lower the gate after inspecting a result. A pilot
may identify useful fixes without being eligible for a final pass.

## Prepare, annotate, import and score

Run these commands in PowerShell from the project root. Choose a new dataset
folder when preparing another sample: preparation refuses to overwrite one.
The cached predictions below are historical outputs, so this first test measures
those recorded associations rather than a fresh run of the current production
tracker.

```powershell
$trackingTestDataset = 'backend/diagnostics/tracking-ground-truth/pilot_new'
./backend/venv/Scripts/python.exe -B backend/prepare_tracking_test.py --video 'C:\Users\USER\Pictures\Camera Roll\WIN_20260818_13_29_43_Pro.mp4' --predictions 'backend/diagnostics/entry-tracking/entry_full_20261002/immediate_one_detection.json' --output-dir $trackingTestDataset --start-frame 0 --end-frame 180
```

Open the new folder's `annotate.html` in a browser, label every visible fruit,
review every frame, record uncertainty and export `annotation_bundle.json`.
Browser storage is a convenience; export backups regularly. If a browser blocks
local files, serve the prepared folder locally and open its annotation page.
Store the export beside `manifest.json` after independent review, then import
and evaluate:

```powershell
./backend/venv/Scripts/python.exe -B backend/import_tracking_annotations.py --dataset $trackingTestDataset --annotations "$trackingTestDataset/annotation_bundle.json"
./backend/venv/Scripts/python.exe -B backend/evaluate_tracking_test.py --ground-truth "$trackingTestDataset/ground_truth.csv" --predictions "$trackingTestDataset/predictions.csv" --manifest "$trackingTestDataset/manifest.json" --output-dir "$trackingTestDataset/evaluation_iou50" --iou-threshold 0.5
```

Read `evaluation_iou50/REPORT.md` and `tracking_evaluation.json`, including every
per-fruit failure and per-frame event. Incomplete review or unresolved identity
must be fixed before a scored correctness result; an empty prepared GT file is
not a perfect-tracking result. Use separate output folders when repeating at IoU
0.30 and 0.70. Export/import validates declarations and file structure, not the
truth of human labels. The separate cohort sheet and independent review remain
necessary.

For the complete existing clip, preparation can use `--end-frame 514` in a new
folder. That is still development footage and requires all 515 frames to be
annotated; the cached run contains 32,875 predicted observations, illustrating
the annotation workload without defining the true fruit count.

## Link tracking errors to the mapping issue

After freezing the labels, evaluate the same predictions against them and trace
each map's retained source frames to their physical labels. A retained map must
contain observations of exactly one confirmed physical fruit. List every fruit
split over raw IDs/capture segments, its discarded viewing time and its mapping
coverage. If an identity event falls outside the retained frames, it is not
evidence that the event corrupted that map.

Reconstruct a small affected subset twice using the same crop pixels, masks,
rotation parameters and segmentation outputs: once with current associations,
once with independently verified physical associations. Do not bridge an
unobserved interval or alter the mapper's reliability thresholds. Compare
accepted views, rejected pairs, surface/longitude coverage and visually checked
alignment. Improvement with corrected associations supports tracking as a cause
for those fruit. Continued failure with correct identities points to masks,
motion estimation, fusion or insufficient actual surface visibility.

## Evidence to preserve

Keep the frozen manifest, original frames, reviewed annotation bundle,
ground-truth CSV, predictions, per-frame matches, per-fruit tables, metric JSON,
error clips, tracker/model/source hashes and exact commands together. Record
missing/unreviewed frames, unresolved events and boundary-censored paths. Report
development results separately from held-out results, and synthetic test
correctness separately from real fruit accuracy. Preserve failed configurations
and their results; neither a successful program exit nor an empty error list on
unlabelled footage establishes that the tracker is correct.

## Test current tracker and guard predictions

The prepared pilot at `backend/diagnostics/tracking-test/20261004_pilot` already
contains historical `predictions.csv`, current `predictions_current_raw.csv`
and current `predictions_current_capture.csv`. Both current files have 9,882
observations from original frames 0..180. Their conversion checked source-video
hash, interval and dimensions; see `candidate_predictions.json` and
`prepare_current_comparison.py` in that folder. All three can be evaluated
against the same independent labels and frozen manifest, without creating a new
annotation bundle or changing its dataset ID:

```powershell
$trackingPreparedDataset = 'backend/diagnostics/tracking-test/20261004_pilot'
./backend/venv/Scripts/python.exe -B backend/evaluate_tracking_test.py --ground-truth "$trackingPreparedDataset/ground_truth.csv" --predictions "$trackingPreparedDataset/predictions_current_raw.csv" --manifest "$trackingPreparedDataset/manifest.json" --output-dir "$trackingPreparedDataset/current_raw_evaluation_iou50"
./backend/venv/Scripts/python.exe -B backend/evaluate_tracking_test.py --ground-truth "$trackingPreparedDataset/ground_truth.csv" --predictions "$trackingPreparedDataset/predictions_current_capture.csv" --manifest "$trackingPreparedDataset/manifest.json" --output-dir "$trackingPreparedDataset/current_capture_evaluation_iou50"
```

The prepared ground truth starts empty. Complete the blind annotation and import
steps before scoring. Replaying current code produced identical raw association
rows to the historical pilot; this is a reproducibility result, not evidence of
correct physical identities. The guard produced 282 capture IDs versus 202 raw
tracker IDs, which requires independent labels to distinguish protective splits
from lost continuity.

The pilot initially freezes historical predictions. To evaluate the current
association code on exactly the same images, replay the retained detector
outputs through the current tracker. This isolates association changes from
detector changes and makes zero detector, defect or mapping inference calls:

```powershell
$trackingCandidate = 'backend/diagnostics/tracking-ground-truth/current_tracker_new'
./backend/venv/Scripts/python.exe -B backend/export_tracking_test_predictions.py --video 'C:\Users\USER\Pictures\Camera Roll\WIN_20260818_13_29_43_Pro.mp4' --detections-cache 'backend/diagnostics/entry-tracking/entry_full_20261002/raw_detections.npz' --output-dir $trackingCandidate --frames 181 --device cpu
```

The exporter requires the cache's original `report.json` to agree with the video
SHA-256 and requires every requested original frame. It writes `tracking.json`
for raw tracker IDs and `capture_tracking.json` for the guard's capture IDs,
plus guard decisions, configuration, version information, input hashes and
frozen source files. A guard may protect against wrong-fruit mixing by splitting
a capture at a gap; report those splits separately from raw tracking accuracy.

Before scoring a candidate against existing labels, confirm the same video
hash, original interval 0..180, full-frame region and dimensions in both
reports. Convert the candidate's zero-based xyxy JSON to local one-based xywh
MOT CSV using the existing preparation converter; do not renumber physical
ground-truth identities or replace the frozen annotation manifest:

```powershell
@'
import csv, json, sys
from pathlib import Path
from backend.prepare_tracking_test import prediction_rows
candidate = Path(sys.argv[1])
for source, target in [('tracking.json', 'raw_predictions.csv'), ('capture_tracking.json', 'capture_predictions.csv')]:
    rows = prediction_rows(json.loads((candidate/source).read_text()), 0, 180)
    with (candidate/target).open('w', newline='', encoding='utf-8') as stream:
        csv.writer(stream).writerows(rows)
'@ | ./backend/venv/Scripts/python.exe -B - $trackingCandidate
./backend/venv/Scripts/python.exe -B backend/evaluate_tracking_test.py --ground-truth "$trackingTestDataset/ground_truth.csv" --predictions "$trackingCandidate/raw_predictions.csv" --manifest "$trackingTestDataset/manifest.json" --output-dir "$trackingCandidate/raw_evaluation_iou50"
./backend/venv/Scripts/python.exe -B backend/evaluate_tracking_test.py --ground-truth "$trackingTestDataset/ground_truth.csv" --predictions "$trackingCandidate/capture_predictions.csv" --manifest "$trackingTestDataset/manifest.json" --output-dir "$trackingCandidate/capture_evaluation_iou50"
```

Both reports remain blocked until the independent labels are complete and unresolved events
are resolved. Reuse those verified labels for candidate comparisons on this
exact interval; creating a different prepared dataset changes its bundle ID.

For a genuinely new held-out recording, omit `--detections-cache` to run the
local D-FINE detector and current tracker, and prepare/annotate its original
frames independently. That mode performs real detector inference, records the
checkpoint hash and does not run defect segmentation or mapping.
