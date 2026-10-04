"""Independent image-content diagnostics; never used to build the production map.

LK measurements are noisy correspondences, not ground-truth physical poses.
Normalization corrects mask centroid translation only (no scale/shape warp).
"""
from pathlib import Path
import json
import cv2
import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
FIXTURE = ROOT / 'diagnostics/algorithm-audit/longitude_failure_491_20261002/captured_views'


def ellipse(mask):
    ys, xs = np.nonzero(mask)
    xy = np.column_stack((xs, ys)).astype(float)
    center = xy.mean(axis=0)
    covariance = np.cov(xy, rowvar=False, bias=True)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    return center, 2*np.sqrt(eigenvalues), eigenvectors


def load():
    data = {}
    for row in json.loads((FIXTURE/'views.json').read_text()):
        with np.load(FIXTURE/row['file']) as source:
            image, mask = source['image'].copy(), source['mask'].copy()
        center, axes, vectors = ellipse(mask)
        matrix = np.array([[1, 0, 100-center[0]], [0, 1, 100-center[1]]], np.float32)
        canvas = cv2.warpAffine(image, matrix, (200, 200))
        cmask = cv2.warpAffine(mask, matrix, (200, 200), flags=cv2.INTER_NEAREST)
        hsv = cv2.cvtColor(canvas, cv2.COLOR_BGR2HSV)
        glare = (hsv[:,:,1] < 102) & (hsv[:,:,2] > 90) & (cmask > 0)
        y, x = np.mgrid[:200, :200]
        support = ((x-100)**2 + (y-100)**2 < (axes.mean()*.7)**2) & (cmask > 0)
        glare = cv2.dilate(glare.astype(np.uint8), np.ones((5,5),np.uint8))>0
        data[row['frame']] = dict(image=image, mask=mask, canvas=canvas, cmask=cmask,
                                 center=center, axes=axes, support=support & ~glare,
                                 glare=glare, bbox=row['bbox'], vectors=vectors)
    return data


def flow(source, target):
    left, right = source['canvas'], target['canvas']
    gray1, gray2 = left[:,:,1], right[:,:,1]
    pts = cv2.goodFeaturesToTrack(gray1, 100, .02, 5, mask=(source['support']*255).astype(np.uint8), blockSize=5)
    if pts is None:
        return dict(n=0), None
    pred, ok, error = cv2.calcOpticalFlowPyrLK(gray1, gray2, pts, None, winSize=(19,19), maxLevel=2,
                                            criteria=(cv2.TERM_CRITERIA_COUNT|cv2.TERM_CRITERIA_EPS,60,.005))
    back, back_ok, _ = cv2.calcOpticalFlowPyrLK(gray2,gray1,pred,None,winSize=(19,19),maxLevel=2,
                                              criteria=(cv2.TERM_CRITERIA_COUNT|cv2.TERM_CRITERIA_EPS,60,.005))
    fb = np.linalg.norm(back-pts,axis=2).ravel()
    initial = pts[:,0]
    predicted = pred[:,0]
    x,y = np.clip(np.rint(predicted).astype(int),0,199).T
    keep=(ok.ravel()>0)&(back_ok.ravel()>0)&(fb<.7)&(error.ravel()<20)&target['support'][y,x]
    a,b=initial[keep],predicted[keep]
    displacement=b-a
    result=dict(n=int(keep.sum()), median_fb_px=float(np.median(fb[keep])) if keep.any() else None,
                median_lk_error=float(np.median(error.ravel()[keep])) if keep.any() else None,
                source_center=source['center'].tolist(),target_center=target['center'].tolist(),
                source_axes=source['axes'].tolist(),target_axes=target['axes'].tolist(),
                matches=[dict(source_crop=(u+source['center']-100).tolist(),target_crop=(v+target['center']-100).tolist(),
                              centroid_corrected_displacement=(v-u).tolist()) for u,v in zip(a,b)])
    if len(a):
        result.update(median_centroid_corrected_displacement_px=np.median(displacement,axis=0).tolist(),
                      displacement_range_px=np.percentile(displacement,[10,90],axis=0).tolist())
    # Sphere approximation: infer angular motion from masked feature displacement.
    # Shape/centroid errors directly bias this number; expose it as a diagnostic.
    if len(a)>=8:
        radius=float((source['axes'].mean()+target['axes'].mean())/2)
        xy=a-100
        z=np.sqrt(np.maximum(radius*radius-(xy*xy).sum(axis=1),1))
        xyz=np.column_stack((xy,z))
        def residual(v):
            rotation=cv2.Rodrigues(v)[0]
            return ((xyz @ rotation.T)[:,:2]-(b-100)).ravel()
        opt=least_squares(residual,np.zeros(3),loss='soft_l1',f_scale=1.)
        errors=np.linalg.norm(residual(opt.x).reshape(-1,2),axis=1)
        def two_axis_residual(v):
            return residual(np.array([v[0],v[1],0.]))
        constrained=least_squares(two_axis_residual,[.00001,0.],bounds=([0.,-np.deg2rad(20)],[np.deg2rad(20),np.deg2rad(20)]),loss='soft_l1',f_scale=1.)
        constrained_errors=np.linalg.norm(two_axis_residual(constrained.x).reshape(-1,2),axis=1)
        result.update(sphere_flow_rotation_vector_deg=np.rad2deg(opt.x).tolist(),
                      median_sphere_reprojection_error_px=float(np.median(errors)),
                      positive_x_two_axis_fit_deg=np.rad2deg(constrained.x).tolist(),
                      positive_x_two_axis_median_reprojection_error_px=float(np.median(constrained_errors)))
    combined=np.hstack((left,right))
    for index,(p,q) in enumerate(zip(a,b)):
        color=tuple(int(v) for v in cv2.cvtColor(np.uint8([[[int(index*180/max(len(a),1)),230,250]]]),cv2.COLOR_HSV2BGR)[0,0])
        x1,y1=np.rint(p).astype(int);x2,y2=np.rint(q).astype(int)
        cv2.circle(combined,(x1,y1),3,color,1); cv2.circle(combined,(x2+200,y2),3,color,1)
        cv2.line(combined,(x1,y1),(x2+200,y2),color,1)
        cv2.putText(combined,str(index),(x1+3,y1),cv2.FONT_HERSHEY_SIMPLEX,.3,color,1)
        cv2.putText(combined,str(index),(x2+203,y2),cv2.FONT_HERSHEY_SIMPLEX,.3,color,1)
    return result,combined


def main():
    HERE.mkdir(parents=True,exist_ok=True)
    cv2.setNumThreads(1)
    inputs=load()
    selected=[305,306,307,308,309,310,315,320,325,329,331,335,340,345,350,355,360,364]
    sheet=np.full((3*224,6*200,3),240,np.uint8)
    for index,frame in enumerate(selected):
        row,col=divmod(index,6)
        sheet[row*224:row*224+200,col*200:col*200+200]=inputs[frame]['canvas']
        cv2.putText(sheet,f'frame {frame}',(col*200+8,row*224+218),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
    cv2.imwrite(str(HERE/'contact_sheet.png'),sheet)
    results=[]
    for a,b in zip(sorted(inputs),sorted(inputs)[1:]):
        result,visual=flow(inputs[a],inputs[b])
        result.update(source_frame=a,target_frame=b)
        results.append(result)
        if (a,b) in [(305,306),(307,308),(308,309),(309,310),(315,316),(324,325),(334,335),(349,350),(359,360)]:
            cv2.imwrite(str(HERE/f'flow_{a}_{b}.png'),visual)
    summary={'method':__doc__,'input_fixture':str(FIXTURE),'pairs':results,
             'limitations':['Automated LK matches have not all been manually verified.',
                            'Sphere flow rotations assume front-side positive depth and mask centroids; they are approximate diagnostics.',
                            'Crops are centered without scale correction. Silhouette change can bias flow rotations.',
                            'No ground-truth 3D poses or unique fruit labels are supplied.']}
    (HERE/'image_motion.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps([dict(source_frame=row['source_frame'], target_frame=row['target_frame'],
                           n=row['n'], vector=row.get('sphere_flow_rotation_vector_deg'),
                           three_axis_error=row.get('median_sphere_reprojection_error_px'),
                           positive_two_axis_error=row.get('positive_x_two_axis_median_reprojection_error_px'))
                      for row in results if row['source_frame'] in (305,306,312,325,326,327,328,334,337,339,349,359)],indent=2))


if __name__=='__main__':
    main()
