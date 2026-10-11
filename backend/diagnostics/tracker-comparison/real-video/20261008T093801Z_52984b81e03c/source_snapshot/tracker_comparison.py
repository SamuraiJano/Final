"""Separate six-tracker experiment using installed Ultralytics APIs and local checkpoints.

Run without arguments for file selection, or --video PATH [--model PATH].
No production pipeline, identity correction, segmentation, or grading is imported.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
import uuid

import cv2
import numpy as np

from tracker_comparison_metrics import (DiagnosticSettings, EVENT_FIELDS, FRAME_FIELDS,
                                        OBSERVATION_FIELDS, RawTrackStatistics, TRACK_FIELDS)

ROOT = Path(__file__).resolve().parent
TRACKERS = dict(bytetrack='ByteTrack', botsort='BoT-SORT', ocsort='OC-SORT',
                deepocsort='Deep OC-SORT', fasttrack='FastTracker', tracktrack='TrackTrack')
SUMMARY_FIELDS = ('tracker_name', 'mode', 'timing_scope', 'processed_frames', 'processing_fps',
                  'average_time_ms', 'total_processing_seconds', 'unique_raw_ids',
                  'maximum_active_ids', 'mean_active_ids', 'final_active_ids',
                  'mean_lifetime_seconds', 'median_lifetime_seconds', 'minimum_lifetime_seconds',
                  'maximum_lifetime_seconds', 'mean_consistency_percent', 'median_consistency_percent',
                  'substantial_persistence_ids', 'substantial_persistence_percent', 'suspected_id_fragmentations',
                  'short_lived_under_0.25s_count', 'short_lived_under_0.25s_percent',
                  'short_lived_under_0.5s_count', 'short_lived_under_0.5s_percent',
                  'short_lived_under_1s_count', 'short_lived_under_1s_percent')


def configure_ultralytics():
    # Keep package settings out of working directories and do not override user configuration.
    directory = Path(os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT/'runtime'/'tracker-comparison')))
    (directory/'Ultralytics').mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def create_run_directory(parent: Path):
    parent.mkdir(parents=True, exist_ok=True)
    path = parent/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:12])
    path.mkdir(exist_ok=False)
    return path


def installed_trackers(device: str):
    configure_ultralytics()
    import ultralytics
    from ultralytics.trackers.track import TRACKER_MAP
    from ultralytics.utils import YAML

    root = Path(ultralytics.__file__).parent/'cfg'/'trackers'
    configurations = {}
    for key in TRACKERS:
        matches = [path for path in sorted(root.glob('*.yaml')) if YAML.load(path).get('tracker_type') == key]
        if key not in TRACKER_MAP or len(matches) != 1:
            raise RuntimeError(f'Installed Ultralytics {ultralytics.__version__} does not provide {key} unambiguously')
        path = matches[0]
        args = YAML.load(path)
        if args.get('with_reid', False):
            raise RuntimeError(f'{path.name} enables ReID; this raw-box experiment requires installed default ReID-off configs')
        implementation_path = Path(sys.modules[TRACKER_MAP[key].__module__].__file__)
        configurations[key] = dict(filename=path.name, path=str(path), sha256=sha256_file(path),
                                   contents=path.read_text(encoding='utf-8'), arguments=args,
                                   runtime_arguments=dict(device=device),
                                   implementation_path=str(implementation_path),
                                   implementation_sha256=sha256_file(implementation_path),
                                   implementation=TRACKER_MAP[key].__module__+'.'+TRACKER_MAP[key].__name__)
    return configurations


def fresh_tracker(key, configurations, device):
    from ultralytics.trackers.track import TRACKER_MAP
    from ultralytics.utils import IterableSimpleNamespace

    args = dict(configurations[key]['arguments'], device=device)
    tracker = TRACKER_MAP[key](args=IterableSimpleNamespace(**args))
    tracker.reset()
    if tracker.frame_id != 0:
        raise RuntimeError(f'{key} did not reset to frame zero')
    return tracker


class Detector:
    """Reuse the application's local D-FINE loader and preprocessing, without its tracker wrapper."""

    def __init__(self, checkpoint: Path, device: str, confidence: float, iou: float, image_size: int):
        import torch

        self.device, self.confidence, self.iou, self.image_size = device, confidence, iou, image_size
        self.checkpoint = checkpoint
        if device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA is unavailable. Use --device cpu explicitly or install CUDA-enabled PyTorch.')
        if checkpoint.suffix.lower() == '.pth':
            loader = ROOT.parents[1]/'Inference Runner'/'backend'/'python'
            if not (loader/'dfine_checkpoint.py').is_file():
                raise FileNotFoundError(f'Application D-FINE loader is missing: {loader / "dfine_checkpoint.py"}')
            sys.path.insert(0, str(loader))
            from dfine_checkpoint import load_dfine_nano
            self.processor, self.model, labels = load_dfine_nano(checkpoint, device)
            self.processor.size = dict(height=image_size, width=image_size)
            self.names = dict(enumerate(labels))
            self.kind = 'D-FINE (application checkpoint loader)'
            self.preprocessing = 'RTDetrImageProcessor: BGR→RGB, square resize, processor normalization, float32'
            self.loader_metadata = dict(path=str(loader/'dfine_checkpoint.py'),
                                        sha256=sha256_file(loader/'dfine_checkpoint.py'))
        elif checkpoint.suffix.lower() == '.pt':
            from ultralytics import YOLO
            self.model = YOLO(str(checkpoint), task='detect')
            if self.model.task != 'detect':
                raise ValueError('Select an object-detection checkpoint, not segmentation or classification weights')
            self.names = self.model.names
            self.kind = 'Ultralytics YOLO (explicitly selected local checkpoint)'
            self.preprocessing = 'Ultralytics predict, rect=False, square letterbox, float32, half=False'
            self.loader_metadata = None
        else:
            raise ValueError('Detector checkpoint must be the application .pth or a local Ultralytics detection .pt')

    def predict(self, frame):
        if self.checkpoint.suffix.lower() == '.pt':
            result = self.model.predict(frame, conf=self.confidence, iou=self.iou, imgsz=self.image_size,
                                        device=self.device, verbose=False, rect=False, half=False)[0]
            return np.asarray(result.boxes.data.cpu().numpy(), dtype=np.float32).reshape(-1, 6)
        import torch
        from PIL import Image
        from dfine_segmenter import suppress_duplicate_detections

        height, width = frame.shape[:2]
        inputs = self.processor(images=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), return_tensors='pt')
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            outputs = self.model(**inputs)
            detections = self.processor.post_process_object_detection(outputs, threshold=self.confidence,
                                                                       target_sizes=[(height, width)])[0]
        rows = np.column_stack((detections['boxes'].cpu().numpy(), detections['scores'].cpu().numpy(),
                                detections['labels'].cpu().numpy())).astype(np.float32)
        return suppress_duplicate_detections(rows, iou_threshold=self.iou)

    def synchronize(self):
        if self.device == 'cuda':
            import torch
            torch.cuda.synchronize()


def timed_call(operation, synchronize, clock=None):
    clock = clock or perf_counter
    synchronize()
    start = clock()
    result = operation()
    synchronize()
    elapsed = clock()-start
    if elapsed <= 0:
        raise RuntimeError('Nonpositive processing duration')
    return result, elapsed


def update_tracker(tracker, detections, frame):
    from ultralytics.engine.results import Boxes
    # Private copies protect the canonical cache from tracker mutation.
    return tracker.update(Boxes(np.array(detections, dtype=np.float32, copy=True), frame.shape[:2]), frame)


class VideoFrames:
    def __init__(self, path: Path):
        self.capture = cv2.VideoCapture(str(path))
        if not self.capture.isOpened():
            self.capture.release()
            raise ValueError(f'Cannot open video: {path}')
        self.fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        if not np.isfinite(self.fps) or self.fps <= 0:
            self.capture.release()
            raise ValueError('Video has no positive source FPS; cannot assign source-timeline timestamps')
        self.metadata = dict(path=str(path), filename=path.name, source_fps=self.fps,
                             width=int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                             height=int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                             declared_frame_count=int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.timestamp_fallback_frames = 0

    def __iter__(self):
        index, previous = 0, -1.
        while True:
            ok, frame = self.capture.read()
            if not ok:
                break
            timestamp = float(self.capture.get(cv2.CAP_PROP_POS_MSEC))/1000
            if not np.isfinite(timestamp) or timestamp < 0 or (index and timestamp <= previous):
                timestamp = index/self.fps
                self.timestamp_fallback_frames += 1
            if timestamp < previous:
                raise ValueError('Video timestamps are inconsistent with the source FPS fallback')
            yield index, timestamp, frame
            index, previous = index+1, timestamp

    def close(self):
        self.capture.release()


def frame_hash(frame):
    return hashlib.sha256(frame.tobytes()).hexdigest()


def warm_detector(detector, video, count):
    reader = VideoFrames(video)
    actual = 0
    try:
        for _, _, frame in reader:
            if actual >= count:
                break
            detector.predict(frame)
            detector.synchronize()
            actual += 1
    finally:
        reader.close()
    return actual


def build_inputs(video, detector, cache_detections, folder):
    """Decode canonical input once; detection caching and file writes are separately timed."""
    reader = VideoFrames(video)
    rows, offsets, timestamps, hashes, detector_seconds = [], [0], [], [], []
    try:
        for index, timestamp, frame in reader:
            timestamps.append(timestamp)
            hashes.append(frame_hash(frame))
            if cache_detections:
                detections, elapsed = timed_call(lambda: detector.predict(frame), detector.synchronize)
                validate_detections(detections)
                rows.append(detections)
                offsets.append(offsets[-1]+len(detections))
                detector_seconds.append(elapsed)
            if (index+1) % 100 == 0:
                print(f'Common input: {index+1} frames', flush=True)
    finally:
        reader.close()
    count = len(timestamps)
    if not count:
        raise ValueError('Video contains no decodable frames')
    declared = reader.metadata['declared_frame_count']
    if declared > 0 and declared != count:
        raise ValueError(f'Incomplete video decode: container declares {declared} frames, decoded {count}')
    metadata = dict(reader.metadata, frame_count=count, duration_seconds=count/reader.fps,
                    observation_span_seconds=timestamps[-1]-timestamps[0],
                    timestamp_method='OpenCV source POS_MSEC; source frame/FPS fallback when missing or non-increasing',
                    timestamp_fallback_frames=reader.timestamp_fallback_frames)
    inputs = dict(timestamps=np.array(timestamps), frame_hashes=hashes, rows=None, offsets=None,
                  detector_seconds=detector_seconds)
    if cache_detections:
        inputs['rows'] = np.concatenate(rows).astype(np.float32)
        inputs['rows'].flags.writeable = False
        inputs['offsets'] = np.asarray(offsets, dtype=np.int64)
        np.savez(folder/'detections.npz', rows=inputs['rows'], offsets=inputs['offsets'],
                 timestamps=inputs['timestamps'], frame_hashes=np.array(hashes),
                 detector_seconds=np.array(detector_seconds))
    write_json(folder/'input_manifest.json', dict(video=metadata, frame_hashes=hashes,
                                                  timestamps=timestamps, detection_cache=cache_detections))
    return inputs, metadata


def validate_detections(rows):
    if rows.ndim != 2 or rows.shape[1] != 6 or not np.isfinite(rows).all():
        raise ValueError('Detector must return finite xyxy,confidence,class rows')
    if np.any(rows[:, 2:4] <= rows[:, :2]):
        raise ValueError('Detector returned a box with nonpositive dimensions')


def cached_rows(inputs, index):
    return inputs['rows'][inputs['offsets'][index]:inputs['offsets'][index+1]]


def verify_frame(inputs, index, timestamp, frame):
    if index >= len(inputs['timestamps']):
        raise ValueError('Tracker run decoded more frames than the common input')
    if frame_hash(frame) != inputs['frame_hashes'][index] or abs(timestamp-inputs['timestamps'][index]) > 1e-6:
        raise ValueError(f'Video changed or decoded differently at frame {index}')


def annotate(frame, rows, name, index, seconds):
    image = frame.copy()
    for row in rows:
        x1, y1, x2, y2 = [int(x) for x in row[:4]]
        cv2.rectangle(image, (x1, y1), (x2, y2), (60, 220, 100), 2)
        cv2.putText(image, f'ID {int(row[4])}', (x1, max(20, y1-6)),
                    cv2.FONT_HERSHEY_SIMPLEX, .65, (60, 220, 100), 2)
    cv2.rectangle(image, (0, 0), (min(image.shape[1], 900), 65), (20, 30, 20), -1)
    cv2.putText(image, f'{name} | Frame: {index} | Processing FPS: {1/seconds:.1f}', (12, 40),
                cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
    return image


def run_tracker(key, mode, configurations, video, detector, inputs, video_meta,
                folder, diagnostics, warmup_frames, annotated):
    folder.mkdir(exist_ok=False)
    write_json(folder/'tracker_config.json', configurations[key])
    (folder/configurations[key]['filename']).write_text(configurations[key]['contents'], encoding='utf-8')
    # Warm-up tracker is discarded. It cannot consume IDs or temporal state in the measured run.
    warm = fresh_tracker(key, configurations, detector.device)
    reader = VideoFrames(video)
    warm_count = 0
    try:
        for index, timestamp, frame in reader:
            if index >= warmup_frames:
                break
            verify_frame(inputs, index, timestamp, frame)
            rows = cached_rows(inputs, index) if mode == 'cached' else detector.predict(frame)
            update_tracker(warm, rows, frame)
            detector.synchronize()
            warm_count += 1
    finally:
        reader.close()
    del warm
    tracker = fresh_tracker(key, configurations, detector.device)
    statistics = RawTrackStatistics(TRACKERS[key], mode, diagnostics)
    reader = VideoFrames(video)
    writer = None
    if annotated:
        writer = cv2.VideoWriter(str(folder/'annotated.mp4'), cv2.VideoWriter_fourcc(*'mp4v'),
                                 video_meta['source_fps'], (video_meta['width'], video_meta['height']))
        if not writer.isOpened():
            reader.close()
            writer.release()
            raise RuntimeError('Cannot create annotated MP4 with the installed OpenCV encoder')
    digest = hashlib.sha256()
    detection_matches_cache = True if inputs['rows'] is not None else None
    try:
        with (folder/'observations.csv').open('w', encoding='utf-8', newline='') as file:
            observation_writer = csv.DictWriter(file, fieldnames=OBSERVATION_FIELDS)
            observation_writer.writeheader()
            for index, timestamp, frame in reader:
                verify_frame(inputs, index, timestamp, frame)
                detections = cached_rows(inputs, index) if mode == 'cached' else None

                def operation():
                    nonlocal detections
                    if mode == 'full':
                        detections = detector.predict(frame)
                    return update_tracker(tracker, detections, frame)

                tracks, elapsed = timed_call(operation, detector.synchronize)
                validate_detections(detections)
                digest.update(np.asarray([index], dtype=np.int64).tobytes())
                digest.update(np.asarray(detections, dtype=np.float32).tobytes())
                if mode == 'full' and inputs['rows'] is not None:
                    detection_matches_cache &= np.array_equal(detections, cached_rows(inputs, index))
                statistics.observe(index, timestamp, tracks, elapsed)
                for row in tracks:
                    observation_writer.writerow(dict(frame=index, timestamp=timestamp, track_id=int(row[4]),
                                                       **dict(zip(OBSERVATION_FIELDS[3:], map(float, row[[0,1,2,3,5,6]])))))
                if writer:
                    writer.write(annotate(frame, tracks, TRACKERS[key]+' / '+mode, index, elapsed))
                if (index+1) % 100 == 0:
                    print(f'{TRACKERS[key]} / {mode}: {index+1}/{video_meta["frame_count"]} frames', flush=True)
    finally:
        reader.close()
        if writer:
            writer.release()
    if len(statistics.frames) != video_meta['frame_count']:
        raise ValueError(f'{key} / {mode} did not process the complete common video')
    summary, tracks = statistics.finish()
    summary.update(tracker_key=key, warmup_frames_excluded=warm_count, fresh_state_verified=True,
                   detection_sequence_sha256=digest.hexdigest(), detection_matches_cache=detection_matches_cache,
                   identical_video_frames_verified=True, config_sha256=configurations[key]['sha256'],
                   result_folder=str(folder))
    write_json(folder/'summary.json', summary)
    write_csv(folder/'tracks.csv', TRACK_FIELDS, tracks)
    write_csv(folder/'events.csv', EVENT_FIELDS, statistics.events)
    write_csv(folder/'frames.csv', FRAME_FIELDS, statistics.frames)
    return dict(summary=summary, tracks=tracks)


def environment_metadata(device):
    import torch
    import ultralytics
    import psutil
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    try:
        gpu_snapshot = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.used,utilization.gpu',
                                                '--format=csv,noheader'], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        gpu_snapshot = None
    return dict(date_time_utc=datetime.now(timezone.utc).isoformat(), git_commit=commit, git_worktree_dirty=dirty,
                python=sys.version, platform=platform.platform(), cpu=platform.processor(),
                logical_cpu_count=psutil.cpu_count(), ram_bytes=psutil.virtual_memory().total,
                ultralytics_version=ultralytics.__version__, pytorch_version=torch.__version__,
                cuda_version=torch.version.cuda, gpu=gpu, selected_device=device,
                hardware=gpu if device == 'cuda' else platform.processor(),
                torch_threads=torch.get_num_threads(), opencv_threads=cv2.getNumThreads(),
                gpu_snapshot_at_start=gpu_snapshot)


def compare(args, detector_factory=Detector):
    video, checkpoint = Path(args.video).resolve(), Path(args.model).resolve()
    for label, path in (('Video', video), ('Detector checkpoint', checkpoint)):
        if not path.is_file():
            raise FileNotFoundError(f'{label} does not exist: {path}')
    keys = list(TRACKERS) if args.trackers == ['all'] else args.trackers
    if not keys or len(set(keys)) != len(keys) or any(key not in TRACKERS for key in keys):
        raise ValueError('Choose all or a list of distinct supported tracker keys')
    if not 0 <= args.conf <= 1 or not 0 <= args.iou <= 1 or args.imgsz <= 0 or args.warmup < 0:
        raise ValueError('Invalid confidence, IoU, image size, or warm-up count')
    diagnostics = DiagnosticSettings(fragmentation_window_seconds=args.fragment_window_seconds,
                                     fragmentation_distance_box_diagonals=args.fragment_distance,
                                     substantial_lifetime_seconds=args.substantial_seconds)
    configurations = installed_trackers(args.device)
    folder = create_run_directory(Path(args.output).resolve())
    write_json(folder/'status.json', dict(status='running', started_utc=datetime.now(timezone.utc).isoformat()))
    try:
        metadata = environment_metadata(args.device)
        metadata.update(source_video_sha256=sha256_file(video), detector_checkpoint=str(checkpoint),
                        detector_checkpoint_sha256=sha256_file(checkpoint), confidence=args.conf, nms_iou=args.iou,
                        image_size=[args.imgsz, args.imgsz], selected_trackers=keys, requested_mode=args.mode,
                        tracker_configurations={key: configurations[key] for key in keys},
                        experiment_source_sha256={name: sha256_file(ROOT/name) for name in
                            ('tracker_comparison.py', 'tracker_comparison_metrics.py', 'tracker_comparison_report.py', 'dfine_segmenter.py')},
                        methodology_source='https://docs.ultralytics.com/modes/track/',
                        methodology_video='https://www.youtube.com/watch?v=ZsxHIN2PoiY',
                        diagnostic_settings=diagnostics.__dict__,
                        timing_methodology=dict(clock='time.perf_counter', cuda_synchronization=args.device == 'cuda',
                            full_includes='detector preprocessing, inference, postprocessing/NMS, CPU box transfer and tracker update',
                            cached_includes='cached box adapter and tracker update (including configured GMC)',
                            excludes='model loading, warm-up, video decode, input verification, cache I/O, diagnostics, overlays, encoding, CSV/JSON/HTML writing',
                            processing_fps='processed_frames / total_processing_seconds',
                            average_time_ms='1000 * total_processing_seconds / processed_frames',
                            warmup_policy='Initial detector warm-up and disposable per-run tracker warm-up excluded; every measured run restarts at frame 0 and includes the complete video'),
                        experiment_scope='Raw installed trackers, stock YAMLs plus device; no production edge-box association, identity correction, segmentation, view selection or grading',
                        identity_metric_scope='Observed raw IDs; no ground-truth physical identities; substantial persistence is an application diagnostic within the observed interval')
        write_json(folder/'run_metadata.json', metadata)
        detector = detector_factory(checkpoint, args.device, args.conf, args.iou, args.imgsz)
        metadata.update(detector_kind=detector.kind, preprocessing=detector.preprocessing,
                        detector_names=detector.names, checkpoint_loader=detector.loader_metadata,
                        detector_warmup_frames_excluded=warm_detector(detector, video, args.warmup))
        inputs, video_meta = build_inputs(video, detector, args.mode != 'full', folder)
        metadata['video'] = video_meta
        if inputs['detector_seconds']:
            total = sum(inputs['detector_seconds'])
            metadata['common_detection_pass'] = dict(processed_frames=video_meta['frame_count'],
                total_seconds=total, average_time_ms=1000*total/video_meta['frame_count'],
                processing_fps=video_meta['frame_count']/total,
                scope='detector_only; not combined with replay FPS or called full-pipeline throughput',
                cache_filename='detections.npz', cache_sha256=sha256_file(folder/'detections.npz'))
        write_json(folder/'run_metadata.json', metadata)
        modes = ['full', 'cached'] if args.mode == 'both' else [args.mode]
        results = []
        for mode in modes:
            for key in keys:
                target = folder/key if len(modes) == 1 else folder/key/mode
                target.parent.mkdir(parents=True, exist_ok=True)
                results.append(run_tracker(key, mode, configurations, video, detector, inputs, video_meta,
                                           target, diagnostics, args.warmup, args.annotated))
                write_json(folder/'comparison_summary.json', dict(metadata=metadata,
                                                                  results=[r['summary'] for r in results], complete=False))
        if sha256_file(video) != metadata['source_video_sha256'] or sha256_file(checkpoint) != metadata['detector_checkpoint_sha256']:
            raise ValueError('Video or checkpoint changed during the experiment')
        cached_digests = {r['summary']['detection_sequence_sha256'] for r in results if r['summary']['mode'] == 'cached'}
        if len(cached_digests) > 1:
            raise RuntimeError('Cached trackers did not receive identical detections')
        metadata['completed_utc'] = datetime.now(timezone.utc).isoformat()
        metadata['cached_detection_sequences_identical'] = len(cached_digests) == 1 if 'cached' in modes else None
        write_json(folder/'run_metadata.json', metadata)
        write_csv(folder/'comparison_summary.csv', SUMMARY_FIELDS, [r['summary'] for r in results])
        write_json(folder/'comparison_summary.json', dict(metadata=metadata, results=[r['summary'] for r in results], complete=True))
        from tracker_comparison_report import generate_report
        generate_report(folder/'report.html', metadata, results)
        write_json(folder/'status.json', dict(status='complete', completed_utc=metadata['completed_utc']))
        print(f'Comparison complete: {folder / "report.html"}', flush=True)
        return folder
    except BaseException as error:
        write_json(folder/'status.json', dict(status='failed', error_type=type(error).__name__, error=str(error)))
        print(f'Comparison failed. Diagnostic results retained at {folder}', file=sys.stderr, flush=True)
        raise


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--video', help='Conveyor video; omitted opens a file picker')
    cli.add_argument('--model', default=os.getenv('FRUIT_DETECTOR_WEIGHTS', str(ROOT/'models'/'D-FINE'/'detection'/'best_stg1.pth')),
                     help='Local detector checkpoint; defaults to the final detector selected by the application')
    cli.add_argument('--select', action='store_true', help='Select both video and detector using file dialogs')
    cli.add_argument('--trackers', nargs='+', default=['all'], choices=['all', *TRACKERS])
    cli.add_argument('--mode', default='both', choices=['both', 'full', 'cached'])
    cli.add_argument('--device', default=os.getenv('FRUIT_DEVICE', 'cuda'), choices=['cuda', 'cpu'])
    cli.add_argument('--conf', type=float, default=.25)
    cli.add_argument('--iou', type=float, default=.7)
    cli.add_argument('--imgsz', type=int, default=640)
    cli.add_argument('--warmup', type=int, default=3, help='Excluded warm-up frames; measured runs still include every video frame')
    cli.add_argument('--annotated', action='store_true', help='Save per-tracker MP4 boxes/raw-ID overlays outside processing timing')
    cli.add_argument('--output', default=str(ROOT/'results'/'tracker_comparison'))
    cli.add_argument('--fragment-window-seconds', type=float, default=.5, help='Application-defined suspected-fragmentation window')
    cli.add_argument('--fragment-distance', type=float, default=.5, help='Application-defined candidate distance in box diagonals')
    cli.add_argument('--substantial-seconds', type=float, default=1., help='Application-defined substantial persistence duration')
    return cli


def select_inputs(args):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    try:
        if args.select or not args.video:
            args.video = filedialog.askopenfilename(title='Select conveyor comparison video',
                filetypes=[('Videos', '*.mp4 *.avi *.mov *.mkv'), ('All files', '*.*')])
        if args.video and args.select:
            current = Path(args.model).resolve()
            args.model = filedialog.askopenfilename(title='Select trained naartjie detector',
                initialdir=str(current.parent), initialfile=current.name,
                filetypes=[('Detector checkpoints', '*.pth *.pt'), ('All files', '*.*')])
    finally:
        root.destroy()
    return bool(args.video and args.model)


def main():
    cli = parser()
    args = cli.parse_args()
    if not args.video:
        args.select = True
    if (args.select or not args.video) and not select_inputs(args):
        print('Comparison cancelled before processing.')
        return 0
    try:
        compare(args)
    except Exception as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
