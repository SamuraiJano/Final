"""Export current tracker predictions, with cached or fresh D-FINE detections.

Exports original zero-based frames and actual boxes. Neither mode annotates
physical identity, performs mapping, or runs defect segmentation.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import inspect
import json
import math
import os
from pathlib import Path
import re
from time import perf_counter
import cv2
import numpy as np


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_cached_detections(cache_path, video_hash, frames):
    """Require video provenance and every requested original frame index."""
    cache_path = Path(cache_path)
    try:
        provenance = json.loads((cache_path.parent/'report.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError('Cached detections require their original parent report.json') from error
    if not isinstance(provenance, dict) or provenance.get('input_sha256', {}).get('video') != video_hash:
        raise ValueError('Cache provenance does not match the supplied video SHA-256')
    with np.load(cache_path, allow_pickle=False) as cached:
        by_frame = {}
        for key in cached.files:
            match = re.fullmatch(r'frame_(\d+)', key)
            if match is None or int(match.group(1)) in by_frame:
                raise ValueError(f'Invalid or duplicate cached frame key: {key}')
            by_frame[int(match.group(1))] = key
        missing = sorted(set(range(frames))-by_frame.keys())
        if missing:
            raise ValueError(f'Cached detections lack original frames {missing[:10]}')
        rows = []
        for frame in range(frames):
            array = np.asarray(cached[by_frame[frame]])
            if array.ndim != 2 or array.shape[1] != 6 or not np.issubdtype(array.dtype, np.number):
                raise ValueError(f'Cached frame {frame} requires Nx6 detector rows')
            if not np.isfinite(array).all() or np.any(array[:, 2:4] <= array[:, :2]):
                raise ValueError(f'Cached frame {frame} has invalid boxes')
            if np.any((array[:, 4] < 0) | (array[:, 4] > 1)):
                raise ValueError(f'Cached frame {frame} has invalid confidence')
            if np.any(array[:, 5] < 0) or np.any(array[:, 5] != np.floor(array[:, 5])):
                raise ValueError(f'Cached frame {frame} has invalid classes')
            rows.append(array.astype(np.float32, copy=True))
    return rows, provenance


def export_predictions(video, output, frames=181, detections_cache=None, device=None, weights=None,
                       debug_overlay=False, debug_csv=False):
    from dfine_segmenter import DfineDetector, associate_fruit_detections, inference_device, make_fruit_tracker
    from fruit_identity import FruitIdentityGuard
    from conveyor_identity import ConveyorIdentityManager, ConveyorIdentitySettings
    video, output = Path(video).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f'Use a new output directory: {output}')
    if isinstance(frames, bool) or not isinstance(frames, int) or frames < 1:
        raise ValueError('frames must be a positive integer')
    backend = Path(__file__).resolve().parent
    # Keep library settings in the writable workspace instead of AppData.
    settings_directory = backend/'runtime/ultralytics'
    settings_directory.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('YOLO_CONFIG_DIR', str(settings_directory))
    video_hash = sha256_file(video)
    cached_rows, provenance = None, None
    if detections_cache is not None:
        detections_cache = Path(detections_cache).resolve()
        cached_rows, provenance = load_cached_detections(detections_cache, video_hash, frames)
    chosen_device = device or ('cpu' if cached_rows is not None else inference_device())
    if chosen_device not in ('cpu', 'cuda'):
        raise ValueError('device must be cpu or cuda')
    detector = None
    if cached_rows is None:
        weights = Path(weights or backend/'models/D-FINE/detection/best_stg1.pth').resolve()
        detector = DfineDetector(weights, chosen_device)
        tracker = detector.tracker
    else:
        tracker = make_fruit_tracker(chosen_device)
    tracker.reset()
    identity_settings = ConveyorIdentitySettings.from_environment()
    if debug_overlay or debug_csv:
        identity_settings = replace(identity_settings,
            debug_identity_overlay=debug_overlay or identity_settings.debug_identity_overlay,
            debug_identity_csv=debug_csv or identity_settings.debug_identity_csv)
    guard = (ConveyorIdentityManager(identity_settings, tracker.max_time_lost)
             if identity_settings.conveyor_identity_validation else FruitIdentityGuard())
    typical_size = None
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f'Cannot open video: {video}')
    raw_sequence, capture_sequence, decision_sequence = [], [], []
    tracker_source = Path(inspect.getfile(type(tracker)))
    source_payloads = {name: (backend/name).read_bytes() for name in
                     ('dfine_segmenter.py', 'fruit_identity.py', 'conveyor_identity.py', 'export_tracking_test_predictions.py')}
    source_payloads['installed_TRACKTRACK.py'] = tracker_source.read_bytes()
    source_hashes = {name: hashlib.sha256(payload).hexdigest() for name, payload in source_payloads.items()}
    started = perf_counter()
    try:
        width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if width <= 0 or height <= 0 or not math.isfinite(fps) or fps <= 0:
            raise ValueError('Invalid video dimensions or FPS')
        if isinstance(guard, ConveyorIdentityManager):
            guard.set_frame_rate(fps)
            if identity_settings.debug_identity_csv or identity_settings.debug_identity_overlay:
                output.mkdir(parents=True)
                guard.configure_debug(output)
        for frame_index in range(frames):
            ok, image = capture.read()
            if not ok:
                raise ValueError(f'Video ends before original frame {frame_index}')
            if image.shape[:2] != (height, width):
                raise ValueError('Video dimensions change')
            if cached_rows is not None:
                tracked, typical_size = associate_fruit_detections(tracker, cached_rows[frame_index], image, typical_size)
            else:
                boxes = detector.track(image, conf=.25)[0].boxes.data
                tracked = boxes.detach().cpu().numpy() if hasattr(boxes, 'detach') else np.asarray(boxes)
            tracked = np.asarray(tracked, dtype=float).reshape(-1, 7)
            raw_sequence.append({'frame': frame_index, 'tracks': tracked.tolist()})
            if isinstance(guard, ConveyorIdentityManager):
                timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.
                decisions = guard.update(tracked[:, :4], tracked[:, 4].astype(int), frame_index, image.shape[:2], timestamp)
                guard.write_debug(image)
            else:
                decisions = guard.update(tracked[:, :4], tracked[:, 4].astype(int), frame_index, image.shape[:2])
            guarded = tracked.copy()
            for index, decision in enumerate(decisions):
                guarded[index, 4] = decision['capture_id']
            capture_sequence.append({'frame': frame_index, 'tracks': guarded.tolist()})
            decision_sequence.append({'frame': frame_index, 'decisions': decisions})
            if frame_index % 30 == 0 or frame_index == frames-1:
                print(f'Current tracker: original frame {frame_index+1}/{frames}', flush=True)
    finally:
        capture.release()
        if isinstance(guard, ConveyorIdentityManager):
            guard.close_debug()
    elapsed = perf_counter()-started
    output.mkdir(parents=True, exist_ok=True)
    (output/'source').mkdir()
    for name, payload in source_payloads.items():
        (output/'source'/name).write_bytes(payload)
    payloads = {'tracking.json': raw_sequence, 'capture_tracking.json': capture_sequence,
                'guard_decisions.json': decision_sequence, 'guard_metadata.json': guard.metadata}
    for name, payload in payloads.items():
        (output/name).write_text(json.dumps(payload, indent=2), encoding='utf-8')
    report = {
        'schema_version': 1, 'recorded_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'cached_detector_replay' if cached_rows is not None else 'fresh_detector_and_tracker',
        'video': str(video), 'frames_tested': frames, 'source_start_frame': 0, 'source_end_frame': frames-1,
        'source_frame_index_base': 0, 'width': width, 'height': height, 'fps': fps, 'device': chosen_device,
        'input_sha256': {'video': video_hash}, 'source_sha256': source_hashes,
        'installed_tracker_source': str(tracker_source.resolve()),
        'software_versions': {'ultralytics': version('ultralytics'), 'opencv': cv2.__version__, 'numpy': np.__version__},
        'tracker_configuration': vars(tracker.args), 'identity_guard_configuration': guard.configuration(),
        'detection_threshold': .25, 'actual_detector_inference_calls': 0 if detector is None else detector.inference_calls,
        'defect_inference_calls': 0, 'mapping_executed': False,
        'tracking_observations': sum(len(frame['tracks']) for frame in raw_sequence),
        'raw_tracker_ids': len({int(row[4]) for frame in raw_sequence for row in frame['tracks']}),
        'capture_ids': len({int(row[4]) for frame in capture_sequence for row in frame['tracks']}),
        'elapsed_tracking_seconds': elapsed, 'outputs_sha256': {name: sha256_file(output/name) for name in payloads},
        'raw_predictions': 'tracking.json', 'guard_capture_predictions': 'capture_tracking.json',
        'limitations': 'Software predictions, not physical identity truth. Guard captures intentionally split at gaps. No mapping or grade claimed.',
    }
    if detections_cache is not None:
        report.update(detections_cache=str(detections_cache), detections_cache_sha256=sha256_file(detections_cache),
                      cached_detector_provenance=provenance,
                      detector_input='Frozen detections; current detector not rerun.')
        recorded_model_hash = provenance.get('input_sha256', {}).get('detection_model')
        if recorded_model_hash:
            report['input_sha256']['detection_model'] = recorded_model_hash
    else:
        report.update(detection_model=str(weights), detector_input='Fresh D-FINE detector inference.')
        report['input_sha256']['detection_model'] = sha256_file(weights)
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=181)
    parser.add_argument('--detections-cache', type=Path)
    parser.add_argument('--device', choices=('cpu', 'cuda'))
    parser.add_argument('--weights', type=Path, help='Fresh detector mode only')
    parser.add_argument('--debug-overlay', action='store_true', help='Save T/F labels, trajectories and predictions to identity_debug.mp4')
    parser.add_argument('--debug-csv', action='store_true', help='Save per-observation identity_debug.csv')
    args = parser.parse_args()
    if args.detections_cache is not None and args.weights is not None:
        parser.error('--weights applies only to fresh detector inference')
    try:
        report = export_predictions(args.video, args.output_dir, args.frames, args.detections_cache, args.device, args.weights,
                                    args.debug_overlay, args.debug_csv)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({key: report[key] for key in ('mode', 'frames_tested', 'actual_detector_inference_calls',
                                                  'tracking_observations', 'raw_tracker_ids', 'capture_ids')}, indent=2))


if __name__ == '__main__':
    main()
