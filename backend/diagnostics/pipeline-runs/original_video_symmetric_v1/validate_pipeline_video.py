"""Record a reproducible end-to-end integration test using the user's models.

Track selection is deterministic: the first N IDs with a usable complete crop.
Every video frame is tracked. Geometry selects views before defect inference.
Outputs are isolated from dashboard history and retain intermediate evidence.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

import algorithm
import main as api
from benchmark_conveyor_crops import contact_sheet


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video',type=Path)
    parser.add_argument('--label',required=True)
    parser.add_argument('--track-limit',type=int,default=12)
    parser.add_argument('--frames',type=int)
    parser.add_argument('--bidirectional',action='store_true')
    args=parser.parse_args()
    output=api.BACKEND/'diagnostics'/'pipeline-runs'/args.label
    output.mkdir(parents=True,exist_ok=False)
    for name in ('algorithm.py','main.py','dfine_segmenter.py','validate_pipeline_video.py'):
        (output/name).write_bytes((api.BACKEND/name).read_bytes())
    video=args.video.resolve()
    metadata={'recorded_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'video':str(video),'video_sha256':sha256(video),
              'algorithm_sha256':sha256(api.BACKEND/'algorithm.py'),
              'detector_sha256':sha256(api.MODELS/'detection'/'best_stg1.pth'),
              'segmenter_sha256':sha256(api.MODELS/'segmentation'/'model.pt'),
              'selection':f'First {args.track_limit} distinct tracker IDs with a usable complete fruit crop',
              'limitations':'No manual ground truth. This tests model integration, operability and evidence; it does not establish accuracy.',
              'status':'loading_models'}
    def save():
        (output/'report.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    save()
    print('Loading the actual D-FINE detection and segmentation checkpoints...',flush=True)
    pipeline,detector,segmenter=api._make_pipeline(capture_stride_frames=1,max_views_per_track=180)
    pipeline.settings.bidirectional_matching=args.bidirectional
    metadata['settings']=asdict(pipeline.settings)
    metadata['detector_classes']=detector.names
    metadata['defect_classes']=segmenter.names
    metadata['device']=detector.device
    metadata['tracker']=type(detector.tracker).__name__
    metadata['status']='capturing'
    save()
    capture=cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f'Cannot open {video}')
    fps=capture.get(cv2.CAP_PROP_FPS)
    selected=set(); records=[]; previous=None; index=0; sampled=0
    started=time.perf_counter()
    try:
        while args.frames is None or index<args.frames:
            ok,frame=capture.read()
            if not ok:
                break
            gray=cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(320,180),interpolation=cv2.INTER_AREA)
            changed=previous is None or cv2.mean(cv2.absdiff(gray,previous))[0]>=.1
            if changed:
                previous=gray; sampled+=1
            boxes=detector.track(frame,conf=pipeline.detection_conf)[0].boxes
            rows=[]
            for item in boxes.data:
                x1,y1,x2,y2,identity,confidence,category=map(float,item)
                identity=int(identity)
                rows.append([identity,x1,y1,x2,y2,confidence,int(category)])
                if changed and (identity in selected or len(selected)<args.track_limit):
                    try:
                        if pipeline.add_tracked_detection(frame,identity,(x1,y1,x2,y2),index):
                            selected.add(identity)
                    except algorithm.MappingError as error:
                        if identity in selected:
                            counter=pipeline.rejected_views_by_id.setdefault(identity,{})
                            counter[str(error)]=counter.get(str(error),0)+1
            records.append({'frame':index,'changed':changed,'tracks':rows})
            if index in (0,150,300,450,600):
                overlay=frame.copy()
                for identity,x1,y1,x2,y2,confidence,category in rows:
                    if identity not in selected:
                        continue
                    cv2.rectangle(overlay,(round(x1),round(y1)),(round(x2),round(y2)),(0,255,0),2)
                    cv2.putText(overlay,f'ID {identity} {confidence:.2f}',(round(x1),max(18,round(y1)-5)),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,255,0),2)
                cv2.imwrite(str(output/f'detection_frame_{index:04d}.png'),overlay)
            index+=1
            if index%60==0:
                print(f'Captured {index} frames, {sampled} changed images, {len(selected)} selected tracks',flush=True)
    finally:
        capture.release()
    (output/'tracking.json').write_text(json.dumps(records),encoding='utf-8')
    metadata.update(status='mapping',frames=index,fps=fps,sampled_frames=sampled,
                    capture_seconds=time.perf_counter()-started,fruits=[])
    save()
    for identity in sorted(selected):
        views=pipeline.views_by_id[identity].copy()
        folder=output/str(identity); folder.mkdir(exist_ok=True)
        manifest=[]
        # Save all inputs before mapping, so the test can be rerun without a GPU.
        for i,view in enumerate(views):
            name=f'view_{i:03d}.npz'
            np.savez_compressed(folder/name,image=view.image,mask=view.object_mask)
            manifest.append({'file':name,'frame':view.frame_index,'bbox':view.fruit_bbox})
        (folder/'views.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        positions=np.unique(np.linspace(0,len(views)-1,min(len(views),32)).astype(int))
        contact_sheet([views[i] for i in positions],folder/'view_contact_sheet.png')
        before=segmenter.inference_calls
        row=api._finish_track(pipeline,identity,output)
        row['segmentation_calls']=segmenter.inference_calls-before
        row['evidence']=[]
        segmented=[v for v in views if v.defect_masks]
        if segmented:
            samples=np.unique(np.linspace(0,len(segmented)-1,min(len(segmented),6)).astype(int))
            for i in samples:
                view=segmented[i]
                cv2.imwrite(str(folder/f'frame_{view.frame_index:04d}_crop.png'),view.image)
                cv2.imwrite(str(folder/f'frame_{view.frame_index:04d}_fruit_mask.png'),view.object_mask*255)
                overlay=view.image.copy()
                combined=np.zeros(view.object_mask.shape,bool)
                for name,mask in view.defect_masks.items():
                    cv2.imwrite(str(folder/f'frame_{view.frame_index:04d}_{name}.png'),mask*255)
                    combined|=mask>0
                overlay[combined]=(.5*overlay[combined]+.5*np.array([0,0,255])).astype(np.uint8)
                filename=f'frame_{view.frame_index:04d}_defect_overlay.png'
                cv2.imwrite(str(folder/filename),overlay)
                row['evidence'].append(filename)
        # Store masks for every inferred view, not just the six illustrated ones.
        for view in segmented:
            np.savez_compressed(folder/f'defects_frame_{view.frame_index:04d}.npz',**view.defect_masks)
        metadata['fruits'].append(row)
        save()
        print(f'ID {identity}: {len(views)} captured, {len(row.get("mapped_view_frames",[]))} mapped, '
              f'{row["status"]}, grade={row.get("grade")}, rotation={row.get("rotation_coverage_deg")}',flush=True)
    metadata.update(status='complete',seconds=time.perf_counter()-started,
                    metrics=api._analysis_metrics(index,started,detector,segmenter,fps),
                    outcomes=dict(Counter(row['status'] for row in metadata['fruits'])))
    save()
    print(json.dumps(metadata['outcomes'],indent=2),flush=True)


if __name__=='__main__':
    main()
