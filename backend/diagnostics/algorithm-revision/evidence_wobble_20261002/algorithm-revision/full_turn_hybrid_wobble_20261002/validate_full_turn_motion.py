"""Score actual motion and mapping against independently rendered full turns.

Perfect spheres and masks isolate reconstruction. These are development controls,
not real fruit or neural-model accuracy tests. No motion estimates are mocked.
"""
from dataclasses import asdict
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from validate_extended_motion_controls import body_texture, angle_error_deg
from validate_motion_resolution import rotation_y


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'diagnostics/algorithm-revision/full_turn_observable_20261002'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(steps, pattern):
    radius, size, center = 55., 150, np.array([74.5, 74.5])
    yy, xx = np.mgrid[:size, :size]
    x, y = xx-center[0], yy-center[1]
    mask = x*x+y*y < radius*radius
    z = np.sqrt(np.maximum(radius*radius-x*x-y*y, 0.))
    camera = np.stack((x, y, z), axis=-1)
    angles = np.r_[0., np.cumsum(steps)]
    poses = np.array([rotation_y(angle) for angle in angles])
    images = []
    for pose in poses:
        channel = np.uint8(np.clip(body_texture(camera @ pose, pattern), 0., 255.))
        channel[~mask] = 0
        images.append(np.repeat(channel[:, :, None], 3, axis=2))
    # Fixed body landmarks around the sphere; score only front-visible truth.
    landmarks = []
    for latitude in (-30., 0., 30.):
        for longitude in np.arange(0., 360., 30.):
            lat, lon = np.deg2rad([latitude, longitude])
            landmarks.append(radius*np.array([np.cos(lat)*np.sin(lon),
                                              np.sin(lat), np.cos(lat)*np.cos(lon)]))
    return dict(images=np.array(images), mask=mask.astype(np.uint8), angles_deg=angles,
                poses=poses, landmarks_xyz=np.array(landmarks), radius=radius, center=center)


def evaluate(module, inputs, native_all=False, green_mad=False, hybrid=False, transverse_angle=10.):
    settings = module.Settings(spheroid_type='auto', rotation_axis='y',
                               rotation_direction=1, min_pair_angle_deg=.25,
                               maximum_view_index_gap=1, select_rotating_views=True,
                               bidirectional_matching=True, minimum_longitude_coverage_deg=350,
                               maximum_pair_gap_deg=55, defect_observations_complete=True)
    settings.transverse_angle_deg = transverse_angle
    if native_all:
        settings.image_downsample = 1
        settings.highpass_sigma = 5.
    if green_mad:
        settings.image_downsample = 1
        settings.highpass_sigma = 5.
        settings.matching_cost = 'green_mad'
    if hybrid:
        settings.native_matching_cost = 'green_mad'
        settings.minimum_view_rotation_deg = 8.
    # Explicit all-clear labels test map execution; no segmentation accuracy claim.
    views = [module.FruitView(image, inputs['mask'], frame_index=frame,
                             defect_masks={'known_clear': np.zeros_like(inputs['mask'])})
             for frame, image in enumerate(inputs['images'])]
    model = module.fit_spheroid(views, settings)
    pose, available, pairs, trace = np.eye(3), True, [], []
    for frame, truth in enumerate(inputs['poses']):
        if frame:
            row = dict(source_frame=frame-1, target_frame=frame,
                       true_increment_deg=float(inputs['angles_deg'][frame]-inputs['angles_deg'][frame-1]))
            details = {}
            try:
                rotation, residual = module.estimate_rotation(views[frame-1], views[frame],
                                                             model, frame-1, settings, details)
                row.update(status='measured', residual=residual,
                           vector_deg=np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel().tolist(), **details)
                if available:
                    pose = rotation @ pose
            except module.MappingError as error:
                row.update(status='unavailable', reason=str(error), **details)
                available = False
            pairs.append(row)
        item = dict(frame=frame, true_angle_deg=float(inputs['angles_deg'][frame]),
                    chain_available=available)
        if available:
            true_camera = inputs['landmarks_xyz'] @ truth.T
            visible = true_camera[:, 2] > 10.
            predicted = inputs['landmarks_xyz'][visible] @ pose.T
            errors = np.linalg.norm(predicted[:, :2]-true_camera[visible, :2], axis=1)
            item.update(pose_error_deg=angle_error_deg(pose, truth),
                        visible_landmarks=int(visible.sum()),
                        landmark_rms_px=float(np.sqrt(np.mean(errors**2))))
        trace.append(item)
    try:
        mapped = module.build_surface_map(views, settings)
        mapping = dict(status=mapped.status, grade=mapped.grade,
                       selected_frames=mapped.view_frames, observed_surface_pct=mapped.observed_surface_pct,
                       observed_longitude_deg=mapped.observed_longitude_deg,
                       measured_defect_pct=mapped.defect_pct_of_observed,
                       diagnostics=mapped.selection_diagnostics)
        cv2.imwrite(str(OUTPUT / f'{inputs["case"]}_surface_map.png'), mapped.bgr_map)
        cv2.imwrite(str(OUTPUT / f'{inputs["case"]}_observed.png'), mapped.observed_mask*255)
    except module.MappingError as error:
        mapping = dict(status='mapping_failed', grade=None, reason=str(error),
                       diagnostics=getattr(error, 'diagnostics', []))
    scored = [row for row in trace if row['chain_available']]
    summary = dict(input_pairs=len(pairs), measured_pairs=sum(row['status']=='measured' for row in pairs),
                   endpoint_pose_error_deg=trace[-1].get('pose_error_deg'),
                   maximum_pose_error_deg=max(row['pose_error_deg'] for row in scored),
                   maximum_landmark_rms_px=max(row['landmark_rms_px'] for row in scored))
    summary['motion_control_pass'] = (summary['measured_pairs']==len(pairs)
                                     and summary['maximum_pose_error_deg']<=5.
                                     and summary['maximum_landmark_rms_px']<=5.)
    summary['clear_map_control_pass'] = mapping.get('grade')=='Class 1'
    return dict(settings=asdict(settings), fitted_radius_px=model.A,
                pairs=pairs, trace=trace, mapping=mapping, summary=summary)


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='full_turn_observable_20261002')
    parser.add_argument('--native-all', action='store_true')
    parser.add_argument('--green-mad', action='store_true')
    parser.add_argument('--hybrid', action='store_true')
    parser.add_argument('--transverse-angle', type=float, default=10.)
    parser.add_argument('--algorithm-source', type=Path, default=ROOT/'algorithm.py')
    args = parser.parse_args()
    if not args.label.replace('_','').replace('-','').isalnum():
        raise ValueError('Use a simple diagnostic folder label')
    OUTPUT = ROOT/'diagnostics/algorithm-revision'/args.label
    OUTPUT.mkdir(parents=True, exist_ok=False)
    frozen = OUTPUT/'algorithm_snapshot.py'
    frozen.write_bytes(args.algorithm_source.read_bytes())
    for name in (Path(__file__).name, 'validate_extended_motion_controls.py', 'validate_motion_resolution.py'):
        (OUTPUT/name).write_bytes((ROOT/name).read_bytes())
    spec = importlib.util.spec_from_file_location('full_turn_algorithm', frozen)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cv2.setNumThreads(1)
    report = dict(recorded_at=datetime.now(timezone(timedelta(hours=2))).isoformat(),
                  algorithm_sha256=digest(frozen), validator_sha256=digest(Path(__file__)),
                  method='Analytical body-to-camera y rotations, independent body textures and 36 spherical '
                         'landmarks. Actual spheroid fit, MAD matcher, pose composition, selector and fusion. '
                         'Perfect sphere masks and explicit zero defect labels. No mocked rotations.',
                  limitations='Development synthetic controls selected after small-motion diagnosis. '
                              'Perfect masks/camera and no glare, translation, perspective or occlusion. '
                              'All-clear labels test area/class execution, not either model accuracy.',
                  acceptance={'all_pairs_measured':True, 'maximum_pose_error_deg':5.,
                              'maximum_front_visible_landmark_rms_px':5., 'clear_grade':'Class 1'}, cases={})
    cases = {'constant_6deg_texture_a': ([6.]*60, 'a'),
             'variable_06_54deg_texture_b': ([.6,5.4]*60, 'b')}
    for name, (steps, pattern) in cases.items():
        started = time.perf_counter()
        inputs = render(steps, pattern)
        np.savez_compressed(OUTPUT/f'{name}_inputs.npz', **inputs)
        inputs['case'] = name
        result = evaluate(module, inputs, args.native_all, args.green_mad, args.hybrid, args.transverse_angle)
        result.update(input_sha256=digest(OUTPUT/f'{name}_inputs.npz'), seconds=time.perf_counter()-started)
        report['cases'][name] = result
        (OUTPUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(name, json.dumps(result['summary']),flush=True)
    fig, axes = plt.subplots(2, 2, figsize=(12,8), layout='constrained')
    for panels, (name, result) in zip(axes, report['cases'].items()):
        trace = result['trace']
        angle = [row['true_angle_deg'] for row in trace]
        for panel,key,title in zip(panels, ['pose_error_deg','landmark_rms_px'],
                                  ['3D pose error (degrees)', 'Front-visible landmark RMS (pixels)']):
            panel.plot(angle,[row.get(key,np.nan) for row in trace],color='#28734d')
            panel.axhline(5.,color='#bb7440',ls='--',label='Predeclared 5-unit limit')
            panel.set(title=name.replace('_',' '),xlabel='True rotation (degrees)',ylabel=title)
            panel.grid(alpha=.2)
            panel.legend(fontsize=8)
    fig.suptitle('Actual motion estimation across independently rendered 360-degree turns')
    fig.savefig(OUTPUT/'full_turn_accuracy.png',dpi=300)
    fig.savefig(OUTPUT/'full_turn_accuracy.pdf')
    plt.close(fig)
    rows = []
    for name,result in report['cases'].items():
        s,m = result['summary'],result['mapping']
        rows.append(f"| {name} | {s['measured_pairs']}/{s['input_pairs']} | {s['maximum_pose_error_deg']:.3f} | "
                    f"{s['maximum_landmark_rms_px']:.3f} | {m['status']} | {m.get('grade')} | "
                    f"{s['motion_control_pass']} / {s['clear_map_control_pass']} |")
    (OUTPUT/'FULL_TURN_CONTROLS.md').write_text(
        '# Full-turn reconstruction controls\n\n'+report['method']+'\n\n'+report['limitations']+
        '\n\nMotion passes require every pair and maximum errors below the predeclared 5° / 5 px limits. '
        'A broken chain remains unavailable; later pairs do not repair its score. Clear map execution is scored separately.\n\n'
        '| Case | Measured pairs | Max pose ° | Max RMS px | Map status | Grade | Motion / clear map pass |\n'
        '| --- | --- | --- | --- | --- | --- | --- |\n'+'\n'.join(rows)+
        '\n\n![Pose and landmark errors](full_turn_accuracy.png)\n',encoding='utf-8')
    files = sorted(path for path in OUTPUT.iterdir() if path.is_file())
    (OUTPUT/'SHA256SUMS.txt').write_text('\n'.join(f'{digest(path)}  {path.name}' for path in files)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
