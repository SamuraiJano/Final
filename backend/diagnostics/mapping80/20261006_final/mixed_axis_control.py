"""Independent ray/quadric renderer: changing oblate pole, rolling and transverse.

Known rotations are used exclusively by the renderer and error assessment.
The production mapper receives only rendered images, binary masks and indices.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
from pathlib import Path
import sys
import json
import argparse
import numpy as np
import cv2
from scipy.spatial.transform import Rotation

OUTPUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUTPUT.parents[2]))
from validate_dense_mapping import load_module, sha, write
from analyze_dense_mapping import continuous_area


def main(case='mixed'):
    cv2.setNumThreads(1)
    module = load_module(OUTPUT/'final_v4/algorithm.py', 'mixed_control_algorithm')
    settings = module.Settings(**json.loads((OUTPUT/'final_v4/settings.json').read_text()))
    folder = OUTPUT/('mixed_axis_control' if case=='mixed' else 'perpendicular_pole_control')
    folder.mkdir(exist_ok=True)
    A, B = 82., 65.
    angles = np.linspace(0, 360, 65)
    axis = np.array([1., .3, 0.] if case=='mixed' else [1.,0.,0.])
    axis /= np.linalg.norm(axis)
    rotations = Rotation.from_rotvec(np.deg2rad(angles)[:, None]*axis).as_matrix()
    yy, xx = np.mgrid[:210, :210]
    x, y = xx-104.5, yy-104.5
    views, inputs = [], []
    for index, R in enumerate(rotations):
        radii=[B,A,A] if case=='mixed' else [A,B,A]
        M = R @ np.diag(1/np.array(radii,dtype=float)**2) @ R.T
        linear = 2*(M[0, 2]*x+M[1, 2]*y)
        constant = M[0, 0]*x*x+2*M[0, 1]*x*y+M[1, 1]*y*y-1
        discriminant = linear*linear-4*M[2, 2]*constant
        mask = discriminant >= 0
        z = (-linear+np.sqrt(np.maximum(discriminant, 0)))/(2*M[2, 2])
        body = np.stack((x, y, z), axis=-1) @ R
        fx, fy, fz = np.moveaxis(body, -1, 0)
        intensity = (145+24*np.sin(.19*fx+.13*fy+.21*fz)
                     +28*np.cos(.11*fx-.27*fy+.17*fz)
                     +20*np.sin(.31*fx+.09*fy-.13*fz)
                     +18*np.cos(.07*fx+.21*fy+.29*fz))
        channel = np.uint8(np.clip(intensity, 0, 255))
        image = np.stack((np.uint8(channel*.25), channel,
                          np.uint8(np.clip(channel.astype(float)*1.3+30, 0, 255))), axis=-1)
        image[~mask] = 0
        view = module.FruitView(image, mask.astype(np.uint8), frame_index=index)
        file = f'view_{index:03d}.npz'
        np.savez_compressed(folder/file, image=image, mask=mask.astype(np.uint8), true_rotation=R)
        inputs.append(dict(file=file, sha256=sha(folder/file)))
        views.append(view)
    try:
        mapped = module.build_surface_map(views, settings)
        accepted = [d for d in mapped.selection_diagnostics if d['status']=='accepted']
        errors = []
        for d in accepted:
            source, target = d['source_frame'], d['target_frame']
            truth = Rotation.from_matrix(rotations[target] @ rotations[source].T).as_rotvec()
            measured = Rotation.from_rotvec(np.deg2rad(d['rotation_vector_deg']))
            errors.append(float(np.rad2deg((measured.inv()*Rotation.from_rotvec(truth)).magnitude())))
        true_selected_rolling = float((angles[mapped.view_frames[-1]]-angles[mapped.view_frames[0]])*axis[0])
        _,map_radii=module._map_frame(module.fit_spheroid(views,settings),settings)
        band_capacity=100*continuous_area(map_radii,settings.max_latitude_deg)/continuous_area(map_radii)
        report = dict(observed_surface_pct=mapped.observed_surface_pct,
                      fitted_map_radii_px=map_radii.tolist(),ideal_fitted_band_capacity_pct=band_capacity,
                      observed_longitude_deg=mapped.observed_longitude_deg,
                      measured_rolling_deg=mapped.rotation_coverage_deg,
                      true_selected_rolling_deg=true_selected_rolling,
                      maximum_pair_geodesic_error_deg=max(errors),
                      pair_geodesic_errors_deg=errors, selected_frames=mapped.view_frames,
                      selection_diagnostics=mapped.selection_diagnostics,
                      passed=max(errors)<1.5 and abs(mapped.rotation_coverage_deg-true_selected_rolling)<8
                             and mapped.observed_surface_pct>=80 and mapped.observed_longitude_deg>=350
                             and mapped.observed_surface_pct<=band_capacity+.05)
        cv2.imwrite(str(folder/'surface_map.png'), mapped.bgr_map)
        cv2.imwrite(str(folder/'observed_mask.png'), mapped.observed_mask*255)
    except module.MappingError as error:
        report = dict(passed=False, error=str(error))
    report.update(algorithm_sha256=sha(OUTPUT/'final_v4/algorithm.py'),
                  settings=json.loads((OUTPUT/'final_v4/settings.json').read_text()),
                  renderer_sha256=sha(Path(__file__)), true_axis=axis.tolist(),case=case,
                  true_body_radii_px=radii,
                  true_total_rotation_deg=360., inputs=inputs,
                  limitations='Independent synthetic orthographic quadric and exact texture; no real-video accuracy claim.')
    write(folder/'report.json', report)
    print({k:v for k,v in report.items() if k not in ('inputs','selection_diagnostics','settings')}, flush=True)
    if not report['passed']:
        raise AssertionError('Changing-pole mixed-axis rendered control failed')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=('mixed','perpendicular'),default='mixed')
    main(parser.parse_args().case)
