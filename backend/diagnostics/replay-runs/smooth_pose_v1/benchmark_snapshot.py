"""Isolated geometry ablations on preserved inference crops; no model rerun."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np
import algorithm
from algorithm import FruitView,Settings,build_surface_map


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='original_video_symmetric_v1')
    parser.add_argument('--label',required=True)
    parser.add_argument('--tracks',nargs='+')
    parser.add_argument('--estimator',choices=['photometric','flow'],default='photometric')
    parser.add_argument('--pose',choices=['silhouette_trend','smooth'],default='silhouette_trend')
    parser.add_argument('--stride',type=int,default=1)
    parser.add_argument('--direction',type=int,choices=[-1,1],default=1)
    parser.add_argument('--forward-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent/'diagnostics'
    source=root/'pipeline-runs'/args.source
    output=root/'replay-runs'/args.label;output.mkdir(parents=True,exist_ok=False)
    code=Path(algorithm.__file__).read_bytes()
    (output/'algorithm_snapshot.py').write_bytes(code)
    (output/'benchmark_snapshot.py').write_bytes(Path(__file__).read_bytes())
    settings=Settings(spheroid_type='auto',rotation_axis='x',rotation_direction=args.direction,
                      rotation_estimator=args.estimator,pole_pose_method=args.pose,
                      bidirectional_matching=not args.forward_only,select_rotating_views=True,
                      minimum_longitude_coverage_deg=350)
    report={'recorded_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
            'algorithm_sha256':hashlib.sha256(code).hexdigest(),'source':str(source),
            'settings':asdict(settings),'input_stride':args.stride,
            'limitations':'Preserved actual crops and silhouettes; no manual motion truth. Defect masks omitted to isolate reconstruction. Not a grading-accuracy test.',
            'tracks':[]}
    folders=sorted([p for p in source.iterdir() if p.is_dir() and p.name.isdigit()],key=lambda p:int(p.name))
    if args.tracks:folders=[p for p in folders if p.name in args.tracks]
    for folder in folders:
        views=[]
        for item in json.loads((folder/'views.json').read_text())[::args.stride]:
            with np.load(folder/item['file']) as data:
                views.append(FruitView(data['image'],data['mask'],frame_index=item['frame']))
        row={'track':folder.name,'views':len(views)}
        destination=output/folder.name;destination.mkdir()
        start=time.perf_counter()
        try:
            mapped=build_surface_map(views,settings)
            row.update(status=mapped.status,rotation_deg=mapped.rotation_coverage_deg,
                       observed_longitude_deg=mapped.observed_longitude_deg,
                       observed_surface_pct=mapped.observed_surface_pct,
                       view_frames=mapped.view_frames,selection_diagnostics=mapped.selection_diagnostics)
            cv2.imwrite(str(destination/'surface_map.png'),mapped.bgr_map)
            cv2.imwrite(str(destination/'observed.png'),mapped.observed_mask*255)
        except (algorithm.MappingError,ValueError) as error:
            row.update(status='mapping_failed',reason=str(error))
        row['seconds']=time.perf_counter()-start
        report['tracks'].append(row)
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print({k:v for k,v in row.items() if k not in ('selection_diagnostics','view_frames')},flush=True)


if __name__=='__main__':main()
