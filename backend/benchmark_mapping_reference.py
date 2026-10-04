"""Supplementary map-stage checks; production algorithm stays unchanged.

Uses the authors' FSMap image montages and an exact-geometry diagnostic.
Montages are split at black row separators and connected fruit silhouettes;
pixels are not resized. These are published composite views, not original raw
camera frames, so the two map examples are supplementary rather than a full
numerical replication of the paper's map experiment.
"""
from __future__ import annotations

import json
import argparse
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import algorithm
from algorithm import FruitView, Settings, Spheroid, _ellipse, _height, build_surface_map
from benchmark_authors import DATA, ROOT, load_views, object_mask

OUTPUT = ROOT / 'mapping_runs' / 'unlabelled'


def split_montage(path):
    image = cv2.imread(str(path))
    foreground = (image.max(axis=2) > 8).astype(np.uint8)
    empty_rows = np.flatnonzero(foreground.sum(axis=1) < 3)
    middle = empty_rows[(empty_rows > image.shape[0]*.35) & (empty_rows < image.shape[0]*.65)]
    if not len(middle):
        raise ValueError('No clear montage row separator')
    cuts = [(0, int(middle.min())), (int(middle.max())+1, image.shape[0])]
    views, bounds = [], []
    for y1, y2 in cuts:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground[y1:y2], 8)
        fruits = sorted((r for r in stats[1:] if r[4] > 5000), key=lambda r: r[0])
        for x, y, width, height, area in fruits:
            crop = image[y1+y:y1+y+height, x:x+width].copy()
            index = len(views)
            views.append(FruitView(crop, object_mask(crop, 0), frame_index=index))
            bounds.append([int(x),int(y1+y),int(width),int(height)])
    return views, bounds


def reference_examples():
    results = []
    settings = Settings(spheroid_type='auto', rotation_axis='y', rotation_direction=-1,
                        minimum_rotation_coverage_deg=350, maximum_pair_gap_deg=55)
    for name in ('objM0001', 'objM0005'):
        source = DATA/'maps'/'mandarin'/f'{name}_2R.png'
        output = OUTPUT/name
        output.mkdir(parents=True, exist_ok=True)
        views, bounds = split_montage(source)
        for i, view in enumerate(views):
            cv2.imwrite(str(output/f'view_{i:02d}.png'), view.image)
        result = {'object': name, 'views': len(views), 'bounds_xywh': bounds,
                  'axis': 'y', 'direction': -1,
                  'reference': str((DATA/'maps'/'mandarin'/f'unrolled_{name}.png').relative_to(ROOT)),
                  'direction_basis': 'Published montage features move left; positive visible z implies negative y rotation in this code.'}
        try:
            mapped = build_surface_map(views, settings)
            cv2.imwrite(str(output/'our_map.png'), mapped.bgr_map)
            result.update(status='produced', observed_surface_pct=mapped.observed_surface_pct,
                          rotation_coverage_deg=mapped.rotation_coverage_deg)
        except (algorithm.MappingError, ValueError) as error:
            result.update(status='failed', reason=str(error))
        results.append(result)
    return results


def exact_mapping_case(rotation_axis):
    """Give map construction ideal masks, known shape and EXACT rotations.

    Bypass geometry/rotation estimators to test the downstream choice of map
    coordinates independently. A nonzero output is not proof of real accuracy.
    """
    size, A, B = 150, 55., 40.
    yy, xx = np.mgrid[:size, :size]
    X, Y = xx-(size-1)/2, yy-(size-1)/2
    center = np.array([(size-1)/2]*2)
    component = 0 if rotation_axis == 'x' else 1
    views, ellipses, matrices, poles, rotations = [], [], [], [], []
    for k in range(16):
        vector = np.zeros(3); vector[component] = np.deg2rad(k*25)
        rotation = cv2.Rodrigues(vector)[0]
        rotations.append(rotation)
        pole = rotation @ np.array([0.,1.,0.])
        matrix = np.eye(3)/A**2 + (1/B**2-1/A**2)*np.outer(pole,pole)
        Z = _height(matrix, X, Y)
        mask = np.isfinite(Z)
        camera = np.stack([X, Y, np.nan_to_num(Z)], axis=-1)
        body = camera @ rotation
        intensity = np.clip(.5+.2*np.sin(.2*body[:,:,0])+.2*np.cos(.3*body[:,:,2]), 0, 1)
        image = np.repeat(np.uint8(intensity*255)[:,:,None],3,axis=2)
        image[~mask] = 0
        view = FruitView(image, mask.astype(np.uint8), frame_index=k)
        ellipse = _ellipse(view.object_mask)
        ellipse.center = center.copy()
        views.append(view); ellipses.append(ellipse); matrices.append(matrix); poles.append(pole)
    # At reference view 0 the current code makes the fruit y-axis the short
    # symmetry axis, even when the rotation axis is the equatorial x-axis.
    model = Spheroid(A,B,ellipses,matrices,np.eye(3),0,poles)
    exact_pairs = [(rotations[i+1] @ rotations[i].T, 0.) for i in range(15)]
    settings = Settings(rotation_axis=rotation_axis, minimum_rotation_coverage_deg=350,
                        maximum_pair_gap_deg=55)
    result = {'rotation_axis': rotation_axis, 'true_pair_degrees': 25.,
              'true_total_degrees': 375., 'radii': [A,B,A],
              'geometry_and_pair_rotations': 'Analytical oracle, not estimated'}
    with patch.object(algorithm, 'fit_spheroid', return_value=model), \
         patch.object(algorithm, 'estimate_rotation', side_effect=exact_pairs):
        try:
            mapped = build_surface_map(views,settings)
            result.update(status='produced', observed_surface_pct=mapped.observed_surface_pct,
                          rotation_coverage_deg=mapped.rotation_coverage_deg,
                          grade=mapped.grade, result_status=mapped.status)
            cv2.imwrite(str(OUTPUT/f'exact_{rotation_axis}_map.png'), mapped.bgr_map)
        except (algorithm.MappingError, ValueError) as error:
            result.update(status='failed',reason=str(error))
    return result


def main():
    global OUTPUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    args=parser.parse_args()
    OUTPUT=ROOT/'mapping_runs'/args.label
    if (OUTPUT/'report.json').exists():
        raise FileExistsError('Use a new run label; recorded evidence is immutable.')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    result = {'author_map_examples':reference_examples(),
              'exact_geometry_diagnostics':[exact_mapping_case('y'),exact_mapping_case('x')]}
    source=Path(algorithm.__file__).read_bytes()
    result.update(algorithm_sha256=hashlib.sha256(source).hexdigest(),
                  recorded_at=datetime.now(timezone(timedelta(hours=2))).isoformat())
    (OUTPUT/'algorithm_snapshot.py').write_bytes(source)
    (OUTPUT/'benchmark_snapshot.py').write_bytes(Path(__file__).read_bytes())
    (OUTPUT/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
