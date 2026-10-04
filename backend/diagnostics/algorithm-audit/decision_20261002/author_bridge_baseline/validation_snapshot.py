"""Measure selected reconstruction transitions using exact author label chains.

All original author annotations are adjacent-view point correspondences. This
isolated diagnostic joins ONLY identical (view, x, y) endpoints into feature
chains, then scores endpoints across a selected nonadjacent transition. It does
not interpolate new labels, fit rotations to labels, or change production code.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

import algorithm
from algorithm import MappingError, Settings
import benchmark_authors as benchmark


def node(frame, xy):
    return (int(frame), int(xy[0]), int(xy[1]))


def exact_chains(rows):
    """Connect author observations by exact endpoint equality, never proximity."""
    graph = defaultdict(list)
    for row in rows:
        source = node(row['source'], row['source_xy'])
        target = node(row['target'], row['target_xy'])
        graph[source].append((target, row['line']))
        graph[target].append((source, row['line']))
    chains, seen = [], set()
    for first in sorted(graph):
        if first in seen:
            continue
        queue, component = [first], []
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            queue.extend(neighbor for neighbor, _ in graph[current])
        by_frame = defaultdict(list)
        for value in component:
            by_frame[value[0]].append(value)
        chains.append((dict(by_frame), graph))
    return chains


def provenance_path(graph, source, target):
    queue = deque([(source, [])])
    seen = {source}
    while queue:
        current, lines = queue.popleft()
        if current == target:
            return lines
        for neighbor, line in graph[current]:
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, lines + [line]))
    raise ValueError('Disconnected chain')


def scored(row, selected_model, rotations, index_by_frame):
    result = dict(row)
    adjusted = {**row, 'source': index_by_frame[row['source']],
                'target': index_by_frame[row['target']]}
    try:
        prediction = benchmark.predict_point(adjusted, selected_model, rotations)
        error = float(np.linalg.norm(prediction - row['target_xy']))
        baseline = (np.asarray(row['source_xy'])
                    - selected_model.ellipses[adjusted['source']].center
                    + selected_model.ellipses[adjusted['target']].center)
        result.update(status='ok', prediction=prediction.tolist(), error_px=error,
                      center_translation_baseline_px=float(np.linalg.norm(baseline - row['target_xy'])))
    except (MappingError, ValueError) as error:
        result.update(status='failed', reason=str(error))
    return result


def summarize(rows):
    returned = [row for row in rows if row['status'] == 'ok']
    return {'endpoint_pairs': len(rows), 'returned_predictions': len(returned),
            'errors_px_conditional_on_prediction': benchmark.stats([row['error_px'] for row in returned]),
            'center_translation_baseline_px_same_subset': benchmark.stats([
                row['center_translation_baseline_px'] for row in returned]),
            'fraction_all_endpoint_pairs_within_5px': (
                sum(row['error_px'] <= 5 for row in returned) / len(rows) if rows else None),
            'prediction_failure_reasons': dict(Counter(
                row['reason'] for row in rows if row['status'] != 'ok'))}


def inspect_bridge(row, views, model, selected_model, rotations, index_by_frame, settings):
    """Independent adjacent estimates and lifted annotation diagnostics.

    Relaxed residuals here diagnose why a bridge differs; they are never accepted
    into production selection or counted as validated rotations.
    """
    output = {}
    lifted = []
    for endpoint in ('source', 'target'):
        index = row[endpoint]
        xy = np.asarray(row[f'{endpoint}_xy'], float) - model.ellipses[index].center
        height = float(algorithm._height(model.matrices[index], xy[0], xy[1]))
        if np.isfinite(height):
            point = np.r_[xy, height]
            normal_z = float(point @ model.matrices[index][:, 2])
            lifted.append(point)
            output[f'{endpoint}_lifted_point'] = point.tolist()
            output[f'{endpoint}_lifted_front_normal_z'] = normal_z
            output[f'{endpoint}_lifted_radius_px'] = float(np.linalg.norm(point))
        else:
            output[f'{endpoint}_lift_error'] = 'Author point outside fitted surface'
    if len(lifted) == 2:
        # This is an approximate-model lower bound, not annotated 3D truth.
        cosine = float(lifted[0] @ lifted[1] / (np.linalg.norm(lifted[0]) * np.linalg.norm(lifted[1])))
        output['approx_lifted_endpoint_angular_separation_deg'] = float(np.rad2deg(np.arccos(np.clip(cosine, -1, 1))))
    bridge_local_index = index_by_frame[row['source']]
    direct = rotations[bridge_local_index]
    output['direct_rotation_vector_deg'] = np.rad2deg(cv2.Rodrigues(direct)[0]).ravel().tolist()
    output['direct_rotation_magnitude_deg'] = float(np.linalg.norm(output['direct_rotation_vector_deg']))
    relaxed = replace(settings, min_pair_angle_deg=0., max_pair_error=2.)
    pairs, composition = [], np.eye(3)
    for source in range(row['source'], row['target']):
        target = source + 1
        pair_model = algorithm._subset_spheroid(model, [source, target])
        pair = {'source': source, 'target': target}
        try:
            rotation, error = algorithm.estimate_rotation(views[source], views[target], pair_model, 0, relaxed)
            pair.update(normalized_error=error,
                        rotation_vector_deg=np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel().tolist(),
                        passes_original_residual_gate=error <= settings.max_pair_error)
            composition = rotation @ composition
        except MappingError as error:
            pair['unavailable_reason'] = str(error)
        pairs.append(pair)
    output['relaxed_adjacent_estimates'] = pairs
    if all('normalized_error' in pair for pair in pairs):
        output['relaxed_adjacent_composed_rotation_vector_deg'] = np.rad2deg(cv2.Rodrigues(composition)[0]).ravel().tolist()
        output['direct_vs_relaxed_adjacent_composition_angle_deg'] = float(
            np.linalg.norm(np.rad2deg(cv2.Rodrigues(direct @ composition.T)[0])))
        try:
            prediction = benchmark.predict_point(
                {'source': 0, 'target': 1, 'source_xy': row['source_xy']},
                algorithm._subset_spheroid(model, [row['source'], row['target']]), {0: composition})
            output['relaxed_adjacent_composed_prediction'] = prediction.tolist()
            output['relaxed_adjacent_composed_reprojection_error_px'] = float(np.linalg.norm(prediction - row['target_xy']))
        except MappingError as error:
            output['relaxed_adjacent_composed_prediction_unavailable'] = str(error)
    output['limitations'] = ('Lifting uses estimated spheroids, so angular separation is not measured 3D truth. '
                             'Relaxed adjacent pairs may fail the production residual gate and are diagnostic only.')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--reference-report', type=Path, default=(
        benchmark.ROOT / 'runs' / 'operational_profile_v1' / 'report.json'))
    args = parser.parse_args()
    reference = json.loads(args.reference_report.read_text(encoding='utf-8'))
    settings = Settings(**reference['settings'])
    if not settings.select_rotating_views:
        raise ValueError('This diagnostic requires selected rotating views')
    output = benchmark.ROOT / 'bridge_runs' / args.label
    output.mkdir(parents=True, exist_ok=False)
    source = Path(algorithm.__file__).read_bytes()
    (output / 'algorithm_snapshot.py').write_bytes(source)
    (output / 'validation_snapshot.py').write_bytes(Path(__file__).read_bytes())
    (output / 'benchmark_snapshot.py').write_bytes(Path(benchmark.__file__).read_bytes())
    started = time.perf_counter()
    report = {'label': args.label, 'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'settings': asdict(settings), 'algorithm_sha256': hashlib.sha256(source).hexdigest(),
              'reference_report': str(args.reference_report.resolve()),
              'reference_report_sha256': hashlib.sha256(args.reference_report.read_bytes()).hexdigest(),
              'method': 'Estimate production selected transitions on all author images, without labels. '
                        'Score published adjacent labels when both endpoints are retained. For each selected '
                        'nonadjacent bridge, also score distinct feature endpoints connected by exact '
                        '(view,x,y) author label equality, retaining annotation line provenance.',
              'limitations': 'Development data, not held-out accuracy. Chained endpoints are correlated '
                             'with existing labels and each other. Exact joins may miss the same feature '
                             'labelled at slightly different pixels. Unlabelled bridges remain unverified. '
                             'Derived nonblack masks, not silhouette truth. No defect or tracker validation.',
              'tracks': [], 'original_labels': [], 'bridge_endpoint_pairs': []}
    labels_total, gaps = 0, Counter()
    for group in ('mandarins', 'oranges', 'tomatoes'):
        group_rows = benchmark.annotations(group)
        labels_total += len(group_rows)
        gaps.update(abs(row['target'] - row['source']) for row in group_rows)
        for folder in sorted((benchmark.DATA / 'rotation' / 'data' / group).glob('obj*')):
            views = benchmark.load_views(folder, reference['mask_threshold'])
            rows = [row for row in group_rows if row['object'] == folder.name]
            track = {'group': group, 'object': folder.name, 'captured_views': len(views),
                     'author_labels': len(rows), 'bridges': []}
            try:
                model = algorithm.fit_spheroid(views, settings)
                selected, selected_model, selected_rotations, errors, diagnostics = (
                    algorithm._select_rotating_views(views, model, settings))
                indices = [view.frame_index for view in selected]
                index_by_frame = {frame: index for index, frame in enumerate(indices)}
                rotations = dict(enumerate(selected_rotations))
                track.update(status='selected', selected_frames=indices,
                             pair_errors=errors, selection_diagnostics=diagnostics)
                for row in rows:
                    item = {**row, 'group': group}
                    if row['source'] in index_by_frame and row['target'] in index_by_frame:
                        item = scored(item, selected_model, rotations, index_by_frame)
                    else:
                        item.update(status='unavailable', reason='Annotation endpoint excluded from retained segment')
                    report['original_labels'].append(item)
                chains = exact_chains(rows)
                for source_frame, target_frame in zip(indices[:-1], indices[1:]):
                    if target_frame - source_frame <= 1:
                        continue
                    bridge = {'source_frame': source_frame, 'target_frame': target_frame,
                              'gap': target_frame - source_frame, 'endpoint_pairs': [],
                              'ambiguous_chains_skipped': 0}
                    for component_index, (by_frame, graph) in enumerate(chains):
                        if source_frame not in by_frame or target_frame not in by_frame:
                            continue
                        if len(by_frame[source_frame]) != 1 or len(by_frame[target_frame]) != 1:
                            bridge['ambiguous_chains_skipped'] += 1
                            continue
                        source_node, target_node = by_frame[source_frame][0], by_frame[target_frame][0]
                        path = provenance_path(graph, source_node, target_node)
                        row = {'group': group, 'object': folder.name, 'chain_index': component_index,
                               'source': source_frame, 'target': target_frame,
                               'source_xy': list(source_node[1:]), 'target_xy': list(target_node[1:]),
                               'author_annotation_lines': path, 'chain_edges': len(path)}
                        item = scored(row, selected_model, rotations, index_by_frame)
                        item['independent_checks'] = inspect_bridge(
                            row, views, model, selected_model, rotations, index_by_frame, settings)
                        bridge['endpoint_pairs'].append(item)
                        report['bridge_endpoint_pairs'].append(item)
                    track['bridges'].append(bridge)
            except (MappingError, ValueError) as error:
                track.update(status='failed', reason=str(error))
                for row in rows:
                    report['original_labels'].append({**row, 'group': group, 'status': 'unavailable',
                                                      'reason': str(error)})
            report['tracks'].append(track)
            print(f"{group}/{folder.name}: {track['status']}, nonadjacent bridges={len(track['bridges'])}", flush=True)
    bridges = [bridge for track in report['tracks'] for bridge in track['bridges']]
    report['summary'] = {'author_labels_total': labels_total, 'published_annotation_gaps': dict(gaps),
                         'tracks': len(report['tracks']),
                         'selected_tracks': sum(track['status'] == 'selected' for track in report['tracks']),
                         'nonadjacent_selected_bridges': len(bridges),
                         'nonadjacent_bridges_with_exact_chained_labels': sum(bool(bridge['endpoint_pairs']) for bridge in bridges),
                         'nonadjacent_bridges_without_label_verification': sum(not bridge['endpoint_pairs'] for bridge in bridges),
                         'original_published_labels': summarize(report['original_labels']),
                         'chained_nonadjacent_bridge_endpoints': summarize(report['bridge_endpoint_pairs'])}
    report['seconds'] = time.perf_counter() - started
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    # Save strongest and weakest returned bridge cases, rather than successes alone.
    returned = sorted((row for row in report['bridge_endpoint_pairs'] if row['status'] == 'ok'),
                      key=lambda row: row['error_px'])
    examples = (returned[:1] + returned[-3:]) if returned else []
    for index, row in enumerate(examples):
        folder = benchmark.DATA / 'rotation' / 'data' / row['group'] / row['object']
        views = benchmark.load_views(folder, reference['mask_threshold'])
        benchmark.save_correspondence_view(output / f'bridge_example_{index:02d}.png', views, row,
                                          np.asarray(row['prediction']))
    print(json.dumps(report['summary'], indent=2), flush=True)
    print(f'Evidence: {output}', flush=True)


if __name__ == '__main__':
    main()
