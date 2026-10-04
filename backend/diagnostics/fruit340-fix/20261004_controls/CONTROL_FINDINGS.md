# Fruit 340 correction: independent control findings

The final candidate preserves the established known-motion controls. Its bounded native 3D search measures the two independently frozen complete-turn scenes accurately. The one-pixel rolling observability floor removes the subpixel stationary false fits exposed during development.

Final candidate SHA256: `ed3328de998abba50cf9c135957176649bc2d2ef51ededc9eeed90be1bffc9af`. Baseline SHA256: `6c592861d9318456856f6a05c780f6a8fdd77c4c50286cc0b748ff094f397371`.

| Validation | Final result | Evidence |
| --- | --- | --- |
| Established 19-scene motion/stationary suite | All 19 controls pass; 190 moving pairs measured and 752 stationary/uniform pairs rejected | [Full comparison](candidate_03/report.json) |
| Native 3D complete-turn component | 60/60 pairs measured; maximum propagated pose error 0.1289 degrees and visible-landmark RMS 0.0838 pixels | [Component report](native_spatial_component_03/report.json) |
| Native 3D stationary component with independent consensus | All 32 prescribed stationary pairs rejected; zero false motion | [Stationary report](native_stationary_component_03/report.json) |
| Additional changing-light stress | One pre-existing stationary false-motion case remains; all outputs unchanged | [Stress comparison](stress_candidate_03/report.json) |
| Full estimator on independently known 3D tumbling sequences | Both controls retain pre-existing failures when coarse 2D matching succeeds | [Full estimator comparison](spatial_candidate_03/report.json) |

The original 942-pair suite reruns every final-candidate measurement. Baseline measurements are reused explicitly after verifying the exact baseline source, analytical validators, input pixels and acceptance references. All existing measured outputs are preserved. This suite attempts native rescue only on 19 uniform/untextured pairs, and rejects them all; it establishes preservation and unavailable-texture safety rather than successful rescue accuracy.

Before the rolling-pixel floor, independent forward/backward consensus still admitted 13/32 false stationary component matches. The largest rolling displacement was 0.6389 pixels. Their maximum inverse disagreement was 0.5744 degrees, so the three-degree consistency gate alone did not reject them. [Preserved failed component control](native_stationary_consensus_02/report.json).

The additional log-linear light-reversal stress scene at gradient 0.012 with texture B returns one false stationary pair in both baseline and final candidate. That existing 2D path estimates 5.1427 degrees and creates a partial ungraded map. The frozen input was prescribed before either estimator ran. This failure is preserved and is outside the new coarse-failure fallback.

The full estimator also retains large errors on the new 3D tumbling scenes: texture A returns 28/30 pairs with maximum propagated pose error 19.7038 degrees; texture B returns 29/30 with maximum error 20.3130 degrees. All coarse 2D matches pass, so the narrow fallback is never invoked. The component control explicitly calls native 3D matching on every pair and therefore has a different scope. Its good accuracy does not imply that the complete estimator always chooses the right model.

All controls use independently fixed analytical poses and exact synthetic pixels/masks. Failed chains remain unavailable; they are never interpolated. These are development software controls with ideal sphere masks and orthographic projection, rather than held-out real-fruit, detector, defect or grade accuracy measurements. The source reports retain complete settings, provenance hashes, per-pair decisions and absolute acceptance results.
