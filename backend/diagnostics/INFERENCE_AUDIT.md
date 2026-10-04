# Inference audit — 1 October 2026

## What happened

The completed run `beebe44a008345b5bc53bd64cb2c04a6` processed all 761 frames in 795.6 seconds. All 138 reported fruit tracks had `mapping_failed`, before any fruit grade could be assigned. “Needs review” concealed that distinction.

| Saved failure | Fruit tracks |
|---|---:|
| Oblate pole poses do not follow configured rotation | 111 |
| Fewer than two views | 13 |
| Silhouette too small to fit a spheroid | 12 |
| First pair has zero or unreliable estimated rotation | 2 |

The 350-degree rotation and 65% surface thresholds did not cause these saved failures: reconstruction stopped before those grading gates.

## Tracking

`DfineDetector` instantiates the installed Ultralytics `TRACKTRACK` class and calls its `update()` for detector boxes on every frame. Its eight output columns are `[x1,y1,x2,y2,id,score,class,detection_index]`; the adapter correctly keeps the first seven for `Boxes`. ReID is disabled in the installed configuration. This is an active tracker integration, not a placeholder, but identity accuracy over every fruit has not been measured against labelled tracks.

A new integration test uses the installed tracker with actual NumPy-backed boxes, motion, a missed detection, and reappearance. It verifies stable identity and output-column interpretation. The original tracker test only checked a mocked `.track()` call.

The first 240 frames were rerun with detection and tracking, saving selected crops without defect inference. The [contact sheet](current-upload/captures.jpg) shows stable visible fruit features for sampled IDs and also shows the malformed masks. This sample does not exclude swaps elsewhere.

## Confirmed defects and input problems

1. **Incomplete silhouettes entered the shared shape fit.** Clipped ID 1 eventually produced a mask containing only a small patch. Because `B` uses the minimum minor radius, that one bad view distorted the whole fruit: one original sampled fit gave radii about 78.7 and 10.7 pixels. Excluding clipped views recovers a near-sphere of radius 82.3 pixels. ID 123 is frequently occluded by adjacent fruit.
2. **The rotation configuration did not match the visible rollers.** The application used image `y`; the rollers are approximately horizontal, suggesting image `x`. This is an inference from the footage. Default `x,+1` is now explicit and saved with each new report; direction and off-axis motion still require calibration.
3. **The pole solver was mathematically brittle.** It used an angular phase that is undefined for a pole aligned with the rotation axis. A reproduction with just 0.2-degree silhouette orientation jitter and 0.03-pixel minor-radius jitter triggered the same failure. It also fixed an arbitrary ellipse eigenvector sign and prohibited transverse motion even though texture matching permits it.
4. **Encoded FPS differs from useful image-update frequency.** The clip is 30 FPS, but 609 of its 760 adjacent frame transitions have mean intensity change below 1/255 on a 320×180 grayscale image; 605 are below 0.1/255. There are 151 substantial scene updates plus the initial image, roughly six updates per second. Fixed three-frame sampling records repeats; the earlier speed change to 15 frames skips about three actual views and was not properly calibrated.
5. **A single bad pair aborts the whole reconstruction.** Real fruit can have stationary intervals, occlusion, variable rotation, and poor texture matches. These violate assumptions that every captured pair is useful, rotates in the configured direction, and agrees with the other pairs. The code currently rejects the track rather than inventing coverage.
6. **Two additional mathematical defects were found.** The local refinement grid moved its origin while searching; it now uses a fixed origin and bounds. Visibility used `z > 0`, which is valid for a sphere but not for a tilted oblate spheroid; it now uses the surface normal facing the camera.

## Corrections made

- Reject frame-edge truncation, collapsed masks, and strongly concave silhouettes before they affect the shared shape estimate. Record rejection reasons and captured frame numbers.
- Resolve both image-plane and depth sign ambiguity. Match poles in the same permitted two-axis rotation domain as texture matching, with a small residual tolerance for measurement noise. Report the failing pair when consistency is impossible.
- Correct rotation refinement bounds and tilted-spheroid visibility.
- Replace fixed 15-frame video capture with comparison against the last sampled image, while continuing TrackTrack on every frame. Repeated image content does not consume the view budget; the cap is 120 views per fruit.
- Show **Mapping failed** on historical failed fruit and save settings/sampling diagnostics in new reports.

The silhouette quality and pose-noise tolerances are engineering gates, not validated grading parameters. None of these changes relaxes the required observed surface, rotation coverage, or defect thresholds to force a class.

## Verification and remaining failure

Ten tests pass, including the real tracker integration, noisy-pole regression, front/back visibility, invalid silhouettes, and a textured synthetic spheroid completing over 350 degrees with the production coverage and pair-error gates. The earlier synthetic map test used a relaxed error threshold and did not require a complete turn; it has been strengthened. Frontend build and lint pass.

The [saved crop recheck](current-upload/post_fix_audit.json) shows that shape fits recover for IDs 1 and 108 using accepted views and the horizontal axis. ID 123 has only one acceptable silhouette in the inspected interval. ID 14 still has no consistent pose sequence, despite 48 distinct usable silhouettes. This is an unresolved real-data/model mismatch.

The [mapping recheck](current-upload/mapping_audit.json) also fails: ID 1 has near-zero motion in early pairs; ID 108 reaches a texture mismatch at pair 10 with `x,+1`. These diagnostic runs have no defect masks and were never used to assign grades.

**Conclusion:** TrackTrack is implemented. The original end-to-end reconstruction was not correct or calibrated for this video. Concrete defects have been corrected, but real conveyor reconstruction and grading are still unvalidated. A full rerun would not establish correctness while the representative crop checks still fail. The next required work is fitting/calibrating motion and silhouette uncertainty against manually verified fruit sequences, and deciding how to retain reliable contiguous view sequences through stationary or occluded intervals.

Research basis: [Albiol et al., 2021](https://www.mdpi.com/1424-8220/21/6/2232), [Albiol et al., 2022](https://www.mdpi.com/1424-8220/22/14/5452). This application's adaptation and additional rejection rules are not the authors' validated implementation.
