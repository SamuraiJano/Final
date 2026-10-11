"""Independent measured skin-feature reprojection evidence, without grading."""
from dataclasses import asdict, replace
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np
from scipy.optimize import least_squares
import algorithm as a
from validate_dense_mapping import DEFAULT_OUTPUT, load_views, write, stats


def measured_skin_rotation(source,target,model,s):
    """Fit bounded 3D rotations to directly tracked image points in both directions.

    This diagnostic adapter uses the paper's silhouette lift and the existing
    native surface-pattern residual. Optical flow supplies correspondences;
    robust orthographic reprojection and independent inverse checks verify them.
    """
    details={}
    axis=0 if s.rotation_axis=='x' else 1
    side=1-axis
    maximum=s.max_pair_angle_deg

    def directional(v0,v1,index0,index1,direction):
        h,w=v0.object_mask.shape
        yy,xx=np.mgrid[:h,:w]
        center=model.ellipses[index0].center
        X,Y=xx-center[0],yy-center[1]
        matrix=model.matrices[index0]
        Z=a._height(matrix,X,Y)
        normals=np.dstack((X,Y,Z))@matrix
        beta=np.hypot(maximum,s.transverse_angle_deg)+s.relevant_visibility_margin_deg
        mask=(np.isfinite(Z)&(v0.object_mask>0)&
              (normals[:,:,2]>np.sin(np.deg2rad(beta))*np.linalg.norm(normals,axis=2)))
        hsv=cv2.cvtColor(v0.image,cv2.COLOR_BGR2HSV)
        glare=cv2.dilate(((hsv[:,:,1]<102)&(hsv[:,:,2]>90)).astype(np.uint8),np.ones((3,3),np.uint8))
        mask &= glare==0
        green0=np.ascontiguousarray(v0.image[:,:,1]); green1=np.ascontiguousarray(v1.image[:,:,1])
        # Texture gate is unchanged; corners are an engineering alternative to
        # brightest high-pass pixels, which may belong to camera-fixed glare.
        a._relevant(v0,model,index0,replace(s,image_downsample=2,highpass_sigma=2.5))
        p0=cv2.goodFeaturesToTrack(green0,160,.01,3,mask=mask.astype(np.uint8),blockSize=5)
        if p0 is None or len(p0)<s.min_pair_points:
            raise a.MappingError('Insufficient textured skin corners')
        size=(max(v0.image.shape[1],v1.image.shape[1]),max(v0.image.shape[0],v1.image.shape[0]))
        def pad(g):
            return cv2.copyMakeBorder(g,0,size[1]-g.shape[0],0,size[0]-g.shape[1],cv2.BORDER_CONSTANT)
        g0,g1=pad(green0),pad(green1)
        params=dict(winSize=(21,21),maxLevel=3,
                    criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,40,.01))
        p1,status,error=cv2.calcOpticalFlowPyrLK(g0,g1,p0,None,**params)
        back,backstatus,_=cv2.calcOpticalFlowPyrLK(g1,g0,p1,None,**params)
        fberror=np.linalg.norm(back-p0,axis=2).ravel()
        p0,p1=p0[:,0,:],p1[:,0,:]
        ix,iy=np.rint(p1).astype(int).T
        valid=(status.ravel()>0)&(backstatus.ravel()>0)&(fberror<1.)&(error.ravel()<20.)
        valid &= (ix>=0)&(iy>=0)&(ix<v1.image.shape[1])&(iy<v1.image.shape[0])
        valid &= v1.object_mask[np.clip(iy,0,v1.image.shape[0]-1),np.clip(ix,0,v1.image.shape[1]-1)]>0
        p0,p1=p0[valid],p1[valid]
        xy=p0-center
        xyz=np.column_stack((xy,a._height(matrix,xy[:,0],xy[:,1])))
        target_xy=p1-model.ellipses[index1].center
        if len(xyz)<s.min_pair_points:
            raise a.MappingError('Insufficient forward-backward skin correspondences')
        def matrix_of(uv):
            vector=np.zeros(3)
            vector[axis]=direction*np.deg2rad(uv[0]); vector[side]=np.deg2rad(uv[1])
            return cv2.Rodrigues(vector)[0]
        def residual(uv):
            predicted=xyz@matrix_of(uv).T
            return (predicted[:,:2]-target_xy).ravel()
        fitted=least_squares(residual,[maximum/4,0.],bounds=([0.,-s.transverse_angle_deg],
                           [maximum,s.transverse_angle_deg]),loss='soft_l1',f_scale=2.)
        R=matrix_of(fitted.x)
        reprojection=np.linalg.norm((xyz@R.T)[:,:2]-target_xy,axis=1)
        # Two-pixel localization scale plus imperfect silhouette fitting;
        # the three-percent diameter bound follows the published mandarin
        # reprojection scale, kept independently of the photometric gate.
        pixel_limit=.03*(2*model.A)
        inliers=reprojection<=pixel_limit
        if inliers.sum()<s.min_pair_points or inliers.mean()<.5:
            raise a.MappingError('Skin reprojection has insufficient rigid support')
        fitted=least_squares(lambda uv: (residual(uv).reshape(-1,2)[inliers]).ravel(),fitted.x,
                  bounds=([0.,-s.transverse_angle_deg],[maximum,s.transverse_angle_deg]),loss='soft_l1',f_scale=1.)
        R=matrix_of(fitted.x)
        rms=float(np.sqrt(np.mean(residual(fitted.x).reshape(-1,2)[inliers]**2)*2))
        xyz=xyz[inliers]
        log0=np.log(np.maximum(green0.astype(np.float32)/255,1/255))
        log1=np.log(np.maximum(green1.astype(np.float32)/255,1/255))
        patches=a._surface_patches(xyz,matrix,s.highpass_sigma*s.image_downsample)
        values,good0=a._patch_response(log0,patches[None],center,v0.object_mask,matrix)
        moved=np.einsum('ij,pkj->pki',R,patches)
        targets,good1=a._patch_response(log1,moved[None],model.ellipses[index1].center,
                                      v1.object_mask,model.matrices[index1])
        good=good0&good1
        cost=float(a._descriptor_cost_many(values[0],targets,good,s.min_pair_points,True)[0])
        if not np.isfinite(cost) or cost>s.max_pair_error:
            raise a.MappingError(f'Skin photometric residual {cost:.3f} exceeds {s.max_pair_error}')
        return R,cost,dict(corners=len(valid),tracked=int(valid.sum()),inliers=int(inliers.sum()),
                    reprojection_rms_px=rms,
                    mean_forward_backward_error_px=float(fberror[valid].mean()))

    forward,ef,df=directional(source,target,0,1,s.rotation_direction)
    reverse,eb,db=directional(target,source,1,0,-s.rotation_direction)
    inverse=float(np.rad2deg(np.linalg.norm(cv2.Rodrigues(forward@reverse)[0])))
    if inverse>s.keyframe_inverse_tolerance_deg:
        raise a.MappingError(f'Independent skin rotations disagree by {inverse:.2f} degrees')
    vector=np.rad2deg(cv2.Rodrigues(forward)[0]).ravel()
    if abs(vector[axis])<s.min_pair_angle_deg or abs(vector[axis])>=maximum-.01:
        raise a.MappingError('Skin rotation is too small or reaches search boundary')
    details.update(method='tracked_skin_reprojection',inverse_disagreement_deg=inverse,
                   independent_forward_error=ef,independent_backward_error=eb,
                   forward_registration=df,backward_registration=db,
                   rotation_vector_deg=vector.tolist())
    return forward,max(ef,eb),details


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT/'pilot')
    args=parser.parse_args(); output=args.output
    manifest=json.loads((output/'inputs.json').read_text())
    params=json.loads((output/'adaptive_40_10_settings.json').read_text())
    s=a.Settings(**params)
    rows=[]; cv2.setNumThreads(1)
    started=time.perf_counter()
    for record in manifest['records']:
        if len(record['views'])<13:
            continue
        views=load_views(a,output,record); model=a.fit_spheroid(views,s)
        for source in sorted({0,max(0,len(views)//2-4)}):
            for gap in (1,2,3,4):
                target=source+gap; pair=a._subset_spheroid(model,[source,target])
                row=dict(track_id=record['track_id'],source_frame=views[source].frame_index,
                         target_frame=views[target].frame_index,gap=gap)
                try:
                    R,error,details=measured_skin_rotation(views[source],views[target],pair,s)
                    row.update(status='supported',residual=error,**details)
                except a.MappingError as error:
                    row.update(status='rejected',reason=str(error))
                rows.append(row)
        write(output/'skin_registration_probe.json',dict(settings=asdict(s),pairs=rows,
              seconds=time.perf_counter()-started))
        print('skin',record['track_id'],len(rows),'supported',sum(r['status']=='supported' for r in rows),flush=True)
    supported=[r for r in rows if r['status']=='supported']
    summary=dict(pairs=len(rows),supported=len(supported),
                 rolling=stats([abs(r['rotation_vector_deg'][0]) for r in supported]),
                 residual=stats([r['residual'] for r in supported]),
                 support_by_spacing={str(g):sum(r['gap']==g for r in supported) for g in (1,2,3,4)})
    write(output/'skin_registration_probe.json',dict(settings=asdict(s),pairs=rows,summary=summary,
          seconds=time.perf_counter()-started))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
