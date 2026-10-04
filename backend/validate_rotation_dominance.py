"""Isolated axis-dominance rejection experiment; no production or neural model changes."""
from argparse import ArgumentParser
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

import cv2
import numpy as np

import algorithm
from validate_longitude_failure import ROOT, ORIGINAL, digest, geometry_run, save_json


def read_views(folder):
    manifest = json.loads((folder/'views.json').read_text(encoding='utf-8'))
    views = []
    hashes = {}
    for item in manifest:
        path = folder/item['file']
        hashes[item['file']] = digest(path)
        with np.load(path) as data:
            views.append(algorithm.FruitView(data['image'], data['mask'], frame_index=item['frame'],
                                           fruit_bbox=tuple(item['bbox']) if item.get('bbox') else None))
    return views, hashes


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--longitude-run', default='longitude_failure_491_20261002')
    parser.add_argument('--corrected-run', default='corrected_tracks_20261002')
    args = parser.parse_args()
    audit = ROOT/'diagnostics/algorithm-audit'
    output = audit/args.label
    output.mkdir(parents=True, exist_ok=False)
    for name in ('algorithm.py', Path(__file__).name, 'validate_longitude_failure.py'):
        (output/f'{name}.snapshot').write_bytes((ROOT/name).read_bytes())
    settings = replace(algorithm.Settings(**json.loads((ORIGINAL/'report.json').read_text())['metrics']['geometry_settings']),
                       defect_observations_complete=False)
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'method': 'Reject an estimated pair when a transverse Rodrigues component exceeds its configured roller-axis component in absolute magnitude; do not change fitted rotations or search parameters.',
              'settings': settings.__dict__, 'segmentation_executed': False, 'grade_evaluated': False,
              'limitations': 'Development diagnostic with no manual motion truth. Ordered or larger maps do not establish accuracy.',
              'source_sha256': {name: digest(ROOT/name) for name in ('algorithm.py', Path(__file__).name, 'validate_longitude_failure.py')},
              'tracks': []}
    sources = [('legacy491', audit/args.longitude_run/'captured_views')]
    sources += [(f'corrected{identity}', audit/args.corrected_run/str(identity)) for identity in (98,1,14)]
    original_estimator = algorithm.estimate_rotation
    for label, folder in sources:
        views, hashes = read_views(folder)
        destination = output/label
        destination.mkdir()
        row = {'label': label, 'input_folder': str(folder), 'input_file_sha256': hashes,
               'views': len(views), 'variants': {}}
        row['variants']['baseline_auto'] = geometry_run(views, settings, destination/'baseline_auto')
        rejected = []

        def guarded_estimate(source, target, model, index, pair_settings):
            rotation, error = original_estimator(source, target, model, index, pair_settings)
            vector = cv2.Rodrigues(rotation)[0].ravel()
            axis = 0 if pair_settings.rotation_axis == 'x' else 1
            main = abs(float(vector[axis]))
            transverse = max(abs(float(value)) for i,value in enumerate(vector) if i != axis)
            if transverse > main + 1e-7:
                rejected.append({'source_frame': source.frame_index, 'target_frame': target.frame_index,
                                 'rotation_vector_deg': np.rad2deg(vector).tolist(), 'error': error})
                raise algorithm.MappingError('Transverse rotation exceeds configured roller-axis component')
            return rotation, error

        try:
            algorithm.estimate_rotation = guarded_estimate
            row['variants']['guarded_auto'] = geometry_run(views, settings, destination/'guarded_auto')
        finally:
            algorithm.estimate_rotation = original_estimator
        row['guard_rejected_pairs'] = rejected
        save_json(destination/'guard_rejected_pairs.json', rejected)
        report['tracks'].append(row)
        save_json(output/'report.json', report)
        print(json.dumps({'label': label, 'guard_rejected_pairs': len(rejected),
            'baseline': {key: row['variants']['baseline_auto'].get(key) for key in ('status','reason','rotation_coverage_deg','observed_longitude_deg')},
            'guarded': {key: row['variants']['guarded_auto'].get(key) for key in ('status','reason','rotation_coverage_deg','observed_longitude_deg')}}), flush=True)
    print(output, flush=True)


if __name__ == '__main__':
    main()
