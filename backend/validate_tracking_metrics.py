"""Replay retained raw observations and compare passive instrumentation with its baseline.

This is a software check, not a ground-truth tracking benchmark. No model is
invoked and no calibration is inferred from the saved source video.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import cv2
import numpy as np

import algorithm
import tracking_metrics
from tracking_metrics import TrackingConfig, TrackingMetrics


BACKEND = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=BACKEND/'diagnostics/tracking-performance/source_before/algorithm.py')
    parser.add_argument('--output', type=Path, default=BACKEND/'diagnostics/tracking-performance/retained_observation_replay')
    parser.add_argument('--invariance-frames', type=int, default=32)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    observations = {}
    for fruit in report['fruits']:
        for row in fruit.get('tracking_history', []):
            records = observations.setdefault(row['frame'], {})
            raw_id = int(row['raw_track_id'])
            if raw_id in records:
                raise ValueError(f'Duplicate raw ID {raw_id} in frame {row["frame"]}')
            records[raw_id] = row
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise ValueError('Source video could not be opened')
    shape = (int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    images = []
    try:
        for _ in range(min(args.invariance_frames, frame_count)):
            ok, frame = capture.read()
            if not ok:
                raise ValueError('Source frame missing during invariance check')
            images.append(frame)
    finally:
        capture.release()
    args.output.mkdir(parents=True, exist_ok=True)
    # Explicit demonstration region, not a calibrated production configuration.
    config = TrackingConfig(region=(.05,.1,.95,.9))
    collector = TrackingMetrics(config, args.output, 'retained-observation-check')
    started = time.perf_counter()
    for frame in range(frame_count):
        rows = list(observations.get(frame, {}).values())
        collector.observe(frame, rows[0].get('timestamp') if rows else None, shape,
                          [r['raw_track_id'] for r in rows], [r['bbox_xyxy'] for r in rows])
    observe_seconds = time.perf_counter()-started
    started = time.perf_counter()
    data = collector.finish()
    snapshot_seconds = time.perf_counter()-started

    spec = importlib.util.spec_from_file_location('pre_tracking_algorithm', args.baseline)
    baseline = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = baseline
    spec.loader.exec_module(baseline)

    class ReplayDetector:
        names = {0:'fruit'}
        calls = 0
        def track(self, frame, **kwargs):
            records = observations.get(self.calls, {})
            ids = sorted(records)
            self.calls += 1
            return [SimpleNamespace(boxes=SimpleNamespace(
                xyxy=np.array([records[i]['bbox_xyxy'] for i in ids], dtype=float).reshape(-1,4),
                id=np.array(ids), cls=np.zeros(len(ids))))]

    def replay_pipeline(module, instrumented):
        detector = ReplayDetector()
        pipeline = module.NaartjiePipeline(SimpleNamespace(names={0:'defect'}), detector)
        pipeline.set_frame_rate(fps)
        if instrumented:
            pipeline.tracking_metrics = TrackingMetrics(config)
        returns = []
        for index, frame in enumerate(images):
            rows = list(observations.get(index, {}).values())
            returns.append(pipeline.process_frame(frame, index, capture_views=False,
                timestamp=rows[0].get('timestamp') if rows else index/fps))
        image_evidence = []
        for track_id, records in sorted(pipeline.tracking_images_by_id.items()):
            for stage, (frame, image) in sorted(records.items()):
                image_evidence.append([track_id, stage, frame, hashlib.sha256(image.tobytes()).hexdigest()])
        state = dict(returns=returns, detector_calls=detector.calls,
            tracking_history=pipeline.tracking_history_by_id, last_seen=pipeline.last_seen_frame,
            identity_metadata=pipeline.identity_guard.metadata, image_evidence=image_evidence,
            captures=len(pipeline.views_by_id))
        return json.dumps(state, sort_keys=True, allow_nan=False), state

    old, old_state = replay_pipeline(baseline, False)
    new, new_state = replay_pipeline(algorithm, True)
    assert old == new, 'Passive observer changed existing pipeline state or returned IDs'
    assert new_state['detector_calls'] == len(images)
    proof = dict(passed=True, source=str(args.report), source_sha256=digest(args.report),
        source_video_sha256=digest(args.video), baseline_algorithm_sha256=digest(args.baseline),
        current_algorithm_sha256=digest(Path(algorithm.__file__)),
        tracking_metrics_sha256=digest(Path(tracking_metrics.__file__)),
        frames=frame_count, observations=sum(len(rows) for rows in observations.values()),
        duplicate_raw_ids_per_frame=0, shape=shape, observe_seconds=observe_seconds,
        snapshot_and_exports_seconds=snapshot_seconds, summary=data['summary'],
        invariance_frames=len(images), baseline_and_instrumented_pipeline_states_equal=True,
        baseline_detector_calls=old_state['detector_calls'], instrumented_detector_calls=new_state['detector_calls'],
        region_is_demonstration_only=True,
        limitation='Retained raw observations replayed without inference or ground truth. Per-frame detector/tracker timing was not retained, so replay processing FPS is unavailable. Invariance compares identity decisions, histories, returned capture IDs and image evidence on the same saved outputs.')
    (args.output/'validation.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
