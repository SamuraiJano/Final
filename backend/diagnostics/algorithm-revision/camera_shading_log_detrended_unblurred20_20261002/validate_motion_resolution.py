"""Known-motion resolution controls: rendered pixels, analytical landmarks, no neural models.

Freeze the tested algorithm, render a sphere at independently defined angles,
measure adjacent image motion, and compare its propagated landmarks with truth.
This isolates small-motion estimation; it is not a conveyor or grade-accuracy test.
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


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / 'diagnostics/algorithm-revision/adjacent_native_source/algorithm_snapshot.py'
TRUE_ANGLES = [0., .6, 1.2, 2., 3., 3.5, 4., 4.5, 5., 6.5, 8.]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rotation_y(degrees):
    """Analytical truth matrix, independent of the estimator's Rodrigues search."""
    angle = np.deg2rad(degrees)
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, 0., s], [0., 1., 0.], [-s, 0., c]])


def render(case):
    size, radius = 150, 55.
    center = np.array([74.5, 74.5])
    yy, xx = np.mgrid[:size, :size]
    X, Y = xx-center[0], yy-center[1]
    mask = X*X+Y*Y < radius*radius
    Z = np.sqrt(np.maximum(radius*radius-X*X-Y*Y, 0.))
    camera = np.stack((X, Y, Z), axis=-1)
    angles = TRUE_ANGLES if case == 'variable_small_motion' else [0.]*20
    rng = np.random.default_rng(391)
    images = []
    for angle in angles:
        # Camera-to-body points are row vectors multiplied by body-to-camera R.
        body = camera @ rotation_y(angle)
        intensity = (150 + 45*np.sin(.25*body[:, :, 0]) +
                     30*np.cos(.23*body[:, :, 2]) +
                     15*np.sin(.19*body[:, :, 0]+.13*body[:, :, 1]))
        if case == 'stationary_pixel_noise':
            intensity += rng.normal(0., 2., (size, size))
        elif case == 'uniform_stationary':
            intensity = np.full((size, size), 150.)
        channel = np.uint8(np.clip(intensity, 0, 255))
        channel[~mask] = 0
        images.append(np.repeat(channel[:, :, None], 3, axis=2))
    body_points = np.array([[x, y, np.sqrt(radius*radius-x*x-y*y)]
                           for x in (-15., 0., 15.) for y in (-12., 12.)])
    truth_camera = np.array([body_points @ rotation_y(angle).T for angle in angles])
    assert np.all(truth_camera[:, :, 2] > 0), 'All scored landmarks must remain visible.'
    return {'images': np.array(images), 'mask': mask.astype(np.uint8),
            'angles_deg': np.array(angles), 'body_points_xyz': body_points,
            'landmarks_xy': truth_camera[:, :, :2]+center, 'center': center,
            'radius': radius}


def rotation_error_deg(predicted, truth):
    cosine = (np.trace(predicted @ truth.T)-1)/2
    return float(np.rad2deg(np.arccos(np.clip(cosine, -1., 1.))))


def evaluate(module, inputs, settings):
    views = [module.FruitView(image, inputs['mask'], frame_index=index)
             for index, image in enumerate(inputs['images'])]
    start = time.perf_counter()
    model = module.fit_spheroid(views, settings)
    source_xy = inputs['landmarks_xy'][0]
    centered_xy = source_xy-model.ellipses[0].center
    source_xyz = np.column_stack((centered_xy, module._height(
        model.matrices[0], centered_xy[:, 0], centered_xy[:, 1])))
    pose, chain_available = np.eye(3), True
    rows, vectors = [], []
    trace = [{'frame': 0, 'true_angle_deg': float(inputs['angles_deg'][0]),
              'estimated_y_deg': 0., 'pose_error_deg': 0., 'landmark_rms_px': 0.,
              'predicted_landmarks_xy': source_xy.tolist()}]
    for index in range(len(views)-1):
        row = {'source_frame': index, 'target_frame': index+1,
               'true_increment_deg': float(inputs['angles_deg'][index+1]-inputs['angles_deg'][index])}
        details = {}
        try:
            rotation, residual = module.estimate_rotation(
                views[index], views[index+1], model, index, settings, details)
            vector = np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel()
            row.update(status='measured', rotation_vector_deg=vector.tolist(),
                       residual=float(residual), **details)
            vectors.append(vector.tolist())
            if chain_available:
                pose = rotation @ pose
        except module.MappingError as error:
            row.update(status='unavailable', reason=str(error), **details)
            chain_available = False
        rows.append(row)
        item = {'frame': index+1, 'true_angle_deg': float(inputs['angles_deg'][index+1]),
                'chain_available': chain_available}
        if chain_available:
            predicted = (source_xyz @ pose.T)[:, :2]+model.ellipses[index+1].center
            errors = np.linalg.norm(predicted-inputs['landmarks_xy'][index+1], axis=1)
            item.update(estimated_y_deg=float(np.rad2deg(cv2.Rodrigues(pose)[0][1, 0])),
                        pose_error_deg=rotation_error_deg(pose, rotation_y(inputs['angles_deg'][index+1])),
                        landmark_rms_px=float(np.sqrt(np.mean(errors**2))),
                        landmark_errors_px=errors.tolist(), predicted_landmarks_xy=predicted.tolist())
        trace.append(item)
    mapping = {'grade_evaluated': False}
    try:
        mapped = module.build_surface_map(views, settings)
        assert mapped.grade is None
        mapping.update(status=mapped.status, grade=mapped.grade,
                       selected_frames=mapped.view_frames,
                       observed_longitude_deg=mapped.observed_longitude_deg,
                       estimated_rotation_coverage_deg=mapped.rotation_coverage_deg,
                       observed_surface_pct=mapped.observed_surface_pct,
                       diagnostics=mapped.selection_diagnostics)
    except module.MappingError as error:
        mapping.update(status='mapping_failed', reason=str(error), grade=None,
                       observed_longitude_deg=0.)
    measured = [row for row in rows if row['status'] == 'measured']
    scored = [item for item in trace[1:] if item.get('chain_available')]
    return {'settings': asdict(settings), 'fitted_radius_px': model.A,
            'pairs': rows, 'trace': trace, 'mapping': mapping,
            'summary': {'input_pairs': len(rows), 'measured_pairs': len(measured),
                        'native_rechecks': sum(row.get('image_downsample') == 1 for row in measured),
                        'sum_measured_y_components_deg': float(sum(value[1] for value in vectors)),
                        'final_pose_error_deg': trace[-1].get('pose_error_deg'),
                        'final_landmark_rms_px': trace[-1].get('landmark_rms_px'),
                        'max_landmark_rms_px': max((row['landmark_rms_px'] for row in scored), default=None),
                        'all_pairs_measured': len(measured) == len(rows)},
            'seconds': time.perf_counter()-start}


def figures(output, report, rendered):
    colors = {'d4': '#d18d36', 'd2': '#8668bd', 'd1': '#2a78a5', 'adaptive_d4_to_d1': '#257d4c'}
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for panels, case in zip(axes, ('variable_small_motion', 'stationary_pixel_noise')):
        panels[0].plot(rendered[case]['angles_deg'], 'k--', linewidth=2, label='Analytical truth')
        for name, row in report['cases'][case]['variants'].items():
            trace = row['trace']
            panels[0].plot([item['frame'] for item in trace],
                           [item.get('estimated_y_deg', np.nan) for item in trace],
                           label=name, color=colors[name], marker='.', alpha=.8)
            panels[1].plot([item['frame'] for item in trace],
                           [item.get('landmark_rms_px', np.nan) for item in trace],
                           label=name, color=colors[name], marker='.', alpha=.8)
        panels[0].set(title=case.replace('_', ' '), xlabel='Original rendered frame',
                      ylabel='Propagated y rotation (degrees)')
        panels[1].set(xlabel='Original rendered frame', ylabel='Six-landmark RMS error (pixels)')
        panels[0].legend(fontsize=8); panels[1].legend(fontsize=8)
        for panel in panels: panel.grid(alpha=.2)
    fig.suptitle('Known analytical motion: native recheck versus downsampled matching')
    fig.tight_layout(); fig.savefig(output/'motion_and_landmark_accuracy.png', dpi=300)
    fig.savefig(output/'motion_and_landmark_accuracy.pdf'); plt.close(fig)
    fig, axes = plt.subplots(1, 4, figsize=(12, 4))
    inputs = rendered['variable_small_motion']; frame = len(inputs['images'])-1
    for panel, name in zip(axes, colors):
        panel.imshow(cv2.cvtColor(inputs['images'][frame], cv2.COLOR_BGR2RGB))
        truth = inputs['landmarks_xy'][frame]
        panel.scatter(truth[:, 0], truth[:, 1], c='#30e562', marker='o', s=45, label='Truth')
        trace = report['cases']['variable_small_motion']['variants'][name]['trace'][-1]
        if 'predicted_landmarks_xy' in trace:
            points = np.array(trace['predicted_landmarks_xy'])
            panel.scatter(points[:, 0], points[:, 1], c='#ff4646', marker='x', s=45, label='Prediction')
            panel.set_title(f'{name}\nRMS {trace["landmark_rms_px"]:.3f} px')
        else: panel.set_title(f'{name}\nPrediction unavailable')
        panel.set_xlim(25, 125); panel.set_ylim(125, 25); panel.legend(fontsize=7)
    fig.suptitle('Frame 10: analytical visible landmarks after a true 8-degree turn')
    fig.tight_layout(); fig.savefig(output/'endpoint_landmark_comparison.png', dpi=300)
    fig.savefig(output/'endpoint_landmark_comparison.pdf'); plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for panel, case in zip(axes, rendered):
        panel.imshow(cv2.cvtColor(rendered[case]['images'][0], cv2.COLOR_BGR2RGB))
        panel.set(title=case.replace('_', '\n')); panel.axis('off')
    fig.suptitle('Actual rendered inputs; masks and analytical truth retained in NPZ')
    fig.tight_layout(); fig.savefig(output/'rendered_control_inputs.png', dpi=300)
    fig.savefig(output/'rendered_control_inputs.pdf'); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='motion_resolution_20261002')
    parser.add_argument('--algorithm-snapshot', type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    output = ROOT/'diagnostics/algorithm-revision'/args.label
    output.mkdir(parents=True, exist_ok=False)
    frozen = output/'algorithm_snapshot.py'
    frozen.write_bytes(args.algorithm_snapshot.read_bytes())
    (output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    spec = importlib.util.spec_from_file_location('motion_resolution_algorithm', frozen)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cv2.setNumThreads(1)
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'algorithm_sha256': sha256(frozen), 'validator_sha256': sha256(Path(__file__)),
              'method': 'Analytical radius-55 sphere and y rotation matrices; actual image matcher and fitted sphere. '
                        'Six independently rendered front-facing body landmarks are lifted from the source image '
                        'using the fitted model, propagated through all returned adjacent measurements, '
                        'and compared with independent analytical image coordinates. Failed chains are never interpolated.',
              'limitations': 'Synthetic development controls, not held-out author/conveyor, defect or grade accuracy. '
                            'Stationary and uniform scenes contain no turn; numerical coverage cannot establish physical accuracy. '
                            'A successful short-motion control does not validate complete-turn integration.',
              'render_settings': {'radius_px': 55., 'image_size': [150, 150], 'center_xy': [74.5, 74.5],
                                  'variable_angles_deg': TRUE_ANGLES, 'noise_rng_seed': 391,
                                  'stationary_noise_sigma_gray_levels': 2.,
                                  'texture': '150+45*sin(.25*fx)+30*cos(.23*fz)+15*sin(.19*fx+.13*fy)'},
              'acceptance_controls': {'adaptive_variable_endpoint_pose_error_max_deg': 1.,
                                      'adaptive_variable_landmark_rms_max_px': 1.,
                                      'stationary_no_grade_or_full_longitude': True,
                                      'uniform_no_measured_motion': True}, 'cases': {}}
    rendered = {}
    for case in ('variable_small_motion', 'stationary_pixel_noise', 'uniform_stationary'):
        inputs = render(case); rendered[case] = inputs
        np.savez_compressed(output/f'{case}_inputs.npz', **inputs)
        case_report = {'input_npz_sha256': sha256(output/f'{case}_inputs.npz'), 'variants': {}}
        report['cases'][case] = case_report
        for name, downsample, refine in (('d4', 4, False), ('d2', 2, False), ('d1', 1, False),
                                         ('adaptive_d4_to_d1', 4, True)):
            settings = module.Settings(spheroid_type='sphere', rotation_axis='y', rotation_direction=1,
                min_pair_angle_deg=0., image_downsample=downsample, refine_small_motion=refine,
                bidirectional_matching=True, select_rotating_views=True,
                maximum_view_index_gap=1, minimum_longitude_coverage_deg=350,
                defect_observations_complete=False)
            row = evaluate(module, inputs, settings)
            settings_bytes = json.dumps(asdict(settings), sort_keys=True, separators=(',', ':')).encode()
            row['settings_sha256'] = hashlib.sha256(settings_bytes).hexdigest()
            case_report['variants'][name] = row
            write_json(output/'report.json', report)
            print(json.dumps({'case': case, 'variant': name, **row['summary'],
                              'map_status': row['mapping']['status'],
                              'longitude_deg': row['mapping']['observed_longitude_deg']}), flush=True)
    adaptive = report['cases']['variable_small_motion']['variants']['adaptive_d4_to_d1']['summary']
    stationary = report['cases']['stationary_pixel_noise']['variants']['adaptive_d4_to_d1']
    uniform = report['cases']['uniform_stationary']['variants']['adaptive_d4_to_d1']
    report['control_results'] = {
        'adaptive_variable_all_pairs_measured': adaptive['all_pairs_measured'],
        'adaptive_variable_endpoint_pose_error_within_1deg':
            adaptive['final_pose_error_deg'] is not None and adaptive['final_pose_error_deg'] <= 1.,
        'adaptive_variable_all_landmark_rms_within_1px':
            adaptive['max_landmark_rms_px'] is not None and adaptive['max_landmark_rms_px'] <= 1.,
        'stationary_no_grade_or_full_longitude': stationary['mapping']['grade'] is None and
            stationary['mapping']['observed_longitude_deg'] < 350.,
        'uniform_no_measured_motion': uniform['summary']['measured_pairs'] == 0,
        'uniform_no_grade_or_full_longitude': uniform['mapping']['grade'] is None and
            uniform['mapping']['observed_longitude_deg'] < 350.}
    report['all_controls_passed'] = all(report['control_results'].values())
    report['completed_at'] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    figures(output, report, rendered)
    write_json(output/'report.json', report)
    checksums = {str(path.relative_to(output)): sha256(path) for path in output.rglob('*') if path.is_file()}
    write_json(output/'sha256.json', checksums)
    print(json.dumps({'completed': str(output), 'controls': report['control_results']}), flush=True)
    if not report['all_controls_passed']: raise SystemExit(1)


if __name__ == '__main__':
    main()
