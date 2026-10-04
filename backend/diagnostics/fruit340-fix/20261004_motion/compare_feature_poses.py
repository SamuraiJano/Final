"""Compare proposed2-axis pair pose with independent descriptor matches.

The matching inliers are selected by a3-axis diagnostic RANSAC, not labelled
ground truth, so report both all-mutual-match and selected-inlier residuals.
"""
from pathlib import Path
import importlib.util
import json
import sys
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('diagnostic_features',HERE/'feature_motion.py')
features=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=features
spec.loader.exec_module(features)
algorithm=features.algorithm


def main():
    views=[]
    for item in json.loads((features.FIXTURE/'views.json').read_text()):
        with np.load(features.FIXTURE/item['file']) as data:
            views.append(algorithm.FruitView(data['image'].copy(),data['mask'].copy(),frame_index=item['frame'],fruit_bbox=tuple(item['bbox'])))
    settings=algorithm.Settings(**json.loads((HERE/'manual_correspondences.json').read_text())['settings'])
    model=algorithm.fit_spheroid(views,settings)
    by_frame={view.frame_index:(index,view) for index,view in enumerate(views)}
    report=json.loads((HERE/'feature_motion.json').read_text())
    result=[]
    for row in report['results']:
        if row['source_frame'] not in (305,308) or not row.get('matches'):
            continue
        source=row['source_frame'];target=row['target_frame']
        index,_=by_frame[source];target_index,target_view=by_frame[target]
        source_xy=np.array([m['source_crop'] for m in row['matches']])
        target_xy=np.array([m['target_crop'] for m in row['matches']])
        inliers=np.array([m['inlier'] for m in row['matches']])
        xy=source_xy-model.ellipses[index].center
        points=np.column_stack((xy,algorithm._height(model.matrices[index],xy[:,0],xy[:,1])))
        vector=np.array([5.,-5.,0.]) if source==305 else np.array([11.59,-8.22,0.])
        candidate=(points@cv2.Rodrigues(np.deg2rad(vector))[0].T)[:,:2]+model.ellipses[target_index].center
        free=(points@cv2.Rodrigues(np.deg2rad(row['rotation_vector_deg']))[0].T)[:,:2]+model.ellipses[target_index].center
        errors=np.linalg.norm(candidate-target_xy,axis=1)
        free_errors=np.linalg.norm(free-target_xy,axis=1)
        result.append(dict(source_frame=source,target_frame=target,method=row['method'],preprocess=row['preprocess'],
                           mutual_matches=len(errors),three_axis_inliers=int(inliers.sum()),candidate_vector_deg=vector.tolist(),
                           candidate_all_mutual_median_error_px=float(np.median(errors)),
                           diagnostic3d_all_mutual_median_error_px=float(np.median(free_errors)),
                           candidate_inlier_median_error_px=float(np.median(errors[inliers])),
                           diagnostic3d_inlier_median_error_px=float(np.median(free_errors[inliers]))))
        if source==308 and row['method']=='orb' and row['preprocess']=='highpass':
            out=cv2.resize(target_view.image,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST)
            for a,b,c,ok in zip(target_xy,candidate,free,inliers):
                if not ok:
                    continue
                p,q,r=[tuple(np.rint(v*4).astype(int)) for v in (a,b,c)]
                cv2.circle(out,p,5,(255,0,0),2)
                cv2.drawMarker(out,q,(0,255,255),cv2.MARKER_CROSS,9,1)
                cv2.line(out,p,q,(0,255,255),1)
                cv2.circle(out,r,2,(0,255,0),1)
            cv2.imwrite(str(HERE/'native2axis_vs_feature3d_308_309.png'),out)
    output={'method':__doc__,'comparisons':result}
    (HERE/'candidate_feature_comparison.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2))


if __name__=='__main__':
    main()
