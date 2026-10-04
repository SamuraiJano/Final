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
ALLOWED = {'.json', '.py', '.snapshot', '.md', '.txt', '.csv', '.png', '.pdf', '.npz'}
AUTHOR = 'authors-benchmark/runs/hybrid_photometric_profile_20261002'
RETAINED = 'authors-benchmark/bridge_runs/hybrid_photometric_retained_20261002'
MOTION = 'algorithm-revision/hybrid_motion_controls_20261002'
TURN = 'algorithm-revision/full_turn_hybrid_20261002'
FIXED = 'algorithm-revision/fixed_hybrid_conveyor_20261002'
MODEL = 'algorithm-revision/real_segmenter_hybrid_20261002'
AREA = 'authors-benchmark/synthetic_runs/hybrid_photometric_20261002'
SOFTWARE = 'software-checks/hybrid_photometric_20261002'
EQUIVALENCE = 'algorithm-revision/photometric_equivalence_20261002'


def build(label='evidence_hybrid_20261002', refresh=False):
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
    for relative in history:
        copy_collection(relative)
    for relative in ['authors-benchmark/runs/operational_profile_v1/report.json',
                     'authors-benchmark/source_manifest.json',
                     'algorithm-revision/resolution_preprocess_trials_20261002.json']:
        copy_file(DIAGNOSTICS/relative, relative)
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
    for filename in source_names:
        copy_file(BACKEND/filename, Path('source')/filename)
    if sha256(output/'source/algorithm.py') != EXPECTED:
        raise ValueError('Workspace algorithm changed after the captured tests')
    for source in sorted(BACKEND.glob('test_*.py')):
        copy_file(source, Path('source')/source.name)
    copy_file(BACKEND.parent/'README.md', 'source/README.md')

    api_records = {}
    for api_label, expected in [('full_revised_20261002', None), ('full_observable_20261002', PREVIOUS),
                                ('full_hybrid_20261002', EXPECTED)]:
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
    final_api = api_records['full_hybrid_20261002']
    api_complete = final_api['state'] == 'completed'

    baseline = read_json(output/'authors-benchmark/runs/operational_profile_v1/report.json')
    previous = read_json(output/'authors-benchmark/runs/adjacent_observable_profile_20261002/report.json')
    rejected = read_json(output/'authors-benchmark/runs/photometric_green_profile_20261002/report.json')
    author_rows, rms_values, returned, within = [], [], [], []
    for name, report in [('Previous operational', baseline), ('Prior observable 863', previous),
                         ('Rejected native original green 46a46', rejected), ('Final hybrid 951b55', author)]:
        stats = report['summary']['all']; errors = stats['errors_px_conditional_on_prediction']
        author_rows.append([name, f"{stats['predicted_correspondences']}/497", f"{errors['rms']:.5f}",
                            f"{errors['within_5px']}/497", f"{errors['max']:.5f}"])
        rms_values.append(errors['rms']); returned.append(stats['predicted_correspondences']); within.append(errors['within_5px'])
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    labels = ['Previous\noperational', 'Observable\n863', 'Rejected native\noriginal green', 'Final\nhybrid 951']
    colors = ['#8a9289', '#d09247', '#ac503b', '#267a4e']
    axes[0].bar(labels, rms_values, color=colors); axes[0].set(ylabel='Conditional returned-label RMS (pixels)')
    x = list(range(4)); axes[1].bar([v-.18 for v in x], returned, .36, label='Returned predictions', color='#267a4e')
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

**The final hybrid source passes the specified synthetic motion, observability and area controls.**
It preserves approximately the earlier author-label accuracy while fixing the demonstrated
ideal full-turn drift. The four fixed real conveyor examples remain partial. General
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

## Author data and labelled point accuracy

All 578 original images in 36 sequences (15 mandarins, 10 oranges, 11 tomatoes)
and all 497 published correspondences are used. Labels only score predictions;
they do not fit motion. Masks are derived from nonblack backgrounds. These images
were inspected during development and are not held-out evaluation.

{table(['Source/profile', 'Returned / labels', 'Conditional RMS, px', 'Within 5 px / all labels', 'Maximum returned error, px'], author_rows)}

The hybrid returns slightly fewer independent predictions than the prior profiles;
the conditional RMS is approximately unchanged on a different returned subset.
This does not show a general accuracy improvement. The native original-green
replacement is rejected because author accuracy substantially worsens.
Final author maps: `{json.dumps(dict(map_counts))}`. Coverage-eligible maps have no
author defect truth and cannot validate grades.

For publication context, the [2021 paper, Section 4.2 and Table 4](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
reports the following pixel reprojection RMS values. The authors describe about
200 point correspondences per fruit class. The public annotation files evaluated
here contain 132/179/186 labels (497 total), with 119/175/161 returned predictions.

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

## Frozen real conveyor inputs and the user's segmentation model

The exact 215 detector/tracker crops and fruit masks of tracks 98, 1, 14 and 491
are held fixed across variants. They are selected development cases, not a
random or held-out sample. Detection, tracking, GrabCut and neural inference are
not rerun in this geometry comparison. No independent conveyor motion truth is available.

{table(['Track', 'Input views', 'Retained views', 'Original frames', 'Observed longitude, deg', 'Result'], track_rows)}

All four remain below the 350-degree longitude gate and receive no grade. More
coverage, an ordered map, or a low matching residual does not establish correct
surface geometry. Independently marked conveyor landmarks and verified turns
are needed to score field motion and map accuracy.

The separate real D-FINE integration executes {model['segmentation']['calls']} model
calls and returns {model['segmentation']['instances']} defect instances on those
same frozen crops. Actual masks, overlays and partial maps are retained. All
four remain partial and ungraded. This verifies model execution and mapper/report
connection; no defect-mask or grade truth is available to score accuracy. Detection,
tracking and GrabCut are not recomputed in that isolated segmentation run.

![Real conveyor comparison]({FIXED}/fixed_input_comparison.png)
[Actual model record]({MODEL}/report.json).

## Area arithmetic, implementation checks and full-video execution

Known defect longitude wedges are projected with exact geometry and supplied
rotations. This control intentionally bypasses the image matcher and neural
models; it verifies repeated-defect union and spherical area normalization.

{table(['Known observed defect area', 'Measured', 'Absolute error, percentage points', 'Configured class'], area_rows)}

Coverage controls also pass: known 250- and 100-degree turns stay partial.
The configured 10%/20% class boundaries are engineering rules, not published
author validation of conveyor grades.

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
./backend/venv/Scripts/python.exe -B backend/build_algorithm_revision_evidence.py --profile hybrid --label {label} --refresh
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
        'algorithm_sha256': EXPECTED, 'full_api_completed': api_complete, 'retained_author_audit_included': retained is not None,
        'synthetic_motion_controls_passed': True, 'actual_matcher_full_turn_controls_passed': True,
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
    cards = [f'<figure><a href="{html.escape(relative)}"><img src="{html.escape(relative)}" alt="{html.escape(title)}"></a>'
             f'<figcaption>{html.escape(title)} · <a href="{html.escape(str(Path(relative).with_suffix(".pdf")))}">PDF</a></figcaption></figure>'
             for title, relative in figures]
    for track in model['tracks']:
        frame = track['result']['view_evidence'][0]['frame']; prefix = f"{MODEL}/{track['track']}"
        cards.append(f'<figure><img src="{prefix}/frame_{frame:05d}_overlay.png" alt="Actual defect model output track {track["track"]}">'
                     f'<figcaption>Actual defect model: track {track["track"]}, frame {frame}; partial map, no grade.</figcaption></figure>')
    points = sorted((output/AUTHOR).glob('*/*/point_*.png'))
    for picture in points[::max(1, len(points)//6)][:6]:
        relative = picture.relative_to(output).as_posix()
        cards.append(f'<figure><img src="{relative}" alt="Actual published author correspondence">'
                     '<figcaption>Actual author image: green feature annotation and red prediction.</figcaption></figure>')
    gallery = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Naartjie hybrid algorithm validation evidence</title><style>
body{{margin:0;background:#f4f5f2;color:#20332a;font:17px/1.55 system-ui,sans-serif}}main{{max-width:1150px;margin:auto;padding:28px}}
h1{{font-size:32px;line-height:1.15}}a{{color:#226648}}.status{{background:#e3ecd8;padding:14px 18px;border-radius:8px}}
figure{{margin:26px 0;background:white;padding:18px;border:1px solid #d9dfd6;border-radius:8px}}img{{max-width:100%;display:block;height:auto;margin:auto}}
figcaption{{margin-top:12px}}.links{{display:flex;gap:18px;flex-wrap:wrap}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.65 ui-monospace,monospace;background:white;padding:20px}}
</style><main><h1>Naartjie algorithm: hybrid tests and image evidence</h1>
<p class="status">{'Completed hybrid full API run included.' if api_complete else 'Draft: the final hybrid full API run is pending.'}
Specified ideal motion, stationary observability and area controls pass. All four frozen conveyor examples remain partial.
Field motion and real grading accuracy remain unverified. Failed development sources are preserved.</p>
<p class="links"><a href="VALIDATION_REPORT.md">Testing report</a><a href="source/ALGORITHM_EXPLAINED.md">Simple explanation</a>
<a href="bundle_summary.json">Source and scope</a><a href="SHA256SUMS.txt">Checksums</a></p>
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
    parser.add_argument('--label', default='evidence_hybrid_20261002')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args(); build(args.label, args.refresh)


if __name__ == '__main__': main()
