"""Independently reconcile completed experiment summaries with raw observation CSVs."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

import cv2


def csv_rows(path):
    with path.open(encoding='utf-8', newline='') as file:
        return list(csv.DictReader(file))


def close(actual, expected):
    if actual is None or expected is None:
        assert actual is expected, (actual, expected)
    else:
        assert math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-8), (actual, expected)


def validate(folder: Path):
    payload = json.loads((folder/'comparison_summary.json').read_text(encoding='utf-8'))
    assert payload['complete']
    assert json.loads((folder/'status.json').read_text())['status'] == 'complete'
    metadata = payload['metadata']
    for name, relative in metadata.get('source_snapshot', {}).items():
        assert hashlib.sha256((folder/relative).read_bytes()).hexdigest() == metadata['experiment_source_sha256'][name]
    renderer = metadata.get('report_renderer_snapshot') or metadata.get('source_snapshot', {}).get('tracker_comparison_report.py')
    if renderer:
        assert hashlib.sha256((folder/renderer).read_bytes()).hexdigest() == metadata['report_renderer_sha256']
    manifest = json.loads((folder/'input_manifest.json').read_text())
    count = metadata['video']['frame_count']
    expected_modes = ['full', 'cached'] if metadata['requested_mode'] == 'both' else [metadata['requested_mode']]
    assert {(s['tracker_key'], s['mode']) for s in payload['results']} == {
        (key, mode) for key in metadata['selected_trackers'] for mode in expected_modes}
    assert len(payload['results']) == len(expected_modes)*len(metadata['selected_trackers'])
    comparison_csv = csv_rows(folder/'comparison_summary.csv')
    assert len(comparison_csv) == len(payload['results'])
    checks = []
    for summary in payload['results']:
        key, mode = summary['tracker_key'], summary['mode']
        path = folder/key/mode if len(expected_modes) > 1 else folder/key
        assert json.loads((path/'summary.json').read_text()) == summary
        config = metadata['tracker_configurations'][key]
        assert hashlib.sha256((path/config['filename']).read_bytes()).hexdigest() == config['sha256']
        frames = csv_rows(path/'frames.csv')
        tracks = csv_rows(path/'tracks.csv')
        observations = csv_rows(path/'observations.csv')
        events = csv_rows(path/'events.csv')
        assert len(frames) == count == summary['processed_frames']
        assert [int(f['frame']) for f in frames] == list(range(count))
        for index, frame in enumerate(frames):
            close(frame['timestamp'], manifest['timestamps'][index])
        by_id, by_frame = defaultdict(list), defaultdict(list)
        for row in observations:
            by_id[int(row['track_id'])].append(row)
            by_frame[int(row['frame'])].append(int(row['track_id']))
        assert len(by_id) == len(tracks) == summary['unique_raw_ids']
        assert {int(t['track_id']) for t in tracks} == set(by_id)
        for track in tracks:
            rows = by_id[int(track['track_id'])]
            first, last = int(rows[0]['frame']), int(rows[-1]['frame'])
            assert first == int(track['first_frame']) and last == int(track['last_frame'])
            assert len(rows) == int(track['observed_frames'])
            assert last-first+1 == int(track['possible_frames_between_first_and_last'])
            close(track['first_timestamp'], rows[0]['timestamp'])
            close(track['last_timestamp'], rows[-1]['timestamp'])
            close(track['lifetime_seconds'], float(rows[-1]['timestamp'])-float(rows[0]['timestamp']))
            close(track['consistency_percent'], 100*len(rows)/(last-first+1))
            close(track['processed_video_frames_percent'], 100*len(rows)/count)
            close(track['mean_box_width'], mean(float(row['x2'])-float(row['x1']) for row in rows))
            close(track['mean_box_height'], mean(float(row['y2'])-float(row['y1']) for row in rows))
        lifetime = [float(t['lifetime_seconds']) for t in tracks]
        consistency = [float(t['consistency_percent']) for t in tracks]
        for name, values in (('lifetime_seconds', lifetime), ('consistency_percent', consistency)):
            close(summary['mean_'+name], mean(values) if values else None)
            close(summary['median_'+name], median(values) if values else None)
        close(summary['minimum_lifetime_seconds'], min(lifetime) if lifetime else None)
        close(summary['maximum_lifetime_seconds'], max(lifetime) if lifetime else None)
        active = [len(by_frame[index]) for index in range(count)]
        assert all(len(set(ids)) == len(ids) for ids in by_frame.values())
        assert active == [int(frame['active_ids']) for frame in frames]
        assert max(active) == summary['maximum_active_ids']
        close(mean(active), summary['mean_active_ids'])
        assert active[-1] == summary['final_active_ids']
        seconds = sum(float(f['processing_seconds']) for f in frames)
        close(summary['total_processing_seconds'], seconds)
        close(summary['processing_fps'], count/seconds)
        close(summary['average_time_ms'], 1000*seconds/count)
        for diagnostic in summary['short_lived_ids']:
            expected = sum(t < diagnostic['threshold_seconds'] for t in lifetime)
            assert diagnostic['count'] == expected
            close(diagnostic['percent'], 100*expected/len(tracks) if tracks else None)
        settings = summary['diagnostic_settings']
        substantial = sum(float(t['lifetime_seconds']) >= settings['substantial_lifetime_seconds']
                          and float(t['consistency_percent']) >= settings['substantial_consistency_percent'] for t in tracks)
        assert substantial == summary['substantial_persistence_ids']
        assert sum(d['count'] for d in summary['lifetime_distribution']) == len(tracks)
        suspected = [e for e in events if e['event'] == 'Suspected ID Fragmentation']
        assert len(suspected) == summary['suspected_id_fragmentations']
        for event in suspected:
            assert int(event['track_id']) != int(event['previous_track_id'])
            assert int(event['track_id']) in by_id and int(event['previous_track_id']) in by_id
            assert float(event['gap_seconds']) <= settings['fragmentation_window_seconds']+1e-9
            assert float(event['distance_pixels']) <= float(event['distance_limit_pixels'])
        assert summary['fresh_state_verified'] and summary['identical_video_frames_verified']
        if (path/'annotated.mp4').is_file():
            reader = cv2.VideoCapture(str(path/'annotated.mp4'))
            assert reader.isOpened()
            assert int(reader.get(cv2.CAP_PROP_FRAME_COUNT)) == count
            assert int(reader.get(cv2.CAP_PROP_FRAME_WIDTH)) == metadata['video']['width']
            assert int(reader.get(cv2.CAP_PROP_FRAME_HEIGHT)) == metadata['video']['height']
            reader.release()
        row = next(r for r in comparison_csv if r['tracker_name'] == summary['tracker_name'] and r['mode'] == mode)
        for field, value in summary.items():
            if field in row and isinstance(value, (int, float)):
                close(row[field], value)
        checks.append(dict(tracker=key, mode=mode, frames=count, raw_observations=len(observations),
                           raw_ids=len(by_id), summary_matches_observations=True))
    cached = [s for s in payload['results'] if s['mode'] == 'cached']
    assert not cached or len({s['detection_sequence_sha256'] for s in cached}) == 1
    # Same model inputs produce equal behaviour across the two modes when full detections match cache.
    for key in metadata['selected_trackers']:
        pair = [s for s in payload['results'] if s['tracker_key'] == key]
        if len(pair) == 2 and all(s['detection_matches_cache'] for s in pair):
            for field in ('unique_raw_ids', 'mean_lifetime_seconds', 'median_lifetime_seconds',
                          'mean_consistency_percent', 'suspected_id_fragmentations'):
                close(pair[0][field], pair[1][field])
    result = dict(passed=True, checks=checks, modes=expected_modes,
                  cached_detection_sequences_identical=bool(cached),
                  full_detections_match_cache=all(s['detection_matches_cache'] for s in payload['results']) if cached else None)
    return result


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('folder', type=Path)
    cli.add_argument('--output', type=Path)
    args = cli.parse_args()
    result = validate(args.folder.resolve())
    if args.output:
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
