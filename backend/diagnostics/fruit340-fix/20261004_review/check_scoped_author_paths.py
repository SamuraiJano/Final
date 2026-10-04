"""Verify final55-degree scope keeps original author-profile pair decisions."""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import cv2
import numpy as np

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
BENCH=ROOT/'diagnostics/authors-benchmark/runs'
OLD=BENCH/'pixel_switch_trace_author_profile_20261002'
PARTIAL=BENCH/'fruit340_native_3d_retry_author_profile_20261004'
historical=json.loads((OLD/'report.json').read_text())
progress=json.loads((OUT/'author_profile_progress.json').read_text())
oldtracks={(t['group'],t['object']):t for t in historical['tracks']}
sources=(OLD/'algorithm_snapshot.py',OUT/'algorithm.final_scoped_author.snapshot.py')
modules=[]
for i,path in enumerate(sources):
    spec=importlib.util.spec_from_file_location(f'scoped_author_parity_{i}',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    modules.append(module)
old,final=modules
settings=[m.Settings(**historical['settings']) for m in modules]
cases=[(r['group'],r['object'],r['pair']) for r in progress['changed_pairs'] if r['before']['status']=='failed' and r['after']['status']=='ok']
for track in historical['tracks']:
    if len(cases)>=16:
        break
    good=next((p for p in track['pairs'] if p['status']=='ok' and (track['group'],track['object'],p['pair']) not in cases),None)
    if good:
        cases.append((track['group'],track['object'],good['pair']))
if len(cases)!=16:
    raise RuntimeError('Expected exactly16 sample pairs')
search=final._search_rotation
native3d_calls=[]
all_search_calls=[]
def traced(*args,**kwargs):
    all_search_calls.append({'inplane_angle_deg':kwargs.get('inplane_angle_deg',0.),'image_downsample':args[4].image_downsample})
    if kwargs.get('inplane_angle_deg',0)>0:
        native3d_calls.append(all_search_calls[-1])
    return search(*args,**kwargs)
final._search_rotation=traced
cv2.setNumThreads(1)
report={'scope':'16 author-profile pairs, including every10 previously rejected pair rescued by experimental wide retry. Final max55 guard disables all such retries.','source_sha256':{'original':hashlib.sha256(sources[0].read_bytes()).hexdigest(),'final':hashlib.sha256(sources[1].read_bytes()).hexdigest()},'settings_changed':{k:{'original':v,'final':asdict(settings[1]).get(k)} for k,v in historical['settings'].items() if asdict(settings[1]).get(k)!=v},'settings_added':{k:v for k,v in asdict(settings[1]).items() if k not in historical['settings']},'cases':[]}
cache={}
started=time.perf_counter()
for group,name,index in cases:
    if (group,name) not in cache:
        views=[]
        folder=ROOT/'diagnostics/authors-benchmark/data/rotation/data'/group/name
        for path in sorted(folder.glob('im*.png')):
            image=cv2.imread(str(path))
            mask=old._largest_component((image.max(axis=2)>historical['mask_threshold']).astype(np.uint8))
            contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            filled=np.zeros_like(mask)
            cv2.drawContours(filled,[max(contours,key=cv2.contourArea)],-1,1,cv2.FILLED)
            views.append(old.FruitView(image,filled,frame_index=int(path.stem[2:])))
        fitted=[m.fit_spheroid(views,s) for m,s in zip(modules,settings)]
        same_geometry=(fitted[0].A==fitted[1].A and fitted[0].B==fitted[1].B and all(np.array_equal(a,b) for a,b in zip(fitted[0].matrices,fitted[1].matrices)))
        cache[(group,name)]=(views,fitted,same_geometry)
    views,fitted,same_geometry=cache[(group,name)]
    outcomes=[]
    calls_before=len(native3d_calls)
    for m,s,model in zip(modules,settings,fitted):
        details={}
        try:
            rotation,error=m.estimate_rotation(views[index],views[index+1],model,index,s,details)
            outcomes.append((rotation,error,None,details))
        except m.MappingError as exc:
            outcomes.append((None,None,str(exc),details))
    before,after=outcomes
    same=bool((before[0] is not None and after[0] is not None and np.array_equal(before[0],after[0]) and before[1]==after[1]) or (before[0] is None and after[0] is None and before[2]==after[2]))
    row={'group':group,'object':name,'pair':index,'same_geometry':same_geometry,'same_rotation_error_or_failure':same,'original':{'residual':before[1],'reason':before[2]},'final':{'residual':after[1],'reason':after[2],'details':after[3]},'new_3d_call_count':len(native3d_calls)-calls_before}
    report['cases'].append(row)
    print(group,name,index,same,len(native3d_calls)-calls_before,flush=True)
report.update(all_pair_results_bit_identical=all(r['same_rotation_error_or_failure'] and r['same_geometry'] for r in report['cases']),new_3d_call_count=len(native3d_calls),all_search_calls=all_search_calls,seconds=time.perf_counter()-started)
(OUT/'scoped_author_path_parity.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('cases','all_search_calls')},indent=2))
