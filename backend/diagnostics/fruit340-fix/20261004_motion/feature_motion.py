"""Independent SIFT/ORB correspondences for fast-motion pairs, diagnostic only.

Features require mutual descriptor-ratio matches, foreground support and
geometric agreement. RANSAC uses source points lifted onto the frozen fitted
spheroid. Nothing is sent to production mapping. No ground truth poses exist.
"""
from pathlib import Path
import json
import importlib.util
import sys
import cv2
import numpy as np
from scipy.optimize import least_squares

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('frozen_feature_algorithm',ROOT/'diagnostics/fruit340-fix/20261004_candidate/baseline/algorithm.py')
algorithm=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=algorithm
spec.loader.exec_module(algorithm)
FIXTURE=ROOT/'diagnostics/algorithm-audit/longitude_failure_491_20261002/captured_views'


def detector(method):
    if method=='sift':
        return cv2.SIFT_create(nfeatures=1000,contrastThreshold=.005,edgeThreshold=20,sigma=1.2),cv2.NORM_L2
    return cv2.ORB_create(nfeatures=1000,edgeThreshold=8,patchSize=21,fastThreshold=5,scaleFactor=1.15,nlevels=6),cv2.NORM_HAMMING


def keypoints(view,method,preprocess):
    gray=view.image[:,:,1]
    if preprocess=='clahe':
        gray=cv2.createCLAHE(clipLimit=2.,tileGridSize=(6,6)).apply(gray)
    elif preprocess=='highpass':
        gray=cv2.normalize(gray.astype(float)-cv2.GaussianBlur(gray.astype(float),(0,0),4.),None,0,255,cv2.NORM_MINMAX).astype(np.uint8)
    hsv=cv2.cvtColor(view.image,cv2.COLOR_BGR2HSV)
    glare=((hsv[:,:,1]<102)&(hsv[:,:,2]>90)).astype(np.uint8)
    support=cv2.erode(view.object_mask,np.ones((9,9),np.uint8))>0
    support &= cv2.dilate(glare,np.ones((3,3),np.uint8))==0
    feature,norm=detector(method)
    points,descriptors=feature.detectAndCompute(gray,(support*255).astype(np.uint8))
    return points,descriptors,norm


def mutual_match(left,right,norm,ratio):
    if left is None or right is None or len(left)<2 or len(right)<2:
        return []
    matcher=cv2.BFMatcher(norm)
    forward=matcher.knnMatch(left,right,k=2)
    reverse=matcher.knnMatch(right,left,k=2)
    backward={match[0].queryIdx:match[0].trainIdx for match in reverse if len(match)==2 and match[0].distance<ratio*match[1].distance}
    return [match[0] for match in forward if len(match)==2 and match[0].distance<ratio*match[1].distance and backward.get(match[0].trainIdx)==match[0].queryIdx]


def fit_correspondences(source_xy,target_xy,source_index,target_index,model):
    xy=source_xy-model.ellipses[source_index].center
    depth=algorithm._height(model.matrices[source_index],xy[:,0],xy[:,1])
    xyz=np.column_stack((xy,depth))
    good=np.isfinite(xyz).all(axis=1)
    xyz=xyz[good]
    target_xy=target_xy[good]
    def residual(v,indices):
        return ((xyz[indices]@cv2.Rodrigues(v)[0].T)[:,:2]+model.ellipses[target_index].center-target_xy[indices]).ravel()
    if len(xyz)<4:
        return dict(status='insufficient_lifted_matches',count=len(xyz))
    rng=np.random.default_rng(340)
    best=None
    bound=np.deg2rad(25)
    for _ in range(160):
        sample=rng.choice(len(xyz),3,replace=False)
        opt=least_squares(residual,np.zeros(3),args=(sample,),bounds=(-bound,bound),max_nfev=30)
        errors=np.linalg.norm(residual(opt.x,np.arange(len(xyz))).reshape(-1,2),axis=1)
        inliers=errors<2.
        score=int(inliers.sum())
        candidate_median=float(np.median(errors[inliers])) if inliers.any() else float('inf')
        if best is None or score>best[0] or (score==best[0] and candidate_median<best[1]):
            best=(score,candidate_median,opt.x,inliers)
    _,_,vector,inliers=best
    if inliers.sum()>=4:
        opt=least_squares(residual,vector,args=(np.flatnonzero(inliers),),bounds=(-bound,bound),loss='soft_l1',f_scale=.75,max_nfev=100)
        vector=opt.x
    errors=np.linalg.norm(residual(vector,np.arange(len(xyz))).reshape(-1,2),axis=1)
    inliers=errors<2.
    subset=source_xy[good][inliers]
    span=np.ptp(subset,axis=0) if len(subset) else [0,0]
    return dict(status='diagnostic_fit',rotation_vector_deg=np.rad2deg(vector).tolist(),inliers=int(inliers.sum()),
                median_inlier_error_px=float(np.median(errors[inliers])) if inliers.any() else None,
                source_inlier_span_px=np.asarray(span).tolist(),
                supports_rotation_hypothesis=bool(inliers.sum()>=6 and inliers.mean()>=.6 and np.min(span)>=25),
                matches=[dict(source_crop=a.tolist(),target_crop=b.tolist(),inlier=bool(ok),reprojection_error_px=float(error))
                         for a,b,ok,error in zip(source_xy[good],target_xy,inliers,errors)])


def main():
    cv2.setNumThreads(1)
    views=[]
    for item in json.loads((FIXTURE/'views.json').read_text()):
        with np.load(FIXTURE/item['file']) as data:
            views.append(algorithm.FruitView(data['image'].copy(),data['mask'].copy(),frame_index=item['frame'],fruit_bbox=tuple(item['bbox'])))
    settings=algorithm.Settings(**json.loads((HERE/'manual_correspondences.json').read_text())['settings'])
    model=algorithm.fit_spheroid(views,settings)
    by_frame={view.frame_index:(index,view) for index,view in enumerate(views)}
    results=[]
    for method in ('sift','orb'):
        for preprocess in ('raw','clahe','highpass'):
            for a,b in ((305,306),(308,309),(309,310),(310,311)):
                ia,va=by_frame[a];ib,vb=by_frame[b]
                ka,da,norm=keypoints(va,method,preprocess)
                kb,db,_=keypoints(vb,method,preprocess)
                matches=mutual_match(da,db,norm,.8)
                row=dict(source_frame=a,target_frame=b,method=method,preprocess=preprocess,
                         source_keypoints=len(ka),target_keypoints=len(kb),mutual_matches=len(matches))
                if len(matches)>=4:
                    x=np.array([ka[m.queryIdx].pt for m in matches])
                    y=np.array([kb[m.trainIdx].pt for m in matches])
                    row.update(fit_correspondences(x,y,ia,ib,model))
                    manual=json.loads((HERE/'manual_correspondences.json').read_text())
                    marker=next(p for p in manual['pairs'] if p['source_frame']==a)
                    if row.get('rotation_vector_deg') is not None:
                        point=np.array(marker['lifted_source_point'])
                        prediction=(cv2.Rodrigues(np.deg2rad(row['rotation_vector_deg']))[0]@point)[:2]+np.array(marker['target_center'])
                        row['manual_marker_reprojection_error_px']=float(np.linalg.norm(prediction-marker['target_crop']))
                        row['nearest_source_match_to_manual_marker_px']=float(np.linalg.norm(x-marker['source_crop'],axis=1).min())
                    image=cv2.drawMatches(va.image,ka,vb.image,kb,matches,None,flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
                    cv2.imwrite(str(HERE/f'{method}_{preprocess}_{a}_{b}.png'),cv2.resize(image,None,fx=2,fy=2,interpolation=cv2.INTER_NEAREST))
                results.append(row)
    (HERE/'feature_motion.json').write_text(json.dumps({'method':__doc__,'results':results},indent=2))
    print(json.dumps([{k:v for k,v in row.items() if k!='matches'} for row in results],indent=2))


if __name__=='__main__':
    main()
