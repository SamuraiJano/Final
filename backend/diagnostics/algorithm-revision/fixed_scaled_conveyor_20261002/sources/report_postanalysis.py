"""Compare frozen conveyor inputs before and after motion-selection changes.

The same NPZ image/mask files are used in every variant. This runner never
calls detection, GrabCut, segmentation, or grading. Map coverage is a numerical
diagnostic, not reconstruction accuracy: these four tracks have no pose truth.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import shutil
import sys
import time

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


BACKEND = Path(__file__).resolve().parent
DIAGNOSTICS = BACKEND / 'diagnostics'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def load_algorithm(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_views(module, folder: Path):
    views = []
    for item in json.loads((folder / 'views.json').read_text(encoding='utf-8')):
        with np.load(folder / item['file']) as data:
            views.append(module.FruitView(data['image'].copy(), data['mask'].copy(), {},
                                         int(item['frame']), tuple(item['bbox'])))
    return views


def contact_sheet(views, path: Path) -> None:
    if not views:
        return
    columns, size = 8, 180
    rows = (len(views) + columns - 1) // columns
    canvas = np.full((rows * (size + 26), columns * size, 3), 245, np.uint8)
    for index, view in enumerate(views):
        image = view.image.copy()
        contours, _ = cv2.findContours(view.object_mask.astype(np.uint8),
                                      cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(image, contours, -1, (0, 220, 0), 1)
        scale = min((size - 12) / image.shape[1], (size - 12) / image.shape[0])
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        x, y = (index % columns) * size + 6, (index // columns) * (size + 26) + 26
        canvas[y:y + image.shape[0], x:x + image.shape[1]] = image
        cv2.putText(canvas, f'Frame {view.frame_index}', (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, .45, (25, 25, 25), 1)
    cv2.imwrite(str(path), canvas)


def trace_longitude(module, views, model, rotations, settings) -> dict:
    """Use the same selected reference basis and longitude equations as fusion."""
    poses = [np.eye(3)]
    for rotation in rotations:
        poses.append(rotation @ poses[-1])
    basis, radii = module._map_frame(model, settings)
    axes_ref = poses[model.reference_index].T @ basis
    axes = [pose @ axes_ref for pose in poses]
    centers = [np.arctan2((axes_i.T @ [0., 0., 1.])[2] / radii[2],
                         (axes_i.T @ [0., 0., 1.])[0] / radii[0]) for axes_i in axes]
    unwrapped = np.unwrap(centers)
    direction = float(np.sign(np.median(np.diff(unwrapped))))
    progress = direction * (unwrapped - unwrapped[0])
    steps = np.rad2deg(np.diff(progress))
    return {'frames': [view.frame_index for view in views],
            'reference_frame': views[model.reference_index].frame_index,
            'progress_deg': np.rad2deg(progress).tolist(),
            'longitude_steps_deg': steps.tolist(),
            'below_025_count': int(np.sum(steps < .25)),
            'backward_count': int(np.sum(steps < 0)),
            'above_maximum_count': int(np.sum(steps > settings.max_pair_angle_deg + 12)),
            'A': float(model.A), 'B': float(model.B)}


def instrument_estimator(module, adaptive: bool, attempts: list) -> None:
    estimator = module.estimate_rotation
    current = None
    if hasattr(module, '_search_rotation'):
        search = module._search_rotation

        def traced_search(source, target, model, index, settings):
            record = {'image_downsample': settings.image_downsample}
            if current is not None:
                current['searches'].append(record)
                if settings.image_downsample == 1 and len(current['searches']) > 1:
                    current['native_rechecked'] = True
            try:
                rotation, error = search(source, target, model, index, settings)
                record.update(status='accepted', error=float(error),
                    vector_deg=np.rad2deg(cv2.Rodrigues(rotation)[0].ravel()).tolist())
                return rotation, error
            except module.MappingError as error:
                record.update(status='failed', reason=str(error))
                raise

        module._search_rotation = traced_search

    def measured(source, target, model, index, settings, details=None):
        nonlocal current
        row = {'source_frame': source.frame_index, 'target_frame': target.frame_index,
               'image_downsample': settings.image_downsample,
               'adaptive_native': adaptive, 'searches': [], 'native_rechecked': False}
        attempts.append(row)
        current = row
        try:
            call_details = {}
            kwargs = {'details': call_details} if 'details' in inspect.signature(estimator).parameters else {}
            rotation, error = estimator(source, target, model, index, settings, **kwargs)
            vector = np.rad2deg(cv2.Rodrigues(rotation)[0].ravel())
            row.update(status='accepted', final_vector_deg=vector.tolist(), final_error=float(error),
                       estimator_details=call_details)
            if details is not None:
                details.update(call_details)
            return rotation, error
        except module.MappingError as error:
            row.update(status='failed_native' if row['native_rechecked'] else 'failed_coarse',
                       reason=str(error))
            raise
        finally:
            current = None

    module.estimate_rotation = measured


def fragmentation_metrics(diagnostics: list) -> dict:
    """Count original pair boundaries once, even if a child reference is rechecked."""
    reasons = {'failed_motion': set(), 'missing_source_frame': set(),
               'total_rotation_below_025': set(), 'longitude_below_025': set(),
               'longitude_backward': set(), 'longitude_above_maximum': set()}
    for row in diagnostics:
        if row.get('status') != 'split':
            continue
        pair = (row['source_frame'], row['target_frame'])
        reason = row.get('reason', '')
        if row.get('method') == 'map_trajectory_check':
            delta = row['longitude_delta_deg']
            reasons['longitude_below_025' if delta < .25 else 'longitude_above_maximum'].add(pair)
            if delta < 0:
                reasons['longitude_backward'].add(pair)
        elif 'Missing original frames' in reason:
            reasons['missing_source_frame'].add(pair)
        elif 'Unobservable change below 0.25' in reason:
            reasons['total_rotation_below_025'].add(pair)
        else:
            reasons['failed_motion'].add(pair)
    return {name: {'count': len(pairs), 'pairs': sorted(pairs)} for name, pairs in reasons.items()}


def run_variant(source: Path, name: str, folder: Path, inputs: Path,
                adaptive: bool, source_gap: int, image_downsample: int | None = None) -> dict:
    module = load_algorithm(source, f'algorithm_revision_{name}_{folder.parent.name}')
    views = load_views(module, inputs)
    settings = module.Settings(spheroid_type='auto', rotation_axis='x', rotation_direction=1,
        select_rotating_views=True, bidirectional_matching=True,
        minimum_longitude_coverage_deg=350, maximum_pair_gap_deg=55,
        defect_observations_complete=False)
    if name != 'baseline':
        settings = replace(settings, maximum_view_index_gap=source_gap)
    if image_downsample is not None:
        settings = replace(settings, image_downsample=image_downsample)
    attempts, selected_trace = [], {}
    instrument_estimator(module, adaptive, attempts)
    selector = module._select_rotating_views

    def tracing_selector(in_views, model, in_settings):
        selected, selected_model, rotations, errors, diagnostics = selector(in_views, model, in_settings)
        selected_trace.update(trace_longitude(module, selected, selected_model, rotations, in_settings))
        selected_trace.update(pair_errors=errors, selection_diagnostics=diagnostics,
            pair_vectors_deg=[np.rad2deg(cv2.Rodrigues(rotation)[0].ravel()).tolist()
                              for rotation in rotations])
        return selected, selected_model, rotations, errors, diagnostics

    module._select_rotating_views = tracing_selector
    started = time.perf_counter()
    row = {'name': name, 'algorithm_source_sha256': digest(source),
           'settings': asdict(settings), 'adaptive_recheck_threshold_deg': 3. if adaptive else None,
           'input_frames': [view.frame_index for view in views], 'grade_evaluated': False,
           'neural_inference_executed': False, 'mask_extraction_executed': False}
    try:
        mapped = module.build_surface_map(views, settings)
        if mapped.grade is not None:
            raise AssertionError('Geometry-only regression must not assign a grade')
        row.update(status=mapped.status, rotation_deg=mapped.rotation_coverage_deg,
                   longitude_deg=mapped.observed_longitude_deg,
                   surface_pct=mapped.observed_surface_pct, selected_frames=mapped.view_frames,
                   discarded_frames=mapped.discarded_view_frames,
                   selection_diagnostics=mapped.selection_diagnostics)
        cv2.imwrite(str(folder / 'surface_map.png'), mapped.bgr_map)
        cv2.imwrite(str(folder / 'observed_mask.png'), mapped.observed_mask * 255)
        selected_frames = set(mapped.view_frames)
        contact_sheet([view for view in views if view.frame_index in selected_frames],
                      folder / 'selected_views.png')
    except (module.MappingError, ValueError) as error:
        row.update(status='mapping_failed', reason=str(error))
    diagnostics = selected_trace.get('selection_diagnostics', row.get('selection_diagnostics', []))
    row.update(seconds=time.perf_counter() - started,
               estimator_attempt_count=len(attempts),
               native_recheck_count=sum(item.get('native_rechecked', False) for item in attempts),
               estimator_status_counts=dict(Counter(item['status'] for item in attempts)),
               selection_status_counts=dict(Counter(item.get('status', 'unspecified') for item in diagnostics)),
               selection_reason_counts=dict(Counter(item.get('reason', 'no_split_reason') for item in diagnostics)),
               fragmentation=fragmentation_metrics(diagnostics),
               selected_trace=selected_trace)
    save_json(folder / 'motion_attempts.json', attempts)
    save_json(folder / 'longitude_trace.json', selected_trace)
    save_json(folder / 'result.json', row)
    print(json.dumps({key: value for key, value in row.items() if key in
        ('name', 'status', 'reason', 'rotation_deg', 'longitude_deg', 'surface_pct',
         'seconds', 'estimator_attempt_count', 'native_recheck_count', 'selection_reason_counts')}), flush=True)
    return row


def figures_and_summary(output: Path, report: dict) -> None:
    figure, axes = plt.subplots(len(report['tracks']), 2, figsize=(13, 3.5 * len(report['tracks'])), squeeze=False)
    colors = {'baseline': '#777777', 'adjacent_only': '#247ba0', 'adjacent_native': '#c56b12',
              'native_all': '#345a35'}
    for panels, track in zip(axes, report['tracks']):
        for row in track['variants']:
            trace = row['selected_trace']
            if trace:
                panels[0].plot(trace['frames'], trace['progress_deg'], marker='.',
                               label=row['name'], color=colors[row['name']])
        panels[0].set(title=f'Frozen conveyor track {track["track"]}', xlabel='Source frame',
                      ylabel='Estimated longitude progress (degrees)')
        panels[0].legend(fontsize=8)
        variants = track['variants']
        panels[1].barh([row['name'] for row in variants], [row.get('longitude_deg', 0.) for row in variants],
                       color=[colors[row['name']] for row in variants])
        panels[1].axvline(350, color='#b42d33', linestyle='--', label='Eligibility threshold')
        panels[1].set(xlim=(0, 365), xlabel='Numerically observed longitude (degrees)')
        for index, row in enumerate(variants):
            if row['status'] == 'mapping_failed':
                panels[1].text(3, index, 'Mapping failed', va='center', fontsize=8)
    figure.suptitle('Identical real images and masks: motion-selection comparison\nCoverage is a diagnostic; no pose or grade ground truth', fontsize=14)
    figure.tight_layout(rect=(0, 0, 1, .96))
    figure.savefig(output / 'fixed_input_comparison.png', dpi=300)
    figure.savefig(output / 'fixed_input_comparison.pdf')
    plt.close(figure)

    lines = ['# Fixed conveyor input regression', '',
        'Every variant receives identical frozen BGR crops and fruit masks. No detector, '
        'GrabCut, defect segmenter, or grading runs. These inputs have no labelled pose '
        'or defect truth, so improved coverage is not evidence of improved accuracy.', '',
        'The baseline is the preserved production source from the preceding audit. '
        'The adjacent candidate breaks on rejected motion and unknown source-frame gaps. '
        'The native variant rechecks only accepted quarter-resolution estimates below '
        '3 degrees at original crop resolution; a coarse residual failure is never rescued.', '',
        '| Track | Variant | Result | Selected views | Rotation / longitude (deg) | Native rechecks |',
        '|---|---|---|---:|---:|---:|']
    for track in report['tracks']:
        for row in track['variants']:
            lines.append(f'| {track["track"]} | {row["name"]} | {row["status"]} | '
                         f'{len(row.get("selected_frames", []))} | '
                         f'{row.get("rotation_deg", 0.):.2f} / {row.get("longitude_deg", 0.):.2f} | '
                         f'{row["native_recheck_count"]} |')
    lines += ['', '## Fragmentation and ordering', '',
              'The JSON and per-pair logs retain every estimate and selection decision. '
              'A short retained segment can result from residual rejection, a missing source frame, '
              'or longitude ordering checks. The following counts expose these causes rather '
              'than treating a successful map as accuracy evidence.', '']
    for track in report['tracks']:
        lines.append(f'### Track {track["track"]}')
        lines.append('')
        for row in track['variants']:
            trace = row['selected_trace']
            lines.append(f'- {row["name"]}: {row["estimator_status_counts"]}; '
                         f'selection reasons {row["selection_reason_counts"]}; '
                         f'final steps below 0.25 degrees: {trace.get("below_025_count", "not available")}; '
                         f'backwards steps: {trace.get("backward_count", "not available")}.')
        lines.append('')
    lines += ['### Unique boundaries that split each candidate', '',
              'The counts below concern original source-frame pairs. Repeated checks of '
              'a pair after a reference-frame change count once. Backwards longitude '
              'is a subset of longitude below 0.25 degrees.', '',
              '| Track | Variant | Failed motion | Missing frame | Total rotation <0.25 deg | Longitude <0.25 deg | Backwards longitude |',
              '|---|---|---:|---:|---:|---:|---:|']
    for track in report['tracks']:
        for row in track['variants']:
            if row['name'] == 'baseline':
                continue
            counts = row['fragmentation']
            lines.append(f'| {track["track"]} | {row["name"]} | '
                f'{counts["failed_motion"]["count"]} | {counts["missing_source_frame"]["count"]} | '
                f'{counts["total_rotation_below_025"]["count"]} | '
                f'{counts["longitude_below_025"]["count"]} | '
                f'{counts["longitude_backward"]["count"]} |')
    lines += ['## Reproduction', '', '```powershell',
              report['reproduction_command'], '```', '',
              'Source files, settings, script, and input hashes are frozen beside this report. '
              'The report was generated from actual saved images; the evidence images are not synthetic.']
    (output / 'REGRESSION.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--native-candidate', type=Path,
        default=DIAGNOSTICS / 'algorithm-revision/adjacent_native_source/algorithm_snapshot.py')
    parser.add_argument('--baseline', type=Path,
        default=DIAGNOSTICS / 'algorithm-revision/production_before_20261002/algorithm.py')
    parser.add_argument('--label', default='fixed_conveyor_20261002')
    parser.add_argument('--source-frame-gap', type=int, default=1)
    parser.add_argument('--native-only', action='store_true',
                        help='Run only the native candidate at the specified resolution')
    parser.add_argument('--image-downsample', type=int,
                        help='Override crop resolution; 1 means original pixels')
    args = parser.parse_args()
    candidate, baseline, native = args.candidate.resolve(), args.baseline.resolve(), args.native_candidate.resolve()
    if not all(path.is_file() for path in (candidate, baseline, native)):
        raise FileNotFoundError('Candidate, native candidate, and baseline sources must exist')
    output = DIAGNOSTICS / 'algorithm-revision' / args.label
    output.mkdir(parents=True, exist_ok=False)
    snapshots = output / 'sources'
    snapshots.mkdir()
    shutil.copy2(baseline, snapshots / 'baseline.py')
    shutil.copy2(candidate, snapshots / 'adjacent_candidate.py')
    shutil.copy2(native, snapshots / 'adjacent_native.py')
    shutil.copy2(Path(__file__), snapshots / Path(__file__).name)
    cv2.setNumThreads(1)
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
        'scope': 'Fixed-input geometry regression; map eligibility is not accuracy.',
        'sources': {'baseline': str(baseline), 'candidate': str(candidate), 'native_candidate': str(native)},
        'source_sha256': {path.name: digest(path) for path in snapshots.iterdir()},
        'source_frame_gap': args.source_frame_gap,
        'reproduction_command': f'.\\backend\\venv\\Scripts\\python.exe -B "{snapshots / Path(__file__).name}" '
            f'--candidate "{snapshots / "adjacent_candidate.py"}" '
            f'--native-candidate "{snapshots / "adjacent_native.py"}" '
            f'--baseline "{snapshots / "baseline.py"}" '
            f'--label <new-label> --source-frame-gap {args.source_frame_gap}',
        'tracks': []}
    if args.native_only:
        report['reproduction_command'] += ' --native-only'
    if args.image_downsample is not None:
        report['reproduction_command'] += f' --image-downsample {args.image_downsample}'
    variants = [('baseline', snapshots / 'baseline.py', False),
                ('adjacent_only', snapshots / 'adjacent_candidate.py', False),
                ('adjacent_native', snapshots / 'adjacent_native.py', True)]
    if args.native_only:
        variants = [('native_all', snapshots / 'adjacent_native.py', False)]
    fixtures = [(track, DIAGNOSTICS / 'algorithm-audit/corrected_tracks_20261002' / str(track))
                for track in (98, 1, 14)]
    fixtures.append((491, DIAGNOSTICS / 'algorithm-audit/longitude_failure_491_20261002/captured_views'))
    for track, original in fixtures:
        folder = output / str(track)
        folder.mkdir()
        inputs = folder / 'inputs'
        inputs.mkdir()
        manifest = json.loads((original / 'views.json').read_text(encoding='utf-8'))
        shutil.copy2(original / 'views.json', inputs / 'views.json')
        hashes = {}
        for item in manifest:
            shutil.copy2(original / item['file'], inputs / item['file'])
            hashes[item['file']] = digest(inputs / item['file'])
        save_json(inputs / 'sha256.json', hashes)
        base_module = load_algorithm(snapshots / 'baseline.py', f'revision_input_{track}')
        contact_sheet(load_views(base_module, inputs), folder / 'all_input_views.png')
        track_report = {'track': track, 'original_fixture': str(original),
                        'input_count': len(manifest), 'input_sha256': hashes, 'variants': []}
        report['tracks'].append(track_report)
        for name, source, adaptive in variants:
            destination = folder / name
            destination.mkdir()
            print(f'Track {track}: {name}', flush=True)
            track_report['variants'].append(run_variant(source, name, destination, inputs,
                                                        adaptive, args.source_frame_gap,
                                                        args.image_downsample))
            save_json(output / 'report.json', report)
    report['completed_at'] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    save_json(output / 'report.json', report)
    figures_and_summary(output, report)
    print(f'Completed fixed-input evidence: {output}', flush=True)


if __name__ == '__main__':
    main()
