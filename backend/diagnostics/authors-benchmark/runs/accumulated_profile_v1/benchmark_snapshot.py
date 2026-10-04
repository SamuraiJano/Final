"""Reproducible, isolated benchmark against the Albiol authors' public data.

No detector, tracker, defect network, server, or production settings are changed.
Run with backend/venv/Scripts/python.exe -B backend/benchmark_authors.py download
and then use the 'run' subcommand described by --help.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time
import urllib.request

import cv2
import numpy as np

from algorithm import (FruitView, MappingError, Settings, _ellipse, _height,
                       _largest_component, build_surface_map, estimate_rotation,
                       fit_spheroid)

ROOT = Path(__file__).resolve().parent / 'diagnostics' / 'authors-benchmark'
DATA = ROOT / 'data'
SOURCES = {
    'rotation': ('alalbiol/3d-rotation-estimation-fruits',
                 'f20d6757052388c4f86048a0d5f7ad015c29bb08'),
    'maps': ('csdemeras/FSMap', '4e148a1b436374948a9102ad39cdc4d5b3e36eb3'),
}


def fetch(url: str) -> bytes:
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'fruit-reference-benchmark'})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def download() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for key, (repo, commit) in SOURCES.items():
        tree = json.loads(fetch(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1'))
        if tree.get('truncated'):
            raise RuntimeError('Incomplete repository listing')
        selected = [item for item in tree['tree'] if item['type'] == 'blob' and (
            item['path'] in {'README.md', 'LICENSE'} or
            (key == 'rotation' and item['path'].startswith('data/')) or
            (key == 'maps' and item['path'] in {
                'mandarin/objM0001_2R.png', 'mandarin/unrolled_objM0001.png',
                'mandarin/objM0005_2R.png', 'mandarin/unrolled_objM0005.png'}))]

        def save(item):
            path = DATA / key / item['path']
            url = f"https://raw.githubusercontent.com/{repo}/{commit}/{item['path']}"
            if not path.exists():
                payload = fetch(url)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            payload = path.read_bytes()
            git_sha = hashlib.sha1(f'blob {len(payload)}\0'.encode() + payload).hexdigest()
            if git_sha != item['sha']:
                raise RuntimeError(f'Content integrity check failed: {path}')
            return {'file': str(path.relative_to(ROOT)), 'url': url,
                    'git_blob_sha': git_sha, 'sha256': hashlib.sha256(payload).hexdigest(),
                    'bytes': len(payload)}

        with ThreadPoolExecutor(max_workers=8) as pool:
            manifest.extend(pool.map(save, selected))
        print(f'Downloaded and verified {len(selected)} files from {repo}', flush=True)
    (ROOT / 'source_manifest.json').write_text(json.dumps({
        'repositories': SOURCES, 'files': manifest}, indent=2), encoding='utf-8')


def object_mask(image: np.ndarray, threshold: int = 8) -> np.ndarray:
    """Extract the pre-isolated fruit from the authors' black background.

    These are derived masks, not author-supplied ground-truth silhouettes.
    Keep outer contour and fill internal dark skin features.
    """
    foreground = (image.max(axis=2) > threshold).astype(np.uint8)
    largest = _largest_component(foreground)
    contours, _ = cv2.findContours(largest, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(largest)
    cv2.drawContours(filled, [max(contours, key=cv2.contourArea)], -1, 1, cv2.FILLED)
    return filled


def load_views(folder: Path, threshold: int) -> list[FruitView]:
    views = []
    for path in sorted(folder.glob('im*.png')):
        frame = cv2.imread(str(path))
        if frame is None:
            raise ValueError(f'Unreadable image: {path}')
        index = int(path.stem[2:])
        views.append(FruitView(frame, object_mask(frame, threshold), frame_index=index))
    if [v.frame_index for v in views] != list(range(len(views))):
        raise ValueError(f'Nonconsecutive author view numbers: {folder}')
    return views


def annotations(group: str) -> list[dict]:
    path = DATA / 'rotation' / 'data' / group / 'ground_truth.txt'
    rows = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        name, a, b, sx, sy, tx, ty = line.split(',')
        rows.append({'line': lineno, 'object': name, 'source': int(a), 'target': int(b),
                     'source_xy': [int(sx), int(sy)], 'target_xy': [int(tx), int(ty)]})
    return rows


def stats(values) -> dict:
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {'count': 0}
    return {'count': len(a), 'mean': float(a.mean()), 'rms': float(np.sqrt(np.mean(a*a))),
            'median': float(np.median(a)),
            'p90': float(np.percentile(a, 90)), 'max': float(a.max()),
            'within_2px': int((a <= 2).sum()), 'within_5px': int((a <= 5).sum())}


def predict_point(row, model, rotations):
    source, target = row['source'], row['target']
    relative = np.eye(3)
    if target > source:
        for i in range(source, target):
            if i not in rotations:
                raise MappingError(f'Missing accepted rotation {i}')
            relative = rotations[i] @ relative
    else:
        for i in range(source-1, target-1, -1):
            if i not in rotations:
                raise MappingError(f'Missing accepted rotation {i}')
            relative = rotations[i].T @ relative
    xy = np.asarray(row['source_xy'], float) - model.ellipses[source].center
    z = float(_height(model.matrices[source], xy[0], xy[1]))
    if not np.isfinite(z):
        raise MappingError('Annotated source point lies outside fitted spheroid')
    point = relative @ np.r_[xy, z]
    # A projection on the hidden side is not a valid feature correspondence.
    if point @ model.matrices[target][:, 2] <= 0:
        raise MappingError('Predicted point is on hidden target surface')
    return point[:2] + model.ellipses[target].center


def save_correspondence_view(path, views, row, predicted):
    a = views[row['source']].image.copy()
    b = views[row['target']].image.copy()
    cv2.circle(a, tuple(row['source_xy']), 5, (0, 255, 255), 2)
    cv2.circle(b, tuple(row['target_xy']), 6, (0, 255, 0), 2)
    if predicted is not None:
        cv2.drawMarker(b, tuple(np.rint(predicted).astype(int)), (0, 0, 255),
                       cv2.MARKER_CROSS, 16, 2)
    h = max(a.shape[0], b.shape[0])
    canvas = np.zeros((h+55, a.shape[1]+b.shape[1]+12, 3), np.uint8)
    canvas[45:45+a.shape[0], :a.shape[1]] = a
    canvas[45:45+b.shape[0], a.shape[1]+12:] = b
    cv2.putText(canvas, f"{row['object']}  {row['source']} -> {row['target']}",
                (7, 17), cv2.FONT_HERSHEY_SIMPLEX, .45, (255,255,255), 1)
    cv2.putText(canvas, 'Green: author label  Red: prediction', (7,35),
                cv2.FONT_HERSHEY_SIMPLEX, .4, (255,255,255), 1)
    cv2.imwrite(str(path), canvas)


def run(args):
    settings = Settings(spheroid_type=args.shape, rotation_axis=args.axis,
                        rotation_estimator=args.estimator,
                        pole_pose_method=args.pose,
                        accumulate_small_rotations=args.accumulate,
                        bidirectional_matching=args.bidirectional,
                        select_rotating_views=args.select_views,
                        exclude_specular_texture=args.exclude_glare,
                        rotation_direction=args.direction,
                        minimum_rotation_coverage_deg=args.minimum_rotation,
                        minimum_longitude_coverage_deg=args.minimum_longitude,
                        maximum_pair_gap_deg=55,
                        defect_observations_complete=False)
    label = args.label
    destination = ROOT / 'runs' / label
    if (destination / 'report.json').exists():
        raise FileExistsError('Use a new run label; recorded evidence is immutable.')
    destination.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name('algorithm.py').read_bytes()
    (destination / 'algorithm_snapshot.py').write_bytes(source)
    (destination / 'benchmark_snapshot.py').write_bytes(Path(__file__).read_bytes())
    all_rows, tracks = [], []
    start = time.perf_counter()
    for group in args.groups:
        ground_truth = annotations(group)
        folders = sorted((DATA / 'rotation' / 'data' / group).glob('obj*'))
        if args.objects:
            folders = [f for f in folders if f.name in args.objects]
        for folder in folders:
            t0 = time.perf_counter()
            views = load_views(folder, args.mask_threshold)
            output = destination / group / folder.name
            output.mkdir(parents=True, exist_ok=True)
            track = {'group': group, 'object': folder.name, 'views': len(views),
                     'split': 'calibration' if folder.name == ('obj0001' if group == 'oranges' else 'obj0000') else 'evaluation',
                     'pairs': [], 'geometry': None, 'map': None}
            model, rotations = None, {}
            # Always document segmentation; ground truth is never used in fitting.
            silhouette_stats = []
            for i, view in enumerate(views):
                ellipse = _ellipse(view.object_mask)
                silhouette_stats.append({'view': i, 'major': ellipse.major,
                                         'minor': ellipse.minor,
                                         'mask_pixels': int(view.object_mask.sum())})
                if i < 4:
                    preview = view.image.copy()
                    contours, _ = cv2.findContours(view.object_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    cv2.drawContours(preview, contours, -1, (0,255,0), 1)
                    cv2.imwrite(str(output / f'mask_{i:02d}.png'), preview)
            track['silhouettes'] = silhouette_stats
            try:
                model = fit_spheroid(views, settings)
                track['geometry'] = {'status': 'ok', 'A': model.A, 'B': model.B}
            except (MappingError, ValueError) as error:
                track['geometry'] = {'status': 'failed', 'reason': str(error)}
            if model is not None:
                # Evaluate every adjacent pair independently even if the full map
                # aborts, retaining the failure rate in all summary denominators.
                for i in range(len(views)-1):
                    try:
                        rotation, cost = estimate_rotation(views[i], views[i+1], model, i, settings)
                        rotations[i] = rotation
                        track['pairs'].append({'pair': i, 'status': 'ok', 'cost': cost,
                            'rotation_vector_deg': np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel().tolist()})
                    except (MappingError, ValueError) as error:
                        track['pairs'].append({'pair': i, 'status': 'failed', 'reason': str(error)})
            for annotation in [r for r in ground_truth if r['object'] == folder.name]:
                row = {**annotation, 'group': group, 'split': track['split']}
                predicted = None
                try:
                    if model is None:
                        raise MappingError('Track geometry failed')
                    predicted = predict_point(row, model, rotations)
                    error = float(np.linalg.norm(predicted - row['target_xy']))
                    center_only = (np.asarray(row['source_xy']) - model.ellipses[row['source']].center
                                   + model.ellipses[row['target']].center)
                    row.update(status='ok', prediction=predicted.tolist(), error_px=error,
                               error_pct_diameter=100*error/(2*model.A),
                               center_translation_baseline_px=float(np.linalg.norm(center_only-row['target_xy'])))
                except (MappingError, ValueError) as error:
                    row.update(status='failed', reason=str(error))
                all_rows.append(row)
                if sum(r['object'] == folder.name and r['group'] == group for r in all_rows) <= 3:
                    save_correspondence_view(output / f"point_{row['line']:03d}.png", views, row, predicted)
            try:
                result = build_surface_map(views, settings)
                cv2.imwrite(str(output / 'surface_map.png'), result.bgr_map)
                cv2.imwrite(str(output / 'observed.png'), result.observed_mask*255)
                track['map'] = {'status': 'produced', 'result_status': result.status,
                                'grade': result.grade, 'observed_surface_pct': result.observed_surface_pct,
                                'rotation_coverage_deg': result.rotation_coverage_deg,
                                'observed_longitude_deg': result.observed_longitude_deg,
                                'view_frames':result.view_frames,
                                'discarded_view_frames':result.discarded_view_frames,
                                'selection_diagnostics':result.selection_diagnostics}
            except (MappingError, ValueError) as error:
                track['map'] = {'status': 'failed', 'reason': str(error)}
            track['seconds'] = time.perf_counter()-t0
            tracks.append(track)
            (output / 'result.json').write_text(json.dumps(track, indent=2), encoding='utf-8')
            print(f"{label}: {group}/{folder.name}: geometry={track['geometry']['status']}, "
                  f"pairs={len(rotations)}/{len(views)-1}, map={track['map']['status']}", flush=True)
    summary = {}
    for split in ('all', 'calibration', 'evaluation', *args.groups):
        rows = [r for r in all_rows if split == 'all' or r['split'] == split or r['group'] == split]
        subset = [t for t in tracks if split == 'all' or t['split'] == split or t['group'] == split]
        good = [r for r in rows if r['status'] == 'ok']
        summary[split] = {'tracks': len(subset), 'geometry_ok': sum(t['geometry']['status']=='ok' for t in subset),
            'maps_produced': sum(t['map']['status']=='produced' for t in subset),
            'labelled_correspondences': len(rows), 'predicted_correspondences': len(good),
            'errors_px_conditional_on_prediction': stats([r['error_px'] for r in good]),
            'center_translation_baseline_px_same_subset': stats([r['center_translation_baseline_px'] for r in good]),
            'fraction_all_labels_within_5px': sum(r['error_px']<=5 for r in good)/len(rows) if rows else None,
            'geometry_failure_reasons': dict(Counter(t['geometry'].get('reason') for t in subset if t['geometry']['status']!='ok')),
            'map_failure_reasons': dict(Counter(t['map'].get('reason') for t in subset if t['map']['status']!='produced'))}
    report = {'label': label, 'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'settings': asdict(settings), 'mask_threshold': args.mask_threshold,
              'mask_method': 'largest nonblack component, external contour filled; derived masks, not ground truth',
              'algorithm_sha256': hashlib.sha256(source).hexdigest(),
              'source_repositories': SOURCES, 'seconds': time.perf_counter()-start,
              'summary': summary, 'tracks': tracks, 'correspondences': all_rows}
    (destination / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: {field: value for field, value in v.items() if 'reasons' not in field}
                      for k, v in summary.items()}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('download')
    benchmark = commands.add_parser('run')
    benchmark.add_argument('--label', required=True)
    benchmark.add_argument('--groups', nargs='+', default=['mandarins'], choices=['mandarins','oranges','tomatoes'])
    benchmark.add_argument('--objects', nargs='+')
    benchmark.add_argument('--axis', choices=['x','y'], default='x')
    benchmark.add_argument('--direction', type=int, choices=[-1,1], default=1)
    benchmark.add_argument('--shape', choices=['auto','oblate','sphere'], default='auto')
    benchmark.add_argument('--mask-threshold', type=int, default=0)
    benchmark.add_argument('--bidirectional', action='store_true')
    benchmark.add_argument('--select-views', action='store_true')
    benchmark.add_argument('--exclude-glare', action='store_true')
    benchmark.add_argument('--minimum-rotation',type=float,default=350)
    benchmark.add_argument('--minimum-longitude',type=float,default=0)
    benchmark.add_argument('--estimator',choices=['photometric','flow'],default='photometric')
    benchmark.add_argument('--pose',choices=['silhouette_trend','smooth'],default='silhouette_trend')
    benchmark.add_argument('--accumulate',action='store_true')
    args = parser.parse_args()
    if args.command == 'download':
        download()
    else:
        run(args)


if __name__ == '__main__':
    main()
