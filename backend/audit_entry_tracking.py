"""Audit a retained tracking replay without claiming physical-identity ground truth."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np


def overlaps(boxes, box):
    intersection = np.maximum(0, np.minimum(boxes[:, 2:4], box[2:4]) -
                              np.maximum(boxes[:, :2], box[:2])).prod(axis=1)
    area = np.maximum(0, boxes[:, 2:4]-boxes[:, :2]).prod(axis=1)
    target_area = np.maximum(0, box[2:4]-box[:2]).prod()
    return intersection / np.maximum(area+target_area-intersection, 1e-6)


def audit(directory):
    names = ('baseline_three_detections.json', 'immediate_one_detection.json')
    sequences = [json.loads((directory/name).read_text()) for name in names]
    summary = {}
    for name, sequence in zip(names, sequences):
        counts = Counter()
        duplicates = 0
        for frame in sequence:
            rows = np.asarray(frame['tracks'], dtype=float).reshape(-1, 7)
            counts.update(rows[:, 4].astype(int))
            for index, row in enumerate(rows[:-1]):
                duplicates += int(np.count_nonzero(overlaps(rows[index+1:], row) > .7))
        summary[name] = {
            'track_ids': len(counts),
            'ids_with_at_most_two_observations': sum(value <= 2 for value in counts.values()),
            'median_observed_frames_per_id': float(np.median(list(counts.values()))),
            'coincident_box_pairs_iou_above_0_7': duplicates,
            'frames_tested': len(sequence),
        }
    matches = defaultdict(Counter)
    for before, after in zip(*sequences):
        assert before['frame'] == after['frame']
        current = np.asarray(after['tracks'], dtype=float).reshape(-1, 7)
        if not len(current):
            continue
        for row in np.asarray(before['tracks'], dtype=float).reshape(-1, 7):
            scores = overlaps(current, row)
            index = int(scores.argmax())
            if scores[index] > .5:
                matches[int(row[4])][int(current[index, 4])] += 1
    eligible = {identity: values for identity, values in matches.items() if sum(values.values()) >= 10}
    split = {identity: dict(values) for identity, values in eligible.items()
             if sum(value >= 3 for value in values.values()) > 1}
    summary['cross_replay_identity_consistency'] = {
        'eligible_baseline_ids': len(eligible),
        'ids_with_multiple_substantial_matches': len(split),
        'ids_without_multiple_substantial_matches': len(eligible)-len(split),
        'multiple_matches': split,
        'rule': 'Best per-frame box IoU > 0.5; at least 10 matched frames per baseline ID; '
                'multiple IDs each matched on at least 3 frames count as inconsistent.',
        'limitation': 'The legacy tracker is not ground truth. These are consistency checks, '
                      'not measured ID-switch accuracy or unique physical fruit counts.',
    }
    (directory/'all_frame_tracking_checks.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), indent=2))
