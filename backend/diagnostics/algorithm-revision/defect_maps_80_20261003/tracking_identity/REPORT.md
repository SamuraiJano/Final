# Tracking identity audit — 3 October 2026

The detector finds a fruit box in each image. The tracker links those boxes to one physical fruit over time. Surface reconstruction requires that link: rotating views of two different naartjies must never be fused into one map. A one-fruit capture chamber or conveyor pockets identified by an encoder could supply identity instead of a visual multi-object tracker. The present video contains many fruit simultaneously, so removing every form of association would remove a necessary input to reconstruction.

An ID switch means an existing identity follows a different physical fruit. Fragmentation means one fruit receives several successive IDs. The first can mix texture and defects into an invalid map; the second loses viewing time and usually produces several partial maps. Different numeric IDs between separate analysis runs are expected and are neither error by themselves.

## What was checked

Read every `tracking_history` in the original full application job `ea6e595b8f3f45f2b5edfda8dafff3f2`, and compare each saved observation with the frozen detector-only replay in `backend/diagnostics/entry-tracking/entry_full_20261002`. No neural models, map reconstruction, or model training were run. Original results, sealed evidence bundles, and production tracker source were not changed.

- 515 original frames; 474 saved track records; 32,875 observed boxes.
- All 32,875 boxes matched the retained replay with exactly zero coordinate discrepancy.
- Current tracker adapter and frozen replay adapter have the same SHA-256: `20049bf4e24678342364f85b1f4eea69a36f5385c858189b40b52fac11fc360a`.
- Median motion over 19,540 consecutive pairs of fully visible boxes was 0.12 pixels sideways and 13.06 pixels downward per original frame. This establishes an image-coordinate motion pattern, not metres per second.
- A deliberately broad diagnostic flagged complete-box movement exceeding 0.35 fruit diameters per frame, lateral movement exceeding 0.25 diameters, backward movement exceeding 0.15 diameters, or more than a factor-of-two area change. All 19 flagged pairs occurred at the shared clip-start transition from frame 0 to 1; none occurred later. These are exploratory thresholds, not validated identity safeguards. Smooth exchanges between nearby fruit can evade them.
- 172 successive observations had a gap, including 117 two-frame gaps and a maximum gap of 26 frames. A gap does not prove an identity switch.

The earlier full-clip comparison between legacy and immediate-entry tracking contained seven association disagreements. Together these involve 15 revised track IDs. Fourteen have zero usable map views and one has only one; **all 15 failed mapping and none produced a surface map**. Consequently, these known disagreements do not explain defects or seams in the current mapped fruit. The legacy tracker is not ground truth, so the seven disagreements are not seven measured ID switches.

The current mapping algorithm already rejects missing-frame pair bridges (`Settings.maximum_view_index_gap=1`) and splits motion sequences at failed or unobservable transitions. This is useful protection, but a smooth identity switch on consecutive frames may still pass geometry. Spheroid fitting currently starts with all captured views of one published ID, before the final rotating sequence is selected. An identity safeguard must separate uncertain view sequences **before shape fitting**, not merely suppress one rotation measurement later.

![Tracking audit](tracking_audit.png)

[300 dpi PNG](tracking_audit.png) · [PDF](tracking_audit.pdf) · [raw audit](audit.json)

## A reversible configuration experiment

Replayed the same cached actual D-FINE outputs over all 515 original video frames, on CPU, changing only camera-motion compensation to `none`. This tested a plausible fixed-camera explanation without rerunning either neural model or changing production tracking.

| Continuity indicator | Existing sparse optical flow | Experiment with compensation disabled |
| --- | ---: | ---: |
| Published track IDs | 474 | 506 |
| IDs with at most two observations | 54 | 82 |
| Median observations per ID | 86 | 83 |
| Concurrent box pairs with IoU > 0.7 | 0 | 0 |

Fourteen existing IDs substantially matched multiple experimental IDs. Track counts alone cannot identify the better physical associations, but this experiment increased short fragments. It provides no support for disabling camera-motion compensation as an immediate fix. The production setting remains unchanged. The final tracker-only replay took approximately 27.7 seconds; this is not full-pipeline throughput. A preceding replay produced byte-identical experimental tracking rows. Recorded versions are Ultralytics 8.4.170, OpenCV 5.0.0 and NumPy 2.5.3.

The same script runs a known synthetic counterexample against the installed tracker: physical fruit A appears at a box, one detection is missing, and physical fruit B appears at the identical box. The published identity is `1 → absent → 1`. This demonstrates that geometry alone cannot determine physical identity after ambiguity. It does **not** demonstrate that this replacement occurred in the user's real clip.

[Experiment report](no_gmc_experiment.json) · [experimental tracking rows](no_gmc_tracking.json) · [reproduction script](replay_without_gmc.py)

## Concrete identity safeguards to implement and test

1. **Label a validation subset first.** Give 20–30 physical fruit permanent manual labels from entry to exit in this original clip. Include closely spaced fruit, every known edge disagreement, missing detections and any apparent crossing. Record `frame, physical_id, bbox` and explicitly mark unresolvable occlusions as unknown. Reserve a subset of these paths for the final check after tuning.
2. **Use conveyor motion in association.** Predict each centre from its last two or three trustworthy complete observations. Gate candidate boxes by prediction error, direction of travel and plausible size. Express tolerances as fractions of each fruit's diameter and as permitted displacement per elapsed frame, so changing resolution does not invalidate the rules. Determine final thresholds on the labelled paths; the exploratory audit thresholds above are not a calibrated production recommendation. Exempt or handle clipped entry/exit arcs separately, because their visible centres and box areas change rapidly.
3. **Use real lane constraints where the machine supplies them.** Permit matches within a calibrated physical lane or conveyor pocket. Do not invent lanes from a single image if fruit can roll between them. Mechanical spacing and guide channels reduce ambiguous crossings more directly than a generic appearance model.
4. **Expose ambiguous association.** If two different prior tracks are similarly plausible for one detection, or one prior track can plausibly match two detections, log the alternatives and set `identity_status='uncertain'`. A long gap or reappearance near another fruit must be evaluated as possible replacement, rather than automatically trusted because the tracker retained a numeric ID. The current adapter does not expose these quality flags.
5. **Separate map capture at uncertainty before fitting.** Retain the tracker ID for the annotated video, but close the current map-capture segment and start another. Do not combine segment areas or defects under a claim that they are the same fruit. Uncertain identity should prevent a final whole-fruit grade, even if the map claims high coverage; an 80% coverage gate does not certify identity.
6. **Validate the changes with the same cached detections.** Measure true ID switches, fragmented physical paths and wrongly merged map segments on the manually labelled subset. Also check first accepted detection, final observation and simultaneous duplicate IDs. Require zero wrong-fruit map merges in the labelled test paths, then rerun map reconstruction only for those paths to verify defects and coverage. Report the number of labelled fruit and occlusions; do not convert a box-consistency check into an accuracy claim.

A simple guard API could return a reason alongside an association:

```python
check_identity_continuity(previous, current, other_candidates, predicted_motion)
# -> {"trusted": bool, "reason": str, "gap_frames": int,
#     "prediction_error_diameters": float, "best_cost": float,
#     "runner_up_cost": float}
```

Run it before new views enter a map segment. Store its decisions with the video frame and original detector coordinates. When `trusted` is false, keep the observed detection for audit and start an independent reconstruction segment. The thresholds, ambiguity rule and segment handling need the labelled replay validation above. This API is a proposed design, not a claim that it is already active.

Generic person ReID embeddings are not established naartjie identity descriptors; a fruit-specific appearance model would require training and validation across rotation, lighting and occlusion. Simply enabling `with_reid=True` would not supply that evidence, and the D-FINE adapter currently supplies no per-detection embeddings to the tracker's `model='auto'` path.

## Reproduce this audit

From the project root, using PowerShell:

```powershell
./backend/venv/Scripts/python.exe -B backend/diagnostics/algorithm-revision/tracking_identity_20261003/audit_saved_tracking.py
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'backend/runtime/ultralytics'
./backend/venv/Scripts/python.exe -B backend/diagnostics/algorithm-revision/tracking_identity_20261003/replay_without_gmc.py
./backend/venv/Scripts/python.exe -B backend/diagnostics/algorithm-revision/tracking_identity_20261003/make_audit_figure.py
```

These commands overwrite only this new diagnostic folder's audit files. The video and cached detections must remain at their recorded source paths. SHA-256 inputs are recorded in the JSON reports. Figure rendering was visually checked for readable labels and layout.
