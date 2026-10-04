"""Trace a recorded longitude-order failure using cached boxes, without neural inference."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import cv2
import numpy as np

import algorithm


ROOT = Path(__file__).resolve().parent
VIDEO = Path(r'C:\Users\USER\Pictures\Camera Roll\WIN_20260818_13_29_43_Pro.mp4')
BASELINE = ROOT / 'diagnostics/entry-tracking/entry_full_20261002/baseline_three_detections.json'
ORIGINAL = ROOT / 'results/f2276fe89ce24fe1a155c228a00e3f17'


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def longitude_trace(views, model, rotations, settings, diagnostics) -> dict:
    """Repeat exactly the production pose-to-longitude computation, preserving intermediates."""
    poses = [np.eye(3)]
    for rotation in rotations:
        poses.append(rotation @ poses[-1])
    basis, radii = algorithm._map_frame(model, settings)
    axes_ref = poses[model.reference_index].T @ basis
    axes = [pose @ axes_ref for pose in poses]
    centers = []
    rays = []
    for axes_i in axes:
        ray = axes_i.T @ np.array([0.0, 0.0, 1.0])
        rays.append(ray.tolist())
        centers.append(np.arctan2(ray[2] / radii[2], ray[0] / radii[0]))
    unwrapped = np.unwrap(centers)
    differences = np.diff(unwrapped)
    direction = float(np.sign(np.median(differences)))
    progress = direction * (unwrapped - unwrapped[0])
    deltas = np.rad2deg(np.diff(progress))
    vectors = [np.rad2deg(cv2.Rodrigues(rotation)[0].ravel()).tolist() for rotation in rotations]
    bad = []
    for index, delta in enumerate(deltas):
        if delta < .25 or delta > settings.max_pair_angle_deg + 12:
            bad.append({'pair_index': index, 'source_frame': views[index].frame_index,
                        'target_frame': views[index+1].frame_index,
                        'longitude_progress_delta_deg': float(delta),
                        'rotation_vector_deg': vectors[index],
                        'reason': 'below_0.25_deg' if delta < .25 else 'above_max_pair_plus_12_deg'})
    return {'selected_frames': [view.frame_index for view in views],
            'A': model.A, 'B': model.B, 'reference_index': model.reference_index,
            'reference_frame': views[model.reference_index].frame_index,
            'reference_axes': model.reference_axes.tolist(),
            'map_basis': basis.tolist(), 'map_radii': radii.tolist(),
            'fruit_to_camera_axes': [value.tolist() for value in axes],
            'camera_rays_in_fruit_frame': rays,
            'camera_center_longitudes_deg': np.rad2deg(centers).tolist(),
            'unwrapped_center_longitudes_deg': np.rad2deg(unwrapped).tolist(),
            'progress_direction': direction,
            'progress_deg': np.rad2deg(progress).tolist(),
            'progress_delta_deg': deltas.tolist(),
            'pair_rotation_vectors_deg': vectors,
            'bad_transitions': bad, 'selection_diagnostics': diagnostics}


def geometry_run(views, settings, folder: Path) -> dict:
    folder.mkdir()
    trace = {}
    selector = algorithm._select_rotating_views

    def tracing_selector(in_views, in_model, in_settings):
        selected, model, rotations, errors, diagnostics = selector(in_views, in_model, in_settings)
        trace.update(longitude_trace(selected, model, rotations, in_settings, diagnostics))
        trace['pair_errors'] = errors
        trace['captured_ellipses'] = [{'frame': view.frame_index,
            'major': ellipse.major, 'minor': ellipse.minor,
            'center': ellipse.center.tolist(), 'v_minor': ellipse.v_minor.tolist()}
            for view, ellipse in zip(in_views, in_model.ellipses)]
        save_json(folder / 'longitude_trace.json', trace)
        return selected, model, rotations, errors, diagnostics

    algorithm._select_rotating_views = tracing_selector
    start = time.perf_counter()
    row = {'settings': asdict(settings), 'grade_evaluated': False,
           'segmentation_executed': False, 'input_frames': [view.frame_index for view in views]}
    try:
        mapped = algorithm.build_surface_map(views, settings)
        cv2.imwrite(str(folder / 'surface_map.png'), mapped.bgr_map)
        cv2.imwrite(str(folder / 'observed.png'), mapped.observed_mask*255)
        row.update(status=mapped.status, rotation_coverage_deg=mapped.rotation_coverage_deg,
                   observed_longitude_deg=mapped.observed_longitude_deg,
                   observed_surface_pct=mapped.observed_surface_pct,
                   selected_frames=mapped.view_frames)
    except (algorithm.MappingError, ValueError) as error:
        row.update(status='mapping_failed', reason=str(error))
    finally:
        algorithm._select_rotating_views = selector
    row.update(seconds=time.perf_counter()-start, bad_transitions=trace.get('bad_transitions', []))
    save_json(folder / 'result.json', row)
    by_frame = {view.frame_index: view for view in views}
    for pair in trace.get('bad_transitions', []):
        tiles = []
        for key in ('source_frame', 'target_frame'):
            view = by_frame[pair[key]]
            image = view.image.copy()
            contours, _ = cv2.findContours(view.object_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(image, contours, -1, (0, 255, 0), 1)
            scale = min(500/image.shape[1], 500/image.shape[0])
            image = cv2.resize(image, (round(image.shape[1]*scale), round(image.shape[0]*scale)))
            tile = np.full((560, 520, 3), 242, np.uint8)
            tile[50:50+image.shape[0], 10:10+image.shape[1]] = image
            cv2.putText(tile, f'Frame {view.frame_index}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (30,30,30), 2)
            tiles.append(tile)
        sheet = np.concatenate(tiles, axis=1)
        cv2.putText(sheet, f'Longitude step: {pair["longitude_progress_delta_deg"]:.3f} deg',
                    (10, 548), cv2.FONT_HERSHEY_SIMPLEX, .7, (30,30,30), 2)
        cv2.imwrite(str(folder / f'bad_pair_{pair["source_frame"]:05d}_{pair["target_frame"]:05d}.png'), sheet)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--track', type=int, default=491)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    output = ROOT / 'diagnostics/algorithm-audit' / args.label
    output.mkdir(parents=True, exist_ok=False)
    for name in ('algorithm.py', 'main.py', 'dfine_segmenter.py', Path(__file__).name):
        (output / f'{name}.snapshot').write_bytes((ROOT/name).read_bytes())
    original_report = json.loads((ORIGINAL/'report.json').read_text(encoding='utf-8'))
    original_row = next(row for row in original_report['fruits'] if row['track_id'] == args.track)
    save_json(output/'original_result.json', original_row)
    save_json(output/'original_metrics.json', original_report['metrics'])
    # Defect observations are explicitly absent in a geometry-only audit.
    settings = replace(algorithm.Settings(**original_report['metrics']['geometry_settings']),
                       defect_observations_complete=False)
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
        'track': args.track, 'original_status': original_row['status'],
        'video': str(VIDEO), 'video_sha256': digest(VIDEO),
        'cached_track_input': str(BASELINE), 'cached_track_sha256': digest(BASELINE),
        'algorithm_sha256': digest(ROOT/'algorithm.py'),
        'original_report_sha256': digest(ORIGINAL/'report.json'),
        'limitations': ('Actual cached detector boxes and original images; fresh GrabCut masks. '
            'No neural model executed, no manual rotation truth and no defect masks or grade. '
            'Only override from original geometry settings is defect_observations_complete=False.'),
        'grabcut_rng_seed': 0, 'variants': {}}
    cv2.setRNGSeed(0)
    placeholder = SimpleNamespace(names={0: 'skin_wrinkling', 1: 'dark_marking', 2: 'wind_scarring',
                                         3: 'light_brown_discolouration', 4: 'open_skin'})
    pipeline = algorithm.NaartjiePipeline(placeholder, settings=settings,
        capture_stride_frames=1, max_views_per_track=120, defer_defect_segmentation=True)
    cached = json.loads(BASELINE.read_text(encoding='utf-8'))
    capture = cv2.VideoCapture(str(VIDEO))
    if not capture.isOpened():
        raise RuntimeError(f'Cannot read {VIDEO}')
    try:
        for item in cached:
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError('Video ended before cached observation list')
            for row in item['tracks']:
                if int(row[4]) != args.track:
                    continue
                try:
                    pipeline.add_tracked_detection(frame, args.track, row[:4], item['frame'])
                except algorithm.MappingError as error:
                    counts = pipeline.rejected_views_by_id.setdefault(args.track, {})
                    counts[str(error)] = counts.get(str(error), 0) + 1
    finally:
        capture.release()
    views = pipeline.views_by_id.get(args.track, [])
    inputs = output/'captured_views'
    inputs.mkdir()
    manifest = []
    mask_comparisons = []
    for index, view in enumerate(views):
        filename = f'view_{index:03d}.npz'
        np.savez_compressed(inputs/filename, image=view.image, mask=view.object_mask)
        cv2.imwrite(str(inputs/f'frame_{view.frame_index:05d}_crop.png'), view.image)
        cv2.imwrite(str(inputs/f'frame_{view.frame_index:05d}_fruit_mask.png'), view.object_mask*255)
        manifest.append({'file': filename, 'frame': view.frame_index, 'bbox': view.fruit_bbox})
        original_mask = ORIGINAL/str(args.track)/f'frame_{view.frame_index:05d}_fruit_mask.png'
        if original_mask.is_file():
            mask = cv2.imread(str(original_mask), cv2.IMREAD_GRAYSCALE)>0
            if mask.shape == view.object_mask.shape:
                union = mask | (view.object_mask>0)
                mask_comparisons.append({'frame': view.frame_index,
                    'iou_with_original_saved_mask': float((mask & (view.object_mask>0)).sum()/union.sum())})
    save_json(inputs/'views.json', manifest)
    report.update(captured_views=len(views), captured_frames=[view.frame_index for view in views],
        original_captured_frames=original_row['view_frames'],
        rejected_views=pipeline.rejected_views_by_id.get(args.track, {}),
        tracked_history=pipeline.tracking_history_by_id.get(args.track, []),
        saved_original_mask_comparisons=mask_comparisons)
    save_json(output/'report.json', report)
    print(f'Track {args.track}: {len(views)} usable crops; masks compared: {mask_comparisons}', flush=True)
    report['variants']['auto'] = geometry_run(views, settings, output/'auto')
    save_json(output/'report.json', report)
    print('AUTO', json.dumps(report['variants']['auto']), flush=True)
    if 'not consistently ordered' in report['variants']['auto'].get('reason', ''):
        report['variants']['sphere'] = geometry_run(views, replace(settings, spheroid_type='sphere'), output/'sphere')
        save_json(output/'report.json', report)
        print('SPHERE', json.dumps(report['variants']['sphere']), flush=True)
    print(f'Evidence: {output}', flush=True)


if __name__ == '__main__':
    main()
