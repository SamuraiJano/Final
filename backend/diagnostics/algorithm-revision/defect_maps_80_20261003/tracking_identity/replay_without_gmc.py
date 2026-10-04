"""CPU-only tracker experiments from retained real detections; no model inference."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import ultralytics

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))
from dfine_segmenter import make_fruit_tracker, associate_fruit_detections
from ultralytics.trackers.utils.gmc import GMC

REPLAY = BACKEND/'diagnostics/entry-tracking/entry_full_20261002'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overlaps(boxes, target):
    intersection = np.maximum(0, np.minimum(boxes[:, 2:4], target[2:4]) -
                              np.maximum(boxes[:, :2], target[:2])).prod(axis=1)
    return intersection / np.maximum(np.maximum(boxes[:, 2:4]-boxes[:, :2], 0).prod(axis=1) +
                                    np.maximum(target[2:4]-target[:2], 0).prod() - intersection, 1e-6)


def stats(sequence):
    counts = Counter()
    duplicated = 0
    for record in sequence:
        rows = np.array(record['tracks'], float).reshape(-1, 7)
        counts.update(rows[:, 4].astype(int))
        for index, row in enumerate(rows[:-1]):
            duplicated += int(np.count_nonzero(overlaps(rows[index+1:], row) > .7))
    return {'frames': len(sequence), 'observations': sum(counts.values()), 'track_records': len(counts),
            'ids_at_most_two_observations': sum(value <= 2 for value in counts.values()),
            'median_observations_per_id': float(np.median(list(counts.values()))),
            'coincident_box_pairs_iou_above_0_7': duplicated}


def main():
    started = time.perf_counter()
    video = Path(json.loads((REPLAY/'report.json').read_text())['video'])
    cache = np.load(REPLAY/'raw_detections.npz')
    tracker = make_fruit_tracker('cpu')
    tracker.args.gmc_method = 'none'
    tracker.gmc = GMC(method='none')
    tracker.reset()
    capture = cv2.VideoCapture(str(video))
    size = None
    after = []
    for frame_index, name in enumerate(sorted(cache.files)):
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError('Source video ended before saved detector observations.')
        tracked, size = associate_fruit_detections(tracker, cache[name], frame, size)
        after.append({'frame': frame_index, 'tracks': tracked.tolist()})
    capture.release()
    cache.close()
    after_path = HERE/'no_gmc_tracking.json'
    after_path.write_text(json.dumps(after, indent=2), encoding='utf-8')
    before = json.loads((REPLAY/'immediate_one_detection.json').read_text())
    matches = defaultdict(Counter)
    for old, new in zip(before, after):
        boxes = np.array(new['tracks'], float).reshape(-1, 7)
        for row in np.array(old['tracks'], float).reshape(-1, 7):
            if not len(boxes):
                continue
            scores = overlaps(boxes, row)
            best = int(scores.argmax())
            if scores[best] > .5:
                matches[int(row[4])][int(boxes[best, 4])] += 1
    eligible = {key: value for key, value in matches.items() if sum(value.values()) >= 10}
    disagreement = {key: dict(value) for key, value in eligible.items()
                    if sum(count >= 3 for count in value.values()) > 1}
    # Known synthetic identity replacement: same-class B appears exactly where A
    # disappeared. Geometry cannot establish which physical entity is present.
    replacement_tracker = make_fruit_tracker('cpu')
    replacement_tracker.gmc = GMC(method='none')
    replacement_tracker.reset()
    frame = np.zeros((160, 160, 3), np.uint8)
    replacement_history = []
    replacement_size = None
    for frame_index, truth in enumerate(('A', 'none', 'B')):
        detection = (np.empty((0, 6), np.float32) if truth == 'none' else
                     np.array([[45,45,85,85,.95,0]], np.float32))
        tracked, replacement_size = associate_fruit_detections(replacement_tracker, detection, frame, replacement_size)
        replacement_history.append({'frame': frame_index, 'physical_identity_in_synthetic_scene': truth,
                                    'published_track_ids': tracked[:, 4].astype(int).tolist()})
    report = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'diagnostic_kind': 'Cached real detections, CPU tracker replay only; no detector or segmentation calls.',
        'change': 'Disable camera-motion compensation; keep all association/edge adapter settings unchanged.',
        'duration_seconds': time.perf_counter()-started,
        'software_versions': {'ultralytics': ultralytics.__version__, 'opencv': cv2.__version__, 'numpy': np.__version__},
        'existing_sparse_optical_flow_gmc': stats(before), 'experimental_no_gmc': stats(after),
        'cross_replay': {'eligible_original_ids': len(eligible), 'ids_matching_multiple_experimental_ids': len(disagreement),
                         'details': disagreement, 'rule': 'Per-frame best IoU > 0.5; at least 10 matched frames; multiple IDs each >= 3 matched frames.',
                         'interpretation': 'Disagreement/fragmentation indicator, not physical-identity ground truth or measured ID-switch accuracy.'},
        'known_synthetic_identity_replacement': replacement_history,
        'source_sha256': {'tracker_adapter': sha(BACKEND/'dfine_segmenter.py'), 'raw_detections': sha(REPLAY/'raw_detections.npz'),
                          'existing_tracking': sha(REPLAY/'immediate_one_detection.json'), 'video': sha(video),
                          'script': sha(Path(__file__)), 'experiment_tracking': sha(after_path)},
        'limitations': ['No physical fruit IDs have been manually labelled for the real video.',
                        'Track count alone cannot decide which tracker is more accurate.',
                        'The synthetic A/B replacement is deliberately indistinguishable from detector geometry; it proves a limitation, not a diagnosed switch in the user video.',
                        'No surface maps were built and no grade/coverage improvement is claimed.',
                        'Production tracking source and configuration were not changed.']}
    (HERE/'no_gmc_experiment.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
