"""Long stationary and multi-axis known-motion controls, without neural models.

Two independently chosen body textures are rendered on a radius-55 sphere.
Known incremental x/y rotations use an analytical axis-angle formula. Scored
landmark truth comes from those matrices, never from the estimator's output.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
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

from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT/'diagnostics/algorithm-revision/motion_resolution_scaled_20261002/algorithm_snapshot.py'
Y_STEPS = [.6, .6, .8, 1., .5, .5, .5, .5, 1.5, 1.5]
X_STEPS = [.3, -.25, .4, -.35, .15, -.3, .25, -.15, .4, -.45]
TEXTURES = {
    'a': '150+36*sin(.18*fx+.13*fy)+28*cos(.17*fz-.09*fy)+22*sin(.11*fx+.21*fz)',
    'b': '135+33*sin(.09*fx-.15*fy+.18*fz)+27*cos(.27*fx+.08*fy)+20*cos(.13*fy-.21*fz)+16*sin(.21*fx+.17*fy+.12*fz)'}


def rotation_xy(x_deg, y_deg):
    """Independent analytical exponential of a known axis-angle vector."""
    vector = np.deg2rad([x_deg, y_deg, 0.])
    angle = np.linalg.norm(vector)
    if angle == 0: return np.eye(3)
    x, y, z = vector/angle
    skew = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
    return np.eye(3)+np.sin(angle)*skew+(1-np.cos(angle))*(skew @ skew)


def body_texture(body, pattern):
    fx, fy, fz = (body[:, :, index] for index in range(3))
    if pattern == 'a':
        return 150+36*np.sin(.18*fx+.13*fy)+28*np.cos(.17*fz-.09*fy)+22*np.sin(.11*fx+.21*fz)
    return (135+33*np.sin(.09*fx-.15*fy+.18*fz)+27*np.cos(.27*fx+.08*fy)+
            20*np.cos(.13*fy-.21*fz)+16*np.sin(.21*fx+.17*fy+.12*fz))


def render(pattern, stationary):
    size, radius = 150, 55.
    center = np.array([74.5, 74.5])
    yy, xx = np.mgrid[:size, :size]
    X, Y = xx-center[0], yy-center[1]
    mask = X*X+Y*Y < radius*radius
    Z = np.sqrt(np.maximum(radius*radius-X*X-Y*Y, 0.))
    camera = np.stack((X, Y, Z), axis=-1)
    steps = [[0., 0.]]*119 if stationary else list(zip(X_STEPS, Y_STEPS))
    poses = [np.eye(3)]
    for x_step, y_step in steps: poses.append(rotation_xy(x_step, y_step) @ poses[-1])
    rng = np.random.default_rng(391 if pattern == 'a' else 923)
    images = []
    for pose in poses:
        intensity = body_texture(camera @ pose, pattern)
        if stationary: intensity += rng.normal(0., 2., (size, size))
        channel = np.uint8(np.clip(intensity, 0, 255)); channel[~mask] = 0
        images.append(np.repeat(channel[:, :, None], 3, axis=2))
    landmarks = np.array([[x, y, np.sqrt(radius*radius-x*x-y*y)]
                          for x in (-15., 0., 15.) for y in (-12., 12.)])
    camera_points = np.array([landmarks @ pose.T for pose in poses])
    assert np.all(camera_points[:, :, 2] > 0)
    return {'images': np.array(images), 'mask': mask.astype(np.uint8),
            'truth_poses': np.array(poses), 'truth_increment_xy_deg': np.array(steps),
            'body_landmarks_xyz': landmarks, 'truth_landmarks_xy': camera_points[:, :, :2]+center,
            'radius': radius, 'center': center}


def angle_error_deg(predicted, truth):
    cosine = (np.trace(predicted @ truth.T)-1)/2
    return float(np.rad2deg(np.arccos(np.clip(cosine, -1., 1.))))


def evaluate(module, inputs, settings):
    started = time.perf_counter()
    views = [module.FruitView(image, inputs['mask'], frame_index=index)
             for index, image in enumerate(inputs['images'])]
    model = module.fit_spheroid(views, settings)
    source_xy = inputs['truth_landmarks_xy'][0]-model.ellipses[0].center
    source_xyz = np.column_stack((source_xy, module._height(model.matrices[0], source_xy[:, 0], source_xy[:, 1])))
    pose, available = np.eye(3), True
    pairs, trace = [], []
    for frame in range(len(views)):
        if frame:
            row = {'source_frame': frame-1, 'target_frame': frame,
                   'true_increment_xy_deg': inputs['truth_increment_xy_deg'][frame-1].tolist()}
            details = {}
            try:
                rotation, residual = module.estimate_rotation(views[frame-1], views[frame], model, frame-1,
                                                             settings, details)
                row.update(status='measured', residual=residual,
                           rotation_vector_deg=np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel().tolist(), **details)
                if available: pose = rotation @ pose
            except module.MappingError as error:
                row.update(status='unavailable', reason=str(error), **details); available = False
            pairs.append(row)
        item = {'frame': frame, 'chain_available': available,
                'true_pose_vector_deg': np.rad2deg(cv2.Rodrigues(inputs['truth_poses'][frame])[0]).ravel().tolist()}
        if available:
            predicted = (source_xyz @ pose.T)[:, :2]+model.ellipses[frame].center
            errors = np.linalg.norm(predicted-inputs['truth_landmarks_xy'][frame], axis=1)
            item.update(estimated_pose_vector_deg=np.rad2deg(cv2.Rodrigues(pose)[0]).ravel().tolist(),
                        pose_error_deg=angle_error_deg(pose, inputs['truth_poses'][frame]),
                        landmark_rms_px=float(np.sqrt(np.mean(errors**2))),
                        landmark_errors_px=errors.tolist(), predicted_landmarks_xy=predicted.tolist())
        trace.append(item)
    mapping = {'grade_evaluated': False}
    try:
        mapped = module.build_surface_map(views, settings)
        assert mapped.grade is None
        mapping.update(status=mapped.status, grade=mapped.grade, selected_frames=mapped.view_frames,
                       observed_longitude_deg=mapped.observed_longitude_deg,
                       estimated_rotation_coverage_deg=mapped.rotation_coverage_deg,
                       diagnostics=mapped.selection_diagnostics)
    except module.MappingError as error:
        mapping.update(status='mapping_failed', grade=None, reason=str(error), observed_longitude_deg=0.,
                       diagnostics=getattr(error, 'diagnostics', []))
    measured = [row for row in pairs if row['status'] == 'measured']
    scored = [row for row in trace if row['chain_available']]
    return {'settings': asdict(settings), 'settings_sha256': hashlib.sha256(
                json.dumps(asdict(settings), sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'pairs': pairs, 'trace': trace, 'mapping': mapping,
            'summary': {'frames': len(views), 'input_pairs': len(pairs), 'measured_pairs': len(measured),
                        'native_rechecks': sum(row.get('image_downsample') == 1 for row in measured),
                        'all_pairs_measured': len(measured) == len(pairs),
                        'endpoint_pose_error_deg': trace[-1].get('pose_error_deg'),
                        'endpoint_landmark_rms_px': trace[-1].get('landmark_rms_px'),
                        'maximum_pose_error_deg': max((row['pose_error_deg'] for row in scored), default=None),
                        'maximum_landmark_rms_px': max((row['landmark_rms_px'] for row in scored), default=None)},
            'seconds': time.perf_counter()-started}


def save_figures(output, report, rendered):
    fig, axes = plt.subplots(4, 2, figsize=(12, 13))
    for panels, (case, inputs) in zip(axes, rendered.items()):
        for name, row in report['cases'][case]['variants'].items():
            color = '#ce8635' if name == 'coarse_d4' else '#237c50'
            frames = [item['frame'] for item in row['trace']]
            panels[0].plot(frames, [item.get('pose_error_deg', np.nan) for item in row['trace']], color=color, label=name)
            panels[1].plot(frames, [item.get('landmark_rms_px', np.nan) for item in row['trace']], color=color, label=name)
        panels[0].set(title=case.replace('_', ' '), xlabel='Rendered frame', ylabel='3D pose error (degrees)')
        panels[1].set(xlabel='Rendered frame', ylabel='Visible landmark RMS (pixels)')
        for panel in panels: panel.grid(alpha=.2); panel.legend(fontsize=8)
    fig.suptitle('Independent controls: noncommuting x/y wobble and 120 stationary noisy frames')
    fig.tight_layout(); fig.savefig(output/'extended_motion_accuracy.png', dpi=300)
    fig.savefig(output/'extended_motion_accuracy.pdf'); plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(12, 8))
    for panels, pattern in zip(axes, ('a', 'b')):
        case = f'variable_xy_texture_{pattern}'; inputs = rendered[case]
        panels[0].imshow(cv2.cvtColor(inputs['images'][0], cv2.COLOR_BGR2RGB))
        panels[0].set_title(f'Texture {pattern}: actual input frame 0')
        for panel, name in zip(panels[1:], ('coarse_d4', 'adaptive_d4_to_d1')):
            panel.imshow(cv2.cvtColor(inputs['images'][-1], cv2.COLOR_BGR2RGB))
            truth = inputs['truth_landmarks_xy'][-1]
            panel.scatter(truth[:, 0], truth[:, 1], marker='o', c='#3cee70', s=45, label='Analytical truth')
            last = report['cases'][case]['variants'][name]['trace'][-1]
            if 'predicted_landmarks_xy' in last:
                prediction = np.array(last['predicted_landmarks_xy'])
                panel.scatter(prediction[:, 0], prediction[:, 1], marker='x', c='#ff4343', s=45, label='Predicted')
                panel.set_title(f'{name}\nRMS {last["landmark_rms_px"]:.3f} px')
            else: panel.set_title(f'{name}: no complete measured chain')
            panel.legend(fontsize=7)
        for panel in panels: panel.set_xlim(0, 150); panel.set_ylim(150, 0)
    fig.suptitle('Two different body textures; visible landmarks scored in original pixel coordinates')
    fig.tight_layout(); fig.savefig(output/'extended_landmark_comparison.png', dpi=300)
    fig.savefig(output/'extended_landmark_comparison.pdf'); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='extended_motion_controls_20261002')
    parser.add_argument('--algorithm-snapshot', type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    output = ROOT/'diagnostics/algorithm-revision'/args.label
    output.mkdir(parents=True, exist_ok=False)
    frozen = output/'algorithm_snapshot.py'; frozen.write_bytes(args.algorithm_snapshot.read_bytes())
    (output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    helper = ROOT/'validate_motion_resolution.py'; (output/helper.name).write_bytes(helper.read_bytes())
    spec = importlib.util.spec_from_file_location('extended_motion_algorithm', frozen)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    cv2.setNumThreads(1)
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'algorithm_sha256': sha256(frozen), 'validator_sha256': sha256(Path(__file__)),
              'method': 'Independently rendered radius-55 sphere; analytical x/y axis-angle increments, '
                        'noncommuting pose composition and six known front-facing body landmarks. '
                        'Stationary controls use 120 frames with independent pixel noise. Actual matcher, '
                        'shape fit and map selector executed; no neural inference or defect masks.',
              'limitations': 'Synthetic development controls with perfect silhouettes, fixed camera and two textures. '
                            'No field or grade accuracy, glare/occlusion evaluation or verified full turn. '
                            '3D pose error and landmark errors score the full measured chain; failed chains are unavailable. '
                            'Partial maps and absence of a grade cannot establish accurate motion.',
              'render_settings': {'radius_px': 55., 'size': [150, 150], 'center_xy': [74.5, 74.5],
                                  'increment_x_deg': X_STEPS, 'increment_y_deg': Y_STEPS, 'textures': TEXTURES,
                                  'stationary_frames': 120, 'noise_sigma_gray_levels': 2., 'noise_seeds': {'a': 391, 'b': 923}},
              'acceptance_controls': {'moving_endpoint_pose_max_deg': 1., 'moving_all_landmark_rms_max_px': 1.,
                                      'stationary_endpoint_pose_max_deg': 1., 'stationary_all_landmark_rms_max_px': 1.,
                                      'stationary_no_grade_or_350deg_longitude': True}, 'cases': {}}
    rendered = {}
    for stationary in (False, True):
        for pattern in ('a', 'b'):
            case = f'{"stationary_120" if stationary else "variable_xy"}_texture_{pattern}'
            inputs = render(pattern, stationary); rendered[case] = inputs
            np.savez_compressed(output/f'{case}_inputs.npz', **inputs)
            row = {'stationary': stationary, 'input_sha256': sha256(output/f'{case}_inputs.npz'), 'variants': {}}
            report['cases'][case] = row
            for name, adaptive in (('coarse_d4', False), ('adaptive_d4_to_d1', True)):
                settings = module.Settings(spheroid_type='sphere', rotation_axis='y', rotation_direction=1,
                    min_pair_angle_deg=0., image_downsample=4, refine_small_motion=adaptive,
                    bidirectional_matching=True, select_rotating_views=True, maximum_view_index_gap=1,
                    minimum_longitude_coverage_deg=350, defect_observations_complete=False)
                result = evaluate(module, inputs, settings); row['variants'][name] = result
                write_json(output/'report.json', report)
                print(json.dumps({'case': case, 'variant': name, **result['summary'],
                                  'map_status': result['mapping']['status'],
                                  'longitude_deg': result['mapping']['observed_longitude_deg']}), flush=True)
    report['control_results'] = {}
    for case, row in report['cases'].items():
        result = row['variants']['adaptive_d4_to_d1']; summary = result['summary']
        checks = {'all_pairs_measured': summary['all_pairs_measured'],
                  'endpoint_pose_within_1deg': summary['endpoint_pose_error_deg'] is not None and summary['endpoint_pose_error_deg'] <= 1.,
                  'all_landmark_rms_within_1px': summary['maximum_landmark_rms_px'] is not None and summary['maximum_landmark_rms_px'] <= 1.}
        if row['stationary']:
            checks['no_grade_or_full_longitude'] = result['mapping']['grade'] is None and result['mapping']['observed_longitude_deg'] < 350.
        report['control_results'][case] = checks
    report['all_controls_passed'] = all(all(checks.values()) for checks in report['control_results'].values())
    report['completed_at'] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    save_figures(output, report, rendered); write_json(output/'report.json', report)
    write_json(output/'sha256.json', {str(path.relative_to(output)): sha256(path) for path in output.rglob('*') if path.is_file()})
    print(json.dumps({'completed': str(output), 'all_controls_passed': report['all_controls_passed'],
                      'controls': report['control_results']}), flush=True)
    if not report['all_controls_passed']: raise SystemExit(1)


if __name__ == '__main__': main()
