"""Paced end-to-end one-camera replay; dropped frames/incomplete fruit stay counted.

Repeated recordings extend load duration, not independent accuracy evidence.
No frame-rate reduction, model-size change or fewer-than-nine grade is permitted.
"""
from collections import Counter, deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import argparse
import hashlib
import json
import os
import subprocess
import threading
import time
import platform

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'runtime' / 'ultralytics-validation'))
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import cv2
import numpy as np
import psutil
cv2.setNumThreads(1)


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')


def percentile(values, q):
    return float(np.percentile(values, q)) if values else None


class PacedCapture:
    def __init__(self, video, repeats=1, frames=None):
        self.video, self.repeats, self.limit = video, repeats, frames
        source = cv2.VideoCapture(str(video))
        self.fps, self.total = source.get(cv2.CAP_PROP_FPS), int(source.get(cv2.CAP_PROP_FRAME_COUNT))
        source.release()
        if not self.fps > 0:
            raise ValueError('Recording must have a known source frame rate')
        self.condition = threading.Condition()
        self.frames = deque(maxlen=4)
        self.stop_event = threading.Event()
        self.finished = False
        self.produced = 0
        self.origin = None
        self.thread = threading.Thread(target=self._run, daemon=True, name='paced-camera-replay')

    def _run(self):
        self.origin = time.monotonic()
        try:
            for _ in range(self.repeats):
                source = cv2.VideoCapture(str(self.video))
                try:
                    while not self.stop_event.is_set() and (self.limit is None or self.produced < self.limit):
                        ok, frame = source.read()
                        if not ok:
                            break
                        index = self.produced
                        timestamp = self.origin + index / self.fps
                        self.stop_event.wait(max(0., timestamp - time.monotonic()))
                        if self.stop_event.is_set(): break
                        with self.condition:
                            self.frames.append((index, frame, timestamp))
                            self.produced += 1
                            self.condition.notify_all()
                finally: source.release()
        finally:
            with self.condition:
                self.finished = True
                self.condition.notify_all()

    def next(self, after):
        with self.condition:
            self.condition.wait_for(lambda: self.finished or (self.frames and self.frames[-1][0] > after), timeout=1)
            return next((item for item in self.frames if item[0] > after), None)

    def close(self):
        self.stop_event.set(); self.thread.join()


class ResourceMonitor:
    def __init__(self):
        self.samples, self.event = [], threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.process = psutil.Process()

    def _run(self):
        self.process.cpu_percent()
        while not self.event.wait(1):
            row = dict(timestamp=time.monotonic(), rss_bytes=self.process.memory_info().rss,
                       process_cpu_percent=self.process.cpu_percent(), system_cpu_percent=psutil.cpu_percent())
            try:
                gpu = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,power.draw',
                    '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=2,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if gpu.returncode == 0:
                    values = [v.strip() for v in gpu.stdout.strip().split(',')]
                    row.update(gpu_utilization_percent=float(values[0]), gpu_memory_mb=float(values[1]), gpu_power_watts=float(values[2]))
            except (OSError, ValueError, subprocess.TimeoutExpired): pass
            for name, path in (('pi_temperature_c', '/sys/class/thermal/thermal_zone0/temp'),
                               ('pi_throttling', '/sys/devices/platform/soc/soc:firmware/get_throttled')):
                try:
                    value = Path(path).read_text().strip()
                    row[name] = float(value) / 1000 if name == 'pi_temperature_c' else value
                except (OSError, ValueError): pass
            if platform.machine().lower() in ('aarch64', 'armv7l'):
                try:
                    throttle = subprocess.run(['vcgencmd', 'get_throttled'], capture_output=True,
                                              text=True, timeout=1)
                    if throttle.returncode == 0:
                        row['pi_throttling'] = throttle.stdout.strip()
                except (OSError, subprocess.TimeoutExpired): pass
            self.samples.append(row)

    def close(self):
        self.event.set(); self.thread.join()


def labels_metrics(rows, path):
    if path is None:
        return dict(available=False, reason='No independently labelled fruit, identity or defect truth provided')
    labels = json.loads(path.read_text())
    matches = [(r, labels[r['fruit_uid']]) for r in rows if r.get('fruit_uid') in labels]
    graded = [(r, truth) for r, truth in matches if r.get('grade')]
    return dict(available=True, matched_fruit=len(matches), graded_labelled_fruit=len(graded),
        incomplete_labelled_fruit=sum(not r.get('evidence_complete', r.get('surface_map') is not None) for r, _ in matches),
        fruit_grade_accuracy=sum(r['grade'] == truth for r, truth in graded) / len(graded) if graded else None,
        severe_defect_misses=sum(truth == 'Class 3' and r.get('grade') in ('Class 1', 'Class 2') for r, truth in matches),
        severe_unassessed=sum(truth == 'Class 3' and not r.get('grade') for r, truth in matches),
        false_rejects=sum(truth == 'Class 1' and r.get('grade') in ('Class 2', 'Class 3') for r, truth in matches))


def run(args):
    os.environ['FRUIT_DEVICE'] = args.device
    os.environ['FRUIT_HARDWARE_PROFILE'] = args.hardware
    import main
    from inspection_config import InspectionConfiguration
    config = InspectionConfiguration()
    config.update(dict(algorithm='nine_view', nine_view=dict(region=tuple(args.region),
        decision_deadline_seconds=args.deadline, expected_dwell_seconds=args.dwell,
        expected_fruit_rate=args.fruit_rate)))
    # Isolated benchmark settings never overwrite the operator's saved mode.
    main.inspection_configuration = config
    label = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid4().hex[:6]
    output = ROOT / 'diagnostics/nine-view' / label
    output.mkdir(parents=True)
    job = main.RESULTS / uuid4().hex
    job.mkdir()
    request = dict(options={key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        input_size=[640, 640], platform=platform.platform(), initial_settings=asdict(config.snapshot()),
        region_calibration='CLI test region; not independently verified physical conveyor calibration',
        replay='source-paced, four-frame ring, original source frames; repeated clips labelled as load repetition', sources={})
    for name, payload in main.SOURCE_SNAPSHOTS.items():
        (output / f'{name}.snapshot').write_bytes(payload)
        request['sources'][name] = hashlib.sha256(payload).hexdigest()
    benchmark_source = Path(__file__).read_bytes()
    (output / 'benchmark_nine_view.py.snapshot').write_bytes(benchmark_source)
    request['sources']['benchmark_nine_view.py'] = hashlib.sha256(benchmark_source).hexdigest()
    import torch
    import transformers
    request['software'] = dict(python=platform.python_version(), torch=torch.__version__,
        transformers=transformers.__version__, opencv=cv2.__version__)
    request['device'] = dict(requested=args.device, cpu=platform.processor(),
        gpu=torch.cuda.get_device_name() if args.device == 'cuda' and torch.cuda.is_available() else None,
        pi_hardware_present=platform.machine().lower() in ('aarch64', 'armv7l') and Path('/proc/device-tree/model').exists())
    request['checkpoint_sha256'] = {}
    for name, path in [('detection', Path(os.getenv('FRUIT_DETECTOR_WEIGHTS', main.MODELS / 'detection/best_stg1.pth'))),
                       ('segmentation', Path(os.getenv('DFINE_SEG_WEIGHTS', main.MODELS / 'segmentation/model.pt')))]:
        with path.open('rb') as checkpoint:
            request['checkpoint_sha256'][name] = hashlib.file_digest(checkpoint, 'sha256').hexdigest()
    request['source_sha256'] = hashlib.sha256(args.video.read_bytes()).hexdigest()
    write(output / 'request.json', request)
    print('Evidence', output, flush=True)
    pipeline, detector, segmenter = main._make_pipeline(capture_stride_frames=1)
    pipeline.run_id = job.name
    pipeline.set_frame_rate(29.93)
    collector = main._begin_tracking(job)
    pipeline.tracking_metrics = collector
    writer = main.TrackWriter(job)
    capture = PacedCapture(args.video, args.repeats, args.frames)
    pipeline.set_frame_rate(capture.fps)
    monitor = ResourceMonitor()
    switches = []
    processed, dropped, sequence = 0, 0, -1
    next_switch, last_progress = args.switch_seconds, time.monotonic()
    monitor.thread.start(); capture.thread.start()
    started = time.monotonic()
    try:
        while True:
            item = capture.next(sequence)
            if item is None:
                if capture.finished: break
                continue
            index, frame, timestamp = item
            dropped += max(0, index - sequence - 1)
            sequence = index
            source_time = timestamp - capture.origin
            if args.switch_seconds and source_time >= next_switch:
                previous = config.snapshot().algorithm
                mode = 'surface_mapping' if previous == 'nine_view' else 'nine_view'
                config.update({'algorithm': mode})
                switches.append(dict(source_seconds=source_time, algorithm=mode, active=len(pipeline.routes)))
                next_switch += args.switch_seconds
            pipeline.process_frame(frame, index, timestamp=source_time, capture_monotonic=timestamp)
            main._update_tracking_preview(frame, collector)
            for track_id, last in list(pipeline.last_seen_frame.items()):
                if index - last > pipeline.identity_guard.lost_track_buffer_frames:
                    writer.finish(pipeline, track_id)
            for track_id in pipeline.ready_tracks(): writer.finish(pipeline, track_id)
            writer.collect()
            processed += 1
            if time.monotonic() - last_progress > 5:
                print('Processed', processed, 'source frames', capture.produced, 'dropped', dropped,
                      'fruit results', len(writer.results), 'queued crops', pipeline.nine.pending_depth(), flush=True)
                last_progress = time.monotonic()
        pipeline.flush()
        for track_id in list(pipeline.last_seen_frame): writer.finish(pipeline, track_id)
        writer.collect(wait=True)
        # Expired fruit may still have bounded model jobs finishing in the
        # scheduler. Include that work in elapsed time and model counters.
        pipeline.close()
        duration = time.monotonic() - started
        collector.finish()
        rows = writer.results
        inspection = pipeline.runtime_metrics()
        nine = [r for r in rows if r.get('algorithm') == 'nine_view']
        published_latencies = [r['publication_latency_seconds'] for r in nine if 'publication_latency_seconds' in r]
        runtime = dict(source_fps=capture.fps, source_frames=capture.produced, processed_frames=processed,
            dropped_capture_frames=dropped, processed_fps=processed / duration, duration_seconds=duration,
            frame_age_p50_ms=percentile(list(pipeline.frame_ages), 50) * 1000 if pipeline.frame_ages else None,
            frame_age_p95_ms=percentile(list(pipeline.frame_ages), 95) * 1000 if pipeline.frame_ages else None,
            fruit_arrivals_per_second=pipeline.counters['entered_fruit'] / (capture.produced / capture.fps),
            completed_fruit_per_second=sum(bool(r.get('evidence_complete')) for r in nine) / duration,
            selected_crops_per_fruit=[r.get('selected_crops') for r in nine],
            processed_crops_per_fruit=[r.get('processed_crops') for r in nine],
            incomplete_fruit=sum(not r.get('evidence_complete') for r in nine),
            incomplete_reasons=dict(Counter(r.get('reason') for r in nine if not r.get('evidence_complete'))),
            evidence_complete=sum(bool(r.get('evidence_complete')) for r in nine),
            graded_fruit=sum(bool(r.get('grade')) for r in nine),
            deadline_misses=sum(bool(r.get('deadline_missed')) for r in nine),
            publication_latency_p50_seconds=percentile(published_latencies, 50),
            publication_latency_p95_seconds=percentile(published_latencies, 95),
            detector_mean_ms=detector.total_latency_ms / detector.inference_calls if detector.inference_calls else None,
            segmentation_effective_ms_per_crop=segmenter.total_latency_ms / segmenter.inference_calls if segmenter.inference_calls else None,
            source_camera_kept_up=dropped == 0,
            decision_acceptance_pass=bool(nine) and all(r.get('evidence_complete') and not r.get('deadline_missed') and r.get('grade') for r in nine))
        observed_arrivals = runtime['fruit_arrivals_per_second']
        # Counts include detached/lost fruit, whereas routes retain only active identities.
        nine_arrivals = pipeline.nine.counts['arrivals'] + pipeline.nine.counts['active_overloads']
        runtime.update(nine_view_fruit= len(nine), surface_mapping_fruit=len(rows) - len(nine),
            duplicate_terminal_uids=len(rows) - len({r['fruit_uid'] for r in rows}),
            required_crop_samples_per_second=9 * observed_arrivals,
            required_nine_view_samples_per_second=9 * nine_arrivals / (capture.produced / capture.fps),
            configured_required_crop_samples_per_second=9 * args.fruit_rate if args.fruit_rate else None,
            segmenter_serial_upper_bound_fruit_per_second=1000 / (9 * runtime['segmentation_effective_ms_per_crop'])
                if runtime['segmentation_effective_ms_per_crop'] else None,
            detector_only_estimated_fps=1000 / runtime['detector_mean_ms'] if runtime['detector_mean_ms'] else None,
            serial_detection_budget_at_source_rate=runtime['source_fps'] * runtime['detector_mean_ms'] / 1000
                if runtime['detector_mean_ms'] else None)
        metrics_notes = ['Segmenter-only upper bound excludes shared detection, selection, queueing and export.',
                         'Arrivals are accepted tracker identities, not independently counted physical fruit.',
                         'Missing bins and unsupported identity associations are included in failed decisions.']
        monitor.close()
        metrics = dict(runtime=runtime, inspection=inspection, detection=main._model_metrics(detector),
            segmentation=main._model_metrics(segmenter), resource_samples=monitor.samples,
            peak_rss_bytes=max((r['rss_bytes'] for r in monitor.samples), default=None),
            accuracy=labels_metrics(rows, args.labels), switches=switches, interpretation=metrics_notes,
            pi_telemetry_available=any('pi_temperature_c' in r for r in monitor.samples))
        report = dict(job_id=job.name, created_at=datetime.now(timezone.utc).isoformat(), mode='video',
            source_name=args.video.name, status='complete', metrics=metrics, fruits=rows)
        main._write_report(job, report)
        write(output / 'benchmark.json', dict(job_id=job.name, metrics=metrics, statuses=dict(Counter(r['status'] for r in rows))))
        print('RESULT', json.dumps({k: v for k, v in runtime.items() if not k.endswith('_crops_per_fruit')}), flush=True)
    except Exception as error:
        write(output / 'failure.json', dict(error_type=type(error).__name__, error=str(error),
            processed_frames=processed, dropped_capture_frames=dropped, results=len(writer.results)))
        raise
    finally:
        capture.close(); monitor.close(); writer.close(); pipeline.close(); pipeline.close_identity_debug()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, default=Path(r'C:\Users\USER\Pictures\Camera Roll\WIN_20260818_13_05_49_Pro.mp4'))
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    parser.add_argument('--hardware', choices=['laptop', 'pi4'], default='laptop')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--frames', type=int)
    parser.add_argument('--region', nargs=4, type=float, default=[0, 0, 1, 1])
    parser.add_argument('--deadline', type=float, default=5.)
    parser.add_argument('--dwell', type=float)
    parser.add_argument('--fruit-rate', type=float)
    parser.add_argument('--switch-seconds', type=float, default=0.)
    parser.add_argument('--labels', type=Path)
    parser.add_argument('--score-report', type=Path, help='Score an existing report after independent UID/grade annotation; no model run')
    options = parser.parse_args()
    if options.repeats < 1 or (options.frames is not None and options.frames < 1) or options.switch_seconds < 0:
        parser.error('Invalid duration/switch options')
    if options.score_report:
        if not options.labels:
            parser.error('--score-report requires --labels')
        print(json.dumps(labels_metrics(json.loads(options.score_report.read_text(encoding='utf-8'))['fruits'], options.labels), indent=2))
    else:
        run(options)
