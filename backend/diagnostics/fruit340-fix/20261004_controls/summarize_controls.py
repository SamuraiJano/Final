"""Collect completed, source-matched control reports without changing evidence."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    report = json.loads((ROOT/name/"report.json").read_text(encoding="utf-8"))
    assert report.get("completed_at"), f"Incomplete report: {name}"
    return report


def main():
    original = load("candidate_03")
    light = load("stress_candidate_03")
    spatial = load("spatial_candidate_03")
    native = load("native_spatial_component_03")
    stationary = load("native_stationary_component_03")
    previous = load("native_stationary_consensus_02")
    candidate_hash = original["algorithm_sha256"]["candidate"]
    assert light["algorithm_sha256"]["candidate"] == spatial["algorithm_sha256"]["candidate"] == native["algorithm_sha256"] == stationary["algorithm_sha256"] == candidate_hash
    original_pairs = [pair for case in original["cases"].values() for pair in case["variants"]["candidate"]["pairs"]]
    old_false = [pair for case in previous["cases"].values() for pair in case["pairs"] if pair["status"]=="false_motion"]
    native_max_pose = max(case["summary"]["maximum_pose_error_deg"] for case in native["cases"].values())
    native_max_landmark = max(case["summary"]["maximum_landmark_rms_px"] for case in native["cases"].values())
    lines = [
        "# Fruit 340 correction: independent control findings", "",
        "The final candidate preserves the established known-motion controls. Its bounded native 3D search measures the two independently frozen complete-turn scenes accurately. The one-pixel rolling observability floor removes the subpixel stationary false fits exposed during development.", "",
        f"Final candidate SHA256: `{candidate_hash}`. Baseline SHA256: `{original['algorithm_sha256']['baseline']}`.", "",
        "| Validation | Final result | Evidence |",
        "| --- | --- | --- |",
        f"| Established 19-scene motion/stationary suite | All 19 controls pass; 190 moving pairs measured and 752 stationary/uniform pairs rejected | [Full comparison](candidate_03/report.json) |",
        f"| Native 3D complete-turn component | 60/60 pairs measured; maximum propagated pose error {native_max_pose:.4f} degrees and visible-landmark RMS {native_max_landmark:.4f} pixels | [Component report](native_spatial_component_03/report.json) |",
        "| Native 3D stationary component with independent consensus | All 32 prescribed stationary pairs rejected; zero false motion | [Stationary report](native_stationary_component_03/report.json) |",
        "| Additional changing-light stress | One pre-existing stationary false-motion case remains; all outputs unchanged | [Stress comparison](stress_candidate_03/report.json) |",
        "| Full estimator on independently known 3D tumbling sequences | Both controls retain pre-existing failures when coarse 2D matching succeeds | [Full estimator comparison](spatial_candidate_03/report.json) |", "",
        "The original 942-pair suite reruns every final-candidate measurement. Baseline measurements are reused explicitly after verifying the exact baseline source, analytical validators, input pixels and acceptance references. All existing measured outputs are preserved. This suite attempts native rescue only on 19 uniform/untextured pairs, and rejects them all; it establishes preservation and unavailable-texture safety rather than successful rescue accuracy.", "",
        f"Before the rolling-pixel floor, independent forward/backward consensus still admitted {len(old_false)}/32 false stationary component matches. The largest rolling displacement was {max(pair['native_rolling_movement_px'] for pair in old_false):.4f} pixels. Their maximum inverse disagreement was {max(pair['inverse_disagreement_deg'] for pair in old_false):.4f} degrees, so the three-degree consistency gate alone did not reject them. [Preserved failed component control](native_stationary_consensus_02/report.json).", "",
        "The additional log-linear light-reversal stress scene at gradient 0.012 with texture B returns one false stationary pair in both baseline and final candidate. That existing 2D path estimates 5.1427 degrees and creates a partial ungraded map. The frozen input was prescribed before either estimator ran. This failure is preserved and is outside the new coarse-failure fallback.", "",
        "The full estimator also retains large errors on the new 3D tumbling scenes: texture A returns 28/30 pairs with maximum propagated pose error 19.7038 degrees; texture B returns 29/30 with maximum error 20.3130 degrees. All coarse 2D matches pass, so the narrow fallback is never invoked. The component control explicitly calls native 3D matching on every pair and therefore has a different scope. Its good accuracy does not imply that the complete estimator always chooses the right model.", "",
        "All controls use independently fixed analytical poses and exact synthetic pixels/masks. Failed chains remain unavailable; they are never interpolated. These are development software controls with ideal sphere masks and orthographic projection, rather than held-out real-fruit, detector, defect or grade accuracy measurements. The source reports retain complete settings, provenance hashes, per-pair decisions and absolute acceptance results.", "",
    ]
    with (ROOT/"CONTROL_FINDINGS.md").open("x",encoding="utf-8") as target:
        target.write("\n".join(lines))
    names = ("candidate_03","stress_candidate_03","spatial_candidate_03","native_spatial_component_03","native_stationary_component_03","native_stationary_consensus_02")
    evidence = {"final_algorithm_sha256":candidate_hash,"original_pairs":len(original_pairs),
        "original_measured_pairs":sum(pair["status"]=="measured" for pair in original_pairs),
        "original_unavailable_pairs":sum(pair["status"]=="unavailable" for pair in original_pairs),
        "native_component_maximum_pose_error_deg":native_max_pose,"native_component_maximum_landmark_rms_px":native_max_landmark,
        "pre_floor_false_stationary_matches_after_consensus":len(old_false),
        "post_floor_false_stationary_matches":sum(case["summary"]["false_motion_pairs"] for case in stationary["cases"].values()),
        "evidence_sha256":{name:digest(ROOT/name/"report.json") for name in names},"findings_sha256":digest(ROOT/"CONTROL_FINDINGS.md")}
    with (ROOT/"CONTROL_FINDINGS.json").open("x",encoding="utf-8") as target:
        json.dump(evidence,target,indent=2)
    print(json.dumps(evidence,indent=2))


if __name__=="__main__":
    main()
