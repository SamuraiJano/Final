"""Replay known motion, stationary noise and brightness offsets on one snapshot.

No production edits, model calls or changed accuracy thresholds. Failed or
unobservable pairs remain unavailable; no missing pose is extrapolated.
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
from validate_observable_motion import figures


ROOT = Path(__file__).resolve().parent
INPUT = ROOT/'diagnostics/algorithm-revision/extended_motion_controls_20261002'
SOURCE = ROOT/'diagnostics/algorithm-revision/photometric_candidate_source/algorithm_snapshot.py'
def settings_for(module, reference, profile):
    settings = module.Settings(**reference['variants']['adaptive_d4_to_d1']['settings'])
    settings.image_downsample = 1
    settings.highpass_sigma = 5.
    settings.matching_cost = 'green_mad'
    settings.bidirectional_matching = True
    settings.min_pair_angle_deg = .25
    if profile == 'hybrid':
        settings.image_downsample = 4
        settings.highpass_sigma = 1.25
        settings.matching_cost = 'mad'
        settings.native_matching_cost = 'green_mad'
        settings.minimum_view_rotation_deg = 8.
    return settings


def checks_for(result, stationary):
    summary = result['summary']
    if stationary:
        return {'all_119_dominant_turns_unavailable': summary['input_pairs'] == 119 and summary['measured_pairs'] == 0,
                'endpoint_pose_not_extrapolated': summary['endpoint_pose_error_deg'] is None and summary['endpoint_landmark_rms_px'] is None,
                'no_map_or_grade': result['mapping']['status'] == 'mapping_failed' and result['mapping']['grade'] is None}
    return {'all_10_pairs_measured': summary['input_pairs'] == 10 and summary['measured_pairs'] == 10,
            'endpoint_pose_within_1deg': summary['endpoint_pose_error_deg'] is not None and summary['endpoint_pose_error_deg'] <= 1.,
            'all_landmark_rms_within_1px': summary['maximum_landmark_rms_px'] is not None and summary['maximum_landmark_rms_px'] <= 1.}


def two_frame_inputs(inputs):
    result = {name: value.copy() for name, value in inputs.items()}
    for name in ('images', 'truth_poses', 'truth_landmarks_xy'):
        result[name] = result[name][:2]
    result['truth_increment_xy_deg'] = result['truth_increment_xy_deg'][:1]
    return result


def exposure_control(module, inputs, settings, output, name):
    original = two_frame_inputs(inputs)
    shifted = two_frame_inputs(inputs)
    maximum = int(original['images'][1].max())
    assert maximum+10 <= 255, 'Exposure control must not clip any image pixel'
    # A global additive exposure offset is applied to the complete second image,
    # including the background. Silhouettes and all known geometry stay fixed.
    shifted['images'][1] = np.uint8(shifted['images'][1].astype(np.int16)+10)
    input_path = output/f'{name}_plus10_inputs.npz'
    np.savez_compressed(input_path, **shifted, offset_gray_levels=10)
    baseline = controls.evaluate(module, original, settings)
    offset = controls.evaluate(module, shifted, settings)
    comparison = {'rotation_change_deg': None, 'residual_change': None}
    measured = (baseline['pairs'][0]['status'] == 'measured' and offset['pairs'][0]['status'] == 'measured')
    if measured:
        before = cv2.Rodrigues(np.deg2rad(baseline['pairs'][0]['rotation_vector_deg']))[0]
        after = cv2.Rodrigues(np.deg2rad(offset['pairs'][0]['rotation_vector_deg']))[0]
        comparison['rotation_change_deg'] = controls.angle_error_deg(after, before)
        comparison['residual_change'] = abs(offset['pairs'][0]['residual']-baseline['pairs'][0]['residual'])
    checks = {'both_pairs_measured': measured,
              'rotation_change_within_0_01deg': measured and comparison['rotation_change_deg'] <= .01,
              'residual_change_within_0_00001': measured and comparison['residual_change'] <= 1.e-5,
              'both_known_pose_errors_within_1deg': all(row['summary']['endpoint_pose_error_deg'] is not None and
                  row['summary']['endpoint_pose_error_deg'] <= 1. for row in (baseline, offset)),
              'both_known_landmark_errors_within_1px': all(row['summary']['endpoint_landmark_rms_px'] is not None and
                  row['summary']['endpoint_landmark_rms_px'] <= 1. for row in (baseline, offset))}
    return {'global_offset_gray_levels': 10, 'pixels_saturated': 0,
            'maximum_second_frame_before_offset': maximum, 'input_sha256': sha256(input_path),
            'baseline': baseline, 'plus_10': offset, 'comparison': comparison, 'control_results': checks}


def exposure_figure(output, report):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    names = list(report['exposure_controls'])
    for panel, metric, ylabel, limit in zip(axes,
            ('rotation_change_deg', 'residual_change'),
            ('Change in estimated rotation (degrees)', 'Change in reported residual'), (.01, 1.e-5)):
        values = [report['exposure_controls'][name]['comparison'][metric] for name in names]
        panel.bar(['Texture A', 'Texture B'], [np.nan if value is None else value for value in values], color='#267a4e')
        panel.axhline(limit, linestyle='--', color='#a64736', label='Predeclared invariance limit')
        panel.set(ylabel=ylabel, ylim=(0., limit*1.25)); panel.legend(fontsize=8); panel.grid(axis='y', alpha=.2)
    fig.suptitle('Unsaturated +10 gray exposure offset on the second image only')
    fig.tight_layout(); fig.savefig(output/'brightness_offset_invariance.png', dpi=300)
    fig.savefig(output/'brightness_offset_invariance.pdf'); plt.close(fig)


def stationary_result_figure(output, report):
    # Show actual outcomes, including returned false turns and partial maps.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for panel, name in zip(axes, ('stationary_120_texture_a', 'stationary_120_texture_b')):
        row = report['cases'][name]['result']; summary = row['summary']
        panel.bar(['Returned turns', 'Unavailable'],
                  [summary['measured_pairs'], summary['input_pairs']-summary['measured_pairs']],
                  color=['#a64f36', '#267a4e'])
        endpoint = 'unavailable' if summary['endpoint_pose_error_deg'] is None else f"{summary['endpoint_pose_error_deg']:.3f} degrees"
        panel.set(title=name.replace('_', ' '), ylabel='Adjacent image pairs', ylim=(0, 145))
        panel.text(.5, 135, f"Endpoint: {endpoint}\nMap: {row['mapping']['status']}\nGrade: {row['mapping']['grade']}",
                   ha='center', va='top', fontsize=8)
    fig.suptitle('True stationary scenes: actual returned turns and mapping outcomes')
    fig.tight_layout(); fig.savefig(output/'stationary_observability.png', dpi=300)
    fig.savefig(output/'stationary_observability.pdf'); plt.close(fig)


def report_text(report):
    rows = []
    for name, row in report['cases'].items():
        summary = row['result']['summary']
        endpoint = summary['endpoint_pose_error_deg']
        landmark = summary['maximum_landmark_rms_px']
        rows.append(f"| {name} | {summary['measured_pairs']}/{summary['input_pairs']} | "
                    f"{endpoint if endpoint is not None else 'unavailable'} | "
                    f"{landmark if endpoint is not None else 'unavailable'} | "
                    f"{'PASS' if all(row['control_results'].values()) else 'FAIL'} |")
    exposure_rows = []
    for name, row in report['exposure_controls'].items():
        exposure_rows.append(f"| {name} | {row['comparison']['rotation_change_deg']} | "
                             f"{row['comparison']['residual_change']} | "
                             f"{'PASS' if all(row['control_results'].values()) else 'FAIL'} |")
    return ('# Isolated original-green photometric controls\n\n'
            f"Completed {report['completed_at']}. Source SHA256 `{report['algorithm_sha256']}`.\n\n"
            f"Overall control result: **{'PASS' if report['all_controls_passed'] else 'FAIL'}**.\n\n"
            'The unchanged four archived NPZ scenes are replayed using the actual fitted sphere, '
            f"matcher, pose propagation and map selector. Settings profile: {report['settings_description']} "
            'Full settings and a quarter-degree observable rolling minimum are recorded with each result. '
            'No production code is edited and no neural model is executed. Where green_mad is used, '
            'high-pass texture selection stays in place; matching samples green intensities and '
            'subtracts the median brightness difference.\n\n'
            '| Scene | Returned / attempted pairs | Endpoint pose error, deg | Maximum landmark RMS, px | Control |\n'
            '| --- | --- | --- | --- | --- |\n'+'\n'.join(rows)+'\n\n'
            'Moving criteria are unchanged: all ten pairs measured, endpoint pose error at most one '
            'degree and every landmark RMS at most one pixel. Each stationary scene contains 120 '
            'independently noisy images; its 119 dominant-turn measurements must all be unavailable, '
            'with no propagated endpoint and no map or grade. A helper maximum of zero refers only '
            'to the initial reference frame and does not score rejected motion as exactly zero.\n\n'
            'The exposure control adds ten gray levels to every pixel of the second image of one '
            'known moving pair per texture, including the background. It verifies that no pixel '
            'saturates; silhouettes, poses and landmarks are unchanged. Before execution, rotation '
            'invariance is bounded by 0.01 degrees and residual invariance by 0.00001. Both original '
            'and shifted pairs must still satisfy one-degree/one-pixel known geometry.\n\n'
            '| Exposure scene | Rotation change, deg | Residual change | Control |\n'
            '| --- | --- | --- | --- |\n'+'\n'.join(exposure_rows)+'\n\n'
            'Synthetic development results cover two ideal textures, perfect masks, a fixed analytical '
            'camera and short motion. They do not establish field, real segmentation, defect-grade or '
            'general complete-turn accuracy. Previous failed sources and controls remain frozen. '
            'Every input, settings record, execution source, figure and result is hashed.\n\n'
            '![Moving geometry](observable_moving_accuracy.png)\n'
            '![Stationary availability](stationary_observability.png)\n'
            '![Exposure invariance](brightness_offset_invariance.png)\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='photometric_motion_controls_20261002')
    parser.add_argument('--algorithm-source', '--algorithm-snapshot', dest='algorithm_snapshot', type=Path, default=SOURCE)
    parser.add_argument('--expected-sha256', help='Optional exact source hash to verify before execution')
    parser.add_argument('--profile', choices=('native_green', 'hybrid'), default='native_green')
    args = parser.parse_args()
    if args.expected_sha256 and sha256(args.algorithm_snapshot) != args.expected_sha256:
        raise ValueError('The requested frozen green candidate source differs from this test')
    output = ROOT/'diagnostics/algorithm-revision'/args.label
    output.mkdir(parents=True, exist_ok=False)
    frozen = output/'algorithm_snapshot.py'; frozen.write_bytes(args.algorithm_snapshot.read_bytes())
    for name in (Path(__file__).name, 'validate_extended_motion_controls.py', 'validate_motion_resolution.py',
                 'validate_native_prefilter.py', 'validate_observable_motion.py'):
        (output/name).write_bytes((ROOT/name).read_bytes())
    baseline = json.loads((INPUT/'report.json').read_text(encoding='utf-8'))
    module = load_module(frozen, 'photometric_motion_candidate')
    original_threads = cv2.getNumThreads(); cv2.setNumThreads(1)
    description = ('Native resolution 1, high-pass sigma 5, green_mad and bidirectional matching.'
                   if args.profile == 'native_green' else
                   'Quarter resolution 4, paper MAD, high-pass sigma 1.25 and bidirectional matching; '
                   'successful coarse turns below 8 degrees rechecked with native green_mad. '
                   'The frozen algorithm rejects native/coarse rolling disagreement above 3 degrees.')
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'algorithm_sha256': sha256(frozen), 'validator_sha256': sha256(Path(__file__)),
              'settings_profile': args.profile, 'settings_description': description,
              'method': 'Exact four frozen NPZ inputs. '+description+' Quarter-degree observable rolling. '
                        'Actual estimator and selector, independent truth used only for scoring.',
              'acceptance': {'moving_all_10_measured': True, 'moving_endpoint_pose_max_deg': 1.,
                             'moving_maximum_landmark_rms_px': 1., 'stationary_all_119_unavailable': True,
                             'stationary_no_map_or_grade': True, 'exposure_rotation_change_max_deg': .01,
                             'exposure_residual_change_max': 1.e-5}, 'cases': {}, 'exposure_controls': {}}
    try:
        for name, reference in baseline['cases'].items():
            path = INPUT/f'{name}_inputs.npz'
            with np.load(path) as stored: inputs = {key: stored[key] for key in stored.files}
            (output/path.name).write_bytes(path.read_bytes())
            settings = settings_for(module, reference, args.profile)
            result = controls.evaluate(module, inputs, settings)
            result['summary']['native_attempts_including_unavailable'] = sum(pair.get('image_downsample') == 1 for pair in result['pairs'])
            checks = checks_for(result, reference['stationary'])
            report['cases'][name] = {'stationary': reference['stationary'], 'input_sha256': sha256(path),
                                     'result': result, 'control_results': checks}
            write_json(output/'report.json', report)
            print(json.dumps({'case': name, **result['summary'], 'map_status': result['mapping']['status'],
                              'controls': checks}), flush=True)
            if not reference['stationary']:
                row = exposure_control(module, inputs, settings, output, name)
                report['exposure_controls'][name] = row
                write_json(output/'report.json', report)
                print(json.dumps({'exposure_case': name, **row['comparison'], 'controls': row['control_results']}), flush=True)
    finally:
        cv2.setNumThreads(original_threads)
    report['all_controls_passed'] = (all(all(row['control_results'].values()) for row in report['cases'].values()) and
                                     all(all(row['control_results'].values()) for row in report['exposure_controls'].values()))
    report['completed_at'] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    figures(output, report); stationary_result_figure(output, report); exposure_figure(output, report)
    write_json(output/'report.json', report)
    (output/'PHOTOMETRIC_MOTION_CONTROLS.md').write_text(report_text(report), encoding='utf-8')
    write_json(output/'sha256.json', {str(path.relative_to(output)): sha256(path) for path in output.rglob('*') if path.is_file()})
    print(json.dumps({'completed': str(output), 'all_controls_passed': report['all_controls_passed'],
                      'algorithm_sha256': report['algorithm_sha256']}), flush=True)
    if not report['all_controls_passed']: raise SystemExit(1)


if __name__ == '__main__': main()
