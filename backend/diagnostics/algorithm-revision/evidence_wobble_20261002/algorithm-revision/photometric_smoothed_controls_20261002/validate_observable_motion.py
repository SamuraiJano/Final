"""Declare unobservable rolling explicitly; never propagate unavailable motion.

An isolated snapshot combines native-only sigma2 filtering with a quarter-degree
minimum rolling component, consistent at direct measurement and view selection.
The original failed forced-zero-minimum controls remain frozen and unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import validate_extended_motion_controls as controls
from validate_native_prefilter import load_module
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
INPUT = ROOT/'diagnostics/algorithm-revision/extended_motion_controls_20261002'
PREFILTER = ROOT/'diagnostics/algorithm-revision/native_prefilter_trials_20261002/report.json'


def candidate_snapshot(text):
    green = '    green = v.image[:, :, 1].astype(np.float32) / 255.0\n'
    assert text.count(green) == 1
    text = text.replace(green, green+'    if down == 1:\n        green = cv2.GaussianBlur(green, (0, 0), 2.0)\n')
    selection = '    pair_settings = replace(s, min_pair_angle_deg=0.)\n    records, segments = [], []'
    assert text.count(selection) == 1
    return text.replace(selection,
        '    pair_settings = replace(s, min_pair_angle_deg=.25)\n    records, segments = [], []')


def raw_stationary_audit(raw_report):
    result = {}
    for case in ('stationary_120_texture_a', 'stationary_120_texture_b'):
        row = raw_report['cases'][case]['variants']['native_prefilter_sigma_2.000000']
        measured = [pair for pair in row['pairs'] if pair['status'] == 'measured']
        y = [abs(pair['rotation_vector_deg'][1]) for pair in measured]
        result[case] = {'input_pairs': len(row['pairs']), 'returned_measurements': len(measured),
                        'maximum_dominant_y_deg': max(y),
                        'measurements_at_or_above_quarter_degree': sum(value >= .25 for value in y),
                        'maximum_total_vector_deg': max(float(np.linalg.norm(pair['rotation_vector_deg'])) for pair in measured),
                        'original_raw_endpoint_pose_error_deg': row['summary']['endpoint_pose_error_deg'],
                        'original_raw_endpoint_landmark_rms_px': row['summary']['endpoint_landmark_rms_px']}
    return result


def figures(output, report):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for panels, case in zip(axes, ('variable_xy_texture_a', 'variable_xy_texture_b')):
        row = report['cases'][case]['result']; trace = row['trace']
        frames = [item['frame'] for item in trace]
        panels[0].plot(frames, [item.get('pose_error_deg', np.nan) for item in trace], '.-', color='#267a4e')
        panels[1].plot(frames, [item.get('landmark_rms_px', np.nan) for item in trace], '.-', color='#267a4e')
        panels[0].set(title=case.replace('_', ' '), xlabel='Rendered frame', ylabel='3D pose error (degrees)')
        panels[1].set(xlabel='Rendered frame', ylabel='Visible landmark RMS (pixels)')
        for panel in panels: panel.grid(alpha=.2); panel.axhline(1., color='#a64736', linestyle='--', label='Unchanged acceptance limit'); panel.legend(fontsize=8)
    fig.suptitle('Observable moving measurements: identical known x/y poses and landmarks')
    fig.tight_layout(); fig.savefig(output/'observable_moving_accuracy.png', dpi=300)
    fig.savefig(output/'observable_moving_accuracy.pdf'); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for panel, case in zip(axes, ('stationary_120_texture_a', 'stationary_120_texture_b')):
        summary = report['cases'][case]['result']['summary']
        panel.bar(['Observable returned', 'Declared unavailable'],
                  [summary['measured_pairs'], summary['input_pairs']-summary['measured_pairs']], color=['#a64f36', '#267a4e'])
        panel.set(title=case.replace('_', '\n'), ylabel='Adjacent image pairs', ylim=(0, 130))
        panel.text(.5, 65., 'No propagated endpoint pose\nNo stationary map or grade', ha='center', fontsize=10)
    fig.suptitle('120 stationary noisy frames per texture: availability, not invented zero rotation')
    fig.tight_layout(); fig.savefig(output/'stationary_observability.png', dpi=300)
    fig.savefig(output/'stationary_observability.pdf'); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='observable_motion_controls_20261002')
    args = parser.parse_args()
    output = ROOT/'diagnostics/algorithm-revision'/args.label
    output.mkdir(parents=True, exist_ok=False)
    original = INPUT/'algorithm_snapshot.py'
    candidate = output/'algorithm_snapshot.py'
    candidate.write_text(candidate_snapshot(original.read_text(encoding='utf-8')), encoding='utf-8')
    for name in (Path(__file__).name, 'validate_extended_motion_controls.py', 'validate_native_prefilter.py', 'validate_motion_resolution.py'):
        (output/name).write_bytes((ROOT/name).read_bytes())
    baseline = json.loads((INPUT/'report.json').read_text(encoding='utf-8'))
    raw_report = json.loads(PREFILTER.read_text(encoding='utf-8'))
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'base_algorithm_sha256': sha256(original), 'candidate_algorithm_sha256': sha256(candidate),
              'validator_sha256': sha256(Path(__file__)),
              'method': 'Isolated algorithm snapshot: native-only float-green Gaussian sigma2 before physical-width sigma5 high-pass; '
                        'selector pair_settings minimum dominant rolling .25 degrees; direct pair Settings minimum .25 degrees. '
                        'Replay exact four frozen NPZs. A rejected pair makes propagation unavailable, never zero.',
              'limitations': 'Development observability test after failure inspection; no held-out field or grade accuracy. '
                            'Original forced-zero-minimum raw-motion errors are unchanged and included. '
                            'Declaring a stationary turn unobservable does not measure an exact zero rotation. '
                            'Perfect spheres, perfect masks, two textures and short moving sequences do not validate full-turn reconstruction.',
              'raw_failure_report': str(PREFILTER), 'raw_failure_report_sha256': sha256(PREFILTER),
              'unchanged_raw_stationary_audit': raw_stationary_audit(raw_report),
              'controls': {'stationary_all_119_dominant_turns_unavailable': True,
                           'stationary_no_endpoint_pose_extrapolation': True, 'stationary_no_map_or_grade': True,
                           'moving_all_10_pairs_measured': True, 'moving_endpoint_pose_error_max_deg': 1.,
                           'moving_maximum_landmark_rms_px': 1.}, 'cases': {}}
    module = load_module(candidate, 'observable_motion_candidate'); cv2.setNumThreads(1)
    for case, reference in baseline['cases'].items():
        path = INPUT/f'{case}_inputs.npz'
        with np.load(path) as stored: inputs = {name: stored[name] for name in stored.files}
        settings = module.Settings(**reference['variants']['adaptive_d4_to_d1']['settings'])
        settings.min_pair_angle_deg = .25
        result = controls.evaluate(module, inputs, settings)
        result['summary']['native_attempts_including_unavailable'] = sum(pair.get('image_downsample') == 1 for pair in result['pairs'])
        summary = result['summary']
        if reference['stationary']:
            checks = {'all_119_dominant_turns_unavailable': summary['input_pairs'] == 119 and summary['measured_pairs'] == 0,
                      'endpoint_pose_not_extrapolated': summary['endpoint_pose_error_deg'] is None and summary['endpoint_landmark_rms_px'] is None,
                      'no_map_or_grade': result['mapping']['status'] == 'mapping_failed' and result['mapping']['grade'] is None}
        else:
            checks = {'all_10_pairs_measured': summary['input_pairs'] == 10 and summary['measured_pairs'] == 10,
                      'endpoint_pose_within_1deg': summary['endpoint_pose_error_deg'] is not None and summary['endpoint_pose_error_deg'] <= 1.,
                      'all_landmark_rms_within_1px': summary['maximum_landmark_rms_px'] is not None and summary['maximum_landmark_rms_px'] <= 1.}
        report['cases'][case] = {'stationary': reference['stationary'], 'input_file': str(path),
                                 'input_sha256': sha256(path), 'result': result, 'control_results': checks}
        write_json(output/'report.json', report)
        print(json.dumps({'case': case, **summary, 'map_status': result['mapping']['status'], 'controls': checks}), flush=True)
    report['all_controls_passed'] = all(all(row['control_results'].values()) for row in report['cases'].values())
    report['completed_at'] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    figures(output, report); write_json(output/'report.json', report)
    write_json(output/'sha256.json', {str(path.relative_to(output)): sha256(path) for path in output.rglob('*') if path.is_file()})
    print(json.dumps({'completed': str(output), 'all_controls_passed': report['all_controls_passed'],
                      'candidate_algorithm_sha256': report['candidate_algorithm_sha256']}), flush=True)
    if not report['all_controls_passed']: raise SystemExit(1)


if __name__ == '__main__': main()
