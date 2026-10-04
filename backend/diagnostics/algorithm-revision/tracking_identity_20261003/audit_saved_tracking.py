"""Read saved boxes; flag discontinuities without claiming identity ground truth."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
JOB = BACKEND / 'results/ea6e595b8f3f45f2b5edfda8dafff3f2'
REPLAY = BACKEND / 'diagnostics/entry-tracking/entry_full_20261002'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def center(box):
    return (box[:2] + box[2:]) / 2


def size(box):
    return np.maximum(box[2:] - box[:2], 1)


def interior(box):
    return bool(box[0] > 2 and box[1] > 2 and box[2] < 1918 and box[3] < 1078)


def main():
    histories = {}
    result_rows = {}
    by_frame = defaultdict(dict)
    for path in sorted(JOB.glob('*/result.json')):
        row = json.loads(path.read_text(encoding='utf-8'))
        identity = int(row['track_id'])
        history = [(int(item['frame']), np.array(item['bbox_xyxy'], float))
                   for item in row.get('tracking_history', [])]
        histories[identity] = history
        result_rows[identity] = row
        for frame, box in history:
            by_frame[frame][identity] = box
    all_pairs = []
    interior_pairs = []
    gaps = []
    for identity, history in histories.items():
        for (old_frame, old), (frame, new) in zip(history, history[1:]):
            gap = frame - old_frame
            movement = (center(new) - center(old)) / gap
            diameter = float(np.sqrt(np.prod(size(old))))
            item = {'track_id': identity, 'old_frame': old_frame, 'frame': frame,
                    'frame_gap': gap, 'movement_px_per_frame': movement.tolist(),
                    'movement_diameters_per_frame': float(np.linalg.norm(movement) / diameter),
                    'lateral_diameters_per_frame': float(abs(movement[0]) / diameter),
                    'vertical_diameters_per_frame': float(movement[1] / diameter),
                    'both_boxes_complete': interior(old) and interior(new),
                    'bbox_area_ratio': float(np.prod(size(new)) / np.prod(size(old))),
                    'old_box': old.tolist(), 'box': new.tolist()}
            all_pairs.append(item)
            if item['both_boxes_complete'] and gap == 1:
                interior_pairs.append(item)
            if gap > 1:
                gaps.append(item)
    movement = np.array([item['movement_px_per_frame'] for item in interior_pairs])
    ranking = sorted(interior_pairs, key=lambda item: item['movement_diameters_per_frame'], reverse=True)
    # Deliberately broad diagnostic thresholds, never a production identity rule.
    flags = [item for item in all_pairs if item['both_boxes_complete'] and
             (item['movement_diameters_per_frame'] > .35 or
              item['lateral_diameters_per_frame'] > .25 or
              item['vertical_diameters_per_frame'] < -.15 or
              item['bbox_area_ratio'] > 2 or item['bbox_area_ratio'] < .5)]
    flag_counts = Counter(item['track_id'] for item in flags)
    replay = json.loads((REPLAY / 'immediate_one_detection.json').read_text(encoding='utf-8'))
    matched = mismatched = missing = 0
    maximum_box_difference = 0.
    for frame in replay:
        for row in frame['tracks']:
            identity = int(row[4])
            actual = by_frame[frame['frame']].get(identity)
            if actual is None:
                missing += 1
                continue
            difference = float(np.max(np.abs(actual - np.array(row[:4]))))
            maximum_box_difference = max(maximum_box_difference, difference)
            matched += difference <= .001
            mismatched += difference > .001
    report = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'analysis_scope': 'Saved 515-frame full application bbox histories, compared with the prior 515-frame detector-only replay. No neural inference, no production edits.',
        'source_job': JOB.name, 'track_records': len(histories),
        'observations': sum(len(value) for value in histories.values()),
        'consecutive_complete_box_pairs': len(interior_pairs),
        'median_complete_motion_px_per_frame': np.median(movement, axis=0).tolist(),
        'complete_motion_1st_99th_percentiles_px_per_frame': np.percentile(movement, [1, 99], axis=0).tolist(),
        'maximum_complete_movement_diameters_per_frame': ranking[0]['movement_diameters_per_frame'],
        'flag_rules': 'Both boxes complete; per-frame movement > 0.35 fruit diameters OR lateral movement > 0.25 diameters OR upward movement > 0.15 diameters OR area changes > 2x or < 0.5x. Broad flags do not prove identity switches.',
        'flagged_pairs': flags, 'flagged_track_pair_counts': dict(flag_counts),
        'gapped_observation_pairs': len(gaps), 'gap_distribution': dict(Counter(item['frame_gap'] for item in gaps)),
        'longest_gap': max((item['frame_gap'] for item in gaps), default=0),
        'largest_consecutive_complete_movements': ranking[:20],
        'gap_details': gaps,
        'replay_matches': {'matching_saved_boxes': int(matched), 'mismatched_saved_boxes': int(mismatched),
                           'missing_observations': missing, 'maximum_box_coordinate_difference_px': maximum_box_difference},
        'previous_cross_replay_consistency': json.loads((REPLAY/'all_frame_tracking_checks.json').read_text(encoding='utf-8'))['cross_replay_identity_consistency'],
        'previous_disagreement_mapping_results': [
            {'baseline_track_id': int(old_identity), 'revised_track_id': int(new_identity),
             'matched_frames': matched_frames, 'usable_views': result_rows[int(new_identity)]['views'],
             'mapping_status': result_rows[int(new_identity)]['status']}
            for old_identity, values in json.loads((REPLAY/'all_frame_tracking_checks.json').read_text(encoding='utf-8'))['cross_replay_identity_consistency']['multiple_matches'].items()
            for new_identity, matched_frames in values.items()],
        'mapping_status_counts': dict(Counter(row['status'] for row in result_rows.values())),
        'source_sha256': {'script': digest(Path(__file__)), 'dfine_segmenter_current': digest(BACKEND/'dfine_segmenter.py'),
                          'replay_dfine_segmenter': digest(REPLAY/'dfine_segmenter.py'),
                          'replay_tracking': digest(REPLAY/'immediate_one_detection.json'), 'source_report': digest(JOB/'report.json')},
        'limitations': ['No manually labelled physical fruit identities are available, so true ID-switch accuracy cannot be measured.',
                        'An identity switch between nearby similar fruits can have smooth boxes and evade every geometric flag.',
                        'A flag can be a detector box jump, occlusion, or fruit movement rather than an identity switch.',
                        'The seven previous cross-replay disagreements may be fragmentation; the baseline tracker is not ground truth.']
    }
    (HERE/'audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('track_records','observations','consecutive_complete_box_pairs',
          'median_complete_motion_px_per_frame','complete_motion_1st_99th_percentiles_px_per_frame',
          'maximum_complete_movement_diameters_per_frame','flagged_track_pair_counts',
          'gapped_observation_pairs','gap_distribution','longest_gap','replay_matches','mapping_status_counts','source_sha256')}, indent=2))


if __name__ == '__main__':
    main()
