"""Isolate geometry/rotation sensitivity using actual corrected tracker outputs.

No detector/segmenter is rerun, no grade is claimed, and production code/settings
are unchanged. Each ablation sees identical preserved crops and fruit masks.
"""
import argparse
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import algorithm
from algorithm import FruitView, MappingError, NaartjiePipeline, Settings, build_surface_map, fit_spheroid
from benchmark_conveyor_crops import contact_sheet


class NoSegmentation:
    names = {0: 'unused_in_geometry_test'}

    def predict(self, *_args, **_kwargs):
        raise AssertionError('This experiment must not run segmentation or manufacture defect masks')


def write(path, data):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def iou(rows, box):
    intersection=np.maximum(0,np.minimum(rows[:,2:4],box[2:4])-
                            np.maximum(rows[:,:2],box[:2])).prod(axis=1)
    areas=np.maximum(0,rows[:,2:4]-rows[:,:2]).prod(axis=1)
    area=np.maximum(0,box[2:4]-box[:2]).prod()
    return intersection/np.maximum(areas+area-intersection,1e-6)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    parser.add_argument('--baseline-tracks',type=int,nargs='+',default=[125,1,14])
    args=parser.parse_args()
    backend=Path(__file__).resolve().parent
    root=backend/'diagnostics/algorithm-audit'/args.label
    root.mkdir(parents=True,exist_ok=False)
    for name in ('algorithm.py','dfine_segmenter.py','main.py','validate_algorithm_decision.py'):
        (root/name).write_bytes((backend/name).read_bytes())
    prior=backend/'diagnostics/entry-tracking/entry_full_20261002'
    before=json.loads((prior/'baseline_three_detections.json').read_text())
    after=json.loads((prior/'immediate_one_detection.json').read_text())
    input_report=json.loads((prior/'report.json').read_text())
    original=json.loads((backend/'diagnostics/api-runs/full_original_20261002/response.json').read_text())
    matched={}
    for identity in args.baseline_tracks:
        counts=Counter()
        for old,new in zip(before,after):
            reference=next((row for row in old['tracks'] if int(row[4])==identity),None)
            rows=np.asarray(new['tracks']).reshape(-1,7)
            if reference is None or not len(rows):continue
            overlaps=iou(rows,np.asarray(reference))
            index=int(overlaps.argmax())
            if overlaps[index]>.8:counts[int(rows[index,4])]+=1
        if not counts:raise RuntimeError(f'Cannot match baseline fruit {identity}')
        current,count=counts.most_common(1)[0]
        matched[current]={'baseline_id':identity,'matched_frame_count':count,
                          'all_candidate_counts':dict(counts),
                          'historical_result':next(row for row in original['fruits'] if row['track_id']==identity)}
    settings=Settings(spheroid_type='auto',rotation_axis='x',rotation_direction=1,
                      select_rotating_views=True,bidirectional_matching=True,
                      minimum_longitude_coverage_deg=350,maximum_pair_gap_deg=55,
                      defect_observations_complete=False)
    pipeline=NaartjiePipeline(NoSegmentation(),settings=settings,capture_stride_frames=1,
                              max_views_per_track=120,defer_defect_segmentation=True)
    capture=cv2.VideoCapture(input_report['video'])
    cv2.setNumThreads(1)
    for item in after:
        ok,frame=capture.read()
        if not ok:raise RuntimeError('Original video ended before saved tracker data')
        for row in item['tracks']:
            identity=int(row[4])
            if identity not in matched:continue
            # Fix the extraction seed per frame to make this diagnostic repeatable.
            # Historical GrabCut seeds were not retained, so old/new crop changes
            # cannot be attributed to tracker boxes alone.
            cv2.setRNGSeed(item['frame'])
            try:pipeline.add_tracked_detection(frame,identity,row[:4],item['frame'])
            except MappingError as error:
                counts=pipeline.rejected_views_by_id.setdefault(identity,{})
                counts[str(error)]=counts.get(str(error),0)+1
    capture.release()
    variants={'baseline_auto_x_positive_d4':settings,
              'sphere_x_positive_d4':replace(settings,spheroid_type='sphere'),
              'auto_x_positive_d2':replace(settings,image_downsample=2),
              'negative_direction_control':replace(settings,rotation_direction=-1),
              'vertical_axis_control':replace(settings,rotation_axis='y')}
    report={'recorded_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
            'scope':'Geometry only; actual corrected track boxes and original images; same fixed crops/masks per variant.',
            'limitations':'No manual rotation or silhouette ground truth. Geometry coverage is not accuracy. '
                          'Historical/new masks can differ because extraction seed and boxes differ. No defect inference or grade.',
            'input_tracking_run':str(prior),'video_sha256':input_report['input_sha256']['video'],
            'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
                             ('algorithm.py','dfine_segmenter.py','main.py','validate_algorithm_decision.py')},
            'selection_rule':f'Baseline IDs {args.baseline_tracks}: prior numerically graded example plus first two selected records; not random.',
            'tracks':[]}
    write(root/'report.json',report)
    for identity,match in matched.items():
        folder=root/str(identity);folder.mkdir()
        views=pipeline.views_by_id.get(identity,[])
        contact_sheet(views,folder/'all_captured_views.png')
        manifest=[]
        for index,view in enumerate(views):
            filename=f'view_{index:03d}.npz'
            np.savez_compressed(folder/filename,image=view.image,mask=view.object_mask)
            manifest.append({'file':filename,'frame':view.frame_index,'bbox':view.fruit_bbox})
        write(folder/'views.json',manifest)
        track={'corrected_id':identity,**match,'first_seen_frame':pipeline.tracking_history_by_id[identity][0]['frame'],
               'last_seen_frame':pipeline.tracking_history_by_id[identity][-1]['frame'],
               'captured_views':len(views),'capture_frames':[view.frame_index for view in views],
               'rejections':pipeline.rejected_views_by_id.get(identity,{}),'variants':[]}
        report['tracks'].append(track)
        for name,variant in variants.items():
            started=time.perf_counter();destination=folder/name;destination.mkdir()
            row={'name':name,'settings':asdict(variant)}
            try:
                model=fit_spheroid(views,variant)
                row['shape']={'A':model.A,'B':model.B,'ellipse_major_range':[min(e.major for e in model.ellipses),max(e.major for e in model.ellipses)],
                              'ellipse_minor_range':[min(e.minor for e in model.ellipses),max(e.minor for e in model.ellipses)]}
                mapped=build_surface_map(views,variant)
                assert mapped.grade is None
                row.update(status=mapped.status,rotation_deg=mapped.rotation_coverage_deg,
                           longitude_deg=mapped.observed_longitude_deg,surface_pct=mapped.observed_surface_pct,
                           mapped_frames=mapped.view_frames,discarded_frames=mapped.discarded_view_frames,
                           pair_vectors_deg=mapped.pair_rotation_vectors_deg,pair_errors=mapped.pair_errors,
                           diagnostics=mapped.selection_diagnostics)
                cv2.imwrite(str(destination/'surface_map.png'),mapped.bgr_map)
                cv2.imwrite(str(destination/'observed.png'),mapped.observed_mask*255)
                selected={value for value in mapped.view_frames}
                contact_sheet([view for view in views if view.frame_index in selected],destination/'selected_views.png')
            except (MappingError,ValueError) as error:
                row.update(status='mapping_failed',reason=str(error))
            row['seconds']=time.perf_counter()-started
            track['variants'].append(row)
            write(root/'report.json',report)
            print({'id':identity,**{key:value for key,value in row.items() if key not in
                  ('settings','shape','mapped_frames','discarded_frames','pair_vectors_deg','pair_errors','diagnostics')}},flush=True)
    figure,axes=plt.subplots(len(report['tracks']),2,figsize=(12,3.5*len(report['tracks'])),squeeze=False)
    for panels,track in zip(axes,report['tracks']):
        for variant in track['variants']:
            if 'mapped_frames' not in variant:continue
            y=np.r_[0,np.cumsum([abs(value[0 if variant['settings']['rotation_axis']=='x' else 1]) for value in variant['pair_vectors_deg']])]
            panels[0].plot(variant['mapped_frames'],y,label=variant['name'])
        panels[0].set(xlabel='Original frame index',ylabel='Estimated dominant rotation (degrees)',title=f'Baseline {track["baseline_id"]} / corrected {track["corrected_id"]}')
        panels[0].legend(fontsize=7)
        entries=track['variants'];panels[1].barh([item['name'] for item in entries],[item.get('longitude_deg',0) for item in entries])
        panels[1].axvline(350,color='red',linestyle='--');panels[1].set(xlim=(0,365),xlabel='Numerically observed longitude (degrees)')
    figure.suptitle('Same real crops, isolated geometry assumptions — coverage is not accuracy',fontsize=14)
    figure.tight_layout();figure.savefig(root/'algorithm_sensitivity.png',dpi=300);figure.savefig(root/'algorithm_sensitivity.pdf');plt.close(figure)
    report['completed_at']=datetime.now(timezone(timedelta(hours=2))).isoformat()
    write(root/'report.json',report)
    print('Completed isolated algorithm sensitivity test.',flush=True)


if __name__=='__main__':main()
