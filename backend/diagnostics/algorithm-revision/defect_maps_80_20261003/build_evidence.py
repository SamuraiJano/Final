"""Copy selected saved proof, draw report figures, and optionally seal a ZIP.

No detector, tracker, segmenter or reconstruction runs here. Original results
and earlier evidence bundles are read only. Run from the project root.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
ROOT = BACKEND.parent
JOB_ID = 'd0cb7e25b5e14d76a7ebf03c111e259b'
SOURCE_ID = 'ed3aa02cca364812a145610aad627a83'
COLOURS = {
    'Dark marking': '#38bdf8',
    'Light brown discolouration': '#facc15',
    'Open skin': '#ef4444',
    'Skin wrinkling': '#a78bfa',
    'Wind scarring': '#4ade80',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert digest(source) == digest(target)


def saved_asset(url):
    assert url.startswith('/results/')
    path = (BACKEND / url.lstrip('/')).resolve()
    path.relative_to((BACKEND / 'results').resolve())
    assert path.is_file()
    return path


def copy_proof():
    report = read_json(BACKEND / 'results' / JOB_ID / 'report.json')
    summary = read_json(HERE / 'summary.json')
    assert digest(BACKEND / 'results' / SOURCE_ID / 'report.json') == \
        summary['original_report_sha256']
    assert digest(BACKEND / 'results' / JOB_ID / 'report.json') == \
        read_json(HERE / 'metadata_finalization.json')['final_report_sha256']
    ui_folder = BACKEND / 'diagnostics/ui-checks/defect_maps_80_actual_20261003'
    ui = read_json(ui_folder / 'report.json')
    assert ui['passed'] and ui['job_id'] == JOB_ID
    assert all(item['method'] == 'GET' for item in ui['api_requests'])
    checks_folder = BACKEND / 'diagnostics/software-checks/defect_maps_80_20261003'
    checks = read_json(checks_folder / 'summary.json')
    assert all(item['exit_code'] == 0 for item in checks['checks'])
    for name, expected in checks['source_sha256'].items():
        assert digest(ROOT / name) == expected, name
        copy_file(ROOT / name, HERE / 'source' / name)
    for name in ['README.md', 'backend/ALGORITHM_EXPLAINED.md',
                 'backend/TESTING_PROCESS.md',
                 'backend/diagnostics/authors-benchmark/DEVELOPMENT_LOG.md']:
        copy_file(ROOT / name, HERE / 'documentation' / Path(name).name)
    for folder, target in [(ui_folder, 'actual_ui'), (checks_folder, 'checks'),
                           (BACKEND / 'diagnostics/ui-checks/defect_overlay_fixture_caption_20261003',
                            'artificial_ui_controls')]:
        for path in folder.glob('*'):
            if path.is_file():
                copy_file(path, HERE / target / path.name)
    independent_qa = HERE.parent / 'defect_maps_80_20261003_root_qa.json'
    if independent_qa.is_file():
        copy_file(independent_qa, HERE / 'checks/root_independent_map_qa.json')
    audit_folder = HERE.parent / 'tracking_identity_20261003'
    for path in audit_folder.glob('*'):
        if path.is_file():
            copy_file(path, HERE / 'tracking_identity' / path.name)
    examples = []
    for track_id in [98, 340, 32]:
        row = next(row for row in report['fruits'] if row['track_id'] == track_id)
        folder = HERE / 'examples' / str(track_id)
        copy_file(BACKEND / 'results' / JOB_ID / str(track_id) / 'result.json',
                  folder / 'result.json')
        assets = {'surface_map.png': row['surface_map'],
                  'surface_map_overlay.png': row['surface_map_overlay'],
                  'observed.png': row['observed_mask']}
        assets.update({f'defect_{name}.png': url for name, url in row['defect_maps'].items()})
        hashes = []
        for name, url in assets.items():
            source = saved_asset(url)
            copy_file(source, folder / name)
            hashes.append({'name': name, 'original_url': url, 'sha256': digest(source)})
        examples.append({'track_id': track_id, 'grade': row['grade'],
                         'grade_provisional': row['grade_provisional'],
                         'coverage_complete': row['coverage_complete'],
                         'coverage_target_pct': row['coverage_target_pct'],
                         'observed_surface_pct': row['observed_surface_pct'],
                         'observed_longitude_deg': row['observed_longitude_deg'],
                         'defect_pct_of_observed': row['defect_pct_of_observed'],
                         'assets': hashes})
    records = [{key: row.get(key) for key in
                ['track_id', 'grade', 'status', 'grade_provisional', 'coverage_complete',
                 'coverage_target_pct', 'observed_surface_pct', 'observed_longitude_deg',
                 'defect_pct_of_observed', 'surface_map', 'surface_map_overlay']}
               for row in report['fruits']]
    write_json(HERE / 'all_474_display_records.json', records)
    write_json(HERE / 'examples.json', examples)
    originals = read_json(HERE / 'original_assets.json')
    for item in originals:
        assert digest(BACKEND / item['path']) == item['sha256'], item['path']
    old_packs = {}
    for name in ['evi_runtime_20261003.zip', 'partial_grades_20261003.zip']:
        path = HERE.parent / name
        old_packs[name] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    assert old_packs['evi_runtime_20261003.zip']['sha256'] == \
        '5b1a429d17548f7025f9f90f24bae7d1e19e1d5190cf9bd0ca5f1aec562acefb'
    assert old_packs['partial_grades_20261003.zip']['sha256'] == \
        'a8d0004444db14792bfb5dd9738cdf36ceb11aa72fa400298cfb5c8f9ce5f754'
    write_json(HERE / 'provenance.json', {
        'saved_job_id': JOB_ID, 'derived_from_job_id': SOURCE_ID,
        'original_full_video_job_id': 'ea6e595b8f3f45f2b5edfda8dafff3f2',
        'report_sha256': digest(BACKEND / 'results' / JOB_ID / 'report.json'),
        'source_report_sha256': digest(BACKEND / 'results' / SOURCE_ID / 'report.json'),
        'analysis_kind': report['analysis_kind'],
        'grading_policy': report['grading_policy'],
        'previous_grading_policy': report['previous_grading_policy'],
        'original_mapping_geometry_settings': report['metrics']['geometry_settings'],
        'display_policy': report['display_policy'],
        'grades': dict(Counter(row['grade'] or 'ungraded' for row in report['fruits'])),
        'original_map_and_mask_hashes_rechecked': len(originals),
        'new_model_tracker_and_reconstruction_calls': 0,
        'earlier_sealed_bundles_verified_unchanged': old_packs,
        'actual_ui_runtime_note': ui['runtime_note'],
        'actual_ui_checked_at': ui['checked_at'],
        'actual_ui_api_restarted': ui['api_restarted'],
        'actual_ui_analysis_cancelled': ui['analysis_cancelled'],
    })
    return examples


def draw_examples(examples):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11})
    figure, axes = plt.subplots(3, 3, figsize=(18, 11.5))
    figure.suptitle('Actual naartjie maps: preserved texture and coloured predicted defects',
                   fontsize=19, y=.975)
    columns = [('surface_map.png', 'Original surface texture'),
               ('surface_map_overlay.png', 'Defect-category overlay'),
               ('observed.png', 'Observed-area mask: white = observed')]
    for row_index, example in enumerate(examples):
        track_id = example['track_id']
        partial = ' (partial)' if example['grade_provisional'] else ''
        for column_index, (filename, title) in enumerate(columns):
            ax = axes[row_index, column_index]
            image = np.array(Image.open(HERE / 'examples' / str(track_id) / filename))
            ax.imshow(image, cmap='gray' if column_index == 2 else None,
                      vmin=0 if column_index == 2 else None,
                      vmax=255 if column_index == 2 else None)
            ax.axis('off')
            ax.set_title(title, fontsize=12, pad=8)
        label = (f'Fruit {track_id} | {example["grade"]}{partial} | '
                 f'{example["observed_surface_pct"]:.2f}% observed surface | '
                 f'{example["defect_pct_of_observed"]:.2f}% defects / observed area')
        axes[row_index, 0].text(0, -.11, label, transform=axes[row_index, 0].transAxes,
                               ha='left', va='top', fontsize=11)
    handles = [Patch(facecolor=colour, label=label) for label, colour in COLOURS.items()]
    figure.legend(handles=handles, loc='lower center', ncol=5,
                  bbox_to_anchor=(.5, .076), frameon=False, fontsize=11)
    figure.text(.5, .047,
                'Full map canvas retained. Unseen black regions remain unassessed; '
                'they are not clean skin. The overlay changes no map masks or areas.',
                ha='center', fontsize=11)
    figure.text(.5, .022,
                'Saved actual model predictions, not human defect truth. '
                'Regular coverage target: 80% surface plus 350 degrees longitude. '
                'Colours denote defect categories, not overall quality class.',
                ha='center', fontsize=10)
    figure.subplots_adjust(left=.035, right=.985, top=.90, bottom=.15,
                           wspace=.08, hspace=.48)
    folder = HERE / 'figures'
    folder.mkdir(exist_ok=True)
    figure.savefig(folder / 'actual_defect_maps_300dpi.png', dpi=300)
    figure.savefig(folder / 'actual_defect_maps.pdf')
    plt.close(figure)


def seal():
    ignored = {'manifest.json', 'seal.json'}
    files = sorted(path for path in HERE.rglob('*')
                   if path.is_file() and path.name not in ignored)
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(),
                'files': [{'path': path.relative_to(HERE).as_posix(),
                           'bytes': path.stat().st_size, 'sha256': digest(path)}
                          for path in files]}
    write_json(HERE / 'manifest.json', manifest)
    archive = HERE.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as stream:
        for path in files + [HERE / 'manifest.json']:
            stream.write(path, path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(archive) as stream:
        assert stream.testzip() is None
        for item in manifest['files']:
            assert hashlib.sha256(stream.read(item['path'])).hexdigest() == item['sha256']
    write_json(HERE / 'seal.json', {'files': len(files),
        'zip_bytes': archive.stat().st_size, 'zip_sha256': digest(archive),
        'zip_crc': 'pass', 'manifest_verification': 'pass',
        'note': 'seal.json is an external receipt; manifest excludes itself and this receipt.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal', action='store_true')
    args = parser.parse_args()
    examples = copy_proof()
    draw_examples(examples)
    if args.seal:
        seal()
    print(json.dumps({'examples': len(examples), 'built': True, 'sealed': args.seal}))


if __name__ == '__main__':
    main()
