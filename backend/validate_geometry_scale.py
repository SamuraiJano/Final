"""Audit the fixed-size spheroid assumption using preserved silhouette measurements.

This is a read-only setup check. It neither normalizes nor changes images,
estimates new motion, executes neural models, nor evaluates classification.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from validate_algorithm_revision import load_algorithm, load_views, save_json


BACKEND = Path(__file__).resolve().parent
DIAGNOSTICS = BACKEND / 'diagnostics'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def radius_stats(rows: list, A: float) -> dict:
    major = np.asarray([row['major_px'] for row in rows], dtype=float)
    minor = np.asarray([row['minor_px'] for row in rows], dtype=float)
    frames = np.asarray([row['frame'] for row in rows], dtype=float)
    mean = float(major.mean())
    result = {'views': len(rows), 'major_mean_px': mean,
        'major_min_px': float(major.min()), 'major_max_px': float(major.max()),
        'major_population_std_px': float(major.std()),
        'major_cv_pct': float(100 * major.std() / mean),
        'major_range_relative_mean_pct': float(100 * np.ptp(major) / mean),
        'major_min_relative_A_pct': float(100 * (major.min() / A - 1)),
        'major_max_relative_A_pct': float(100 * (major.max() / A - 1)),
        'major_max_absolute_deviation_from_A_pct': float(100 * np.max(np.abs(major - A)) / A),
        'major_first_last_change_pct': float(100 * (major[-1] / major[0] - 1)),
        'minor_min_px': float(minor.min()), 'minor_max_px': float(minor.max()),
        'major_frame_correlation': None,
        'major_linear_trend_pct_per_100_frames': None}
    if len(rows) > 1 and np.std(frames) > 0 and np.std(major) > 0:
        result['major_frame_correlation'] = float(np.corrcoef(frames, major)[0, 1])
        result['major_linear_trend_pct_per_100_frames'] = float(np.polyfit(frames, major, 1)[0] / mean * 10000)
    return result


def distribution(values) -> dict:
    values = np.asarray(values, dtype=float)
    return {'sequences': len(values), 'median': float(np.median(values)),
            'p90': float(np.percentile(values, 90)), 'minimum': float(values.min()),
            'maximum': float(values.max())}


def plot_radius_traces(output: Path, report: dict) -> None:
    figure, axes = plt.subplots(4, 2, figsize=(13, 12))
    for panels, track in zip(axes, report['real_tracks']):
        rows, A, B = track['silhouettes'], track['model']['A_px'], track['model']['B_px']
        frames = [row['frame'] for row in rows]
        major = np.asarray([row['major_px'] for row in rows])
        minor = np.asarray([row['minor_px'] for row in rows])
        panels[0].plot(frames, major, label='Measured major radius', color='#a85918')
        panels[0].plot(frames, minor, label='Measured minor radius', color='#247ba0')
        panels[0].axhline(A, color='#a85918', linestyle='--', label='Shared fitted A')
        panels[0].axhline(B, color='#247ba0', linestyle='--', label='Shared fitted B')
        selected = track['selected_frames_from_52c13']
        if selected:
            panels[0].axvspan(min(selected), max(selected), color='#6f9870', alpha=.13,
                             label='Selected mapping segment')
        panels[0].set(title=f'Conveyor track {track["track"]}', xlabel='Original video frame',
                      ylabel='Ellipse semi-axis (original pixels)')
        panels[0].legend(fontsize=7, ncol=2)
        panels[1].plot(frames, 100 * (major / A - 1), color='#a85918')
        panels[1].axhline(0, color='black', linewidth=.7)
        panels[1].axvspan(min(selected), max(selected), color='#6f9870', alpha=.13)
        panels[1].set(xlabel='Original video frame', ylabel='Major radius deviation from A (%)')
    figure.suptitle('Same preserved fruit masks: does one fixed pixel radius describe every view?\nMeasured variation does not identify its physical cause', fontsize=13)
    figure.tight_layout(rect=(0, 0, 1, .95))
    figure.savefig(output / 'conveyor_radius_traces.png', dpi=300)
    figure.savefig(output / 'conveyor_radius_traces.pdf')
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    authors = report['author_sequences']
    cvs = [row['stats']['major_cv_pct'] for row in authors]
    ranges = [row['stats']['major_range_relative_mean_pct'] for row in authors]
    for panel, values, key, label in zip(axes, (cvs, ranges),
        ('major_cv_pct', 'major_range_relative_mean_pct'),
        ('Major radius CV (%)', 'Major radius range / mean (%)')):
        panel.scatter(np.zeros(len(values)), values, color='#247ba0', alpha=.5,
                      label='All 36 author sequences')
        for position, track in enumerate(report['real_tracks'], 1):
            panel.scatter(position, track['all_view_stats'][key], color='#a85918', s=65)
            panel.scatter(position, track['selected_view_stats'][key], color='#376b3c',
                          marker='x', s=65)
        panel.set(xticks=range(5), xticklabels=['Authors'] + [str(t['track']) for t in report['real_tracks']],
                  xlabel='Sequence / actual tracker ID', ylabel=label)
        panel.scatter([], [], color='#a85918', label='All preserved conveyor views')
        panel.scatter([], [], color='#376b3c', marker='x', label='Selected conveyor segment')
        panel.legend(fontsize=8)
    figure.suptitle('Silhouette scale variation: reference images versus real conveyor\nDifferent sequence lengths and mask methods; not an accuracy test', fontsize=13)
    figure.tight_layout(rect=(0, 0, 1, .91))
    figure.savefig(output / 'author_conveyor_scale_comparison.png', dpi=300)
    figure.savefig(output / 'author_conveyor_scale_comparison.pdf')
    plt.close(figure)


def image_examples(output: Path, module, report: dict, fixed: Path) -> None:
    figure, axes = plt.subplots(4, 4, figsize=(13, 13))
    for panels, track in zip(axes, report['real_tracks']):
        views = load_views(module, fixed / str(track['track']) / 'inputs')
        major = [row['major_px'] for row in track['silhouettes']]
        choices = [('First', 0), ('Smallest', int(np.argmin(major))),
                   ('Largest', int(np.argmax(major))), ('Last', len(views) - 1)]
        for panel, (label, index) in zip(panels, choices):
            view = views[index]
            ellipse = module._ellipse(view.object_mask)
            image = view.image.copy()
            angle = np.rad2deg(np.arctan2(ellipse.v_major[1], ellipse.v_major[0]))
            cv2.ellipse(image, tuple(np.rint(ellipse.center).astype(int)),
                        (round(ellipse.major), round(ellipse.minor)), float(angle), 0, 360,
                        (255, 0, 255), 1)
            contours, _ = cv2.findContours(view.object_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(image, contours, -1, (0, 255, 0), 1)
            panel.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            panel.set_title(f'Track {track["track"]}: {label}, frame {view.frame_index}\na={ellipse.major:.2f}px; b={ellipse.minor:.2f}px', fontsize=9)
            panel.axis('off')
    figure.suptitle('Actual preserved crops: green mask contour, magenta fitted ellipse\nNo image warping, new masks, or neural inference', fontsize=13)
    figure.tight_layout(rect=(0, 0, 1, .94))
    figure.savefig(output / 'scale_mask_examples.png', dpi=300)
    figure.savefig(output / 'scale_mask_examples.pdf')
    plt.close(figure)


def markdown(output: Path, report: dict) -> None:
    summary = report['author_summary']['all']
    lines = ['# Fixed-size spheroid setup audit', '',
        'This diagnostic uses the same frozen 215 conveyor crops and fruit masks as the '
        'fixed-input reconstruction comparisons. It estimates only ellipse radii and '
        'shared spheroid dimensions. No motion estimator, detector, GrabCut, defect '
        'segmenter, image normalization, or grading runs.', '',
        'The source is frozen production revision `52c13a0452875653fb054053fcc0bdbb4a6ed9cb4227c697be32b62fbe811327`. '
        'Selected segments are read from that revision\'s existing results; a later '
        'algorithm revision does not change this historical audit.', '',
        'The [2021 paper, sections 3.1 and 3.1.2](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) '
        'approximates the camera as a parallel projection and fits one shared spheroid '
        'size per fruit. For an ideal oblate spheroid, the projected major radius stays '
        'approximately equal to its equatorial radius A while the minor radius changes '
        'with pose. Thus major-radius variation is a useful consistency check. The '
        'paper allows real fruit and silhouettes to depart from the ideal shape.', '',
        'CV = 100 × population standard deviation / mean major radius. Relative range '
        '= 100 × (maximum − minimum) / mean major radius. Values below use original '
        'image pixels, not rescaled thumbnails.', '',
        '| Real track | Views | A / B (px) | Major radius min..max (px) | CV (%) | Range / mean (%) | First-to-last change (%) |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for track in report['real_tracks']:
        stats, model = track['all_view_stats'], track['model']
        lines.append(f'| {track["track"]} | {stats["views"]} | {model["A_px"]:.2f} / {model["B_px"]:.2f} | '
            f'{stats["major_min_px"]:.2f}..{stats["major_max_px"]:.2f} | {stats["major_cv_pct"]:.2f} | '
            f'{stats["major_range_relative_mean_pct"]:.2f} | {stats["major_first_last_change_pct"]:+.2f} |')
    lines += ['', f'Across all 36 author sequences, the median major-radius CV is '
        f'{summary["major_cv_pct"]["median"]:.2f}% and maximum is '
        f'{summary["major_cv_pct"]["maximum"]:.2f}%. Median relative range is '
        f'{summary["major_range_relative_mean_pct"]["median"]:.2f}% and maximum is '
        f'{summary["major_range_relative_mean_pct"]["maximum"]:.2f}%.', '',
        'Conveyor tracks 98 and 491 exceed the maximum CV in this author sample. '
        'Tracks 1 and 14 overlap the author range. This is a discrepancy in two '
        'sample tracks, not evidence that every conveyor track violates the model.', '',
        '| Real track | Selected source frames | Selected CV (%) | Selected range / mean (%) | Maximum major deviation from shared A (%) |',
        '|---|---|---:|---:|---:|']
    for track in report['real_tracks']:
        stats, frames = track['selected_view_stats'], track['selected_frames_from_52c13']
        lines.append(f'| {track["track"]} | {frames[0]}..{frames[-1]} | '
            f'{stats["major_cv_pct"]:.2f} | {stats["major_range_relative_mean_pct"]:.2f} | '
            f'{stats["major_max_absolute_deviation_from_A_pct"]:.2f} |')
    lines += ['', '## Interpretation and limits', '',
        'A changing pixel radius can arise from perspective and distance changes, '
        'silhouette extraction error, fruit shape departing from a spheroid, or a '
        'combination. This audit has no calibrated camera depth, manual silhouette '
        'truth, or known fruit orientation, so it cannot identify which cause dominates. '
        'Minor-radius variation alone is expected when an oblate fruit rotates.', '',
        'The author comparison uses frozen silhouette statistics from the complete '
        '36-sequence benchmark, originally derived from their isolated black-background '
        'images. The conveyor comparison uses preserved GrabCut masks. These mask '
        'methods and sequence lengths differ. The authors\' measurements are a reference '
        'distribution, not a ground-truth tolerance or a universal acceptance cutoff.', '',
        'No geometry change is justified solely by these measurements. A normalization '
        'trial would need a known-pose control and manual correspondence evaluation '
        'before treating scale variation as the cause of a reconstruction failure.', '',
        '## Evidence', '',
        '- `conveyor_radius_traces.png/pdf`: all major/minor radii and selected frame intervals.',
        '- `author_conveyor_scale_comparison.png/pdf`: all 36 author sequences and four real tracks.',
        '- `scale_mask_examples.png/pdf`: actual first/minimum/maximum/last crops with masks and fitted ellipses.',
        '- `report.json`: per-view radii, models, settings, input hashes, and grouped author statistics.',
        '- `sources/`: exact frozen algorithm, author report, paper text, and diagnostic script.', '',
        'All plots are saved at 300 dpi; source data and source hashes are retained.']
    (output / 'GEOMETRY_SCALE_AUDIT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='geometry_scale_audit_20261002')
    args = parser.parse_args()
    fixed = DIAGNOSTICS / 'algorithm-revision/fixed_scaled_conveyor_20261002'
    output = DIAGNOSTICS / 'algorithm-revision' / args.label
    output.mkdir(parents=True, exist_ok=False)
    sources = output / 'sources'
    sources.mkdir()
    source_files = {'algorithm_snapshot.py': fixed / 'sources/adjacent_native.py',
        'author_operational_reference.json': DIAGNOSTICS / 'authors-benchmark/runs/operational_profile_v1/report.json',
        'PMC8004661.txt': DIAGNOSTICS / 'authors-benchmark/papers/PMC8004661.txt',
        Path(__file__).name: Path(__file__)}
    for name, path in source_files.items():
        shutil.copy2(path, sources / name)
    module = load_algorithm(sources / 'algorithm_snapshot.py', 'geometry_scale_frozen')
    author_report = json.loads((sources / 'author_operational_reference.json').read_text(encoding='utf-8'))
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
        'scope': 'Setup consistency audit; no motion estimation, normalization, neural inference, new masks, or grade.',
        'source_sha256': {name: digest(sources / name) for name in source_files},
        'conveyor_fixture': str(fixed), 'author_reference': str(source_files['author_operational_reference.json']),
        'author_reference_algorithm_sha256': author_report['algorithm_sha256'],
        'author_mask_method': author_report['mask_method'],
        'author_repositories': author_report['source_repositories'],
        'real_tracks': [], 'author_sequences': []}
    for identity in (98, 1, 14, 491):
        folder = fixed / str(identity)
        views = load_views(module, folder / 'inputs')
        settings = module.Settings(spheroid_type='auto', rotation_axis='x', rotation_direction=1)
        model = module.fit_spheroid(views, settings)
        selected = json.loads((folder / 'adjacent_native/result.json').read_text(encoding='utf-8'))['selected_frames']
        rows = [{'frame': view.frame_index, 'major_px': ellipse.major, 'minor_px': ellipse.minor,
                 'center_px': ellipse.center.tolist(), 'mask_pixels': int(view.object_mask.sum()),
                 'major_deviation_from_A_pct': 100 * (ellipse.major / model.A - 1),
                 'selected': view.frame_index in selected}
                for view, ellipse in zip(views, model.ellipses)]
        input_hashes = json.loads((folder / 'inputs/sha256.json').read_text(encoding='utf-8'))
        for filename, expected in input_hashes.items():
            assert digest(folder / 'inputs' / filename) == expected
        report['real_tracks'].append({'track': identity, 'settings': asdict(settings),
            'model': {'A_px': model.A, 'B_px': model.B, 'B_over_A': model.B / model.A,
                      'reference_frame': views[model.reference_index].frame_index},
            'selected_frames_from_52c13': selected, 'silhouettes': rows,
            'all_view_stats': radius_stats(rows, model.A),
            'selected_view_stats': radius_stats([row for row in rows if row['selected']], model.A),
            'input_sha256': input_hashes})
    for track in author_report['tracks']:
        rows = [{'frame': row['view'], 'major_px': row['major'], 'minor_px': row['minor']}
                for row in track['silhouettes']]
        A = track['geometry']['A']
        report['author_sequences'].append({'group': track['group'], 'object': track['object'],
            'A_px': A, 'B_px': track['geometry']['B'], 'silhouettes': rows,
            'stats': radius_stats(rows, A)})
    report['author_summary'] = {}
    for group in ['all'] + sorted({track['group'] for track in report['author_sequences']}):
        selected = [track for track in report['author_sequences'] if group == 'all' or track['group'] == group]
        report['author_summary'][group] = {key: distribution([track['stats'][key] for track in selected])
            for key in ('major_cv_pct', 'major_range_relative_mean_pct')}
    save_json(output / 'report.json', report)
    plot_radius_traces(output, report)
    image_examples(output, module, report, fixed)
    markdown(output, report)
    print(json.dumps(report['author_summary'], indent=2), flush=True)
    for track in report['real_tracks']:
        print(track['track'], track['all_view_stats'], flush=True)
    print(f'Completed scale audit: {output}', flush=True)


if __name__ == '__main__':
    main()
