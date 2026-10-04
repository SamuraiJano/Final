"""Read-only 3D pose search diagnostics for failed 309->310, not production."""
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
sys.path.insert(0,str(ROOT))
SOURCE=ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3/source/algorithm.py'
spec=importlib.util.spec_from_file_location('frozen_3d_review_algorithm',SOURCE)
alg=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=alg
spec.loader.exec_module(alg)
settings=json.loads((ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3/real_model_mapping_report.json').read_text())['settings']
s=alg.Settings(**settings)
folder=ROOT/'diagnostics/algorithm-audit/longitude_failure_491_20261002/captured_views'
views=[]
for item in json.loads((folder/'views.json').read_text()):
    with np.load(folder/item['file']) as data:
        views.append(alg.FruitView(data['image'].copy(),data['mask'].copy(),frame_index=item['frame'],fruit_bbox=tuple(item['bbox'])))
views=alg._prepare(views,s)
model=alg.fit_spheroid(views,s)
cv2.setNumThreads(1)

def setup(index, other):
    source,target=views[index],views[other]
    st=replace(s,image_downsample=1,highpass_sigma=5.,matching_cost='aligned_mad',min_pair_angle_deg=0.)
    points,_,_=alg._relevant(source,model,index,st)
    green=np.log(np.maximum(source.image[:,:,1].astype(np.float32)/255.,1/255.))
    targetgreen=np.log(np.maximum(target.image[:,:,1].astype(np.float32)/255.,1/255.))
    patches=alg._surface_patches(points,model.matrices[index],5.)
    values,valid=alg._patch_response(green,patches[None],model.ellipses[index].center,source.object_mask,model.matrices[index])
    points,patches,values=points[valid[0]],patches[valid[0]],values[0,valid[0]]
    return (points,values,targetgreen,target.object_mask,target,model.ellipses[other].center,s.min_pair_points,model.matrices[other],patches)

def costs(vectors, data, normalize=False):
    return alg._cost_many(np.deg2rad(vectors),*data[:-1],normalize=normalize,compensate_brightness=True,source_patches=data[-1])

def search(forward, backward=None, reverse=False):
    sign=-1 if reverse else 1
    x=np.arange(0,20.001,2)*sign
    y=np.arange(-20,20.001,2)
    z=np.arange(-10,10.001,2)
    xx,yy,zz=np.meshgrid(x,y,z,indexing='ij')
    vectors=np.column_stack((xx.ravel(),yy.ravel(),zz.ravel()))
    def evaluate(vv, normalized=False):
        values=costs(vv,forward,normalized)
        if backward is not None:
            values=(values+costs(-vv,backward,normalized))/2
        return values
    values=evaluate(vectors)
    k=int(np.argmin(values))
    best,cost=vectors[k],float(values[k])
    trace=[{'grid_step':2,'degrees':best.tolist(),'raw_cost':cost}]
    for step in (1.,.5,.25):
        offsets=np.arange(-1.,1.001,step)
        xx,yy,zz=np.meshgrid(offsets,offsets,offsets,indexing='ij')
        vectors=best[None]+np.column_stack((xx.ravel(),yy.ravel(),zz.ravel()))
        valid=((vectors[:,0]*sign>=0)&(vectors[:,0]*sign<=20)&(np.abs(vectors[:,1])<=20)&(np.abs(vectors[:,2])<=10))
        vectors=vectors[valid]
        values=evaluate(vectors)
        k=int(np.argmin(values))
        if float(values[k])<cost:
            best,cost=vectors[k],float(values[k])
        trace.append({'grid_step':step,'degrees':best.tolist(),'raw_cost':cost})
    residual=float(evaluate(best[None],True)[0])
    return {'rotation_vector_deg':best.tolist(),'raw_cost':cost,'residual':residual,'unchanged_residual_gate_passes':residual<=s.max_pair_error,'nonzero_x_gate_passes':abs(float(best[0]))>=.25,'hits_bounds':bool(abs(best[0])>=20 or abs(best[1])>=20 or abs(best[2])>=10),'trace':trace}

manual=json.loads((ROOT/'diagnostics/fruit340-fix/20261004_motion/manual_correspondences.json').read_text())['markers']
report={'source':str(SOURCE),'scope':'3D candidate grid search; x rolling bound20 and residual.58 kept. Additional z range10 is experimental, not an accepted mapper. No defect/map inference.','pairs':[]}
for frame in (308,309,310,311):
    index=next(i for i,v in enumerate(views) if v.frame_index==frame)
    forward,reverse=setup(index,index+1),setup(index+1,index)
    row={'source_frame':frame,'target_frame':views[index+1].frame_index,'forward':search(forward),'reverse':search(reverse,reverse=True),'joint':search(forward,reverse)}
    Rf=cv2.Rodrigues(np.deg2rad(row['forward']['rotation_vector_deg']))[0]
    Rb=cv2.Rodrigues(np.deg2rad(row['reverse']['rotation_vector_deg']))[0]
    row['independent_inverse_disagreement_deg']=float(np.linalg.norm(np.rad2deg(cv2.Rodrigues(Rb@Rf)[0])))
    if str(frame) in manual and str(views[index+1].frame_index) in manual:
        xy=np.array(manual[str(frame)]['crop_xy'])-model.ellipses[index].center
        xyz=np.r_[xy,alg._height(model.matrices[index],xy[0],xy[1])]
        targetxy=np.array(manual[str(views[index+1].frame_index)]['crop_xy'])
        for name in ('forward','joint'):
            rr=cv2.Rodrigues(np.deg2rad(row[name]['rotation_vector_deg']))[0]
            predicted=(rr@xyz)[:2]+model.ellipses[index+1].center
            row[name]['manual_freckle_predicted_xy']=predicted.tolist()
            row[name]['manual_freckle_error_px']=float(np.linalg.norm(predicted-targetxy))
    report['pairs'].append(row)
    (OUT/'three_axis_review.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(row),flush=True)
