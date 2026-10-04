"""Compare scalar and batched search on actual author image pairs."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

import algorithm
from algorithm import Settings, fit_spheroid, estimate_rotation
from benchmark_authors import ROOT, DATA, load_views


def main():
    destination=ROOT/'optimization_runs'/'batch_search_v1'
    destination.mkdir(parents=True,exist_ok=False)
    source=Path(algorithm.__file__).read_bytes()
    (destination/'algorithm_snapshot.py').write_bytes(source)
    (destination/'benchmark_snapshot.py').write_bytes(Path(__file__).read_bytes())
    rows=[]
    for group,name in (('mandarins','obj0000'),('oranges','obj0001'),('tomatoes','obj0000')):
        views=load_views(DATA/'rotation'/'data'/group/name,0)
        settings=Settings(spheroid_type='auto',rotation_axis='x',rotation_direction=-1,bidirectional_matching=True)
        model=fit_spheroid(views,settings)
        for i in range(len(views)-1):
            row={'group':group,'object':name,'pair':i}
            for mode in ('scalar','batch'):
                started=time.perf_counter()
                try:
                    R,error=estimate_rotation(views[i],views[i+1],model,i,
                                               replace(settings,batch_rotation_search=mode=='batch'))
                    row[mode]={'status':'ok','R':R.tolist(),'cost':error}
                except algorithm.MappingError as error:
                    row[mode]={'status':'failed','reason':str(error)}
                row[mode]['seconds']=time.perf_counter()-started
            row['passed']=row['scalar']['status']==row['batch']['status']
            if row['scalar']['status']==row['batch']['status']=='ok':
                relative=np.array(row['batch']['R'])@np.array(row['scalar']['R']).T
                delta=float(np.linalg.norm(np.rad2deg(cv2.Rodrigues(relative)[0])))
                row['rotation_difference_deg']=delta
                row['cost_difference']=abs(row['scalar']['cost']-row['batch']['cost'])
                row['passed'] &= delta<.01 and row['cost_difference']<1e-5
            elif row['scalar']['status']==row['batch']['status']=='failed':
                row['passed'] &= row['scalar']['reason']==row['batch']['reason']
            rows.append(row)
    scalar=sum(r['scalar']['seconds'] for r in rows)
    batch=sum(r['batch']['seconds'] for r in rows)
    report={'recorded_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
            'algorithm_sha256':hashlib.sha256(source).hexdigest(),'pairs':len(rows),
            'passed':all(r['passed'] for r in rows),'scalar_seconds':scalar,'batch_seconds':batch,
            'speedup':scalar/batch,'max_difference_deg':max(r.get('rotation_difference_deg',0) for r in rows),'rows':rows}
    (destination/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
