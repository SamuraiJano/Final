"""Isolated native-only noise-filter trials on frozen known-motion inputs.

Coarse d4 preprocessing is untouched. Native matching filters float green pixels
before the existing physical-width high-pass operation. This script changes a
loaded diagnostic module only; it never edits the production algorithm.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import validate_extended_motion_controls as controls
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
INPUT = ROOT/'diagnostics/algorithm-revision/extended_motion_controls_20261002'


def native_prefilter(original, prefilter_sigma):
    """Return the isolated preprocessing replacement; d4 remains exactly original."""
    def preprocess(view, downsample, highpass_sigma):
        if downsample != 1: return original(view, downsample, highpass_sigma)
        green = view.image[:, :, 1].astype(np.float32)/255.
        green = cv2.GaussianBlur(green, (0, 0), prefilter_sigma)
        high = green-cv2.GaussianBlur(green, (0, 0), highpass_sigma)
        return high.astype(np.float32), view.object_mask.copy()
    return preprocess


def load_module(source, name):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def accuracy_controls(row, stationary):
    summary = row['summary']
    checks = {'all_pairs_measured': summary['all_pairs_measured'],
              'endpoint_pose_within_1deg': summary['endpoint_pose_error_deg'] is not None and summary['endpoint_pose_error_deg'] <= 1.,
              'all_landmark_rms_within_1px': summary['maximum_landmark_rms_px'] is not None and summary['maximum_landmark_rms_px'] <= 1.}
    if stationary:
        checks['no_grade_or_full_longitude'] = row['mapping']['grade'] is None and row['mapping']['observed_longitude_deg'] < 350.
    return checks


def save_figures(output, report):
    fig, axes = plt.subplots(4, 2, figsize=(12, 13))
    colors = ['#ce8635', '#247a4e', '#346aae']
    for panels, (case, entry) in zip(axes, report['cases'].items()):
        for color, (name, row) in zip(colors, entry['variants'].items()):
            trace = row['trace']; frames = [item['frame'] for item in trace]
            panels[0].plot(frames, [item.get('pose_error_deg', np.nan) for item in trace], label=name, color=color)
            panels[1].plot(frames, [item.get('landmark_rms_px', np.nan) for item in trace], label=name, color=color)
        panels[0].set(title=case.replace('_', ' '), xlabel='Original rendered frame', ylabel='3D pose error (degrees)')
        panels[1].set(xlabel='Original rendered frame', ylabel='Visible landmark RMS (pixels)')
        for panel in panels: panel.grid(alpha=.2); panel.legend(fontsize=7)
    fig.suptitle('Native-only float-green prefilter: fixed pixels, poses and acceptance controls')
    fig.tight_layout(); fig.savefig(output/'native_prefilter_comparison.png', dpi=300)
    fig.savefig(output/'native_prefilter_comparison.pdf'); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='native_prefilter_trials_20261002')
    parser.add_argument('--sigmas', nargs='+', type=float, default=[float(np.sqrt((4**2-1)/12)), 2.])
    args = parser.parse_args()
    output = ROOT/'diagnostics/algorithm-revision'/args.label
    output.mkdir(parents=True, exist_ok=False)
    source = output/'algorithm_snapshot.py'; source.write_bytes((INPUT/'algorithm_snapshot.py').read_bytes())
    for name in (Path(__file__).name, 'validate_extended_motion_controls.py', 'validate_motion_resolution.py'):
        (output/name).write_bytes((ROOT/name).read_bytes())
    baseline = json.loads((INPUT/'report.json').read_text(encoding='utf-8'))
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'base_algorithm_sha256': sha256(source), 'runtime_prefilter_source_sha256': sha256(Path(__file__)),
              'reference_report': str(INPUT/'report.json'), 'reference_report_sha256': sha256(INPUT/'report.json'),
              'method': 'Load the exact frozen algorithm module and replace its _preprocess function only for downsample1. '
                        'GaussianBlur is applied to float green pixels before the existing sigma5 high-pass. '
                        'Downsample4 remains unchanged. Replay all four exact NPZ pixel/pose/landmark inputs. '
                        'Baseline results are copied from the frozen extended report, not recomputed.',
              'limitations': 'Isolated development candidate chosen after observing stationary failure; no held-out claim. '
                            'No production edits, neural inference or defect accuracy. Prefilter settings are an engineering '
                            'adaptation; the research paper does not prescribe this native-resolution extension.',
              'prefilter_sigmas_native_px': args.sigmas,
              'first_sigma_rationale': 'sqrt((4^2-1)/12): variance of a four-pixel discrete box averaging kernel.',
              'acceptance_controls': baseline['acceptance_controls'], 'cases': {}, 'trial_controls': {}}
    cv2.setNumThreads(1)
    for case, reference in baseline['cases'].items():
        input_path = INPUT/f'{case}_inputs.npz'
        with np.load(input_path) as stored: inputs = {name: stored[name] for name in stored.files}
        row = {'stationary': reference['stationary'], 'input_file': str(input_path),
               'input_sha256': sha256(input_path),
               'variants': {'unfiltered_native_baseline': reference['variants']['adaptive_d4_to_d1']}}
        report['cases'][case] = row
        for sigma in args.sigmas:
            name = f'native_prefilter_sigma_{sigma:.6f}'
            module = load_module(source, f'prefilter_{case}_{sigma}'.replace('.', '_'))
            module._preprocess = native_prefilter(module._preprocess, sigma)
            settings = module.Settings(**reference['variants']['adaptive_d4_to_d1']['settings'])
            measured = controls.evaluate(module, inputs, settings)
            measured['native_prefilter_sigma_px'] = sigma
            row['variants'][name] = measured
            checks = accuracy_controls(measured, reference['stationary'])
            report['trial_controls'].setdefault(name, {})[case] = checks
            write_json(output/'report.json', report)
            print(json.dumps({'case': case, 'trial': name, **measured['summary'],
                              'map_status': measured['mapping']['status'],
                              'longitude_deg': measured['mapping']['observed_longitude_deg'],
                              'controls': checks}), flush=True)
    report['all_cases_passed_by_trial'] = {name: all(all(checks.values()) for checks in cases.values())
                                         for name, cases in report['trial_controls'].items()}
    report['completed_at'] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    save_figures(output, report); write_json(output/'report.json', report)
    write_json(output/'sha256.json', {str(path.relative_to(output)): sha256(path) for path in output.rglob('*') if path.is_file()})
    print(json.dumps({'completed': str(output), 'all_cases_passed_by_trial': report['all_cases_passed_by_trial']}), flush=True)
    if not any(report['all_cases_passed_by_trial'].values()): raise SystemExit(1)


if __name__ == '__main__': main()
