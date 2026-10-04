"""Read-only diagnostics for fruit 340, legacy fixture 491; no map validity changes."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
from dataclasses import replace
import cv2
import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3/source/algorithm.py'
spec = importlib.util.spec_from_file_location('frozen_review_algorithm', SOURCE)
alg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = alg
spec.loader.exec_module(alg)
meta = json.loads((ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3/real_model_mapping_report.json').read_text())
s = alg.Settings(**meta['settings'])
s.defect_observations_complete = False
folder = ROOT/'diagnostics/algorithm-audit/longitude_failure_491_20261002/captured_views'
views = []
for item in json.loads((folder/'views.json').read_text()):
    with np.load(folder/item['file']) as data:
        views.append(alg.FruitView(data['image'].copy(), data['mask'].copy(), frame_index=item['frame'], fruit_bbox=tuple(item['bbox'])))
views = alg._prepare(views, s)
model = alg.fit_spheroid(views, s)
cv2.setNumThreads(1)

def estimate(source, target, pairmodel, settings):
    row = {}
    try:
        rotation, error = alg._search_rotation(source, target, pairmodel, 0, settings)
        row.update(rotation_vector_deg=np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel().tolist(), residual=error, status='measured')
        row['_rotation'] = rotation
    except alg.MappingError as exc:
        row.update(status='rejected', reason=str(exc))
    return row

report = {'source': str(SOURCE), 'scope': 'Search minima and independent inverse checks using frozen fixture, not mapping accuracy or altered map validity.', 'pairs': []}
for index, source in enumerate(views[:-1]):
    if source.frame_index not in (305, 306, 307, 308, 309, 310, 311, 312, 313, 315, 316, 324, 337, 340, 350, 360):
        continue
    target = views[index+1]
    pairmodel = alg._subset_spheroid(model, [index, index+1])
    reversemodel = alg._subset_spheroid(model, [index+1, index])
    row = {'source_frame': source.frame_index, 'target_frame': target.frame_index, 'modes': {}}
    for mode in ('mad', 'green_mad', 'aligned_mad'):
        direct = replace(s, image_downsample=4 if mode=='mad' else 1, highpass_sigma=1.25 if mode=='mad' else 5., matching_cost=mode, min_pair_angle_deg=0., bidirectional_matching=False)
        forward = estimate(source, target, pairmodel, direct)
        reverse = estimate(target, source, reversemodel, replace(direct, rotation_direction=-s.rotation_direction))
        joint = estimate(source, target, pairmodel, replace(direct, bidirectional_matching=True))
        negative = estimate(source, target, pairmodel, replace(direct, bidirectional_matching=True, rotation_direction=-s.rotation_direction))
        negative_forward = estimate(source, target, pairmodel, replace(direct, rotation_direction=-s.rotation_direction))
        negative_reverse = estimate(target, source, reversemodel, direct)
        if '_rotation' in forward and '_rotation' in reverse:
            row['modes'][mode] = {'independent_inverse_disagreement_deg': float(np.linalg.norm(np.rad2deg(cv2.Rodrigues(reverse['_rotation'] @ forward['_rotation'])[0])))}
        else:
            row['modes'][mode] = {}
        if '_rotation' in negative_forward and '_rotation' in negative_reverse:
            row['modes'][mode]['negative_inverse_disagreement_deg'] = float(np.linalg.norm(np.rad2deg(cv2.Rodrigues(negative_reverse['_rotation'] @ negative_forward['_rotation'])[0])))
        for result in (forward, reverse, joint, negative, negative_forward, negative_reverse):
            result.pop('_rotation', None)
        row['modes'][mode].update(forward=forward, reverse=reverse, joint=joint, negative_direction_probe=negative, negative_forward=negative_forward, negative_reverse=negative_reverse)
    # Record the proportion of selected points that lie on specular regions.
    points, values, _ = alg._relevant(source, model, index, replace(s, image_downsample=1, highpass_sigma=5.))
    e = model.ellipses[index]
    x = np.rint(points[:,0]+e.center[0]).astype(int)
    y = np.rint(points[:,1]+e.center[1]).astype(int)
    hsv = cv2.cvtColor(source.image, cv2.COLOR_BGR2HSV)
    glare = ((hsv[:,:,1] < 102) & (hsv[:,:,2] > 90)).astype(np.uint8)
    glare = cv2.dilate(glare,np.ones((3,3),np.uint8))
    row['selected_native_points'] = len(points)
    row['selected_glare_fraction'] = float(np.mean(glare[y,x]>0))
    row['selected_green_mean'] = float(np.mean(source.image[y,x,1]))
    report['pairs'].append(row)
    (OUT/'pair_review.json').write_text(json.dumps(report, indent=2))
    print(source.frame_index, json.dumps(row['modes']['aligned_mad']), flush=True)

print(OUT/'pair_review.json', flush=True)
