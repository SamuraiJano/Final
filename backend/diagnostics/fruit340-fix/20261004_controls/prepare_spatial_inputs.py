"""Freeze complete-turn 3D analytical motion controls before estimation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
import numpy as np
import validate_extended_motion_controls as textures


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rotation_xyz(vector_deg):
    # Analytical axis-angle exponential defines truth independently of cv2.
    vector = np.deg2rad(np.array(vector_deg, dtype=float))
    angle = np.linalg.norm(vector)
    if angle == 0.:
        return np.eye(3)
    x,y,z = vector / angle
    skew = np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])
    return np.eye(3) + np.sin(angle)*skew + (1.-np.cos(angle))*(skew @ skew)


def main():
    output = Path(__file__).resolve().parent / "spatial_inputs"
    output.mkdir(parents=True, exist_ok=False)
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    renderer = BACKEND / "validate_extended_motion_controls.py"
    (output / renderer.name).write_bytes(renderer.read_bytes())
    manifest = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "method": "Radius55 orthographic sphere centered74.5, independently chosen analytical body textures A/B. Known incremental axis-angle vectors [12, +/-3, +/-6]degrees compose 30 consecutive actual3Dposes. X increments sum360degrees; the exact totalSO3pose need not be identity because axes vary. Y alternates each frame; Z alternates every3frames. True matrices use an independent analytical exponential, never an estimator or cv2.Rodrigues.36fixed body landmarks are scored only when front visible.",
        "acceptance": {"all_30_pairs_measured":True,"maximum_pose_error_max_deg":5.,"maximum_front_visible_landmark_rms_max_px":5.},
        "scope": "Synthetic development controls with ideal masks/projection, no occlusion, crop drift, specular glare or neural inference. Complete pose scoring checks the 3D fallback, not the real fruit accuracy. Explicit all-clear defect labels test map execution only.",
        "cases": {},
    }
    yy,xx = np.mgrid[:150,:150]
    x,y = xx-74.5,yy-74.5
    mask = x*x+y*y < 55.**2
    z = np.sqrt(np.maximum(55.**2-x*x-y*y,0.))
    camera = np.stack((x,y,z),axis=-1)
    steps = np.array([[12.,3.*(-1.)**index,6.*(-1.)**(index//3)] for index in range(30)])
    poses = [np.eye(3)]
    for step in steps:
        poses.append(rotation_xyz(step) @ poses[-1])
    landmarks = []
    for lat in (-30.,0.,30.):
        for lon in np.arange(0.,360.,30.):
            latitude,longitude = np.deg2rad([lat,lon])
            landmarks.append(55.*np.array([np.cos(latitude)*np.sin(longitude),np.sin(latitude),np.cos(latitude)*np.cos(longitude)]))
    for pattern in ("a","b"):
        images = []
        ranges = []
        for pose in poses:
            intensity = textures.body_texture(camera @ pose,pattern)
            assert np.all(intensity[mask] > 0.) and np.all(intensity[mask] < 255.), "Input saturation is forbidden"
            ranges.append([float(intensity[mask].min()),float(intensity[mask].max())])
            channel = np.uint8(intensity)
            channel[~mask] = 0
            images.append(np.repeat(channel[:,:,None],3,axis=2))
        name = f"full_turn_x12_y3_z6_texture_{pattern}"
        path = output / f"{name}.npz"
        np.savez_compressed(path,images=np.array(images),mask=mask.astype(np.uint8),angles_deg=np.arange(31)*12.,
            poses=np.array(poses),landmarks_xyz=np.array(landmarks),radius=55.,center=np.array([74.5,74.5]),axis="x",truth_increment_xyz_deg=steps)
        manifest["cases"][name] = {"kind":"full_turn_x12","rotation_axis":"x","texture":pattern,"frames":31,"input_sha256":digest(path),"float_ranges":ranges,"saturated_pixels":0}
    (output / "inputs.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    (output / "sha256.json").write_text(json.dumps({path.name:digest(path) for path in output.iterdir() if path.is_file() and path.name!="sha256.json"},indent=2),encoding="utf-8")
    print(json.dumps({"frozen_inputs":str(output),"cases":len(manifest["cases"])}))


if __name__ == "__main__":
    main()
