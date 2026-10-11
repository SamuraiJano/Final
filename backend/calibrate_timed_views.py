"""Offline timing calibration. Replay benchmarks never reuse these decoded frames.

Measure belt motion from sparse image features, trim stops/acceleration, then
measure actual full-box track lifetimes and test timestamp schedules. No pose
or box-centre calculation is needed by the timed acquisition implementation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import time
import os

os.environ.setdefault('YOLO_CONFIG_DIR', str(Path(__file__).resolve().parent / 'runtime/ultralytics-validation'))

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent


def operation_ranges(times, speeds, duration, step=.2):
    """Conservative stable-motion runs; reject near-still and transitional samples."""
    speeds = np.asarray(speeds, float)
    positive = speeds[speeds > 2.]
    if len(positive) < 5:
        return [], None
    nominal = float(np.percentile(positive, 65))
    stable = (speeds >= max(2., .65 * nominal)) & (speeds <= 1.4 * nominal)
    # Fill a single failed feature measurement, but never a sustained stop.
    for i in range(1, len(stable) - 1):
        if stable[i - 1] and stable[i + 1]:
            stable[i] = True
    ranges, start = [], None
    for i, moving in enumerate(np.r_[stable, False]):
        if moving and start is None:
            start = i
        if not moving and start is not None:
            left = max(0., times[start] - step) + .4
            right = min(duration, times[i - 1]) - .4
            if right - left >= 1.:
                ranges.append([round(left, 3), round(right, 3)])
            start = None
    return ranges, nominal


def scan_video(path, step=.2):
    cap = cv2.VideoCapture(str(path))
    fps, total = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total / fps
    stride = max(1, round(fps * step))
    times, speeds, signed = [], [], []
    previous = None
    frame_index = 0
    while cap.grab():
        if frame_index % stride == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            small = cv2.resize(frame, (320, 180))  # calibration diagnostic only
            grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if previous is not None:
                old, old_colour, old_time = previous
                hsv = cv2.cvtColor(old_colour, cv2.COLOR_BGR2HSV)
                mask = (((hsv[..., 0] < 38) | (hsv[..., 0] > 170)) &
                        (hsv[..., 1] > 70) & (hsv[..., 2] > 45)).astype(np.uint8) * 255
                points = cv2.goodFeaturesToTrack(old, 160, .01, 5, mask=mask)
                speed, dy = 0., 0.
                if points is not None and len(points) >= 8:
                    new, valid, _ = cv2.calcOpticalFlowPyrLK(old, grey, points, None,
                        winSize=(21, 21), maxLevel=3)
                    moves = (new - points).reshape(-1, 2)[valid.ravel() == 1]
                    if len(moves) >= 8:
                        dt = frame_index / fps - old_time
                        dy = float(np.median(moves[:, 1]) / dt)
                        speed = abs(dy)
                times.append(round(frame_index / fps, 4)); speeds.append(speed); signed.append(dy)
            previous = grey, small, frame_index / fps
        frame_index += 1
    cap.release()
    ranges, nominal = operation_ranges(times, speeds, duration, stride / fps)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(video=path.name, sha256=digest, fps=fps, frames=total, duration_seconds=duration,
        operation_ranges=ranges, operation_seconds=sum(b-a for a,b in ranges),
        nominal_vertical_speed_at_180p=nominal, motion_times=times, motion_speed=speeds,
        motion_signed_y=signed, exclusion='No sustained steady conveyor motion' if not ranges else None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--videos', type=Path, default=ROOT.parent / 'videos')
    parser.add_argument('--output', type=Path, default=ROOT / 'diagnostics/timed-views/calibration.json')
    parser.add_argument('--measure-tracks', action='store_true')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.measure_tracks:
        measure_tracks(args.videos, args.output)
        return
    records = []
    for path in sorted(args.videos.glob('*.mp4')):
        row = scan_video(path); records.append(row)
        print(path.name, row['operation_ranges'], round(row['duration_seconds'], 2), flush=True)
        args.output.write_text(json.dumps(dict(method='Fruit-feature vertical motion; stable speed band, 0.4s transition guard',
            status='automatic ranges pending visual review', videos=records), indent=2), encoding='utf-8')


def measure_tracks(videos, output):
    from export_detector import ExportDetector
    from nine_view import select_crop
    from inspection_config import NineViewSettings
    record = json.loads(output.read_text(encoding='utf-8'))
    tracks, sampled = [], []
    cfg = NineViewSettings(region=(0, 0, 1, 1))
    for video in record['videos']:
        if not video['operation_ranges']:
            continue
        a, b = max(video['operation_ranges'], key=lambda ab: ab[1]-ab[0])
        if b-a < 4.:
            continue  # too short to measure uncensored entry-to-exit dwell
        # Sample up to 10 seconds from every sufficiently long recording.
        end = min(b, a+10.)
        model = ExportDetector('yolo_rgb', threads=4)
        cap = cv2.VideoCapture(str(videos / video['video']))
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(a*video['fps']))
        first = round(a*video['fps']); stride = max(1, round(video['fps']/10))
        history = {}
        for index in range(first, int(end*video['fps'])):
            if not cap.grab(): break
            if (index-first) % stride: continue
            ok, frame = cap.retrieve()
            if not ok: break
            result = model.track(frame)[0].boxes
            if result.id is None: continue
            rows = np.asarray(result.data)
            for row in rows:
                identity = int(row[4]); t = index/video['fps']
                item = history.setdefault(identity, dict(times=[], frames=[], first=t, last=t, rejected=0))
                item['last'] = t
                crop, _ = select_crop(frame, row[:4], index, t, 0., 0, None, cfg, rows[:,:4])
                if crop is not None:
                    item['times'].append(t); item['frames'].append(index)
                else:
                    item['rejected'] += 1
        cap.release()
        eligible = []
        for identity, item in history.items():
            # Ignore clips that start/end with this same fruit already visible.
            if item['first'] <= a+.3 or item['last'] >= end-.3 or len(item['times']) < 4:
                continue
            item.update(video=video['video'], track_id=identity,
                        dwell_seconds=item['times'][-1]-item['times'][0])
            tracks.append(item); eligible.append(item)
        sampled.append(dict(video=video['video'], start=a, end=end, eligible_tracks=len(eligible)))
        print('TIMING',video['video'],len(eligible),flush=True)
        (output.parent/'track_dwell.json').write_text(json.dumps(dict(sampled=sampled,tracks=tracks),indent=2))
    candidates = []
    for count in range(4,10):
        for interval in (.2,.25,.3,.35,.4,.45,.5,.6,.75,1.,1.5,2.):
            success = 0
            for track in tracks:
                timestamps = track['times']; start=timestamps[0]
                accepted = []
                for k in range(count):
                    due = start+k*interval
                    chosen = next((t for t in timestamps if due-1e-6 <= t <= due+min(.15,interval*.75)
                                   and (not accepted or t>accepted[-1])),None)
                    if chosen is not None: accepted.append(chosen)
                success += len(accepted)==count
            candidates.append(dict(views=count,interval_seconds=interval,complete_tracks=success,
                                   eligible_tracks=len(tracks),capture_fraction=success/max(1,len(tracks))))
    feasible = [x for x in candidates if x['views']==4 and x['capture_fraction']>=.95]
    best = max(feasible,key=lambda x:x['interval_seconds']) if feasible else max(
        (x for x in candidates if x['views']==4),key=lambda x:(x['capture_fraction'],x['interval_seconds']))
    record['timing'] = dict(method='Longest four-view interval reaching 95% complete timestamp schedules on uncensored quality-accepted tracks',
        recommended=best,candidates=candidates, eligible_tracks=len(tracks), sampled=sampled,
        dwell_percentiles_seconds={str(q):float(np.percentile([t['dwell_seconds'] for t in tracks],q)) for q in (5,50,95)},
        identity_truth='Detector/TrackTrack associations; not independently labelled physical identities',
        angle_coverage='Timing and distinct frames do not certify different skin angles')
    output.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('RECOMMENDED',best,flush=True)


if __name__ == '__main__':
    main()
