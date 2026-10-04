"""Freeze prescribed camera-light reversal scenes before estimator evaluation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
import numpy as np
import validate_extended_motion_controls as truth


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = Path(__file__).resolve().parent / "stress_inputs"
    output.mkdir(parents=True, exist_ok=False)
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    renderer = BACKEND / "validate_extended_motion_controls.py"
    (output / renderer.name).write_bytes(renderer.read_bytes())
    manifest = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "method": "Independent analytical sphere and x-axis poses, radius55, camera center74.5. Moving cases have body-to-camera poses0,6,12deg; stationary cases0,0,0. Reflectance=20*exp(1+.003*body_texture). Camera-fixed log-linear light reverses sign between three frames: I=reflectance*exp(sign*gradient*(camera_x+.5*camera_y))*exposure; signs[1,-1,1], exposure[1,.75,1.05], gradient=.006 or.012perpx. No clipping allowed. Pattern and strength choices prescribed before estimator evaluation; no neural models or fitted correspondences.",
        "acceptance": {"moving": {"all_pairs_measured": True, "endpoint_pose_error_max_deg": 1., "maximum_landmark_rms_max_px": 1.}, "stationary": {"all_pairs_unavailable": True, "no_map_or_grade": True}},
        "scope": "Development stress scenes, not held-out data or realistic calibration of these abrupt lighting changes. Perfect sphere masks/orthographic projection. They check a photometric fallback with independently fixed motion, including genuinely stationary fruit.",
        "cases": {},
    }
    yy, xx = np.mgrid[:150, :150]
    x, y = xx-74.5, yy-74.5
    mask = x*x+y*y < 55.**2
    z = np.sqrt(np.maximum(55.**2-x*x-y*y, 0.))
    camera = np.stack((x,y,z), axis=-1)
    landmarks = np.array([[lx,ly,np.sqrt(55.**2-lx*lx-ly*ly)] for lx in (-15.,0.,15.) for ly in (-12.,12.)])
    for pattern in ("a", "b"):
        for stationary in (False, True):
            angles = [0.,0.,0.] if stationary else [0.,6.,12.]
            poses = np.array([truth.rotation_xy(angle,0.) for angle in angles])
            for gradient in (.006,.012):
                images = []
                ranges = []
                for pose, sign, exposure in zip(poses, (1.,-1.,1.), (1.,.75,1.05)):
                    reflectance = 20.*np.exp(1.+.003*truth.body_texture(camera @ pose,pattern))
                    intensity = reflectance*np.exp(sign*gradient*(x+.5*y))*exposure
                    assert np.all(intensity[mask] > 0.) and np.all(intensity[mask] < 255.), "Input saturation is forbidden"
                    ranges.append([float(intensity[mask].min()), float(intensity[mask].max())])
                    channel = np.uint8(intensity)
                    channel[~mask] = 0
                    images.append(np.repeat(channel[:,:,None],3,axis=2))
                projected = np.array([landmarks @ pose.T for pose in poses])
                assert np.all(projected[:,:,2] > 0.)
                name = f"{'stationary' if stationary else 'moving_x6'}_log_light_reversal_g{gradient:g}_texture_{pattern}"
                path = output / f"{name}.npz"
                np.savez_compressed(path, images=np.array(images), mask=mask.astype(np.uint8), truth_poses=poses,
                    truth_increment_xy_deg=np.array([[angles[i+1]-angles[i],0.] for i in range(2)]),
                    body_landmarks_xyz=landmarks, truth_landmarks_xy=projected[:,:,:2]+74.5, radius=55., center=np.array([74.5,74.5]))
                manifest["cases"][name] = {"kind":"stationary_stress" if stationary else "short_xy", "rotation_axis":"x", "input_sha256":digest(path), "float_ranges":ranges, "saturated_pixels":0, "frames":3}
    (output / "inputs.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    (output / "sha256.json").write_text(json.dumps({path.name:digest(path) for path in output.iterdir() if path.is_file() and path.name!="sha256.json"},indent=2),encoding="utf-8")
    print(json.dumps({"frozen_inputs":str(output),"cases":len(manifest["cases"])}))


if __name__ == "__main__":
    main()
