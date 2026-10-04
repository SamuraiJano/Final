"""Test the real defect model with frozen detector/tracker crops and current mapper.

This isolates segmentation and map/report integration. Detector predictions and
fruit masks were captured earlier from the original conveyor clip; they are not
recomputed in this run. Diagnostic records do not enter dashboard history.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

import main as api
from algorithm import FruitView


ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    output = ROOT / 'diagnostics/algorithm-revision' / args.label
    output.mkdir(parents=True, exist_ok=False)
    for name, payload in api.SOURCE_SNAPSHOTS.items():
        (output / f'{name}.snapshot').write_bytes(payload)
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print('Loading actual detector and defect segmentation weights on CUDA.', flush=True)
    pipeline, detector, segmenter = api._make_pipeline(capture_stride_frames=1)
    report = {
        'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
        'scope': __doc__, 'algorithm_sha256': api.ALGORITHM_SHA256,
        'settings': asdict(pipeline.settings), 'tracks': [],
        'source_sha256': {name: hashlib.sha256(payload).hexdigest()
                          for name, payload in api.SOURCE_SNAPSHOTS.items()},
        'model_sha256': {str(path.relative_to(ROOT)): digest(path) for path in (
            ROOT / 'models/D-FINE/detection/best_stg1.pth',
            ROOT / 'models/D-FINE/segmentation/model.pt')},
        'limitations': 'No pose or defect ground truth. This proves model and '
                       'mapping execution, not conveyor grading accuracy. '
                       'No detector inference or tracking is repeated in this run.'}
    cv2.setNumThreads(1)
    started = time.perf_counter()
    fixtures = [(track, ROOT / 'diagnostics/algorithm-audit/corrected_tracks_20261002' / str(track))
                for track in (98, 1, 14)]
    fixtures.append((491, ROOT / 'diagnostics/algorithm-audit/longitude_failure_491_20261002/captured_views'))
    for track, fixture in fixtures:
        items = json.loads((fixture / 'views.json').read_text())
        views = []
        for item in items:
            with np.load(fixture / item['file']) as data:
                views.append(FruitView(data['image'].copy(), data['mask'].copy(),
                                       frame_index=item['frame'],
                                       fruit_bbox=tuple(item['bbox']) if item.get('bbox') else None))
        pipeline.views_by_id[track] = views
        before = segmenter.inference_calls
        print(f'Mapping {track}: {len(views)} frozen real conveyor views.', flush=True)
        row = api._finish_track(pipeline, track, output)
        report['tracks'].append({'track': track, 'fixture': str(fixture),
            'input_sha256': {item['file']: digest(fixture / item['file']) for item in items},
            'segmentation_calls': segmenter.inference_calls-before, 'result': row})
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    report['seconds'] = time.perf_counter()-started
    report['detection'] = api._model_metrics(detector)
    report['segmentation'] = api._model_metrics(segmenter)
    report['completed_at'] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    report['passed_execution'] = all(row['segmentation_calls'] > 0 and
        row['result']['status'] != 'mapping_failed' for row in report['tracks'])
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), 'passed_execution': report['passed_execution'],
        'segmentation': report['segmentation'], 'detector_calls': detector.inference_calls}), flush=True)
    if not report['passed_execution']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
