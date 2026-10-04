"""Test native 3D search and inverse checks as components, not automatic selection.

Uses complete independently frozen 3D scenes. Does not pretend the production
estimator invokes this branch when its coarse two-component match succeeds.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
import cv2
import numpy as np
import validate_extended_motion_controls as truth


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2),encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algorithm", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.output / "algorithm.py"
    source.write_bytes(args.algorithm.read_bytes())
    (args.output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    renderer = BACKEND / "validate_extended_motion_controls.py"
    (args.output / renderer.name).write_bytes(renderer.read_bytes())
    spec = importlib.util.spec_from_file_location("native_spatial_component",source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    inputs_directory = Path(__file__).resolve().parent / "spatial_inputs"
    manifest = json.loads((inputs_directory / "inputs.json").read_text(encoding="utf-8"))
    report = {
        "started_at":datetime.now(timezone.utc).isoformat(),"algorithm_sha256":digest(source),
        "validator_sha256":digest(Path(__file__)),"input_manifest_sha256":digest(inputs_directory/"inputs.json"),
        "method":"Explicitly invoke the production native aligned_mad search with boundedZ10degrees on every known pair, followed by separate forward/backward searches and the same3degree SO3 consensus gates. Compare independent analytical pair and propagated pose truth and visible landmark projections. Coarse estimator and automatic fallback eligibility do not run in this component control.",
        "scope":"Component correctness on prespecified perfect synthetic sphere scenes only. This does not validate the full estimator's automatic use of3D, real fruit accuracy, detection or segmentation. The separate full-estimator spatial controls retain failures when coarse2D succeeds.",
        "acceptance":manifest["acceptance"],"cases":{},
    }
    write(args.output/"report.json",report)
    cv2.setNumThreads(1)
    started = time.perf_counter()
    for name, reference in manifest["cases"].items():
        input_path = inputs_directory/f"{name}.npz"
        assert digest(input_path)==reference["input_sha256"]
        with np.load(input_path) as stored:
            inputs = {key:stored[key] for key in stored.files}
        settings = module.Settings(spheroid_type="auto",rotation_axis="x",rotation_direction=1,
            native_matching_cost="aligned_mad",matching_cost="aligned_mad",image_downsample=1,
            highpass_sigma=5.,max_pair_angle_deg=20.,transverse_angle_deg=20.,
            bidirectional_matching=True,min_pair_angle_deg=.25,defect_observations_complete=False)
        views = [module.FruitView(image,inputs["mask"],frame_index=index) for index,image in enumerate(inputs["images"])]
        model = module.fit_spheroid(views,settings)
        pose,available = np.eye(3),True
        rows,trace = [],[]
        for index in range(len(views)-1):
            row = {"source_frame":index,"target_frame":index+1,"truth_increment_xyz_deg":inputs["truth_increment_xyz_deg"][index].tolist()}
            try:
                rotation,residual = module._search_rotation(views[index],views[index+1],model,index,settings,inplane_angle_deg=10.)
                forward,forward_residual = module._search_rotation(views[index],views[index+1],model,index,replace(settings,bidirectional_matching=False),inplane_angle_deg=10.)
                reversed_model = module._subset_spheroid(model,[index+1,index])
                backward,backward_residual = module._search_rotation(views[index+1],views[index],reversed_model,0,replace(settings,bidirectional_matching=False,rotation_direction=-1),inplane_angle_deg=10.)
                inverse_error = truth.angle_error_deg(forward @ backward,np.eye(3))
                forward_error = truth.angle_error_deg(rotation,forward)
                backward_error = truth.angle_error_deg(rotation,backward.T)
                if max(inverse_error,forward_error,backward_error)>3.:
                    raise module.MappingError(f"Independent native disagreement: {inverse_error}, {forward_error}, {backward_error}")
                row.update(status="measured",residual=residual,forward_residual=forward_residual,backward_residual=backward_residual,
                    inverse_disagreement_deg=inverse_error,forward_disagreement_deg=forward_error,backward_disagreement_deg=backward_error,
                    measured_vector_deg=np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel().tolist(),
                    independent_pair_pose_error_deg=truth.angle_error_deg(rotation,inputs["poses"][index+1] @ inputs["poses"][index].T))
                if available:
                    pose = rotation @ pose
            except module.MappingError as error:
                row.update(status="unavailable",reason=str(error))
                available = False
            rows.append(row)
            item = {"frame":index+1,"chain_available":available}
            if available:
                true_camera = inputs["landmarks_xyz"] @ inputs["poses"][index+1].T
                visible = true_camera[:,2]>10.
                predicted = inputs["landmarks_xyz"][visible] @ pose.T
                errors = np.linalg.norm(predicted[:,:2]-true_camera[visible,:2],axis=1)
                item.update(pose_error_deg=truth.angle_error_deg(pose,inputs["poses"][index+1]),landmark_rms_px=float(np.sqrt(np.mean(errors**2))),visible_landmarks=int(visible.sum()))
            trace.append(item)
            write(args.output/f"{name}_partial.json",{"pairs":rows,"trace":trace})
        scored = [item for item in trace if item["chain_available"]]
        summary = {"input_pairs":len(rows),"measured_pairs":sum(row["status"]=="measured" for row in rows),
            "maximum_pair_pose_error_deg":max((row["independent_pair_pose_error_deg"] for row in rows if row["status"]=="measured"),default=None),
            "maximum_pose_error_deg":max((item["pose_error_deg"] for item in scored),default=None),
            "maximum_landmark_rms_px":max((item["landmark_rms_px"] for item in scored),default=None)}
        checks = {"all_30_pairs_measured":summary["measured_pairs"]==30,
            "maximum_pose_within_5deg":summary["measured_pairs"]==30 and summary["maximum_pose_error_deg"]<=5.,
            "maximum_front_visible_landmarks_within_5px":summary["measured_pairs"]==30 and summary["maximum_landmark_rms_px"]<=5.}
        report["cases"][name] = {"input_sha256":digest(input_path),"pairs":rows,"trace":trace,"summary":summary,"checks":checks,"passed":all(checks.values())}
        write(args.output/"report.json",report)
        print(json.dumps({"case":name,"summary":summary,"checks":checks}),flush=True)
    report["seconds"] = time.perf_counter()-started
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["all_component_controls_passed"] = all(row["passed"] for row in report["cases"].values())
    write(args.output/"report.json",report)
    write(args.output/"sha256.json",{str(path.relative_to(args.output)):digest(path) for path in args.output.rglob("*") if path.is_file() and path.name!="sha256.json"})
    print(json.dumps({"completed":str(args.output),"passed":report["all_component_controls_passed"],"seconds":report["seconds"]}),flush=True)


if __name__=="__main__":
    main()
