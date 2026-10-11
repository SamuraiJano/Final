"""Deterministic real-pair calibration, retaining every outcome and inverse check."""
from dataclasses import asdict, replace
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np
import algorithm as a
from validate_dense_mapping import DEFAULT_OUTPUT, load_views, write, stats


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT/'pilot')
    parser.add_argument('--profile',choices=('paper','paper_glare','native','native_glare'),required=True)
    args=parser.parse_args()
    output=args.output
    manifest=json.loads((output/'inputs.json').read_text())
    parameters=json.loads((output/'adaptive_40_10_settings.json').read_text())
    parameters.update(max_pair_angle_deg=40,transverse_angle_deg=10,min_pair_angle_deg=1)
    native=args.profile.startswith('native')
    parameters.update(exclude_specular_texture='glare' in args.profile,refine_small_motion=False,
        matching_cost='aligned_mad' if native else 'mad',image_downsample=1 if native else 2,
        highpass_sigma=5 if native else 2.5)
    s=a.Settings(**parameters)
    rows=[]
    cv2.setNumThreads(1)
    path=output/f'pair_probe_{args.profile}.json'
    started=time.perf_counter()
    for record in manifest['records']:
        if len(record['views'])<13:
            continue
        views=load_views(a,output,record)
        model=a.fit_spheroid(views,s)
        # All records eligible for the probe, two anchors, same four spacings.
        for source in sorted({0,max(0,len(views)//2-4)}):
            for gap in (1,2,3,4):
                target=source+gap
                if target>=len(views):
                    continue
                row=dict(track_id=record['track_id'],source_frame=views[source].frame_index,
                         target_frame=views[target].frame_index,source_index=source,target_index=target)
                pair=a._subset_spheroid(model,[source,target])
                try:
                    rotation,residual=a._search_rotation(views[source],views[target],pair,0,s)
                    vector=np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel()
                    row.update(vector_deg=vector.tolist(),residual=residual,rolling_angle=abs(vector[0]),status='joint_measured')
                    details=dict(image_downsample=s.image_downsample,highpass_sigma=s.highpass_sigma,matching_cost_used=s.matching_cost)
                    a._verify_keyframe_rotation(views[source],views[target],pair,rotation,s,details)
                    row.update(status='inverse_supported',**details)
                except a.MappingError as error:
                    row.update(status='rejected',reason=str(error))
                rows.append(row)
        write(path,dict(profile=args.profile,settings=asdict(s),pairs=rows,seconds=time.perf_counter()-started))
        print(args.profile,record['track_id'],len(rows),'supported',sum(r['status']=='inverse_supported' for r in rows),flush=True)
    supported=[r for r in rows if r['status']=='inverse_supported']
    summary=dict(pairs=len(rows),supported=len(supported),angle=stats([r['rolling_angle'] for r in supported]),
        residual=stats([r['residual'] for r in supported]),
        support_by_spacing={str(g):sum(r['status']=='inverse_supported' and r['target_index']-r['source_index']==g for r in rows) for g in (1,2,3,4)})
    write(path,dict(profile=args.profile,settings=asdict(s),pairs=rows,seconds=time.perf_counter()-started,summary=summary))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
