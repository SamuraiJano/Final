"""Freeze a bounded supplement for the requested observed-area grading policy.

This script reads existing results only. It never runs a model or modifies a job.
Prepare with --ui-report, then seal with --seal after actual browser/gallery checks.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import difflib
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

EVIDENCE = Path(__file__).resolve().parent
WORKSPACE = EVIDENCE.parents[3]
BACKEND = WORKSPACE / 'backend'
SOURCE_ID = 'ea6e595b8f3f45f2b5edfda8dafff3f2'
DERIVED_ID = 'ed3aa02cca364812a145610aad627a83'
EXAMPLES = (32, 340, 98)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    assert digest(source) == digest(destination), source


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui-report', type=Path)
    parser.add_argument('--transport-proof', type=Path)
    parser.add_argument('--failed-ui', type=Path)
    parser.add_argument('--gallery-report', type=Path)
    parser.add_argument('--seal', action='store_true')
    args = parser.parse_args()
    original_dir = BACKEND / 'results' / SOURCE_ID
    derived_dir = BACKEND / 'results' / DERIVED_ID
    summary = json.loads((EVIDENCE / 'regrading_summary.json').read_text())
    original = json.loads((original_dir / 'report.json').read_text())
    derived = json.loads((derived_dir / 'report.json').read_text())
    original_hash = digest(original_dir / 'report.json')
    assert original_hash == summary['original_report_sha256']
    assert derived['analysis_kind'] == 'saved_map_regrading'
    assert derived['derived_from_job_id'] == SOURCE_ID
    assert len(original['fruits']) == len(derived['fruits']) == 474
    assert summary['model_calls_in_this_update'] == 0
    by_id = {fruit['track_id']: fruit for fruit in original['fruits']}
    assert sum(fruit['grade_provisional'] for fruit in derived['fruits']) == 292
    ledger = []
    for fruit in derived['fruits']:
        old = by_id[fruit['track_id']]
        for key in ('observed_surface_pct', 'observed_longitude_deg',
                    'defect_pct_of_observed', 'pair_rotation_vectors_deg',
                    'pair_errors', 'view_frames', 'first_seen_frame', 'last_seen_frame'):
            assert old.get(key) == fruit.get(key), (fruit['track_id'], key)
        ledger.append(dict(track_id=fruit['track_id'], strict_grade=old.get('grade'),
                           strict_status=old['status'], updated_grade=fruit.get('grade'),
                           updated_status=fruit['status'], provisional=fruit['grade_provisional'],
                           coverage_complete=fruit['coverage_complete'],
                           observed_surface_pct=fruit.get('observed_surface_pct'),
                           observed_longitude_deg=fruit.get('observed_longitude_deg'),
                           defect_pct_of_observed=fruit.get('defect_pct_of_observed'),
                           has_map=bool(fruit.get('surface_map'))))
    with (EVIDENCE / 'all_474_grades.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ledger[0]))
        writer.writeheader()
        writer.writerows(ledger)
    write_json(EVIDENCE / 'execution_and_policy.json', dict(
        source_job_id=SOURCE_ID, source_mapping_created_at=original['created_at'],
        derived_job_id=DERIVED_ID, derived_created_at=derived['created_at'],
        source_name=original['source_name'], mapping_metrics=original['metrics'],
        grading_policy=derived['grading_policy'],
        interpretation='Model timings/counts are inherited from the original mapping run; no inference occurred during regrading.'))
    rows = []
    for track_id in EXAMPLES:
        fruit = next(f for f in derived['fruits'] if f['track_id'] == track_id)
        target = EVIDENCE / 'examples' / str(track_id)
        copy_file(original_dir / str(track_id) / 'result.json', target / 'strict_result.json')
        copy_file(derived_dir / str(track_id) / 'result.json', target / 'updated_result.json')
        for name in ('surface_map.png', 'observed.png'):
            assert digest(original_dir / str(track_id) / name) == digest(derived_dir / str(track_id) / name)
            copy_file(derived_dir / str(track_id) / name, target / name)
        for url in fruit.get('defect_maps', {}).values():
            name = Path(url).name
            copy_file(derived_dir / str(track_id) / name, target / name)
        view = fruit['view_evidence'][0]
        for key in ('crop', 'fruit_mask', 'overlay'):
            name = Path(view[key]).name
            copy_file(derived_dir / str(track_id) / name, target / name)
        rows.append((fruit, view))
    snapshots = {
        'mapping_algorithm.py': original_dir / 'algorithm.py.snapshot',
        'mapping_main.py': original_dir / 'main.py.snapshot',
        'grading_algorithm.py': derived_dir / 'grading_algorithm.py.snapshot',
        'grading_main.py': derived_dir / 'grading_main.py.snapshot',
        'dfine_segmenter.py': original_dir / 'dfine_segmenter.py.snapshot',
        'App.jsx': WORKSPACE / 'src/App.jsx',
        'test_partial_grades.py': BACKEND / 'test_partial_grades.py',
        'README.md': WORKSPACE / 'README.md',
        'DEVELOPMENT_LOG.md': BACKEND / 'diagnostics/authors-benchmark/DEVELOPMENT_LOG.md',
        'ALGORITHM_EXPLAINED.md': BACKEND / 'ALGORITHM_EXPLAINED.md',
        'TESTING_PROCESS.md': BACKEND / 'TESTING_PROCESS.md',
        'vite.config.js': WORKSPACE / 'vite.config.js',
    }
    for name, source in snapshots.items():
        copy_file(source, EVIDENCE / 'source' / name)
    diff = difflib.unified_diff(
        snapshots['mapping_algorithm.py'].read_text().splitlines(True),
        snapshots['grading_algorithm.py'].read_text().splitlines(True),
        fromfile='mapping_algorithm_50bdd78e.py', tofile='grading_algorithm_f10e8393.py')
    (EVIDENCE / 'source/grading_changes.patch').write_text(''.join(diff), encoding='utf-8')
    checks_dir = BACKEND / 'diagnostics/software-checks/partial_grades_20261003'
    checks = json.loads((checks_dir / 'summary.json').read_text())
    assert all(check['exit_code'] == 0 for check in checks['checks'])
    for key in ('backend/algorithm.py', 'backend/main.py', 'backend/dfine_segmenter.py', 'src/App.jsx'):
        assert digest(WORKSPACE / key) == checks['source_sha256'][key], key
    for name in ('summary.json', 'python_tests.txt', 'frontend_build.txt', 'frontend_lint.txt'):
        copy_file(checks_dir / name, EVIDENCE / 'checks' / name)
    fixture_dir = BACKEND / 'diagnostics/ui-checks/partial_grades_fixture_20261003'
    for name in ('report.json', 'fixture.json', 'check_partial_grades.py',
                 'partial_class2_drawer.png', 'partial_mobile.png'):
        copy_file(fixture_dir / name, EVIDENCE / 'artificial_ui_controls' / name)
    # Exact deterministic inputs used by the policy map/denominator tests.
    # Rotation is supplied by a mock; this is not photometric-motion validation.
    yy, xx = np.mgrid[:100, :100]
    silhouette = (((xx - 49.5)**2 + (yy - 49.5)**2) < 35**2).astype(np.uint8)
    color = np.zeros((100, 100, 3), np.uint8)
    color[silhouette > 0] = (35, 140, 235)
    angle = np.deg2rad(25.)
    known_rotation = np.array([[np.cos(angle), 0., np.sin(angle)],
                               [0., 1., 0.],
                               [-np.sin(angle), 0., np.cos(angle)]])
    controls = EVIDENCE / 'controls'
    controls.mkdir(exist_ok=True)
    np.savez_compressed(controls / 'policy_test_inputs.npz', bgr_image=color,
                        fruit_mask=silhouette, clean_defect_mask=np.zeros_like(silhouette),
                        fully_defective_mask=silhouette, supplied_rotation=known_rotation)
    write_json(controls / 'method.json', dict(
        source='Exact deterministic construction in test_partial_grades.py::_known_partial_map',
        image_shape=[100, 100, 3], bgr_color=[35, 140, 235], radius_px=35,
        centre_px=[49.5, 49.5], views=2, frame_numbers=[0, 1], supplied_y_rotation_deg=25,
        denominator_control='Fully defective observed latitude band with max_latitude_deg=10; expected defect_pct_of_observed=100 even when defect_pct_of_full_surface<10.',
        limitations='Perfect synthetic silhouette, constant synthetic color and mocked known rotation; verifies policy/map invariance/denominator only, no neural or photometric accuracy.'))
    fig, axes = plt.subplots(3, 4, figsize=(16, 13), gridspec_kw={'width_ratios': [1, 1, 2, 2]})
    for row, (fruit, view) in enumerate(rows):
        track_id = fruit['track_id']
        label = fruit['grade'] + (' (partial)' if fruit['grade_provisional'] else ' (coverage complete)')
        paths = (Path(view['crop']).name, Path(view['overlay']).name, 'surface_map.png', 'observed.png')
        headings = (f'Fruit {track_id}: input frame {view["frame"]}', 'Actual model defect overlay',
                    label, 'Observed-area mask')
        for column, (name, heading) in enumerate(zip(paths, headings)):
            ax = axes[row, column]
            ax.imshow(plt.imread(EVIDENCE / 'examples' / str(track_id) / name), cmap='gray', interpolation='nearest')
            ax.set_title(heading, fontsize=10, pad=8)
            ax.set_xticks([])
            ax.set_yticks([])
        axes[row, 2].set_xlabel(
            f'{fruit["defect_pct_of_observed"]:.3f}% predicted defects / observed area\n'
            f'{fruit["observed_surface_pct"]:.3f}% surface; {fruit["observed_longitude_deg"]:.3f}° longitude',
            fontsize=10)
        axes[row, 3].set_xlabel('White: observed. Black: unassessed.\nMap pixels are unchanged by regrading.', fontsize=10)
    fig.suptitle('Requested grading of partial maps: actual saved conveyor outputs', fontsize=17, y=.99)
    fig.text(.5, .015, 'Grades use predicted defect area divided by observed surface. Red overlays are model predictions, not manual truth.\n'
             'Two partial examples and one coverage-complete example; no detection, segmentation or rotation inference was repeated.',
             ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .06, 1, .955), h_pad=5.5)
    figure_dir = EVIDENCE / 'figures'
    figure_dir.mkdir(exist_ok=True)
    fig.savefig(figure_dir / 'actual_partial_grade_examples_300dpi.png', dpi=300, facecolor='white')
    fig.savefig(figure_dir / 'actual_partial_grade_examples.pdf', dpi=300, facecolor='white')
    plt.close(fig)
    cards = []
    for fruit, view in rows:
        track_id = fruit['track_id']
        label = fruit['grade'] + (' (partial)' if fruit['grade_provisional'] else ' (coverage complete)')
        cards.append(f'<article><h2>Fruit {track_id}: {html.escape(label)}</h2>'
                     f'<p>{fruit["defect_pct_of_observed"]:.3f}% predicted defects on observed area; '
                     f'{fruit["observed_surface_pct"]:.3f}% surface observed, '
                     f'{fruit["observed_longitude_deg"]:.3f}° longitude.</p>'
                     f'<div class="pair"><figure><img src="examples/{track_id}/surface_map.png" alt="Actual surface map for fruit {track_id}">'
                     '<figcaption>Original surface map; pixels unchanged.</figcaption></figure>'
                     f'<figure><img src="examples/{track_id}/observed.png" alt="Observed area mask for fruit {track_id}">'
                     '<figcaption>White: observed; black: unassessed.</figcaption></figure></div>'
                     f'<p><a href="examples/{track_id}/strict_result.json">Earlier strict record</a> · '
                     f'<a href="examples/{track_id}/updated_result.json">Updated policy record</a></p></article>')
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page += '<title>Observed-area partial grading proof</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:auto;padding:28px;color:#172721;background:#f6f8f6}h1{line-height:1.2}a{color:#17583e}article{background:white;border:1px solid #bbc9c0;border-radius:8px;padding:20px;margin:24px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}figure{margin:0}img{width:100%;height:auto}figcaption{font-size:14px}code{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{padding:8px;text-align:left;border-bottom:1px solid #cbd3ce}@media(max-width:650px){.pair{grid-template-columns:1fr}}</style>'
    page += '<h1>Grades from the observed part of each fruit</h1><p>The grading policy assigns grades for partial maps. This separate update assigns <strong>293 Class 1, 1 Class 2 and 180 Review</strong>; <strong>292 grades are provisional</strong>. The two coverage-complete Class 1 results retain regular grades.</p>'
    page += '<p>Defect area is divided by observed surface area. Unseen areas are unassessed. Class 1: less than 10%; Class 2: 10% through 20%; Class 3: more than 20%. Original coverage targets remain 65% observed surface and 350° longitude. Missing maps/defect observations and invalid motion remain ungraded.</p>'
    page += f'<p>Original map job: <code>{SOURCE_ID}</code><br>Saved-map regrading job: <code>{DERIVED_ID}</code>. No model or motion inference was repeated. All 5,691 copied PNG files were verified byte-identical and the original report is unchanged.</p>'
    page += '<p><a href="POLICY_CHANGE.md">Policy, method and limitations</a> · <a href="all_474_grades.csv">All 474 before/after records</a> · <a href="execution_and_policy.json">Execution/settings provenance</a> · <a href="checks/summary.json">64 tests, build and lint</a></p>'
    page += '<p><a href="artificial_ui_controls/report.json">Separate artificial UI controls</a> verify all three partial class labels and filters. Their data/images are mocked fixtures, not actual fruit predictions.</p>'
    page += ''.join(cards)
    page += '<h2>Report-ready figure</h2><p><a href="figures/actual_partial_grade_examples_300dpi.png">300-dpi PNG</a> · <a href="figures/actual_partial_grade_examples.pdf">PDF</a></p><img src="figures/actual_partial_grade_examples_300dpi.png" alt="Actual inputs, model overlays, maps and observed masks for three fruit">'
    if args.ui_report:
        ui_report = args.ui_report.resolve()
        assert ui_report.is_file()
        ui_check = json.loads(ui_report.read_text(encoding='utf-8'))
        assert ui_check.get('passed') is True, 'Actual running-app check must pass before sealing'
        assert ui_check['latest_job_id'] == DERIVED_ID
        assert ui_check['latest_records'] == 474 and ui_check['provisional_records'] == 292
        for path in ui_report.parent.rglob('*'):
            if path.is_file():
                copy_file(path, EVIDENCE / 'actual_ui' / path.relative_to(ui_report.parent))
        page += '<h2>Actual running-app check</h2><p><a href="actual_ui/' + ui_report.name + '">GET-only browser report</a>. Screenshots use the saved derived result, with no mocked API responses or new analysis.</p>'
    if args.transport_proof:
        for path in args.transport_proof.resolve().rglob('*'):
            if path.is_file():
                copy_file(path, EVIDENCE / 'dashboard_transport' / path.relative_to(args.transport_proof.resolve()))
        page += '<p>Dashboard transfer diagnostics, the preserved failed UI attempt, the delivery fix and its separate verification are retained under <code>dashboard_transport/</code>. This delivery change does not reconstruct maps or rerun models.</p>'
    if args.failed_ui:
        for path in args.failed_ui.resolve().rglob('*'):
            if path.is_file():
                copy_file(path, EVIDENCE / 'failed_ui_attempt' / path.relative_to(args.failed_ui.resolve()))
    page += '<p>The increased class count follows a changed decision policy, not improved model accuracy or coverage. No manually labelled conveyor grades are available. Earlier strict-policy evidence remains sealed and unchanged.</p></html>'
    (EVIDENCE / 'index.html').write_text(page, encoding='utf-8')
    if args.gallery_report:
        for path in args.gallery_report.resolve().parent.rglob('*'):
            if path.is_file():
                copy_file(path, EVIDENCE / 'gallery_qa' / path.relative_to(args.gallery_report.resolve().parent))
    sealed_zip = BACKEND / 'diagnostics/algorithm-revision/evi_runtime_20261003.zip'
    assert digest(sealed_zip) == '5b1a429d17548f7025f9f90f24bae7d1e19e1d5190cf9bd0ca5f1aec562acefb', 'Earlier sealed evidence changed'
    write_json(EVIDENCE / 'provenance.json', dict(
        captured_at=datetime.now(timezone.utc).isoformat(),
        original_report_sha256=original_hash,
        derived_report_sha256=digest(derived_dir / 'report.json'),
        mapping_source_sha256=digest(snapshots['mapping_algorithm.py']),
        grading_source_sha256=digest(snapshots['grading_algorithm.py']),
        dashboard_vite_config_sha256=digest(WORKSPACE / 'vite.config.js'),
        earlier_sealed_zip=dict(path=str(sealed_zip.relative_to(WORKSPACE)),
                                bytes=sealed_zip.stat().st_size, sha256=digest(sealed_zip)),
        copy_scope='Three actual examples only; 474-row ledger and all method/settings/source records.',
        actual_ui_included=bool(args.ui_report)))
    assert digest(original_dir / 'report.json') == original_hash
    if args.seal:
        assert args.ui_report, 'Actual UI verification required to seal'
        assert args.gallery_report, 'Final gallery verification required to seal'
        gallery = json.loads(args.gallery_report.read_text(encoding='utf-8'))
        assert gallery.get('passed') is True, 'Gallery must pass before sealing'
        assert gallery['gallery_sha256'] == digest(EVIDENCE / 'index.html'), 'Gallery QA must match exact final HTML'
        manifest = []
        for path in sorted(EVIDENCE.rglob('*')):
            if path.is_file() and path.name not in ('manifest.json', 'seal.json'):
                manifest.append(dict(path=path.relative_to(EVIDENCE).as_posix(),
                                     bytes=path.stat().st_size, sha256=digest(path)))
        write_json(EVIDENCE / 'manifest.json', dict(files=manifest))
        archive = EVIDENCE.with_suffix('.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
            for path in sorted(EVIDENCE.rglob('*')):
                if path.is_file() and path.name != 'seal.json':
                    stream.write(path, path.relative_to(EVIDENCE).as_posix())
        with zipfile.ZipFile(archive) as stream:
            assert stream.testzip() is None
        for item in manifest:
            assert digest(EVIDENCE / item['path']) == item['sha256']
        write_json(EVIDENCE / 'seal.json', dict(files=len(manifest), zip_bytes=archive.stat().st_size,
                  zip_sha256=digest(archive), zip_crc='pass', manifest_verification='pass'))
        print(json.dumps(json.loads((EVIDENCE / 'seal.json').read_text())))
    else:
        print('Prepared proof supplement; use --seal after actual UI and final gallery verification.')


if __name__ == '__main__':
    main()
