"""Check the retained paper profile against its frozen previous implementation.

These are numerical equivalence checks, not ground-truth accuracy scores.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import cv2
import numpy as np

from test_algorithm import AlgorithmTests
from validate_native_prefilter import load_module
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
BASELINE = ROOT/'diagnostics/algorithm-revision/adjacent_observable_source/algorithm_snapshot.py'
BASELINE_SHA = '863fd09cfa629c5b5b8ba7c73963fbe993441b3e3dd989f1e451d0a5f62c9db1'
CANDIDATE_SHA = '951b55a4912d3147d349282846e2e02d20159a410b6bb2e8fdd4ab4dd3abea2d'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='photometric_equivalence_20261002')
    args = parser.parse_args()
    candidate_path = ROOT/'algorithm.py'
    if sha256(BASELINE) != BASELINE_SHA or sha256(candidate_path) != CANDIDATE_SHA:
        raise ValueError('Unexpected execution source; use an explicit new validator for a later source')
    output = ROOT/'diagnostics/algorithm-revision'/args.label
    output.mkdir(parents=True, exist_ok=False)
    (output/'baseline_algorithm.py').write_bytes(BASELINE.read_bytes())
    (output/'algorithm_snapshot.py').write_bytes(candidate_path.read_bytes())
    for name in (Path(__file__).name, 'test_algorithm.py', 'validate_native_prefilter.py', 'validate_motion_resolution.py'):
        (output/name).write_bytes((ROOT/name).read_bytes())
    baseline = load_module(output/'baseline_algorithm.py', 'equivalence_baseline')
    candidate = load_module(output/'algorithm_snapshot.py', 'equivalence_candidate')
    fixture = AlgorithmTests._photometric_fixture()
    vectors = np.deg2rad([[0., 0., 0.], [.3, 1.3, 0.], [-1., 6., 0.], [0., 179., 0.]])
    np.savez_compressed(output/'cost_fixture.npz', points=fixture[0], source_values=fixture[1],
                        target_green=fixture[2], target_mask=fixture[3], center=fixture[5],
                        minimum_points=fixture[6], target_matrix=fixture[7], vectors=vectors)
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'baseline_algorithm_sha256': BASELINE_SHA, 'algorithm_sha256': CANDIDATE_SHA,
              'method': 'Uncompensated paper cost and optional normalized cost against exact frozen 863 '
                        'on known visible/hidden and all-masked hypotheses; actual legacy-profile pair '
                        'estimates on identical archived render inputs. No labels fit any estimate.',
              'limitations': 'Numerical preservation of the old objective is not old or new geometry accuracy. '
                             'Synthetic known-motion and author-label tests score accuracy separately.',
              'cost_checks': [], 'pair_checks': []}
    for normalize in (False, True):
        for masked in (False, True):
            arguments = fixture if not masked else (*fixture[:3], np.zeros_like(fixture[3]), *fixture[4:])
            previous = baseline._cost_many(vectors, *arguments, normalize=normalize)
            current = candidate._cost_many(vectors, *arguments, normalize=normalize)
            np.testing.assert_array_equal(current, previous)
            old_scalar = np.array([baseline._cost(vector, *arguments, normalize=normalize) for vector in vectors])
            new_scalar = np.array([candidate._cost(vector, *arguments, normalize=normalize) for vector in vectors])
            np.testing.assert_array_equal(new_scalar, old_scalar)
            finite = np.isfinite(previous)
            report['cost_checks'].append({'normalize': normalize, 'all_masked': masked,
                'hypotheses': len(vectors), 'finite_hypotheses': int(finite.sum()),
                'maximum_batch_difference': float(np.max(np.abs(current[finite]-previous[finite]))) if finite.any() else None,
                'maximum_scalar_difference': float(np.max(np.abs(new_scalar[finite]-old_scalar[finite]))) if finite.any() else None,
                'exact_equality_including_unavailable': True})
    inputs = [ROOT/'diagnostics/algorithm-revision/full_turn_observable_20261002/constant_6deg_texture_a_inputs.npz',
              ROOT/'diagnostics/algorithm-revision/extended_motion_controls_20261002/variable_xy_texture_a_inputs.npz']
    threads = cv2.getNumThreads(); cv2.setNumThreads(1)
    try:
        for path in inputs:
            with np.load(path) as stored:
                images, mask = stored['images'][:2], stored['mask']
            (output/path.name).write_bytes(path.read_bytes())
            results = []
            for module in (baseline, candidate):
                settings = module.Settings(spheroid_type='sphere', rotation_axis='y', bidirectional_matching=True,
                    image_downsample=4, highpass_sigma=1.25, min_pair_angle_deg=.25, refine_small_motion=True)
                views = [module.FruitView(image, mask, frame_index=index) for index, image in enumerate(images)]
                model = module.fit_spheroid(views, settings)
                try:
                    rotation, residual = module.estimate_rotation(views[0], views[1], model, 0, settings)
                    result = {'status': 'measured', 'rotation_matrix': rotation.tolist(), 'residual': residual}
                except module.MappingError as error:
                    result = {'status': 'unavailable', 'reason': str(error)}
                result['settings'] = asdict(settings); results.append(result)
            previous, current = results
            assert previous['status'] == current['status']
            if previous['status'] == 'measured':
                np.testing.assert_array_equal(current['rotation_matrix'], previous['rotation_matrix'])
                assert current['residual'] == previous['residual']
            else:
                assert current['reason'] == previous['reason']
            report['pair_checks'].append({'input_sha256': sha256(path), 'input_file': path.name,
                                          'baseline': previous, 'candidate': current, 'exact_equivalence': True})
    finally:
        cv2.setNumThreads(threads)
    report['all_checks_passed'] = True
    report['completed_at'] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    write_json(output/'report.json', report)
    (output/'PHOTOMETRIC_EQUIVALENCE.md').write_text(
        '# Retained paper-profile numerical equivalence\n\n'
        f'All checks pass for source `{CANDIDATE_SHA}` against baseline `{BASELINE_SHA}`. '
        'Sixteen batched hypotheses and the matching scalar calculations cover both cost modes, '
        'visible/hidden surfaces and all-masked targets. The legacy pair profile returns identical '
        'rotations, residuals or explicit unavailability on two archived image pairs. '
        'The optional green refinement is not enabled in this legacy check. '
        'This proves numerical preservation on these inputs, not motion or grade accuracy. '
        'Inputs, settings and both exact source snapshots are retained.\n', encoding='utf-8')
    write_json(output/'sha256.json', {str(path.relative_to(output)): sha256(path) for path in output.rglob('*') if path.is_file()})
    print(json.dumps({'all_checks_passed': True, 'source_sha256': CANDIDATE_SHA, 'output': str(output)}, indent=2))


if __name__ == '__main__': main()
