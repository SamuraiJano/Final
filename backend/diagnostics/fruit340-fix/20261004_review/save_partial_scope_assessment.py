"""Record intentionally stopped wide-profile experiment without full-run claims."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
BENCH=ROOT/'diagnostics/authors-benchmark/runs'
PARTIAL=BENCH/'fruit340_native_3d_retry_author_profile_20261004'
old=json.loads((BENCH/'pixel_switch_trace_author_profile_20261002/report.json').read_text())
files=sorted(PARTIAL.glob('*/*/result.json'))
tracks=[json.loads(p.read_text()) for p in files]
keys={(t['group'],t['object']) for t in tracks}
before=[t for t in old['tracks'] if (t['group'],t['object']) in keys]
progress=json.loads((OUT/'author_profile_progress.json').read_text())
parity=json.loads((OUT/'scoped_author_path_parity.json').read_text())
seconds=sum(t['seconds'] for t in tracks)
previous_seconds=sum(t['seconds'] for t in before)
report={
    'run_status':'stopped_partial_on_request',
    'stop_reason':'Root scoped the final native retry to dense max_pair_angle_deg<=20. The exploratory55-degree benchmark is outside final production behavior and was explicitly stopped with Ctrl-C.',
    'process_exit_code':1,
    'full_benchmark_completed':False,
    'full_report_written':(PARTIAL/'report.json').exists(),
    'planned_sequences':36,
    'completed_sequences':len(tracks),
    'completed_by_group':{group:sum(t['group']==group for t in tracks) for group in ('mandarins','oranges','tomatoes')},
    'planned_correspondence_labels':497,
    'labels_associated_with_completed_sequences':sum((r['group'],r['object']) in keys for r in old['correspondences']),
    'aggregate_label_predictions_persisted':False,
    'full497_label_accuracy_claimed':False,
    'experiment_source_sha256':hashlib.sha256((PARTIAL/'algorithm_snapshot.py').read_bytes()).hexdigest(),
    'final_source_sha256':parity['source_sha256']['final'],
    'profile':old['settings'],
    'mask_threshold':old['mask_threshold'],
    'original_profile_settings_changed_in_final':parity['settings_changed'],
    'new_profile_settings_defaults':parity['settings_added'],
    'early20_sequence_timing':{'candidate_seconds':590.6674026000255,'historical_same_sequences_seconds':185.30170179999914,'ratio':3.187598369914314,'elapsed_at_read_seconds':626.6025938987732},
    'completed_sequence_timing':{'candidate_seconds':seconds,'historical_same_sequences_seconds':previous_seconds,'ratio':seconds/previous_seconds,'last_completed_track_elapsed_seconds':max(p.stat().st_mtime for p in files)-(PARTIAL/'algorithm_snapshot.py').stat().st_ctime},
    'timing_limitation':'Historical and current runs occurred at different times, with concurrent current workloads. This is not an isolated speed benchmark. The added3D retry work and approximately3x measured runtime justify avoiding unvalidated55-degree default behavior.',
    'previously_accepted_pair_results_unchanged':progress['common_ok_pair_exact_rotation'],
    'previously_accepted_pair_results_changed':progress['common_ok_pair_changed_rotation'],
    'experimental_new_direct_rescues':progress['changed_pairs'],
    'experimental_changed_maps':progress['changed_maps'],
    'final_scoped_sample_pair_count':len(parity['cases']),
    'final_scoped_sample_results_bit_identical':parity['all_pair_results_bit_identical'],
    'final_scoped_sample_new3d_call_count':parity['new_3d_call_count'],
}
(OUT/'partial_author_scope_assessment.json').write_text(json.dumps(report,indent=2))
(PARTIAL/'PARTIAL_STATUS.json').write_text(json.dumps({k:v for k,v in report.items() if k not in ('experimental_new_direct_rescues','experimental_changed_maps')},indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('profile','experimental_new_direct_rescues','experimental_changed_maps')},indent=2))
