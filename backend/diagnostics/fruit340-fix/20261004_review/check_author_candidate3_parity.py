"""Recheck every successful public-profile3D retry after adding the1px gate."""
from __future__ import annotations
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import cv2
import numpy as np

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
BENCH=ROOT/'diagnostics/authors-benchmark/runs'
NEW=BENCH/'fruit340_native_3d_retry_author_profile_20261004'
PREVIOUS=BENCH/'pixel_switch_trace_author_profile_20261002'
if not (NEW/'report.json').exists():
    raise RuntimeError('Finish the frozen candidate2 public benchmark first')
profile=json.loads((NEW/'report.json').read_text())
historical=json.loads((PREVIOUS/'report.json').read_text())
oldtracks={(t['group'],t['object']):t for t in historical['tracks']}
modules=[]
sources=(OUT/'algorithm.search_patch.snapshot.py',OUT/'algorithm.candidate3_author_parity.snapshot.py')
for number,path in enumerate(sources):
    spec=importlib.util.spec_from_file_location(f'author_gate_parity_{number}',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    modules.append(module)
alg=modules[0]
s=alg.Settings(**profile['settings'])
cv2.setNumThreads(1)
report={'scope':'Every successful native3D retry on the36-sequence public profile, direct pairs and selection. Other source code is identical except one-pixel rejection.', 'candidate2_sha256':hashlib.sha256(sources[0].read_bytes()).hexdigest(),'candidate3_sha256':hashlib.sha256(sources[1].read_bytes()).hexdigest(),'cases':[]}
for track in profile['tracks']:
    original=oldtracks[(track['group'],track['object'])]
    before={p['pair']:p for p in original['pairs']}
    direct=[p['pair'] for p in track['pairs'] if before[p['pair']]['status']=='failed' and p['status']=='ok']
    selected=[r for r in track['map'].get('selection_diagnostics',[]) if r.get('method')=='adjacent_measurement' and r.get('native_retry_accepted')]
    if not direct and not selected:
        continue
    folder=ROOT/'diagnostics/authors-benchmark/data/rotation/data'/track['group']/track['object']
    views=[]
    for path in sorted(folder.glob('im*.png')):
        image=cv2.imread(str(path))
        mask=alg._largest_component((image.max(axis=2)>profile['mask_threshold']).astype(np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        filled=np.zeros_like(mask)
        cv2.drawContours(filled,[max(contours,key=cv2.contourArea)],-1,1,cv2.FILLED)
        views.append(alg.FruitView(image,filled,frame_index=int(path.stem[2:])))
    models={}
    models['direct']=alg.fit_spheroid(views,s)
    prepared=alg._prepare(views,s)
    models['selection']=alg.fit_spheroid(prepared,s)
    cases=[('direct',i,i+1) for i in direct]+[('selection',r['source_frame'],r['target_frame']) for r in selected]
    for kind,a,b in cases:
        fitted=models[kind]
        if kind=='selection':
            fitted=alg._subset_spheroid(fitted,[a,b])
        sourceviews=views if kind=='direct' else prepared
        st=s if kind=='direct' else replace(s,min_pair_angle_deg=.25)
        results=[]
        for module in modules:
            details={}
            try:
                rotation,error=module.estimate_rotation(sourceviews[a],sourceviews[b],fitted,a if kind=='direct' else 0,st,details)
                results.append((rotation,error,details,None))
            except module.MappingError as exc:
                results.append((None,None,details,str(exc)))
        same=bool(results[0][0] is not None and results[1][0] is not None and np.array_equal(results[0][0],results[1][0]) and results[0][1]==results[1][1])
        row={'group':track['group'],'object':track['object'],'source_frame':a,'target_frame':b,'kind':kind,'same_rotation_and_error':same,'candidate2':{'residual':results[0][1],'reason':results[0][3],'details':results[0][2]},'candidate3':{'residual':results[1][1],'reason':results[1][3],'details':results[1][2]}}
        if results[1][0] is not None:
            vector=np.rad2deg(cv2.Rodrigues(results[1][0])[0]).ravel()
            row['rotation_vector_deg']=vector.tolist()
            row['rolling_displacement_px']=float(2*fitted.A*np.sin(np.deg2rad(abs(vector[0]))/2))
        report['cases'].append(row)
        (OUT/'author_candidate3_parity.json').write_text(json.dumps(report,indent=2))
        print(track['group'],track['object'],kind,a,b,same,flush=True)
report['all_successful_retries_identical']=all(r['same_rotation_and_error'] for r in report['cases'])
(OUT/'author_candidate3_parity.json').write_text(json.dumps(report,indent=2))
print('successfully rechecked',len(report['cases']),'cases; parity',report['all_successful_retries_identical'],flush=True)
