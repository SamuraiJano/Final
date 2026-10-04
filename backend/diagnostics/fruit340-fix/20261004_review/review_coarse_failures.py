"""Retry coarse-rejected pairs with unchanged native residual/angle bounds."""
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
spec = importlib.util.spec_from_file_location('frozen_coarse_review_algorithm', SOURCE)
alg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = alg
spec.loader.exec_module(alg)
meta = json.loads((ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3/real_model_mapping_report.json').read_text())
s = alg.Settings(**meta['settings'])
s.defect_observations_complete = False
cv2.setNumThreads(1)
report = {'source': str(SOURCE), 'scope': 'Native search on coarse-rejected pairs. Same .58 residual, .25 dominant motion and20 degree max; inverse mismatch<=3 required. No mapping accuracy claim.', 'pairs': []}
for identity in (98, 1, 14, 491):
    folder = ROOT/f'diagnostics/algorithm-audit/corrected_tracks_20261002/{identity}' if identity != 491 else ROOT/'diagnostics/algorithm-audit/longitude_failure_491_20261002/captured_views'
    views = []
    for item in json.loads((folder/'views.json').read_text()):
        with np.load(folder/item['file']) as data:
            views.append(alg.FruitView(data['image'].copy(), data['mask'].copy(), frame_index=item['frame'], fruit_bbox=tuple(item['bbox'])))
    views = alg._prepare(views,s)
    model = alg.fit_spheroid(views,s)
    previous = json.loads((ROOT/f'diagnostics/identity-mapping-check/20261004_scene_motion_v3/paired_maps_geometry_only/fixture_{identity}/baseline/result.json').read_text())
    failed = {r['source_frame']:r for r in previous['selection_diagnostics'] if r.get('status')=='split' and r.get('image_downsample')==4}
    for index, source in enumerate(views[:-1]):
        if source.frame_index not in failed:
            continue
        target = views[index+1]
        row = {'identity': identity, 'source_frame': source.frame_index,'target_frame':target.frame_index, 'previous_reason': failed[source.frame_index]['reason']}
        pm = alg._subset_spheroid(model, [index,index+1])
        reversepm = alg._subset_spheroid(model, [index+1,index])
        direct = replace(s,image_downsample=1,highpass_sigma=5.,matching_cost='aligned_mad',min_pair_angle_deg=0.,bidirectional_matching=False)
        rotations={}
        for name, v1, v2, fitted, settings in (
            ('forward',source,target,pm,direct),
            ('reverse',target,source,reversepm,replace(direct,rotation_direction=-s.rotation_direction)),
            ('joint',source,target,pm,replace(direct,bidirectional_matching=True))):
            try:
                rotation,error = alg._search_rotation(v1,v2,fitted,0,settings)
                rotations[name] = rotation
                vector=np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel()
                row[name]={'status':'measured','rotation_vector_deg':vector.tolist(),'residual':error,'nonzero_primary':bool(abs(vector[0])>=.25)}
            except alg.MappingError as exc:
                row[name]={'status':'rejected','reason':str(exc)}
        if 'forward' in rotations and 'reverse' in rotations:
            row['independent_inverse_disagreement_deg'] = float(np.linalg.norm(np.rad2deg(cv2.Rodrigues(rotations['reverse']@rotations['forward'])[0])))
        row['strict_retry_passes'] = (set(rotations)=={'forward','reverse','joint'} and row.get('independent_inverse_disagreement_deg',999)<=3 and all(row[k]['nonzero_primary'] for k in ('forward','reverse','joint')))
        report['pairs'].append(row)
        (OUT/'coarse_retry_review.json').write_text(json.dumps(report,indent=2))
        print(identity,source.frame_index,json.dumps(row),flush=True)
