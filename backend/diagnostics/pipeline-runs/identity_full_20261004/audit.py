"""Summarize the complete run without treating stable IDs as manual truth."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
request = json.loads((HERE/'request.json').read_text())
output = Path(request['output'])
report = json.loads((output/'report.json').read_text())
assert report['status'] == 'complete', 'Only completed runs may be scored.'
rows = report['fruits']
metrics = report['metrics']
with Path(request['video']).open('rb') as stream:
    video_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
maps = [r for r in rows if r.get('surface_map')]
usable = [r for r in rows if r.get('views', 0) >= 2]
full = [r for r in maps if r.get('coverage_complete')]
by_frame = defaultdict(list)
for row in rows:
    for observation in row.get('tracking_history', []):
        by_frame[observation['frame']].append((row['track_id'], observation))
checks = {
    'run_complete': report['status'] == 'complete',
    'input_video_unchanged': video_sha == request['video_sha256'],
    'all_795_frames_processed': metrics['frames'] == 795,
    'fresh_detection_on_every_frame': metrics['detection']['calls'] == metrics['frames'],
    'segmentation_executed': metrics['segmentation']['calls'] > 0,
    'identity_validation_enabled': metrics['identity_guard']['conveyor_identity_validation'],
    'stable_ids_unique_across_results': len({r['track_id'] for r in rows}) == len(rows),
    'one_observation_per_stable_id_per_frame': all(len({i for i, _ in observations}) == len(observations) for observations in by_frame.values()),
    'one_observation_per_raw_id_per_frame': all(len({o['raw_track_id'] for _, o in observations}) == len(observations) for observations in by_frame.values()),
    'observation_stable_id_matches_capture': all(o.get('fruit_id') == i for observations in by_frame.values() for i, o in observations),
    'uncertain_identities_never_graded': all(r.get('grade') is None for r in rows if r.get('identity_status') == 'uncertain'),
    'all_full_maps_meet_area_and_longitude': all(r['observed_surface_pct'] >= 80 and r['observed_longitude_deg'] >= 350 for r in full),
    'frozen_sources_match_run_request': all(hashlib.sha256((output/f'{name}.snapshot').read_bytes()).hexdigest() == sha for name, sha in request['source_sha256'].items()),
    'all_result_files_match_report': all(json.loads((output/str(r['track_id'])/'result.json').read_text()) == r for r in rows),
}
def asset_path(url):
    return BACKEND/str(url).lstrip('/')
asset_urls = [r[k] for r in maps for k in ('surface_map', 'observed_mask', 'surface_map_overlay')]
checks['all_map_assets_exist'] = all(asset_path(url).is_file() for url in asset_urls)

# The earlier tracking export used the same video and detector. Compare every
# stored capture box/ID; this is reproducibility evidence, not manual accuracy.
previous = BACKEND/'diagnostics'/'conveyor-identity'/'20261004'/'representative'/'capture_tracking.json'
reference = json.loads(previous.read_text())
expected = {(f['frame'], int(t[4])): t[:4] for f in reference for t in f['tracks']}
current = {(frame, i): o['bbox_xyxy'] for frame, observations in by_frame.items() for i, o in observations}
shared = set(expected) & set(current)
box_diff = max((max(abs(a-b) for a,b in zip(current[k], expected[k])) for k in shared), default=0)
reproducibility = {'expected_observations': len(expected), 'current_observations': len(current),
                   'missing_observation_keys': len(set(expected)-set(current)),
                   'extra_observation_keys': len(set(current)-set(expected)),
                   'maximum_box_difference_px': box_diff,
                   'identical': current == expected}

def percentage(a, b):
    return round(100*a/b, 2) if b else None
def distribution(values):
    return {'minimum': min(values), 'median': statistics.median(values), 'mean': statistics.mean(values), 'maximum': max(values)} if values else {}
summary = {
    'job_id': report['job_id'], 'source_name': report['source_name'],
    'status': report['status'], 'metrics': metrics, 'checks': checks,
    'checks_passed': all(checks.values()), 'tracking_reproducibility': reproducibility,
    'counts': {
        'stable_capture_segments': len(rows),
        'raw_tracker_ids': len({o['raw_track_id'] for observations in by_frame.values() for _, o in observations}),
        'tracked_observations': sum(len(v) for v in by_frame.values()),
        'motion_consistent_segments': sum(r.get('identity_status') == 'motion_consistent' for r in rows),
        'uncertain_segments': sum(r.get('identity_status') == 'uncertain' for r in rows),
        'segments_ever_fully_in_frame': sum(any(not o['touches_frame_edge'] for o in r.get('tracking_history', [])) for r in rows),
        'segments_never_fully_in_frame': sum(all(o['touches_frame_edge'] for o in r.get('tracking_history', [])) for r in rows),
        'segments_with_zero_usable_views': sum(r.get('views', 0) == 0 for r in rows),
        'segments_with_one_usable_view': sum(r.get('views', 0) == 1 for r in rows),
        'segments_with_at_least_two_usable_views': len(usable),
        'any_surface_map': len(maps), 'coverage_complete_maps': len(full),
        'fully_graded': sum(r['status'] == 'graded' for r in rows),
        'provisional_grades': sum(r['status'] == 'graded_partial' for r in rows),
        'mapping_failed': sum(r['status'] == 'mapping_failed' for r in rows),
        'statuses': dict(Counter(r['status'] for r in rows)),
        'grades': dict(Counter(r.get('grade') or 'ungraded' for r in rows)),
        'identity_decisions': dict(Counter(o['identity_decision'] for obs in by_frame.values() for _, o in obs)),
        'failure_reasons': dict(Counter(r.get('reason') for r in rows if r['status'] == 'mapping_failed')),
        'rejected_views': dict(sum((Counter(r.get('rejected_views', {})) for r in rows), Counter())),
    },
    'rates': {
        'any_map_per_capture_segment_pct': percentage(len(maps), len(rows)),
        'complete_coverage_per_capture_segment_pct': percentage(len(full), len(rows)),
        'fully_graded_per_capture_segment_pct': percentage(sum(r['status'] == 'graded' for r in rows), len(rows)),
        'any_map_per_segment_with_two_views_pct': percentage(len(maps), len(usable)),
        'complete_coverage_per_segment_with_two_views_pct': percentage(len(full), len(usable)),
    },
    'surface_coverage_pct': distribution([r['observed_surface_pct'] for r in maps]),
    'longitude_coverage_deg': distribution([r['observed_longitude_deg'] for r in maps]),
    'full_map_ids': [r['track_id'] for r in full],
    'top_surface_coverage': [{'id': r['track_id'], 'area_pct': r['observed_surface_pct'],
                             'longitude_deg': r['observed_longitude_deg'], 'status': r['status']}
                             for r in sorted(maps, key=lambda r: r['observed_surface_pct'], reverse=True)[:10]],
    'limitations': request['limitations'] + ' Rates use capture segments, not independently labelled physical fruit. Stable tracking does not prove accurate rotation, mapping or grades.'
}
(HERE/'audit.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ('metrics', 'top_surface_coverage')}, indent=2))
if not all(checks.values()):
    raise RuntimeError('A completed-run integrity check failed; inspect audit.json.')
