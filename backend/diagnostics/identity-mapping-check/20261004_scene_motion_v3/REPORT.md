# Tracking attribution and mapping rerun — 4 October 2026

**The observed ID changes do not explain the mapping limitation in the tested sequences.** The evidence points to rotation/view selection as the immediate limiting stage. Smooth, unnoticed exchanges between similar fruit remain possible without physical identity labels.

## What was checked

The original 515-frame job contains 474 records and 294 usable maps. The recovered raw-ID transition 244 → 248 had zero and one usable views respectively; neither ID produced a map. All 15 IDs in the earlier seven legacy/current association disagreements also failed mapping. These specific transitions therefore cannot have introduced seams into a saved surface map.

The updated guard detects no boundary within the selected views of any of the 294 maps. It detects boundaries elsewhere in the captured views of 37 maps, so their preselection shape fits may still be affected. An absence of flags is not a physical identity accuracy claim.

## Guard defect found and corrected

The initial guard assumed zero motion on the first observation pair. A common clip-start displacement triggered 19 overly conservative discontinuity flags; the three selected-map boundaries were all at frame 0 → 1. Visual inspection of fruit 16, 18 and 35 shows consistent fruit markings across that transition. This is visual evidence, not an independently labelled tracking benchmark.

Version 3 initializes each track’s first three observations from the robust common motion of at least five complete, same-ID boxes when at least 70% agree within the existing size-normalized gate. It then uses the track’s own history. An isolated jump amid common movement remains rejected. Four new regression cases check common startup motion, an isolated jump, an incoherent scene and return to local velocity.

The corrected replay has 646 capture segments, 172 gap boundaries and 1 motion/size boundary. The remaining motion/size boundary is raw ID 254 at frame 287, a record with no usable map views. Capture segments are not unique physical fruit counts.

[First-frame visual comparison](onset_transition.jpg)

## Actual mapping rerun

The CUDA defect model made 42 inference calls and returned 80 predicted instances while remapping 215 frozen views across four sequences. Detector/tracker observations were held fixed to isolate mapping. All four produced maps; one reaches the 80% target and three remain provisional partial maps.

| Physical track in cached replay | Input views | Views selected | Observed surface | Coverage |
| --- | ---: | ---: | ---: | --- |
| 98 | 66 | 24 | 85.074% | Meets target |
| 1 | 46 | 12 | 39.144% | Partial |
| 14 | 44 | 2 | 25.962% | Partial |
| 340 (legacy fixture 491) | 59 | 4 | 26.413% | Partial |

![Mapping coverage](mapping_coverage.png)

All 215 fixture crops were linked to the current raw IDs by pixels. For legacy fixture 491, 31 crops match the current detector-box crop exactly; the other 28 were located exactly in the original frame and matched to the unique overlapping box. Every one belongs to current raw ID 340. Comparing numeric IDs across runs without this correspondence would misidentify the fruit.

The mapper repeatedly splits sequences for unobservable/near-zero estimated rotation, high texture-matching error, disagreements between coarse and native rotation estimates, and longitude progression outside its fusion bounds. For fruit 14 it retains only two of 44 views despite continuous capture identity. This explains the immediate low-coverage outcome, but does not by itself identify whether lighting, masks, physical motion or the estimator is responsible.

## Paired reconstruction and controls

Seven paired geometry cases use the four saved fixtures and freshly recaptured source-frame views of onset fruit 16, 18 and 35. Both variants share identical crop/mask arrays. After the guard correction, each has one capture segment, so the guard makes no input change and the map/observed-mask hashes agree. Identical input results are reused rather than portrayed as independent accuracy trials. No defect observations or grades are claimed by this geometry comparison.

The earlier version-1 paired experiment separated the first frame. It changed coverage very little for the four main fixtures, reduced the short onset maps and made onset fruit 35 fail. Correcting startup initialization removes that introduced failure. The historical exploratory `paired_maps` report used the completed-defect flag with empty masks; its grading statuses are excluded from this assessment. The later geometry-only runs explicitly disable that flag.

**Known-area controls pass:** 5%, 15% and 30% truth produce 5.144%, 15.179% and 30.093% measured defects. Maximum error is 0.179 percentage points. All four coverage controls and all 88 Python tests pass. These controls do not establish conveyor reconstruction or grading accuracy.

## Evidence and reproducibility

[Validation summary](validation.json) · [map/identity overlap](map_overlap.json) · [crop correspondence](fixture_correspondence.json) · [paired geometry report](paired_maps_geometry_only/report.json) · [real model mapping report](real_model_mapping_report.json) · [known-area control report](known_area_report.json)

Sources and input hashes are preserved. Original application reports are untouched. This was a saved-observation mapping test; the complete detector-to-map pipeline was not rerun for all 474 records. The corrected guard applies on the next backend start. A defensible physical-ID accuracy result still needs labelled trajectories.

```powershell
./backend/venv/Scripts/python.exe -B backend/replay_identity_guard.py --output backend/diagnostics/identity-guard/20261004_scene_motion_v3
./backend/venv/Scripts/python.exe -B backend/check_identity_mapping.py
./backend/venv/Scripts/python.exe -B backend/compare_identity_maps.py
./backend/venv/Scripts/python.exe -B -m unittest discover -s backend -p 'test_*.py'
```
