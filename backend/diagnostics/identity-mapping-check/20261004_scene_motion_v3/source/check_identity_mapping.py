"""Locate detected identity boundaries relative to saved map inputs and outputs.

Uses frozen tracker observations and original maps. Flags are not identity
ground truth; this checks possible causal overlap, not a switch accuracy metric.
"""
import hashlib
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--guard-source', type=Path, default=ROOT/'diagnostics/identity-guard/20261004_scene_motion_v3')
    args = parser.parse_args()
    OUTPUT = args.output
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = ROOT/'results/ea6e595b8f3f45f2b5edfda8dafff3f2/report.json'
    guard_source = args.guard_source
    decisions = json.loads((guard_source/'decisions.json').read_text())
    by_observation = {(item['raw_track_id'], item['frame']): item for item in decisions}
    fruits = json.loads(source.read_text())['fruits']
    audit = []
    for fruit in fruits:
        identity = fruit['track_id']
        views = fruit.get('view_frames', [])
        mapped = fruit.get('mapped_view_frames', [])
        groups = defaultdict(list)
        selected = defaultdict(list)
        for frames, destination in ((views, groups), (mapped, selected)):
            for frame in frames:
                item = by_observation[(identity, frame)]
                destination[item['capture_id']].append(frame)
        history = fruit.get('tracking_history', [])
        events = [by_observation[(identity, item['frame'])] for item in history
                  if by_observation[(identity, item['frame'])]['reason'] not in ('continued', 'new_track')]
        audit.append({'raw_track_id': identity, 'status': fruit['status'],
                      'produced_map': bool(fruit.get('surface_map')), 'usable_views': len(views),
                      'captured_segments': dict(groups), 'mapped_segments': dict(selected),
                      'boundary_inside_captured_views': len(groups) > 1,
                      'boundary_inside_mapped_views': len(selected) > 1,
                      'identity_events': events})
    (OUTPUT/'map_overlap.json').write_text(json.dumps(audit, indent=2))

    # Legacy fixture IDs are not necessarily IDs in the current tracker replay.
    # Match original crop pixels to detector-box crops to establish that link.
    replay = ROOT/'diagnostics/entry-tracking/entry_full_20261002'
    sequence = json.loads((replay/'immediate_one_detection.json').read_text())
    fixtures = [(identity, ROOT/'diagnostics/algorithm-audit/corrected_tracks_20261002'/str(identity))
                for identity in (98, 1, 14)]
    fixtures.append((491, ROOT/'diagnostics/algorithm-audit/longitude_failure_491_20261002/captured_views'))
    pending = defaultdict(list)
    for identity, folder in fixtures:
        for item in json.loads((folder/'views.json').read_text()):
            pending[item['frame']].append((identity, folder, item))
    capture = cv2.VideoCapture(json.loads((replay/'report.json').read_text())['video'])
    correspondences = defaultdict(list)
    for frame_index in range(max(pending)+1):
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError('Source video ended before fixture correspondence check')
        if frame_index not in pending:
            continue
        height, width = frame.shape[:2]
        rows = sequence[frame_index]['tracks']
        for identity, folder, item in pending[frame_index]:
            with np.load(folder/item['file']) as data:
                image = data['image']
                matches = []
                for row in rows:
                    x1, y1, x2, y2 = row[:4]
                    px, py = .12*(x2-x1), .12*(y2-y1)
                    left, top = max(0, int(np.floor(x1-px))), max(0, int(np.floor(y1-py)))
                    right, bottom = min(width, int(np.ceil(x2+px))), min(height, int(np.ceil(y2+py)))
                    crop = frame[top:bottom, left:right]
                    if crop.shape == image.shape and np.array_equal(crop, image):
                        raw_id = int(row[4])
                        decision = by_observation[(raw_id, frame_index)]
                        matches.append({'raw_track_id': raw_id, 'capture_id': decision['capture_id'],
                                        'decision': decision['reason'], 'bbox_xyxy': row[:4]})
                localized = None
                if not matches:
                    # Historical adapters sometimes rounded a box differently.
                    # Locate the unchanged crop pixels before comparing boxes.
                    scores = cv2.matchTemplate(frame, image, cv2.TM_SQDIFF)
                    _, _, origin, _ = cv2.minMaxLoc(scores)
                    left, top = origin
                    if np.array_equal(frame[top:top+image.shape[0], left:left+image.shape[1]], image):
                        local_box = np.asarray(item['bbox'], float)
                        target = local_box+np.array([left, top, left, top])
                        candidates = []
                        for row in rows:
                            bounds = np.asarray(row[:4])
                            intersection = np.maximum(0, np.minimum(bounds[2:], target[2:])-np.maximum(bounds[:2], target[:2])).prod()
                            area = (bounds[2:]-bounds[:2]).prod()+(target[2:]-target[:2]).prod()-intersection
                            candidates.append((float(intersection/max(area, 1.)), int(row[4])))
                        candidates.sort(reverse=True)
                        if candidates and candidates[0][0] >= .8 and (len(candidates) == 1 or candidates[0][0]-candidates[1][0] >= .15):
                            overlap, raw_id = candidates[0]
                            decision = by_observation[(raw_id, frame_index)]
                            localized = {'raw_track_id': raw_id, 'capture_id': decision['capture_id'],
                                         'decision': decision['reason'], 'bbox_iou': overlap,
                                         'crop_origin_xy': [left, top]}
                correspondences[str(identity)].append({'frame': frame_index, 'file': item['file'],
                    'input_sha256': sha(folder/item['file']), 'exact_pixel_matches': matches,
                    'localized_crop_match': localized})
    capture.release()
    (OUTPUT/'fixture_correspondence.json').write_text(json.dumps(correspondences, indent=2))
    previous = json.loads((ROOT/'diagnostics/algorithm-revision/tracking_identity_20261003/audit.json').read_text())
    map_rows = [row for row in audit if row['produced_map']]
    failed_rows = [row for row in audit if not row['produced_map']]
    summary = {
        'source_job': source.parent.name, 'source_report_sha256': sha(source),
        'guard_decisions_sha256': sha(guard_source/'decisions.json'),
        'guard_source': str(guard_source),
        'saved_records': len(audit), 'produced_maps': len(map_rows), 'records_without_map': len(failed_rows),
        'maps_with_boundary_inside_captured_views': sum(row['boundary_inside_captured_views'] for row in map_rows),
        'maps_with_boundary_inside_selected_views': sum(row['boundary_inside_mapped_views'] for row in map_rows),
        'failed_records_with_boundary_inside_captured_views': sum(row['boundary_inside_captured_views'] for row in failed_rows),
        'recovered_id_records': [row for row in audit if row['raw_track_id'] in (244, 248)],
        'previous_disagreement_mapping_results': previous['previous_disagreement_mapping_results'],
        'fixture_correspondence': {key: {
            'views': len(items), 'uniquely_matched_views': sum(len(item['exact_pixel_matches']) == 1 for item in items),
            'localized_crop_matches': sum(item['localized_crop_match'] is not None for item in items),
            'unmatched_views': sum(not item['exact_pixel_matches'] and item['localized_crop_match'] is None for item in items),
            'raw_id_counts': dict(Counter(match['raw_track_id'] for item in items
                                         for match in (item['exact_pixel_matches'] or [item['localized_crop_match']]) if match)),
            'capture_id_counts': dict(Counter(match['capture_id'] for item in items
                                             for match in (item['exact_pixel_matches'] or [item['localized_crop_match']]) if match)),
        } for key, items in correspondences.items()},
        'limitations': ['Detected boundaries are not labelled identity switches.',
                       'No boundary in selected views does not rule out a smooth wrong-fruit identity exchange.',
                       'Legacy fixture IDs must be matched by pixels; equal numeric IDs alone are insufficient.'],
    }
    (OUTPUT/'summary.json').write_text(json.dumps(summary, indent=2))
    (OUTPUT/'check_identity_mapping.py.snapshot').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
