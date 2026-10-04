"""Compare conservative native retries on frozen real crops, without grading.

Legacy fixture491 is physical raw track340. This measures execution and image
selection; these clips have no calibrated pose or surface-coverage truth.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    output = ROOT / 'diagnostics/fruit340-fix' / args.label
    output.mkdir(parents=True, exist_ok=False)
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    parameters = json.loads((ROOT / 'diagnostics/algorithm-revision/'
        'identity_mapping_scene_v2_real_model_20261004/report.json').read_text())['settings']
    parameters['defect_observations_complete'] = False
    parameters['grade_partial_maps'] = False
    fixtures = [(str(track), ROOT / 'diagnostics/algorithm-audit/corrected_tracks_20261002' / str(track))
                for track in (98, 1, 14)]
    fixtures.append(('340', ROOT / 'diagnostics/algorithm-audit/longitude_failure_491_20261002/captured_views'))
    report = {'scope': __doc__, 'settings': parameters,
              'limitations': 'No defect inference, grades or pose/coverage ground truth.',
              'tracks': {}, 'source_sha256': {}}
    cv2.setNumThreads(1)
    for variant, path in (('baseline', args.baseline), ('candidate', ROOT / 'algorithm.py')):
        frozen = output / f'{variant}_algorithm.py'
        frozen.write_bytes(path.read_bytes())
        report['source_sha256'][variant] = sha(frozen)
        module = load(frozen, f'native_retry_{variant}')
        settings = module.Settings(**parameters)
        for track, fixture in fixtures:
            folder = output / track / variant
            folder.mkdir(parents=True)
            items = json.loads((fixture / 'views.json').read_text())
            views = []
            for item in items:
                with np.load(fixture / item['file']) as data:
                    views.append(module.FruitView(data['image'].copy(), data['mask'].copy(),
                        frame_index=item['frame'], fruit_bbox=tuple(item['bbox']) if item.get('bbox') else None))
            started = time.perf_counter()
            try:
                mapped = module.build_surface_map(views, settings)
                cv2.imwrite(str(folder / 'surface_map.png'), mapped.bgr_map)
                cv2.imwrite(str(folder / 'observed_mask.png'), mapped.observed_mask*255)
                row = {key: value for key, value in asdict(mapped).items()
                       if key not in ('bgr_map', 'observed_mask', 'defect_maps', 'longitude_deg', 'latitude_deg')}
                assert row['grade'] is None
            except module.MappingError as error:
                row = {'status': 'mapping_failed', 'reason': str(error),
                       'selection_diagnostics': error.diagnostics, 'grade': None}
            row['seconds'] = time.perf_counter()-started
            report['tracks'].setdefault(track, {'fixture': str(fixture),
                'inputs': {item['file']: sha(fixture/item['file']) for item in items}})[variant] = row
            (folder / 'result.json').write_text(json.dumps(row, indent=2), encoding='utf-8')
            (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps({'variant': variant, 'raw_track': track, 'status': row['status'],
                'frames': row.get('view_frames'), 'observed_surface_pct': row.get('observed_surface_pct'),
                'retries': sum(d.get('native_retry_accepted', False) for d in row['selection_diagnostics'])}), flush=True)
    (output / 'sha256.json').write_text(json.dumps({str(path.relative_to(output)): sha(path)
        for path in output.rglob('*') if path.is_file()}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
