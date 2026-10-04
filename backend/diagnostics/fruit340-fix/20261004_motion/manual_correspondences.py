"""A visually identifiable black freckle across305..311 (approximate 2D labels).

These identify image content, not measured 3D fruit pose. The freckle was
selected visually on the enlarged original crops; a local dark-pixel centroid
refines each coordinate. Labels carry +/-2px uncertainty.
"""
from pathlib import Path
import importlib.util
import json
import sys
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
baseline_path=ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3/source/algorithm.py'
spec=importlib.util.spec_from_file_location('frozen_mapping_algorithm',baseline_path)
algorithm=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=algorithm
spec.loader.exec_module(algorithm)
fixture=ROOT/'diagnostics/algorithm-audit/longitude_failure_491_20261002/captured_views'


def main():
    manifest=json.loads((fixture/'views.json').read_text())
    views=[]
    for item in manifest:
        with np.load(fixture/item['file']) as data:
            views.append(algorithm.FruitView(data['image'].copy(),data['mask'].copy(),frame_index=item['frame'],fruit_bbox=tuple(item['bbox'])))
    report=json.loads((ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3/paired_maps_geometry_only/report.json').read_text())
    settings=algorithm.Settings(**report['settings'])
    model=algorithm.fit_spheroid(views,settings)
    by_frame={view.frame_index:(index,view) for index,view in enumerate(views)}
    initial={305:(67,136),306:(72,128),307:(73,117),308:(76,97),309:(69,83),310:(63,62),311:(51,51)}
    markers={}
    for frame,(x,y) in initial.items():
        _,view=by_frame[frame]
        patch=view.image[y-4:y+5,x-4:x+5,1].astype(float)
        weights=np.maximum(np.median(patch)-patch-15,0.)
        yy,xx=np.mgrid[y-4:y+5,x-4:x+5]
        point=np.array([float((xx*weights).sum()/weights.sum()),float((yy*weights).sum()/weights.sum())])
        markers[frame]=dict(crop_xy=point.tolist(),uncertainty_px=2.,feature='Persistent small black freckle, visually checked in enlarged original crops.')
        out=view.image.copy()
        cv2.drawMarker(out,tuple(np.rint(point).astype(int)),(0,255,0),cv2.MARKER_CROSS,9,1)
        cv2.imwrite(str(HERE/f'manual_marker_{frame}.png'),cv2.resize(out,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST))
    baseline=json.loads((ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3/paired_maps_geometry_only/fixture_491/baseline/result.json').read_text())
    diagnostics={(row['source_frame'],row['target_frame']):row for row in baseline['selection_diagnostics']}
    pairs=[]
    for source,target in zip(initial,list(initial)[1:]):
        index,_=by_frame[source]
        target_index,_=by_frame[target]
        a=np.array(markers[source]['crop_xy'])
        b=np.array(markers[target]['crop_xy'])
        xy=a-model.ellipses[index].center
        depth=algorithm._height(model.matrices[index],np.array([xy[0]]),np.array([xy[1]]))[0]
        point=np.array([*xy,depth])
        diag=diagnostics[(source,target)]
        row=dict(source_frame=source,target_frame=target,source_crop=a.tolist(),target_crop=b.tolist(),
                 centroid_corrected_displacement=(b-model.ellipses[target_index].center-xy).tolist(),
                 lifted_source_point=point.tolist(),target_center=model.ellipses[target_index].center.tolist(),
                 baseline_status=diag['status'],baseline_reason=diag.get('reason'))
        if diag.get('rotation_vector_deg') is not None:
            vector=np.array(diag['rotation_vector_deg'])
            predicted=(cv2.Rodrigues(np.deg2rad(vector))[0]@point)[:2]+model.ellipses[target_index].center
            row.update(baseline_vector_deg=vector.tolist(),baseline_predicted_target_crop=predicted.tolist(),
                       baseline_marker_reprojection_error_px=float(np.linalg.norm(predicted-b)))
        pairs.append(row)
    output={'method':__doc__,'markers':markers,'pairs':pairs,'settings':report['settings'],
            'geometry_source':str(baseline_path),'limitations':['A single point cannot determine a 3D rotation.',
               'Marker labels are approximate (2px); image compression and changing highlight alter local dark-pixel centroid.',
               'Reprojection relies on the fitted spheroid and its masked silhouette centroid, not ground truth.']}
    (HERE/'manual_correspondences.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(pairs,indent=2))


if __name__=='__main__':
    main()
