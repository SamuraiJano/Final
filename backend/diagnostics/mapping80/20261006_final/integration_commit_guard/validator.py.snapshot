"""Actual detector, identity guards, deferred segmenter and grading integration.

The first 80 frames of the hashed original video are re-encoded for a bounded
production-pipeline integration check. This is separate from the complete paired
geometry replay and is never used to compute the full-cohort success rate.
--full-video uses the complete original video without re-encoding.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import time

BACKEND=Path(__file__).resolve().parent
OUTPUT=BACKEND/'diagnostics/mapping80/20261006_final/integration'
os.environ.setdefault('YOLO_CONFIG_DIR',str(BACKEND/'runtime/ultralytics-validation'))
Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True,exist_ok=True)
import cv2
import numpy as np
cv2.setNumThreads(1)  # bounded validation resources; objective/data unchanged
import main
from validate_dense_mapping import sha,write
from validation_resources import wait_for_memory


def run(full_video=False):
    OUTPUT.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    resource_wait_seconds = [0.]
    def memory_gate(context, *, initial=False):
        resource_wait_seconds[0] += wait_for_memory(OUTPUT/'resource_status.json',
            physical_gib=8 if initial else 0, commit_gib=12 if initial else 4,
            disk_gib=2 if initial else .25, context=context)
    memory_gate('before loading models', initial=True)
    manifest=json.loads((OUTPUT.parent/'inputs.json').read_text())
    original=Path(manifest['video'])
    if sha(original)!=manifest['video_sha256']:
        raise ValueError('Original video differs from the paired replay')
    clip=OUTPUT/'first_80_frames.mp4'
    capture=cv2.VideoCapture(str(original))
    fps=capture.get(cv2.CAP_PROP_FPS)
    size=(int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    if full_video:
        frames=int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.release()
        clip=original
    else:
        writer=cv2.VideoWriter(str(clip),cv2.VideoWriter_fourcc(*'mp4v'),fps,size)
        frames=0
        try:
            while frames<80:
                ok,image=capture.read()
                if not ok:
                    break
                writer.write(image); frames+=1
        finally:
            writer.release(); capture.release()
    for name,data in main.SOURCE_SNAPSHOTS.items():
        (OUTPUT/name).write_bytes(data)
    (OUTPUT/'validator.py.snapshot').write_bytes(Path(__file__).read_bytes())
    (OUTPUT/'validation_resources.py.snapshot').write_bytes((BACKEND/'validation_resources.py').read_bytes())
    weights=dict(detector=Path(os.getenv('FRUIT_DETECTOR_WEIGHTS',main.MODELS/'detection/best_stg1.pth')),
                 segmenter=Path(os.getenv('DFINE_SEG_WEIGHTS',main.MODELS/'segmentation/model.pt')))
    request=dict(original_video=str(original),original_sha256=sha(original),clip_sha256=sha(clip),
                 frames=frames,fps=fps,full_original_video=full_video,
                 validator_sha256=sha(OUTPUT/'validator.py.snapshot'),opencv_threads=cv2.getNumThreads(),
                 resource_guard_sha256=sha(OUTPUT/'validation_resources.py.snapshot'),
                 resource_guard=dict(initial_physical_gib=8,initial_commit_gib=12,runtime_commit_gib=4,
                                     initial_disk_gib=2,runtime_disk_gib=.25,
                                     behavior='Wait only; no changes to inputs or numerical decisions.'),
                 source_sha256={name:sha(OUTPUT/name) for name in main.SOURCE_SNAPSHOTS},
                 method=__doc__,model_paths={name:str(path.resolve()) for name,path in weights.items()},
                 model_sha256={name:sha(path) for name,path in weights.items()})
    write(OUTPUT/'request.json',request)
    handles={}
    create=main._make_pipeline
    def pipeline(*args,**kwargs):
        p,d,s=create(*args,**kwargs)
        handles.update(pipeline=p,detector=d,segmenter=s)
        process_frame = p.process_frame
        def guarded_frame(*frame_args, **frame_kwargs):
            memory_gate('before production frame')
            return process_frame(*frame_args, **frame_kwargs)
        p.process_frame = guarded_frame
        return p,d,s
    main._make_pipeline=pipeline
    finish=main._finish_track
    def retain_selected(p,identity,output):
        memory_gate('before finishing track '+str(identity))
        views=list(p.views_by_id.get(identity,[]))
        row=finish(p,identity,output)
        if row and row.get('mapped_view_frames'):
            selected=set(row['mapped_view_frames'])
            inputs=[]
            for view in views:
                if view.frame_index in selected:
                    file=f'selected_frame_{view.frame_index:05d}.npz'
                    path=output/str(identity)/file
                    np.savez_compressed(path,image=view.image,mask=view.object_mask,
                                        **{'defect_'+name:mask for name,mask in view.defect_masks.items()})
                    inputs.append(dict(frame=view.frame_index,file=file,sha256=sha(path),
                                       defect_classes=list(view.defect_masks)))
            write(output/str(identity)/'selected_inputs.json',inputs)
        return row
    main._finish_track=retain_selected
    # Guard the allocation-heavy search too: other applications can consume
    # commit headroom while one fruit is being mapped. The original function
    # receives exactly the original arguments after the scheduling pause.
    import algorithm
    cost_many = algorithm._cost_many
    def guarded_cost_many(*args, **kwargs):
        memory_gate('before rotation-cost allocation')
        return cost_many(*args, **kwargs)
    algorithm._cost_many = guarded_cost_many
    last=[-1]
    def progress(**changes):
        frame=changes.get('frames_processed',0)
        if frame//20!=last[0]:
            last[0]=frame//20
            print('Actual model integration',frame,'frames',flush=True)
        write(OUTPUT/'progress.json',dict(**changes,elapsed_seconds=time.perf_counter()-started))
    metrics={}
    try:
        fruits=main.analyze_video(clip,OUTPUT,metrics,progress)
        report=dict(job_id=OUTPUT.name,created_at=datetime.now(timezone.utc).isoformat(),
                    source_name='VALIDATION: complete original video' if full_video else 'VALIDATION: original first 80 frames',
                    status='complete',metrics=metrics,fruits=fruits)
        main._write_report(OUTPUT,report)
        selected=sum(len(r.get('mapped_view_frames',[])) for r in fruits)
        checks=dict(detection_runs_on_every_frame=metrics['detection']['calls']==frames,
                    selected_views_all_segmented=metrics['segmentation']['calls']==selected,
                    segmentation_is_deferred=metrics['deferred_defect_segmentation'] is True,
                    identity_validation_active=metrics['identity_guard']['conveyor_identity_validation'] is True,
                    uncertain_identities_ungraded=all(r.get('grade') is None for r in fruits if r.get('identity_status')=='uncertain'),
                    partial_grades_explicit=all(r.get('grade_provisional') is True for r in fruits
                           if r.get('grade') and not r.get('coverage_complete')),
                    model_weights_unchanged=all(sha(path)==request['model_sha256'][name] for name,path in weights.items()),
                    exact_resource_guard=sha(BACKEND/'validation_resources.py')==request['resource_guard_sha256'],
                    exact_active_source=metrics['algorithm_sha256']==sha(BACKEND/'algorithm.py'))
        summary=dict(passed=all(checks.values()),checks=checks,frames=frames,tracker_records=len(fruits),
                     captured_views=sum(r['views'] for r in fruits),mapping_views=selected,
                     detection_calls=metrics['detection']['calls'],segmentation_calls=metrics['segmentation']['calls'],
                     seconds=time.perf_counter()-started,settings=asdict(handles['pipeline'].settings),
                     resource_wait_seconds=resource_wait_seconds[0],
                     full_original_video=full_video,
                     limitations=('Complete original video' if full_video else 'Bounded re-encoded integration clip')+
                                 ', no manual identity, pose, defect or grade ground truth. '
                                 'Full-cohort before/after metrics come only from the paired original-pixel replay.')
        write(OUTPUT/'summary.json',summary)
        print(json.dumps(summary,indent=2),flush=True)
        if not summary['passed']:
            raise AssertionError('Production model integration checks failed')
    except BaseException as error:
        write(OUTPUT/'failure.json',dict(error=repr(error),metrics=metrics,seconds=time.perf_counter()-started,
                                       resource_wait_seconds=resource_wait_seconds[0]))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--full-video',action='store_true')
    args=parser.parse_args()
    OUTPUT=args.output.resolve()
    run(args.full_video)
