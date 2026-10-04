"""Bundle exact hybrid-source tests and preserve rejected development evidence.

This copies frozen records and draws summary figures. It never runs models,
changes algorithm code or treats missing measurements as zero-error predictions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path
import re
import shutil
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from build_algorithm_revision_evidence import read_json, save_json, sha256, table


BACKEND = Path(__file__).resolve().parent
DIAGNOSTICS = BACKEND/'diagnostics'
EXPECTED = '951b55a4912d3147d349282846e2e02d20159a410b6bb2e8fdd4ab4dd3abea2d'
PREVIOUS = '863fd09cfa629c5b5b8ba7c73963fbe993441b3e3dd989f1e451d0a5f62c9db1'
ALLOWED = {'.json', '.py', '.snapshot', '.md', '.txt', '.csv', '.png', '.pdf', '.npz', '.html'}
AUTHOR = 'authors-benchmark/runs/hybrid_photometric_profile_20261002'
RETAINED = 'authors-benchmark/bridge_runs/hybrid_photometric_retained_20261002'
MOTION = 'algorithm-revision/hybrid_motion_controls_20261002'
TURN = 'algorithm-revision/full_turn_hybrid_20261002'
FIXED = 'algorithm-revision/fixed_hybrid_conveyor_20261002'
MODEL = 'algorithm-revision/real_segmenter_hybrid_20261002'
AREA = 'authors-benchmark/synthetic_runs/hybrid_photometric_20261002'
SOFTWARE = 'software-checks/hybrid_photometric_20261002'
EQUIVALENCE = 'algorithm-revision/photometric_equivalence_20261002'
PROFILES = {
    'hybrid': {'author': AUTHOR, 'retained': RETAINED, 'motion': MOTION, 'turn': TURN,
               'fixed': FIXED, 'model': MODEL, 'software': SOFTWARE, 'api': 'full_hybrid_20261002', 'transverse': 10.0},
    'wobble': {'author': 'authors-benchmark/runs/hybrid_wobble_profile_20261002',
               'retained': 'authors-benchmark/bridge_runs/hybrid_wobble_retained_20261002',
               'motion': 'algorithm-revision/hybrid_wobble_controls_20261002',
               'turn': 'algorithm-revision/full_turn_hybrid_wobble_20261002',
               'fixed': 'algorithm-revision/fixed_hybrid_wobble_conveyor_20261002',
               'model': 'algorithm-revision/real_segmenter_wobble_20261002',
               'software': 'software-checks/service_wobble_20261002',
               'api': 'full_hybrid_wobble_20261002', 'transverse': 20.0},
}


def build(label='evidence_hybrid_20261002', refresh=False, profile='hybrid'):
    config = PROFILES[profile]
    AUTHOR, RETAINED, MOTION, TURN, FIXED, MODEL, SOFTWARE = [config[key] for key in
        ('author', 'retained', 'motion', 'turn', 'fixed', 'model', 'software')]
    final_api_label = config['api']
    wobble = profile == 'wobble'
    if not re.fullmatch(r'[A-Za-z0-9_-]+', label):
        raise ValueError('Use a simple folder label')
    output = DIAGNOSTICS/'algorithm-revision'/label
    if output.exists() and not refresh:
        raise FileExistsError('Evidence exists; use --refresh to update generated reporting')
    output.mkdir(parents=True, exist_ok=True)
    copied, canonical_npz, aliases = [], {}, []

    def copy_file(source, relative):
        source, relative = Path(source), Path(relative)
        if not source.is_file():
            raise FileNotFoundError(source)
        digest = sha256(source)
        if source.suffix == '.npz':
            if digest in canonical_npz:
                aliases.append({'original_bundle_path': relative.as_posix(),
                                'stored_once_at': canonical_npz[digest], 'sha256': digest})
                return
            canonical_npz[digest] = relative.as_posix()
        destination = output/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append({'source': str(source.relative_to(BACKEND.parent)),
                       'bundle_path': relative.as_posix(), 'sha256': digest})

    def copy_collection(relative):
        folder = DIAGNOSTICS/relative
        if not folder.is_dir():
            raise FileNotFoundError(folder)
        for source in sorted(folder.rglob('*')):
            if source.is_file() and source.suffix in ALLOWED and '__pycache__' not in source.parts:
                copy_file(source, Path(relative)/source.relative_to(folder))

    primary = [FIXED, MOTION, TURN, MODEL, AUTHOR, AREA, SOFTWARE, EQUIVALENCE,
               'algorithm-revision/hybrid_photometric_source']
    for relative in primary:
        copy_collection(relative)
    author, motion, turn, model, area, software, equivalence = [read_json(output/relative/'report.json')
        if relative != SOFTWARE else read_json(output/relative/'summary.json')
        for relative in (AUTHOR, MOTION, TURN, MODEL, AREA, SOFTWARE, EQUIVALENCE)]
    for name, report in [('author', author), ('motion', motion), ('turn', turn), ('model', model),
                         ('area', area), ('equivalence', equivalence)]:
        if report['algorithm_sha256'] != EXPECTED:
            raise ValueError(f'{name} execution source differs from the final hybrid source')
    fixed = read_json(output/FIXED/'report.json')
    if fixed['source_sha256']['adjacent_native.py'] != EXPECTED:
        raise ValueError('Fixed crops did not test the hybrid source')
    if software['source_sha256']['backend/algorithm.py'] != EXPECTED or any(row['exit_code'] for row in software['checks']):
        raise ValueError('Required software checks failed or tested another source')
    if wobble and software['source_sha256']['backend/main.py'] != sha256(BACKEND/'main.py'):
        raise ValueError('The tested main profile differs from the current conveyor settings')
    if wobble and (model['settings']['transverse_angle_deg'] != 20.0
                   or model['source_sha256']['main.py'] != software['source_sha256']['backend/main.py']):
        raise ValueError('Actual segmentation execution does not match the tested conveyor profile')
    if not motion['all_controls_passed'] or not equivalence['all_checks_passed']:
        raise ValueError('Final motion/equivalence controls did not pass')
    if not all(row['summary']['motion_control_pass'] and row['summary']['clear_map_control_pass'] for row in turn['cases'].values()):
        raise ValueError('Final actual-matcher full-turn controls did not pass')
    test_count = int(re.search(r'Ran (\d+) tests', (output/SOFTWARE/'python_tests.txt').read_text(encoding='utf-8')).group(1))

    retained = None
    if (DIAGNOSTICS/RETAINED/'report.json').is_file():
        retained = read_json(DIAGNOSTICS/RETAINED/'report.json')
        if retained['algorithm_sha256'] != EXPECTED:
            raise ValueError('Retained-label audit uses another source')
        copy_collection(RETAINED)
    history = ['algorithm-revision/full_turn_observable_20261002',
        'algorithm-revision/full_turn_native_20261002', 'algorithm-revision/full_turn_green_20261002',
        'algorithm-revision/full_turn_green_smoothed_20261002',
        'algorithm-revision/photometric_motion_controls_20261002',
        'algorithm-revision/photometric_smoothed_controls_20261002',
        'algorithm-revision/photometric_candidate_source', 'algorithm-revision/photometric_smoothed_source',
        'algorithm-revision/photometric_objective_20261002',
        'algorithm-revision/observable_motion_controls_20261002',
        'algorithm-revision/extended_motion_controls_20261002',
        'algorithm-revision/native_prefilter_trials_20261002',
        'algorithm-revision/motion_resolution_20261002', 'algorithm-revision/motion_resolution_scaled_20261002',
        'algorithm-revision/native_all_20261002', 'algorithm-revision/geometry_scale_audit_20261002',
        'algorithm-revision/grabcut_threads_20261002', 'algorithm-revision/adjacent_observable_source',
        'authors-benchmark/runs/photometric_green_profile_20261002',
        'authors-benchmark/runs/adjacent_observable_profile_20261002',
        'authors-benchmark/bridge_runs/adjacent_observable_retained_20261002',
        'software-checks/observable_motion_20261002']
    if wobble:
        history += [PROFILES['hybrid'][key] for key in ('author', 'retained', 'motion', 'turn', 'fixed', 'model', 'software')]
        history.append('software-checks/hybrid_wobble_20261002')
        primary += ['algorithm-revision/large_transverse_truth_20261002',
                    'algorithm-revision/transverse_author_comparison_20261002',
                    'algorithm-revision/debug_fruit_98_wobble_20261002',
                    'ui-checks/walkthrough_wobble_20261002']
        for relative in primary[-4:]:
            copy_collection(relative)
        horizontal_relative = 'algorithm-revision/full_turn_x12_wobble_20261002'
        if (DIAGNOSTICS/horizontal_relative/'report.json').is_file():
            primary.append(horizontal_relative)
            copy_collection(horizontal_relative)
        if author['settings']['transverse_angle_deg'] != 20.0:
            raise ValueError('The final author profile did not test a twenty-degree transverse bound')
        if any(case['result']['settings']['transverse_angle_deg'] != 20.0 for case in motion['cases'].values()):
            raise ValueError('The final motion controls did not test the widened bound')
        if any(case['settings']['transverse_angle_deg'] != 20.0 for case in turn['cases'].values()):
            raise ValueError('The final full-turn controls did not test the widened bound')
    for relative in history:
        copy_collection(relative)
    for relative in ['authors-benchmark/runs/operational_profile_v1/report.json',
                     'authors-benchmark/source_manifest.json',
                     'algorithm-revision/resolution_preprocess_trials_20261002.json']:
        copy_file(DIAGNOSTICS/relative, relative)
    service_checks = None
    if wobble:
        copy_file(DIAGNOSTICS/'algorithm-revision/transverse_bound_probe_20261002.json',
                  'algorithm-revision/transverse_bound_probe_20261002.json')
        for filename in ('wobble_refresh_fixed.json', 'wobble_refresh_response.json'):
            copy_file(DIAGNOSTICS/'algorithm-revision/service_20261002'/filename,
                      Path('algorithm-revision/service_20261002')/filename)
        copy_file(DIAGNOSTICS/'authors-benchmark/DEVELOPMENT_LOG.md', 'source/DEVELOPMENT_LOG.md')
        service_checks_path = DIAGNOSTICS/'software-checks/service_wobble_20261002/summary.json'
        if service_checks_path.is_file():
            service_checks = read_json(service_checks_path)
            if any(row['exit_code'] for row in service_checks['checks']):
                raise ValueError('Final service implementation checks failed')
            if SOFTWARE != 'software-checks/service_wobble_20261002':
                copy_collection('software-checks/service_wobble_20261002')
    for filename in ('rotation_LICENSE', 'maps_LICENSE'):
        copy_file(DIAGNOSTICS/'authors-benchmark/evidence_20261002/source_licenses'/filename,
                  Path('author_provenance')/filename)
    source_names = ['ALGORITHM_EXPLAINED.md', 'algorithm.py', 'main.py', 'dfine_segmenter.py',
        'benchmark_authors.py', 'validate_author_bridges.py', 'validate_algorithm_revision.py',
        'validate_model_mapping_integration.py', 'validate_synthetic_mapping.py', 'validate_software_checks.py',
        'validate_full_turn_motion.py', 'validate_motion_resolution.py', 'validate_extended_motion_controls.py',
        'validate_native_prefilter.py', 'validate_observable_motion.py', 'validate_photometric_motion_controls.py',
        'validate_photometric_equivalence.py', 'validate_photometric_objective.py', 'validate_grabcut_threads.py',
        'build_algorithm_revision_evidence.py', 'build_hybrid_revision_evidence.py']
    if wobble:
        source_names += ['validate_large_transverse_motion.py', 'compare_transverse_author_profiles.py',
                         'build_fruit_walkthrough.py', 'validate_fruit_walkthrough.py', 'requirements.txt']
    for filename in source_names:
        copy_file(BACKEND/filename, Path('source')/filename)
    if sha256(output/'source/algorithm.py') != EXPECTED:
        raise ValueError('Workspace algorithm changed after the captured tests')
    for source in sorted(BACKEND.glob('test_*.py')):
        copy_file(source, Path('source')/source.name)
    copy_file(BACKEND.parent/'README.md', 'source/README.md')
    if wobble:
        for filename in ('dev.mjs', 'stop_process_tree.py'):
            copy_file(BACKEND.parent/'scripts'/filename, Path('source/scripts')/filename)
        for relative in ('scripts/dev.mjs', 'scripts/stop_process_tree.py', 'backend/requirements.txt'):
            if sha256(BACKEND.parent/relative) != software['source_sha256'][relative]:
                raise ValueError('Captured service helper differs from the final software checks')

    api_records = {}
    for api_label, expected in [('full_revised_20261002', None), ('full_observable_20261002', PREVIOUS),
                                ('full_hybrid_20261002', EXPECTED),
                                *([('full_hybrid_wobble_20261002', EXPECTED)] if wobble else [])]:
        folder = DIAGNOSTICS/'api-runs'/api_label
        if not folder.is_dir():
            api_records[api_label] = {'state': 'not_started_or_no_retained_request'}
            continue
        copy_collection(f'api-runs/{api_label}')
        summary_path = folder/'summary.json'
        summary = read_json(summary_path) if summary_path.is_file() else None
        if summary and summary.get('finished_at'):
            job = BACKEND/'results'/str(summary['job_id'])
            if job.resolve().parent != (BACKEND/'results').resolve():
                raise ValueError('Invalid API job identifier')
            actual = sha256(job/'algorithm.py.snapshot')
            if expected is not None and actual != expected:
                raise ValueError('API execution source differs from its assigned run')
            if wobble and api_label == final_api_label and sha256(job/'main.py.snapshot') != software['source_sha256']['backend/main.py']:
                raise ValueError('Final API main snapshot does not match the tested twenty-degree profile')
            api_records[api_label] = {'state': 'completed', 'algorithm_sha256': actual, 'summary': summary}
            for filename in ('metrics.json', 'algorithm.py.snapshot', 'main.py.snapshot', 'dfine_segmenter.py.snapshot'):
                if (job/filename).is_file():
                    copy_file(job/filename, Path('api_examples')/api_label/filename)
            rows = [(float(read_json(path).get('observed_longitude_deg') or 0.), path) for path in job.glob('*/result.json')]
            for _, path in sorted(rows, key=lambda item: item[0], reverse=True)[:4]:
                destination = Path('api_examples')/api_label/path.parent.name
                copy_file(path, destination/path.name)
                for picture in path.parent.glob('*.png'):
                    copy_file(picture, destination/picture.name)
        elif (folder/'interruption.json').is_file():
            api_records[api_label] = {'state': 'interrupted_incomplete', 'interruption': read_json(folder/'interruption.json')}
        else:
            api_records[api_label] = {'state': 'pending_incomplete'}
    final_api = api_records[final_api_label]
    api_complete = final_api['state'] == 'completed'

    baseline = read_json(output/'authors-benchmark/runs/operational_profile_v1/report.json')
    previous = read_json(output/'authors-benchmark/runs/adjacent_observable_profile_20261002/report.json')
    rejected = read_json(output/'authors-benchmark/runs/photometric_green_profile_20261002/report.json')
    author_rows, rms_values, returned, within = [], [], [], []
    comparison_profiles = [('Previous operational', baseline), ('Prior observable 863', previous),
                           ('Rejected native original green 46a46', rejected)]
    if wobble:
        comparison_profiles.append(('Hybrid 951b55 transverse 10', read_json(output/PROFILES['hybrid']['author']/'report.json')))
    comparison_profiles.append((f'Final hybrid 951b55 transverse {config["transverse"]:g}', author))
    for name, report in comparison_profiles:
        stats = report['summary']['all']; errors = stats['errors_px_conditional_on_prediction']
        author_rows.append([name, f"{stats['predicted_correspondences']}/497", f"{errors['rms']:.5f}",
                            f"{errors['within_5px']}/497", f"{errors['max']:.5f}"])
        rms_values.append(errors['rms']); returned.append(stats['predicted_correspondences']); within.append(errors['within_5px'])
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    labels = ['Previous\noperational', 'Observable\n863', 'Rejected native\noriginal green']
    if wobble:
        labels.append('Hybrid 951\ntransverse 10')
    labels.append(f'Final hybrid 951\ntransverse {config["transverse"]:g}')
    colors = ['#8a9289', '#d09247', '#ac503b'] + (['#799a6d'] if wobble else []) + ['#267a4e']
    axes[0].bar(labels, rms_values, color=colors); axes[0].set(ylabel='Conditional returned-label RMS (pixels)')
    x = list(range(len(labels))); axes[1].bar([v-.18 for v in x], returned, .36, label='Returned predictions', color='#267a4e')
    axes[1].bar([v+.18 for v in x], within, .36, label='Within 5 pixels', color='#d09247')
    axes[1].set(xticks=x, xticklabels=labels, ylabel='Correspondences / all 497 labels', ylim=(0, 520)); axes[1].legend(fontsize=8)
    for panel in axes: panel.grid(axis='y', alpha=.2)
    fig.suptitle('All 36 author sequences: report accuracy together with prediction availability')
    fig.tight_layout(); fig.savefig(output/'author_comparison.png', dpi=300); fig.savefig(output/'author_comparison.pdf'); plt.close(fig)

    publication_rows, publication_record = [], []
    for group, published_rms in [('mandarins', 6.5), ('oranges', 2.53), ('tomatoes', 5.2)]:
        stats = author['summary'][group]; errors = stats['errors_px_conditional_on_prediction']
        publication_rows.append([group.title(), f'{published_rms:g}', f"{errors['rms']:.3f}",
                                 f"{stats['predicted_correspondences']}/{stats['labelled_correspondences']}"])
        publication_record.append({'group': group, 'published_table4_rms_px': published_rms,
            'independent_hybrid_conditional_rms_px': errors['rms'],
            'returned_predictions': stats['predicted_correspondences'],
            'available_published_labels': stats['labelled_correspondences']})
    save_json(output/'publication_table4_comparison.json', {
        'source': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/', 'section': '4.2, Table 4',
        'verified_at': '2026-10-02', 'paper_reported_correspondences_per_fruit_class': 'approximately 200',
        'algorithm_sha256': EXPECTED, 'comparison': publication_record,
        'scope': 'Independent implementation and different prediction/annotation denominators; '
                 'contextual comparison only, not reproduction or a claim of beating publication accuracy.'})
    fig, axis = plt.subplots(figsize=(10, 5))
    axis.bar([index-.18 for index in range(3)], [row['published_table4_rms_px'] for row in publication_record], .36,
             label='Published Table 4: approximately 200 labels per class', color='#8a9289')
    axis.bar([index+.18 for index in range(3)], [row['independent_hybrid_conditional_rms_px'] for row in publication_record], .36,
             label='Independent hybrid: returned predictions only', color='#267a4e')
    axis.set(xticks=list(range(3)), xticklabels=[f"{row['group'].title()}\n{row['returned_predictions']}/{row['available_published_labels']} returned"
             for row in publication_record], ylabel='RMS reprojection error (pixels)', ylim=(0, 8.5))
    axis.legend(fontsize=8); axis.grid(axis='y', alpha=.2)
    axis.set_title('Publication context: different evaluation scopes, not reproduced accuracy')
    fig.text(.5, .02, 'Unavailable predictions are excluded from this implementation\'s conditional RMS.', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1)); fig.savefig(output/'publication_table4_context.png', dpi=300)
    fig.savefig(output/'publication_table4_context.pdf'); plt.close(fig)

    motion_rows = []
    for name, case in motion['cases'].items():
        stats = case['result']['summary']; stationary = case['stationary']
        motion_rows.append([name, f"{stats['measured_pairs']}/{stats['input_pairs']}",
                           'unavailable' if stationary else f"{stats['endpoint_pose_error_deg']:.3f}",
                           'unavailable' if stationary else f"{stats['maximum_landmark_rms_px']:.3f}",
                           case['result']['mapping']['status']])
    turn_rows = [[name, f"{case['summary']['measured_pairs']}/{case['summary']['input_pairs']}",
                  f"{case['summary']['maximum_pose_error_deg']:.3f}", f"{case['summary']['maximum_landmark_rms_px']:.3f}",
                  case['mapping']['grade'], 'PASS'] for name, case in turn['cases'].items()]
    track_rows = []
    for track in fixed['tracks']:
        row = next(item for item in track['variants'] if item['name'] == 'adjacent_native')
        frames = row['selected_frames']
        track_rows.append([track['track'], track['input_count'], len(frames), f'{frames[0]}–{frames[-1]}',
                           f"{row['longitude_deg']:.2f}", row['status']])
    area_rows = [[f"{row['expected_pct_of_observed']:.0f}%", f"{row['measured_pct_of_observed']:.5f}%",
                 f"{row['absolute_error_percentage_points']:.5f}", row['grade']] for row in area['cases']]
    map_counts = Counter(track['map'].get('result_status', 'mapping_failed') for track in author['tracks'])
    retained_text = 'The final retained-map author-label audit is pending; earlier source results are historical only.'
    if retained is not None:
        stats = retained['summary']['original_published_labels']; errors = stats['errors_px_conditional_on_prediction']
        retained_text = (f"The final retained-map audit returns {stats['returned_predictions']}/497 original labels, "
            f"conditional RMS {errors['rms']:.5f} pixels, with {errors['within_5px']}/497 within five pixels. "
            f"It creates {retained['summary']['nonadjacent_selected_bridges']} nonadjacent bridges. This subset is "
            'selected by the algorithm and has a different denominator from independent pair scoring; unavailable '
            'labels are not silently removed. Exact chained labels are correlated with the published annotations.')
    profile_intro = ('It preserves approximately the earlier author-label accuracy while fixing the demonstrated '
                     'ideal full-turn drift. The four fixed real conveyor examples remain partial.')
    author_transition_text = ('The hybrid returns slightly fewer independent predictions than the prior profiles; '
        'the conditional RMS is approximately unchanged on a different returned subset. '
        'This does not show a general accuracy improvement.')
    profile_setup_text = ''
    large_transverse_text = ''
    fixed_description = ('All four remain below the 350-degree longitude gate and receive no grade. More '
        'coverage, an ordered map, or a low matching residual does not establish correct '
        'surface geometry. Independently marked conveyor landmarks and verified turns '
        'are needed to score field motion and map accuracy.')
    model_description = ('Actual masks, overlays and partial maps are retained. All four remain partial and '
        'ungraded. This verifies model execution and mapper/report connection; no defect-mask or '
        'grade truth is available to score accuracy.')
    service_text = ''
    walkthrough_text = ''
    common_label_comparison = None
    strict_transverse = None
    horizontal_turn = None
    horizontal_turn_failed = False
    horizontal_turn_text = ''
    if wobble:
        common_label_comparison = read_json(output/'algorithm-revision/transverse_author_comparison_20261002/report.json')
        strict_transverse = read_json(output/'algorithm-revision/large_transverse_truth_20261002/report.json')
        if strict_transverse['algorithm_sha256'] != EXPECTED or strict_transverse['acceptance'] != {
                'pair_measured': True, 'pose_error_max_deg': 1.0, 'landmark_rms_max_px': 1.0}:
            raise ValueError('The original strict large-transverse criteria/source changed')
        common_rows = []
        for name, row in common_label_comparison['comparisons'].items():
            before, after = row['same_returned_labels_alpha10'], row['same_returned_labels_alpha20']
            availability = row['availability']
            common_rows.append([name, availability['both_returned'], f"{before['rms']:.5f}", f"{after['rms']:.5f}",
                availability['newly_returned_alpha20'], availability['lost_alpha20']])
        profile_intro = ('The twenty-degree transverse search fixes a demonstrated clipped search boundary '
            'and allows frozen track 98 to meet coverage gates. It returns more author predictions, '
            'with mixed accuracy changes. An additional strict large-transverse probe fails one of four '
            'cases at the one-degree/one-pixel limits. Those errors are retained.')
        author_transition_text = ('Widening the bound returns 462/497 independent predictions instead of '
            '455/497. Conditional RMS rises from 5.10965 to 5.39868 pixels on the different subsets; '
            'the maximum rises from 35.93046 to 39.55996 pixels. On the same 455 returned labels, '
            'RMS slightly falls from 5.10965 to 5.08041 pixels; 17 labels improve, seven worsen and '
            '431 are unchanged. All seven newly available labels remain in the final counts. '
            'Retained-map accuracy has a different tradeoff: on the same 344 returned labels, '
            'RMS rises from 4.99766 to 5.22752 pixels, with 24 newly returned labels and four lost. '
            'More predictions and coverage do not establish a general accuracy improvement.\n\n'
            + table(['Same labelled subset', 'Common labels', 'Alpha 10 RMS, px', 'Alpha 20 RMS, px', 'Newly returned', 'Lost'], common_rows)
            + '\n\n[Exact same-label comparison](algorithm-revision/transverse_author_comparison_20261002/SAME_LABEL_COMPARISON.md). '
            'The 39.55996-pixel error is mandarins/obj0004, annotation line 61, and appears in both '
            'the independent and retained results. Its actual image evidence is preserved.\n\n'
            '![Worst returned author error](algorithm-revision/transverse_author_comparison_20261002/independent_pairs_worst_alpha20.png)')
        profile_setup_text = ('The conveyor profile widens the transverse search bound from ten to twenty '
            'degrees. The [2021 paper, Section 3.2](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) '
            'describes ten degrees as typical; twenty degrees is our engineering adaptation to this '
            'setup. It does not relax the 0.58 residual limit, quarter-degree observable motion or '
            'coverage gates. The fixed track 98 pair 85→86 was clipped at the old ten-degree '
            'boundary: residual 0.61674. With a twenty-degree search it finds approximately '
            '[11.013, −13.222, 0] degrees, residual 0.37731. Another rejected pair 65→66 remains '
            'rejected. The diagnostic probe temporarily disables residual rejection only to inspect '
            'failed minima; those ungated results are not accepted as production motion or ground '
            'truth. [Bound diagnostic](algorithm-revision/transverse_bound_probe_20261002.json).\n')
        transverse_rows = []
        for name, row in strict_transverse['cases'].items():
            for bound, variant in row['bounds'].items():
                stats = variant['result']['summary']
                transverse_rows.append([name, bound, f"{stats['endpoint_pose_error_deg']:.3f}",
                    f"{stats['endpoint_landmark_rms_px']:.3f}", 'PASS' if variant['passed'] else 'FAIL'])
        large_transverse_text = ('## Additional strict large-transverse probe\n\n'
            'Four independently rendered pairs use the two textures, eleven-degree rolling and '
            'both signs of thirteen-degree transverse motion. The same analytical pose and six '
            'projected landmarks score both search bounds. Before the first run, this probe declares '
            'one degree pose error and one pixel landmark RMS, stricter than the separate full-turn '
            'five-degree/five-pixel controls. The original strict report remains unchanged.\n\n'
            + table(['Known pair', 'Transverse bound, deg', 'Pose error, deg', 'Landmark RMS, px', 'Strict control'], transverse_rows)
            + '\n\nAll eight estimates are returned. At twenty degrees, three of four pairs pass; '
            'texture A with negative transverse motion still fails at 3.26551 degrees / 2.88357 '
            'pixels. The wider bound improves three cases substantially but does not generally '
            'validate large-wobble accuracy or field motion. No thresholds are relabelled to hide '
            'the strict failure. [Original probe](algorithm-revision/large_transverse_truth_20261002/LARGE_TRANSVERSE_TRUTH.md).\n\n'
            '![Strict transverse geometry results](algorithm-revision/large_transverse_truth_20261002/large_transverse_truth.png)\n')
        fixed_description = ('Track 98 retains 24 adjacent frames 66–89 and reaches 360 degrees observed '
            'longitude and about 85.31% surface coverage. This geometry-only fixture has no defect '
            'observations and correctly reports missing_defect_masks, with no grade. Tracks 1, 14 '
            'and 491 remain partial. The same fixed inputs and rejection gates are used. More '
            'coverage, an ordered map or a low residual does not establish correct field surface '
            'geometry; independent conveyor landmarks and verified turns are still required.')
        model_description = ('Actual masks, overlays and maps are retained. Track 98 produces Class 1 '
            'after meeting coverage and complete defect-observation gates; the other three tracks '
            'remain partial and ungraded. Class 1 is an execution result under the configured '
            '10%/20% boundaries, not a verified grade. This tests model execution and '
            'mapper/report connection; no defect-mask, field pose or grade truth is available.')
        service_text = ('Backend refresh initially returned an access-denied failure. The service helper '
            'now stops its owned child process tree through psutil before restarting. An actual '
            'managed refresh returned HTTP 200, with replaced backend/worker process IDs and the '
            'prior processes no longer alive. The failed response and successful process evidence '
            'are retained separately; this verifies service restart, not reconstruction accuracy. '
            '[Successful refresh](algorithm-revision/service_20261002/wobble_refresh_fixed.json), '
            '[prior failure](algorithm-revision/service_20261002/wobble_refresh_response.json).\n\n'
            + ('Final service implementation checks are included in [service software checks](software-checks/service_wobble_20261002/summary.json).'
               if service_checks else 'The separate final service software capture is pending.'))
        walkthrough_text = ('## Follow one real naartjie step by step\n\n'
            'The [interactive track-98 debugger](algorithm-revision/debug_fruit_98_wobble_20261002/index.html) '
            'shows all 65 adjacent input pairs, actual masks, accepted/unavailable decisions, source '
            'and target crops, retained frames, the map and three actual model overlays. It compares '
            'the old ten-degree and new twenty-degree bound. Entry/last-seen tracking images and '
            'the donor source are recorded: these detector/tracker observations come from the prior '
            '863 full-video run, while the displayed revised motion uses source951 on the frozen '
            'inputs. It is an illustrative replay, not a fresh completed final-video validation.\n\n'
            'Isolated headless Edge checks load all 65 pair images, Next/Previous navigation, the '
            'mask toggle and all three model overlays with zero JavaScript errors. '
            '[Browser check record](ui-checks/walkthrough_wobble_20261002/report.json).\n\n'
            '![One-fruit processing steps](algorithm-revision/debug_fruit_98_wobble_20261002/one_fruit_steps.png)\n'
            '[Exportable step figure](algorithm-revision/debug_fruit_98_wobble_20261002/one_fruit_steps.pdf).\n')
        if (output/'algorithm-revision/full_turn_x12_wobble_20261002/report.json').is_file():
            horizontal_turn = read_json(output/'algorithm-revision/full_turn_x12_wobble_20261002/report.json')
            if horizontal_turn['algorithm_sha256'] != EXPECTED:
                raise ValueError('Horizontal-turn control source differs')
            horizontal_turn_failed = any(not case['summary']['motion_control_pass'] for case in horizontal_turn['cases'].values())
            horizontal_rows = [[name, f"{case['summary']['measured_pairs']}/{case['summary']['input_pairs']}",
                f"{case['summary']['maximum_pose_error_deg']:.3f}",
                f"{case['summary']['maximum_landmark_rms_px']:.3f}", case['mapping']['grade'],
                'PASS' if case['summary']['motion_control_pass'] else 'FAIL']
                for name, case in horizontal_turn['cases'].items()]
            horizontal_turn_text = ('## Horizontal twelve-degree complete turns fail\n\n'
                'An additional relevant control uses thirty known twelve-degree x-axis steps '
                'on each texture, matching horizontal conveyor rolling. The actual quarter/native '
                'matcher, sphere fit, pose composition and fusion run with the current eight-degree '
                'native recheck trigger and twenty-degree transverse bound. The same established '
                'five-degree maximum pose / five-pixel landmark RMS limits are used.\n\n'
                + table(['Known horizontal turn', 'Returned / attempted', 'Maximum pose error, deg',
                         'Maximum landmark RMS, px', 'All-clear arithmetic', 'Motion control'], horizontal_rows)
                + '\n\nBoth textures fail the motion criteria despite all sixty measurements, full '
                'maps and Class 1 outputs. Source951 with these settings cannot be called generally '
                'motion-accuracy validated. The full-looking maps do not prove correct reconstruction. '
                '[Original unchanged failure](algorithm-revision/full_turn_x12_wobble_20261002/FULL_TURN_CONTROLS.md).\n\n'
                '![Horizontal full-turn accuracy failure](algorithm-revision/full_turn_x12_wobble_20261002/full_turn_accuracy.png)\n')
    motion_statement = ('The current profile fails the additional twelve-degree horizontal full-turn '
        'motion controls, despite passing the earlier six-degree/subdegree controls. It remains a '
        'development profile with unresolved motion accuracy.' if horizontal_turn_failed else
        'The final hybrid source passes the short-motion, complete-turn, stationary observability and area controls.')
    api_text = ('The final hybrid full API run is pending. Its incomplete request, if present, is retained; '
                'no completed hybrid detector/tracker/video outcome is claimed. The old observable-source run '
                'is recorded separately and cannot count as final hybrid validation.')
    if api_complete:
        summary = final_api['summary']
        api_text = (f"The final hybrid API run finished at {summary['finished_at']}. It produced {summary['fruits']} "
            f"tracked report records: statuses `{json.dumps(summary['statuses'])}`; grades `{json.dumps(summary['grades'])}`. "
            'These are execution outcomes, not independently verified unique-fruit counts or accurate grades. '
            'The job execution snapshot is verified against exact source 951b55 and useful output images are retained.')

    report = f"""# Algorithm revision: testing and evidence

Built {datetime.now(timezone(timedelta(hours=2))).isoformat()}.
Status: **{'completed hybrid full API run included' if api_complete else 'draft; final hybrid full API run pending'}**.

**{motion_statement}**
{profile_intro} General
conveyor motion, segmentation and grade accuracy are not established by these tests.

Exact execution source SHA256: `{EXPECTED}`. Detection and segmentation weights
are unchanged. [Simple code explanation](source/ALGORITHM_EXPLAINED.md).

The spheroid shape, 3D texture lifting, rotation search, matrix propagation and
surface-area calculation follow the research papers. The paper's quarter-resolution
high-pass MAD remains the normal matcher. A successful coarse turn below eight
degrees is rechecked at original resolution using smoothed green-channel MAD and
median brightness-offset compensation. A disagreement above three degrees rejects
the transition. Failed or unobservable transitions end a connected sequence;
missing poses are never assumed to be zero or joined by a replacement bridge.
These native rechecks and conservative selection are explicit engineering adaptations.

{profile_setup_text}

## Author data and labelled point accuracy

All 578 original images in 36 sequences (15 mandarins, 10 oranges, 11 tomatoes)
and all 497 published correspondences are used. Labels only score predictions;
they do not fit motion. Masks are derived from nonblack backgrounds. These images
were inspected during development and are not held-out evaluation.

{table(['Source/profile', 'Returned / labels', 'Conditional RMS, px', 'Within 5 px / all labels', 'Maximum returned error, px'], author_rows)}

{author_transition_text}

The native original-green
replacement is rejected because author accuracy substantially worsens.
Final author maps: `{json.dumps(dict(map_counts))}`. Coverage-eligible maps have no
author defect truth and cannot validate grades.

For publication context, the [2021 paper, Section 4.2 and Table 4](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
reports the following pixel reprojection RMS values. The authors describe about
200 point correspondences per fruit class. The public annotation files evaluated
here contain 132/179/186 labels (497 total), with {'/'.join(str(author['summary'][group]['predicted_correspondences']) for group in ('mandarins', 'oranges', 'tomatoes'))} returned predictions.

{table(['Fruit class', 'Published Table 4 RMS, px', 'Independent hybrid conditional RMS, px', 'Returned / available labels'], publication_rows)}

The returned prediction denominator, rejection gates, shape/profile choices and
independent implementation differ from the publication. Conditional error on
returned predictions omits unavailable ones. These values are a contextual
comparison; they do not establish reproduction of the published evaluation or
that this implementation beats its accuracy.

![Publication context with prediction denominators](publication_table4_context.png)
[Publication comparison provenance](publication_table4_comparison.json).

{retained_text}

![Author accuracy and availability](author_comparison.png)
[Exact author record]({AUTHOR}/report.json).

## Independently known motion and unavailable stationary motion

The actual fitted sphere, matcher, matrix propagation and selector execute on
the SAME four archived NPZ scenes used for the previous candidates. Two different
analytic body textures undergo ten known noncommuting x/y wobble steps. Six
independently projected visible landmarks score the complete measured chain.
Moving controls require all ten pairs, endpoint error at most one degree and
every landmark RMS at most one pixel; these limits are unchanged.

{table(['Known scene', 'Returned / attempted', 'Endpoint pose error, deg', 'Maximum visible-landmark RMS, px', 'Mapping outcome'], motion_rows)}

Each stationary scene contains 120 frames with independently sampled pixel noise.
All 119 dominant-turn measurements per texture are unavailable, after 119 native
attempts, with null endpoints and no map or grade. The helper's maximum pose/RMS
of zero comes ONLY from the frame-zero reference scaffold. It is not estimated
zero stationary error, and none of the 238 rejected pairs is scored as zero.
The quarter-degree observability bound is unchanged.

Two unsaturated global +10 gray offsets on the second image only preserve
estimated geometry and residual under the predeclared 0.01-degree/0.00001
invariance limits. Both original and shifted pairs also meet one-degree/one-pixel
known-geometry criteria. [Motion and exposure record]({MOTION}/PHOTOMETRIC_MOTION_CONTROLS.md).

![Moving geometry]({MOTION}/observable_moving_accuracy.png)
![Actual stationary outcomes]({MOTION}/stationary_observability.png)
![Exposure invariance]({MOTION}/brightness_offset_invariance.png)

## Actual matcher over complete known turns

These controls execute the real geometry fit, two-axis image matcher, pose
composition, selector and surface fusion, with no mocked rotations. Texture A
has sixty six-degree steps; texture B has 120 alternating 0.6/5.4-degree steps.
Thirty-six known spherical landmarks are scored whenever front-visible. Perfect
masks and analytical camera geometry isolate motion from detector errors. Limits
are predeclared at five degrees maximum pose error and five pixels landmark RMS.

{table(['Complete known turn', 'Returned / attempted', 'Maximum pose error, deg', 'Maximum front-visible RMS, px', 'All-clear class arithmetic', 'Motion control'], turn_rows)}

Both ideal complete-turn controls pass and all 180 transitions are measured.
Their all-clear masks test zero-defect class arithmetic, not the real segmentation
model or general real-fruit grading accuracy. [Complete-turn record]({TURN}/FULL_TURN_CONTROLS.md).

![Actual full-turn geometry]({TURN}/full_turn_accuracy.png)

{horizontal_turn_text}

{large_transverse_text}

## Frozen real conveyor inputs and the user's segmentation model

The exact 215 detector/tracker crops and fruit masks of tracks 98, 1, 14 and 491
are held fixed across variants. They are selected development cases, not a
random or held-out sample. Detection, tracking, GrabCut and neural inference are
not rerun in this geometry comparison. No independent conveyor motion truth is available.

{table(['Track', 'Input views', 'Retained views', 'Original frames', 'Observed longitude, deg', 'Result'], track_rows)}

{fixed_description}

The separate real D-FINE integration executes {model['segmentation']['calls']} model
calls and returns {model['segmentation']['instances']} defect instances on those
same frozen crops. {model_description} Detection,
tracking and GrabCut are not recomputed in that isolated segmentation run.
Mean segmentation latency is {model['segmentation']['mean_latency_ms']:.1f} ms;
mean confidence {100*model['segmentation']['mean_confidence']:.1f}% is model certainty,
not measured accuracy.

![Real conveyor comparison]({FIXED}/fixed_input_comparison.png)
[Actual model record]({MODEL}/report.json).

{walkthrough_text}

## Area arithmetic, implementation checks and full-video execution

Known defect longitude wedges are projected with exact geometry and supplied
rotations. This control intentionally bypasses the image matcher and neural
models; it verifies repeated-defect union and spherical area normalization.

{table(['Known observed defect area', 'Measured', 'Absolute error, percentage points', 'Configured class'], area_rows)}

Coverage controls also pass: known 250- and 100-degree turns stay partial.
The configured 10%/20% class boundaries are engineering rules, not published
author validation of conveyor grades.
{'This area-only control is reused from the earlier ten-degree hybrid profile: it tests the same source951 fusion code with supplied exact rotations, bypassing the transverse image search.' if wobble else ''}

All {test_count} Python tests, frontend build and lint pass, with commands,
timestamps, output and exact source hashes retained in [{SOFTWARE}]({SOFTWARE}/summary.json).
New checks cover brightness-offset invariance, scalar/batch agreement, all-invalid
hypotheses without NaN warnings, native recheck settings, disagreement rejection
and preservation of the paper matcher for larger motion. Existing failure/no-bridge
and native-failure checks remain. [Legacy-profile equivalence]({EQUIVALENCE}/PHOTOMETRIC_EQUIVALENCE.md)
also confirms bit-identical scalar/batch costs and two archived image-pair outcomes
against source 863 when the optional green adaptation is disabled. Software
equivalence is separate from ground-truth image accuracy.

{api_text}

{service_text}

## Rejected and failed development results remain preserved

The earlier observable source 863 produces full-looking all-clear Class 1 maps
despite maximum full-turn errors of 25.744/21.415 degrees and 17.029/14.371 pixels.
Native resolution with the old high-pass objective also fails (18.651/13.878
degrees; 12.565/9.383 pixels). Those failures motivate the separate photometric
diagnosis; they are not overwritten by later passes.

The original-green source 46a46 passes ideal full turns but returns 83/119 false
stationary texture-A turns and a partial map. Its author RMS is about 18.43 pixels,
so it is rejected. Smoothed-green source 1fb passes the tested ideal short/full
turn and stationary controls; this is not a claim of general author accuracy.
The hybrid keeps the original objective for larger author motions instead of
globally replacing it. [Original-green failure record](algorithm-revision/photometric_motion_controls_20261002/PHOTOMETRIC_MOTION_CONTROLS.md).

Historical source 52 raw forced-zero-minimum stationary chains drift by
59.768 and 7.388 degrees. Native sigma 1.118/2 prefilter trials do not pass all
original raw accuracy limits. These unchanged failures, rejected native trials,
objective curves and source/settings records remain in the bundle. The original
green chart's false static annotation was corrected with explicit postprocessing
provenance; original exports and measurements are preserved.

The older full_revised API is interrupted and incomplete. Full_observable is
an earlier execution source and has its own state in [api_run_states.json](api_run_states.json).
Neither can count as completion of the final hybrid full-video test.
Geometry-size and paired GrabCut-thread diagnostics remain separate historical
investigations; they establish neither a camera correction nor a production
thread-speed improvement.

## Reproduce and report images

The gallery provides actual author/conveyor images, known-answer controls and
300-dpi PNG/PDF figures. Result JSON, NPZ inputs, frozen sources, settings,
software output, model hashes and author source/license provenance are retained.
NPZ inputs are stored once by SHA256; [input_references.json](input_references.json)
resolves duplicate paths from historical reports. Models and the complete original
author dataset/video are not duplicated. The original clip is
`WIN_20260818_13_29_43_Pro.mp4`, SHA256
`dc25964bf6052972cad761b0246f79906e768c6737bf4228ba44711d7272429c`.

Research basis: [2021 spheroid rotation paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 surface-map paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
This is an independent implementation. The public author repositories provide
data and feature annotations rather than the reconstruction software used here.
These are development tests with explicit scope, not certification of real grade accuracy.

```powershell
./backend/venv/Scripts/python.exe -B backend/build_algorithm_revision_evidence.py --profile {profile} --label {label} --refresh
```

Run each validation under a fresh label; recorded inputs/settings/scripts supply
individual reproduction. [SHA256SUMS.txt](SHA256SUMS.txt) identifies every payload;
[bundle_summary.json](bundle_summary.json) states completion and limitations.
"""
    (output/'VALIDATION_REPORT.md').write_text(report, encoding='utf-8')
    save_json(output/'api_run_states.json', api_records)
    save_json(output/'input_references.json', {'method': 'Identical NPZ payloads stored once by SHA256',
        'unique_npz_payloads': len(canonical_npz), 'aliases': aliases})
    save_json(output/'model_sha256.json', model['model_sha256'])
    save_json(output/'bundle_summary.json', {'built_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
        'algorithm_sha256': EXPECTED, 'profile': profile, 'transverse_angle_deg': config['transverse'],
        'tested_main_sha256': software['source_sha256']['backend/main.py'],
        'full_api_label': final_api_label, 'full_api_completed': api_complete, 'retained_author_audit_included': retained is not None,
        'synthetic_motion_controls_passed': not horizontal_turn_failed,
        'actual_matcher_full_turn_controls_passed': not horizontal_turn_failed,
        'six_degree_subdegree_full_turn_controls_passed': True,
        'horizontal_twelve_degree_full_turn_controls_passed': not horizontal_turn_failed if horizontal_turn else None,
        'strict_large_transverse_controls_passed': strict_transverse['twenty_degree_controls_passed'] if strict_transverse else None,
        'same_label_author_comparison_included': common_label_comparison is not None,
        'service_software_checks_included': service_checks is not None,
        'stationary_returned_pairs': 0, 'stationary_unavailable_pairs': 238, 'stationary_endpoint_accuracy': 'unavailable',
        'field_motion_accuracy_verified': False, 'defect_grade_accuracy_verified': False,
        'python_tests': test_count, 'unique_npz_payloads': len(canonical_npz), 'duplicate_npz_aliases': len(aliases),
        'model_sha256': model['model_sha256'], 'primary_collections': primary, 'historical_collections': history,
        'copied_sources': copied})
    figures = [('All author labels: accuracy and availability', 'author_comparison.png'),
        ('Publication Table 4 context: different evaluation denominators', 'publication_table4_context.png'),
        ('Final hybrid complete-turn geometry', f'{TURN}/full_turn_accuracy.png'),
        ('Final hybrid short moving geometry', f'{MOTION}/observable_moving_accuracy.png'),
        ('Final hybrid stationary measurements unavailable', f'{MOTION}/stationary_observability.png'),
        ('Final hybrid exposure-offset invariance', f'{MOTION}/brightness_offset_invariance.png'),
        ('Real conveyor frozen-input comparison', f'{FIXED}/fixed_input_comparison.png'),
        ('Preserved 863 full-turn accuracy failure', 'algorithm-revision/full_turn_observable_20261002/full_turn_accuracy.png'),
        ('Rejected original-green stationary outcomes', 'algorithm-revision/photometric_motion_controls_20261002/stationary_observability.png'),
        ('Historical raw stationary drift', 'algorithm-revision/extended_motion_controls_20261002/extended_motion_accuracy.png'),
        ('Historical rejected native high-pass reconstruction', 'algorithm-revision/full_turn_native_20261002/full_turn_accuracy.png'),
        ('One-axis objective curves: diagnosis only', 'algorithm-revision/photometric_objective_20261002/objective_curves.png')]
    if wobble:
        figures.insert(2, ('Author accuracy on the same returned labels: mixed results',
                          'algorithm-revision/transverse_author_comparison_20261002/same_label_accuracy.png'))
        figures.insert(3, ('Original strict large-transverse probe: one of four wider-bound cases fails',
                          'algorithm-revision/large_transverse_truth_20261002/large_transverse_truth.png'))
        figures.insert(4, ('One naartjie: illustrative processing replay with explicit donor provenance',
                          'algorithm-revision/debug_fruit_98_wobble_20261002/one_fruit_steps.png'))
        if horizontal_turn:
            figures.insert(2, ('Current profile horizontal twelve-degree full-turn accuracy failure',
                'algorithm-revision/full_turn_x12_wobble_20261002/full_turn_accuracy.png'))
    cards = [f'<figure><a href="{html.escape(relative)}"><img src="{html.escape(relative)}" alt="{html.escape(title)}"></a>'
             f'<figcaption>{html.escape(title)} · <a href="{html.escape(str(Path(relative).with_suffix(".pdf")))}">PDF</a></figcaption></figure>'
             for title, relative in figures]
    for track in model['tracks']:
        frame = track['result']['view_evidence'][0]['frame']; prefix = f"{MODEL}/{track['track']}"
        cards.append(f'<figure><img src="{prefix}/frame_{frame:05d}_overlay.png" alt="Actual defect model output track {track["track"]}">'
                     f'<figcaption>Actual defect model: track {track["track"]}, frame {frame}; '
                     f'{html.escape(track["result"]["status"])}; grade {html.escape(str(track["result"]["grade"]))}. '
                     'Execution output; accuracy is unverified.</figcaption></figure>')
    if wobble:
        cards.append('<figure><img src="algorithm-revision/transverse_author_comparison_20261002/independent_pairs_worst_alpha20.png" '
                     'alt="Worst returned alpha20 author prediction, error39.55996pixels">'
                     '<figcaption>Worst returned author prediction: mandarins/obj0004 annotation61, error39.55996 pixels. '
                     'This failure remains in the accuracy totals.</figcaption></figure>')
    points = sorted((output/AUTHOR).glob('*/*/point_*.png'))
    for picture in points[::max(1, len(points)//6)][:6]:
        relative = picture.relative_to(output).as_posix()
        cards.append(f'<figure><img src="{relative}" alt="Actual published author correspondence">'
                     '<figcaption>Actual author image: green feature annotation and red prediction.</figcaption></figure>')
    gallery = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Naartjie hybrid algorithm validation evidence</title><style>
body{{margin:0;background:#f4f5f2;color:#20332a;font:17px/1.55 system-ui,sans-serif}}main{{max-width:1150px;margin:auto;padding:28px}}
h1{{font-size:32px;line-height:1.15}}a{{color:#226648}}.status{{background:{'#f6e2d9' if horizontal_turn_failed else '#e3ecd8'};padding:14px 18px;border-radius:8px}}
figure{{margin:26px 0;background:white;padding:18px;border:1px solid #d9dfd6;border-radius:8px}}img{{max-width:100%;display:block;height:auto;margin:auto}}
figcaption{{margin-top:12px}}.links{{display:flex;gap:18px;flex-wrap:wrap}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.65 ui-monospace,monospace;background:white;padding:20px}}
</style><main><h1>Naartjie algorithm: hybrid tests and image evidence</h1>
<p class="status">{'Completed hybrid full API run included.' if api_complete else 'Draft: the final hybrid full API run is pending.'}
{motion_statement}
{'The additional strict large-transverse probe fails one of four alpha20 cases. Frozen track98 reaches coverage and receives Class1 with actual defect masks; the other three remain partial.' if wobble else 'All four frozen conveyor examples remain partial.'}
Field motion and real grading accuracy remain unverified. Failed development sources are preserved.</p>
<p class="links"><a href="VALIDATION_REPORT.md">Testing report</a><a href="source/ALGORITHM_EXPLAINED.md">Simple explanation</a>
<a href="bundle_summary.json">Source and scope</a><a href="SHA256SUMS.txt">Checksums</a></p>
{'<p><a href="algorithm-revision/debug_fruit_98_wobble_20261002/index.html">Open the step-by-step track-98 debugger</a></p>' if wobble else ''}
{''.join(cards)}<h2>Full testing record</h2><pre>{html.escape(report)}</pre></main></html>'''
    (output/'index.html').write_text(gallery, encoding='utf-8')
    manifest = output/'SHA256SUMS.txt'
    if not manifest.exists(): manifest.write_text('Populated after link validation.\n', encoding='utf-8')
    links = re.findall(r'(?:href|src)="([^"]+)"', gallery)+re.findall(r'\]\(([^)]+)\)', report)
    local_links = [link for link in links if not link.startswith(('http:', 'https:', '#'))]
    missing = [link for link in local_links if not (output/html.unescape(link)).exists()]
    if missing: raise FileNotFoundError(f'Broken generated evidence links: {missing}')
    save_json(output/'evidence_qa.json', {'generated_links_total': len(links), 'generated_local_links_checked': len(local_links), 'missing_links': [],
        'final_source_hash_verified': True, 'npz_deduplicated_by_hash': True, 'full_api_completed': api_complete})
    files = sorted(path for path in output.rglob('*') if path.is_file() and path != manifest)
    manifest.write_text(''.join(f'{sha256(path)}  {path.relative_to(output).as_posix()}\n' for path in files), encoding='utf-8')
    archive = output.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(output.rglob('*')):
            if path.is_file(): package.write(path, Path(output.name)/path.relative_to(output))
    with zipfile.ZipFile(archive) as package:
        if package.testzip(): raise ValueError('Archive CRC validation failed')
        entries = len(package.infolist())
    metadata = {'archive': archive.name, 'sha256': sha256(archive), 'entries': entries,
                'bytes': archive.stat().st_size, 'crc_verified': True, 'full_api_completed': api_complete}
    save_json(archive.with_suffix('.zip.json'), metadata)
    print(json.dumps(metadata, indent=2))
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('hybrid', 'wobble'), default='hybrid')
    parser.add_argument('--label')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args(); build(args.label or ('evidence_wobble_20261002' if args.profile == 'wobble' else 'evidence_hybrid_20261002'), args.refresh, args.profile)


if __name__ == '__main__': main()
