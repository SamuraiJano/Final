"""Fresh 640-pixel inference, frozen-input geometry and complete-pipeline timing.

Each invocation creates new evidence. Geometry timings exclude neural inference
and use explicitly artificial all-clear masks solely to exercise atlas fusion.
Actual production replay runs both trained checkpoints and preserves partial maps.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import random
import platform
import time
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'runtime' / 'ultralytics-validation'))
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import cv2
import numpy as np
cv2.setNumThreads(1)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, data):
    def encode(value):
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        raise TypeError(f'Cannot serialize {type(value).__name__}')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, default=encode, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def timed(operation):
    import torch
    torch.cuda.synchronize()
    started = time.perf_counter()
    result = operation()
    torch.cuda.synchronize()
    return result, time.perf_counter() - started


def model_comparison(video, manifest, inputs, output, frame_count=20):
    import torch
    from dfine_segmenter import DfineDetector, DfineSegmenter, make_fruit_tracker
    detector = DfineDetector(ROOT / 'models/D-FINE/detection/best_stg1.pth', 'cuda')
    segmenter = DfineSegmenter(ROOT / 'models/D-FINE/segmentation/model.pt', device='cuda')
    if detector.input_size != (640, 640) or segmenter.input_size != (640, 640):
        raise ValueError('Model input size must remain 640 x 640')
    capture = cv2.VideoCapture(str(video))
    frames = []
    try:
        for _ in range(frame_count):
            ok, frame = capture.read()
            if not ok:
                break
            frames.append(frame)
    finally:
        capture.release()
    record = next(row for row in manifest['records'] if len(row['views']) >= 40)
    images, masks = [], []
    for item in record['views'][::max(1, len(record['views']) // 8)][:8]:
        path = inputs / 'inputs' / str(record['track_id']) / item['file']
        if sha(path) != item['sha256']:
            raise ValueError('Frozen crop changed')
        with np.load(path) as data:
            masks.append(data['mask'])
            images.append(cv2.bitwise_and(data['image'], data['image'], mask=data['mask']))
    reference_rows = []
    reference_masks = None
    rows = []
    for half in (False, True):
        detector.mixed_precision = segmenter.mixed_precision = half
        for frame in frames[:3]:
            detector.track(frame)
        detector.tracker = make_fruit_tracker('cuda')
        detection_seconds = []
        detections = []
        for frame in frames:
            _, seconds = timed(lambda: detector.track(frame))
            detection_seconds.append(seconds)
            detections.append(detector.last_detection_rows.copy())
        if not half:
            reference_rows = detections
        for batch_size in (1, 4):
            for _ in range(2):
                segmenter.predict_batch(images[:batch_size])
            predictions, durations = [], []
            for start in range(0, len(images), batch_size):
                result, seconds = timed(lambda: segmenter.predict_batch(images[start:start + batch_size]))
                predictions.extend(result); durations.append(seconds)
            class_masks = []
            for result, mask in zip(predictions, masks):
                merged = np.zeros((len(segmenter.names), *mask.shape), bool)
                if result.masks is not None:
                    labels = result.boxes.cls.numpy().astype(int)
                    for label, instance in zip(labels, result.masks.data.numpy()):
                        merged[label] |= (instance > .5) & (mask > 0)
                class_masks.append(merged)
            if reference_masks is None:
                reference_masks = class_masks
            intersections = sum(np.count_nonzero(left & right) for left, right in zip(reference_masks, class_masks))
            unions = sum(np.count_nonzero(left | right) for left, right in zip(reference_masks, class_masks))
            row = dict(precision='mixed_fp16' if half else 'fp32', input_size=[640, 640],
                detection_tracking_fps=len(frames) / sum(detection_seconds),
                detector_p95_ms=float(np.percentile(detection_seconds, 95) * 1000),
                segmentation_batch=batch_size, segmentation_crops_per_second=len(images) / sum(durations),
                segmentation_effective_ms_per_crop=sum(durations) * 1000 / len(images),
                class_mask_iou_vs_fp32_single=intersections / unions if unions else 1.,
                changed_mask_pixels=sum(np.count_nonzero(left != right) for left, right in zip(reference_masks, class_masks)),
                detector_prediction_counts=[len(result) for result in detections],
                detector_counts_vs_fp32=[len(result) - len(base) for result, base in zip(detections, reference_rows)],
                measured_frames=len(frames), measured_crops=len(images))
            rows.append(row)
            print('Model comparison', row['precision'], 'batch', batch_size,
                  round(row['detection_tracking_fps'], 2), 'detector FPS',
                  round(row['segmentation_crops_per_second'], 2), 'crops/s', flush=True)
            write(output / 'models.json', rows)
    del detector, segmenter
    gc.collect(); torch.cuda.empty_cache()
    return rows


def geometry_comparison(manifest, inputs, output, count):
    import algorithm as active
    from realtime_pipeline import RealtimePipeline, OnlineTrack
    from validate_dense_mapping import load_module, load_views
    baseline = load_module(ROOT / 'diagnostics/realtime/20261009_implementation/baseline_source/algorithm.py',
                           'realtime_baseline')
    baseline_settings = baseline.Settings(**json.loads((inputs / 'final_v4/settings.json').read_text()))
    baseline_settings = replace(baseline_settings, defect_observations_complete=False, grade_partial_maps=False)
    chosen = random.Random(817).sample([r for r in manifest['records'] if len(r['views']) >= 40], count)
    class GeometryMasks:
        names = {0: 'ARTIFICIAL_geometry_only'}
        def predict_batch(self, images, **kwargs):
            return [SimpleNamespace(masks=None, boxes=None) for _ in images]
    rows = []
    for record in chosen:
        base_views = load_views(baseline, inputs, record)
        start = time.perf_counter()
        try:
            result = baseline.build_surface_map(base_views, baseline_settings)
            row = dict(mapped=True, coverage=result.observed_surface_pct,
                       longitude=result.observed_longitude_deg, selected_views=len(result.view_frames))
        except baseline.MappingError as failure:
            row = dict(mapped=False, reason=str(failure))
        row.update(profile='reference', record=record['track_id'], seconds=time.perf_counter() - start)
        rows.append(row)
        config = active.Settings(**{**json.loads((inputs / 'final_v4/settings.json').read_text()),
                  'rotation_estimator': 'features', 'keyframe_minimum_rotation_deg': 15.,
                  'feature_rotation_fallback': False, 'vectorized_fusion': True})
        pipeline = RealtimePipeline(GeometryMasks(), settings=config, defer_defect_segmentation=True)
        start = time.perf_counter()
        try:
            views = load_views(active, inputs, record)
            state = OnlineTrack()
            pipeline.online[record['track_id']] = state
            for view in views:
                pipeline._advance(record['track_id'], state, view)
                pipeline._submit(); pipeline._poll()
            pipeline.flush()
            result = pipeline.finish_track(record['track_id'])
            row = dict(mapped=True, coverage=result.observed_surface_pct,
                       longitude=result.observed_longitude_deg, selected_views=len(result.view_frames))
        except active.MappingError as failure:
            row = dict(mapped=False, reason=str(failure))
        finally:
            pipeline.close()
        row.update(profile='realtime', record=record['track_id'], seconds=time.perf_counter() - start,
                   counters=dict(pipeline.counters), synthetic_masks=True, grades_evaluated=False)
        rows.append(row)
        print('Geometry record', record['track_id'], [(r['profile'], round(r['seconds'], 3), r.get('coverage'))
                  for r in rows[-2:]], flush=True)
        write(output / 'geometry.json', rows)
    return rows


def replay(video, output, frames=None, profile='realtime'):
    os.environ['FRUIT_PIPELINE'] = profile
    import main
    source = video
    if frames is not None:
        source = output / f'first_{frames}_frames.mp4'
        capture = cv2.VideoCapture(str(video))
        size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), capture.get(cv2.CAP_PROP_FPS), size)
        try:
            for _ in range(frames):
                ok, image = capture.read()
                if not ok: break
                writer.write(image)
        finally:
            capture.release(); writer.release()
    job = main.RESULTS / uuid4().hex
    job.mkdir()
    metrics = {}
    def progress(**changes):
        write(output / 'progress.json', changes)
        if changes.get('frames_processed', 0) % 20 == 0:
            print('Production', changes, flush=True)
    started = time.perf_counter()
    try:
        fruits = main.analyze_video(source, job, metrics, progress)
        report = dict(job_id=job.name, created_at=datetime.now(timezone.utc).isoformat(),
                      source_name=video.name, mode='video', status='complete', metrics=metrics, fruits=fruits)
        main._write_report(job, report)
        summary = dict(status='complete', job_id=job.name, report=str(job / 'report.json'),
            full_original_video=frames is None, source_video_sha256=sha(video), metrics=metrics,
            maps=sum('surface_map' in row for row in fruits),
            complete_maps=sum(row.get('coverage_complete', False) for row in fruits),
            tracker_records=len(fruits), mapped_coverage_median=float(np.median(
                [row['observed_surface_pct'] for row in fruits if 'observed_surface_pct' in row]))
                if any('observed_surface_pct' in row for row in fruits) else None,
            limitations='No manually verified physical identity, pose or defect labels. '
                        'Pipeline FPS includes decoding, capture, inference, mapping, draining and exports; model loading excluded.')
        write(output / 'pipeline.json', summary)
        print('PIPELINE RESULT', json.dumps(summary), flush=True)
        return summary
    except BaseException as failure:
        write(output / 'failure.json', dict(type=type(failure).__name__, reason=str(failure),
                                           elapsed_seconds=time.perf_counter() - started, job_id=job.name))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', action='store_true')
    parser.add_argument('--geometry', type=int, default=0)
    parser.add_argument('--pipeline', action='store_true')
    parser.add_argument('--frames', type=int)
    parser.add_argument('--profile', choices=['realtime', 'reference'], default='realtime')
    args = parser.parse_args()
    inputs = ROOT / 'diagnostics/mapping80/20261006_final'
    manifest = json.loads((inputs / 'inputs.json').read_text())
    video = Path(manifest['video'])
    if sha(video) != manifest['video_sha256']:
        raise ValueError('Source video differs from frozen evidence')
    label = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid4().hex[:6]
    output = ROOT / 'diagnostics/realtime/20261009_implementation' / label
    output.mkdir()
    from validation_resources import memory_headroom
    request = dict(video=str(video), source_sha256=sha(video), options=vars(args),
                   memory=memory_headroom(), input_size=[640, 640],
                   platform=platform.platform(), python=platform.python_version(),
                   opencv=cv2.__version__, sources={}, checkpoints={})
    for name in ('algorithm.py', 'main.py', 'dfine_segmenter.py', 'fast_rotation.py',
                 'surface_atlas.py', 'realtime_pipeline.py', 'inference_scheduler.py', 'benchmark_realtime.py'):
        payload = (ROOT / name).read_bytes()
        (output / f'{name}.snapshot').write_bytes(payload)
        request['sources'][name] = hashlib.sha256(payload).hexdigest()
    for path in (ROOT / 'models/D-FINE/detection/best_stg1.pth',
                 ROOT / 'models/D-FINE/segmentation/model.pt'):
        request['checkpoints'][str(path.relative_to(ROOT))] = sha(path)
    import torch
    request['torch'] = torch.__version__
    request['cuda'] = torch.version.cuda
    request['gpu'] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    write(output / 'request.json', request)
    print('Evidence', output, flush=True)
    if args.models: model_comparison(video, manifest, inputs, output)
    if args.geometry: geometry_comparison(manifest, inputs, output, args.geometry)
    if args.pipeline: replay(video, output, args.frames, args.profile)


if __name__ == '__main__':
    main()
