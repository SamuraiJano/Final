"""Prescribed stationary samples for the native 3D component, no mocked poses."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(BACKEND))
import cv2
import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    path.write_text(json.dumps(value,indent=2),encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algorithm",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    files = [BACKEND/"diagnostics/algorithm-revision/extended_motion_controls_20261002"/f"stationary_120_texture_{pattern}_inputs.npz" for pattern in ("a","b")]
    files += [BACKEND/"diagnostics/algorithm-revision/camera_shading_inputs_20261002"/f"stationary_120_lambertian_multiplicative_texture_{pattern}.npz" for pattern in ("a","b")]
    # The first six pairs of each fixed noise scene are prescribed samples,
    # never selected by outcomes. Every fixed light-reversal pair is included.
    selected = [(path,6) for path in files]
    stress = Path(__file__).resolve().parent/"stress_inputs"
    manifest = json.loads((stress/"inputs.json").read_text(encoding="utf-8"))
    selected += [(stress/f"{name}.npz",2) for name,row in manifest["cases"].items() if row["kind"]=="stationary_stress"]
    write(args.output/"prescribed_inputs.json",[{"file":str(path),"sha256":digest(path),"first_pairs":count} for path,count in selected])
    source = args.output/"algorithm.py"
    source.write_bytes(args.algorithm.read_bytes())
    spec = importlib.util.spec_from_file_location("native_3d_stationary",source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    report = {"started_at":datetime.now(timezone.utc).isoformat(),"algorithm_sha256":digest(source),"validator_sha256":digest(Path(__file__)),
        "method":"Explicitly invoke production native bidirectional aligned_mad withZbound10degrees, rolling/transverse bounds20degrees, radius fitted from exact frozen sphere masks, native sigma5, unchanged0.58residual/.25degree minimum gates. Prescribed first6pairs of each of four stationary noisy scenes, plus all8prescribed stationary light-reversal pairs. No mocked motion or zero substitution.",
        "scope":"Limited component safety control, not full-pipeline map/grade execution or proof for all realistic lighting. Automatic coarse eligibility is bypassed explicitly. Samples are fixed before estimation, not selected by failures. Exact stationary poses are identities in frozen input NPZs.","cases":{}}
    write(args.output/"report.json",report)
    cv2.setNumThreads(1)
    started = time.perf_counter()
    for path,count in selected:
        with np.load(path) as stored:
            inputs = {key:stored[key] for key in stored.files}
        assert np.allclose(inputs["truth_poses"],np.eye(3)[None])
        settings = module.Settings(spheroid_type="sphere",rotation_axis="x",rotation_direction=1,
            native_matching_cost="aligned_mad",matching_cost="aligned_mad",image_downsample=1,highpass_sigma=5.,
            max_pair_angle_deg=20.,transverse_angle_deg=20.,bidirectional_matching=True,min_pair_angle_deg=.25,
            defect_observations_complete=False)
        views = [module.FruitView(image,inputs["mask"],frame_index=index) for index,image in enumerate(inputs["images"][:count+1])]
        model = module.fit_spheroid(views,settings)
        rows = []
        for index in range(count):
            row = {"source_frame":index,"target_frame":index+1}
            try:
                rotation,residual = module._search_rotation(views[index],views[index+1],model,index,settings,inplane_angle_deg=10.)
                row.update(status="false_motion",residual=residual,rotation_vector_deg=np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel().tolist())
            except module.MappingError as error:
                row.update(status="unavailable",reason=str(error))
            rows.append(row)
        summary = {"tested_pairs":count,"false_motion_pairs":sum(row["status"]=="false_motion" for row in rows)}
        report["cases"][path.stem] = {"input_sha256":digest(path),"pairs":rows,"summary":summary,"passed":summary["false_motion_pairs"]==0}
        write(args.output/"report.json",report)
        print(json.dumps({"case":path.stem,**summary}),flush=True)
    report["all_component_stationary_controls_passed"] = all(row["passed"] for row in report["cases"].values())
    report["seconds"] = time.perf_counter()-started
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    write(args.output/"report.json",report)
    write(args.output/"sha256.json",{str(path.relative_to(args.output)):digest(path) for path in args.output.rglob("*") if path.is_file() and path.name!="sha256.json"})
    print(json.dumps({"completed":str(args.output),"passed":report["all_component_stationary_controls_passed"],"seconds":report["seconds"]}),flush=True)


if __name__=="__main__":
    main()
