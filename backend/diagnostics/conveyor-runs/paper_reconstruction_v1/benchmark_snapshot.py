"""Versioned reconstruction checks on saved user-video crops (no model rerun).

The old capture contains no defect inference. These tests measure operability
and diagnostics, not labelled reconstruction/grade accuracy.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

import algorithm
from algorithm import (FruitView, Settings, _validate_capture_mask,
                       fit_spheroid, estimate_rotation, build_surface_map)

ROOT = Path(__file__).resolve().parent / 'diagnostics'


def load_capture(folder):
    root = folder.parent
    changes = json.loads((root/'frame_changes.json').read_text())['change_frames']
    tracks = json.loads((root/'tracks.json').read_text())
    views, seen, rejected = [], set(), []
    for item in json.loads((folder/'views.json').read_text()):
        scene = int(np.searchsorted(changes, item['frame'], side='right'))
        if scene in seen:
            continue
        seen.add(scene)
        with np.load(folder/item['file']) as data:
            view = FruitView(data['image'], data['mask'], {}, item['frame'], tuple(item['bbox']))
        box = next(row[1:5] for row in tracks[item['frame']]['tracks'] if row[0] == int(folder.name))
        try:
            if box[0] <= 2 or box[1] <= 2 or box[2] >= 1918 or box[3] >= 1078:
                raise RuntimeError('Fruit is cut off by the video frame')
            _validate_capture_mask(view.object_mask, view.fruit_bbox, Settings())
            views.append(view)
        except RuntimeError as error:
            rejected.append({'frame':item['frame'],'reason':str(error)})
    return views, rejected


def contact_sheet(views, path):
    if not views:
        return
    cols, size = 8, 160
    rows = (len(views)+cols-1)//cols
    canvas = np.full((rows*(size+24),cols*size,3),240,np.uint8)
    for i, view in enumerate(views):
        crop=view.image.copy()
        contours,_=cv2.findContours(view.object_mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(crop,contours,-1,(0,255,0),1)
        scale=min((size-8)/crop.shape[1],(size-8)/crop.shape[0])
        crop=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
        x=(i%cols)*size+4; y=(i//cols)*(size+24)+24
        canvas[y:y+crop.shape[0],x:x+crop.shape[1]]=crop
        cv2.putText(canvas,f'{i}: frame {view.frame_index}',(x,y-6),cv2.FONT_HERSHEY_SIMPLEX,.4,(20,20,20),1)
    cv2.imwrite(str(path),canvas)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    parser.add_argument('--tracks',nargs='+',default=['1','14','108','123'])
    parser.add_argument('--directions',type=int,nargs='+',default=[1,-1])
    parser.add_argument('--bidirectional',action='store_true')
    parser.add_argument('--min-pair-angle',type=float,default=1.)
    args=parser.parse_args()
    output=ROOT/'conveyor-runs'/args.label
    output.mkdir(parents=True,exist_ok=False)
    source=Path(algorithm.__file__).read_bytes()
    (output/'algorithm_snapshot.py').write_bytes(source)
    (output/'benchmark_snapshot.py').write_bytes(Path(__file__).read_bytes())
    report={'recorded_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
            'source':'backend/diagnostics/current-upload; older saved conveyor capture, not latest 17-second upload',
            'limitations':'No ground-truth rotations, defect labels or defect inference in these captures. No grading validation.',
            'algorithm_sha256':hashlib.sha256(source).hexdigest(),'tracks':[]}
    for track in args.tracks:
        views,rejected=load_capture(ROOT/'current-upload'/track)
        folder=output/track; folder.mkdir()
        contact_sheet(views,folder/'views_and_masks.png')
        for direction in args.directions:
            settings=Settings(spheroid_type='auto',rotation_axis='x',rotation_direction=direction,
                              bidirectional_matching=args.bidirectional,min_pair_angle_deg=args.min_pair_angle,
                              minimum_rotation_coverage_deg=350,maximum_pair_gap_deg=55)
            record={'track':track,'direction':direction,'settings':asdict(settings),
                    'views':len(views),'frames':[v.frame_index for v in views],
                    'rejected_views':rejected,'pairs':[]}
            try:
                model=fit_spheroid(views,settings)
                record['radii']=[model.A,model.B,model.A]
                for i in range(len(views)-1):
                    try:
                        R,error=estimate_rotation(views[i],views[i+1],model,i,settings)
                        record['pairs'].append({'pair':i,'status':'ok','cost':error,
                                               'vector_deg':np.rad2deg(cv2.Rodrigues(R)[0]).ravel().tolist()})
                    except (RuntimeError,ValueError) as error:
                        record['pairs'].append({'pair':i,'status':'failed','reason':str(error)})
                mapped=build_surface_map(views,settings)
                record['map']={'status':'produced','result_status':mapped.status,
                               'rotation_coverage_deg':mapped.rotation_coverage_deg,
                               'observed_surface_pct':mapped.observed_surface_pct}
                cv2.imwrite(str(folder/f'map_direction_{direction}.png'),mapped.bgr_map)
                cv2.imwrite(str(folder/f'observed_direction_{direction}.png'),mapped.observed_mask*255)
            except (RuntimeError,ValueError) as error:
                record['map']={'status':'failed','reason':str(error)}
            report['tracks'].append(record)
            (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            accepted=sum(p['status']=='ok' for p in record['pairs'])
            print(f'Track {track} direction {direction}: {len(views)} views; {accepted}/{len(record["pairs"])} pairs; {record["map"]}',flush=True)


if __name__=='__main__':
    main()
