"""Compare first-detection tracking on identical cached real detector outputs."""
import argparse
from datetime import datetime, timezone, timedelta
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from ultralytics.engine.results import Boxes
from ultralytics.trackers.track_tracker import TRACKTRACK
from ultralytics.utils import YAML, IterableSimpleNamespace
from ultralytics.utils.checks import check_yaml

from dfine_segmenter import DfineDetector, inference_device, make_fruit_tracker, associate_fruit_detections
from algorithm import NaartjiePipeline
import main as api


def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')


def iou(boxes, target):
    boxes = np.asarray(boxes)
    target = np.asarray(target)
    intersection = np.maximum(0, np.minimum(boxes[:, 2:], target[2:]) -
                              np.maximum(boxes[:, :2], target[:2])).prod(axis=1)
    areas = np.maximum(0, boxes[:, 2:] - boxes[:, :2]).prod(axis=1)
    return intersection / np.maximum(areas + np.maximum(0, target[2:]-target[:2]).prod() - intersection, 1e-6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--frames', type=int, default=160)
    parser.add_argument('--replay-from', type=Path)
    args = parser.parse_args()
    backend = Path(__file__).resolve().parent
    output = backend/'diagnostics/entry-tracking'/args.label
    output.mkdir(parents=True, exist_ok=False)
    video = Path('C:/Users/USER/Pictures/Camera Roll/WIN_20260818_13_29_43_Pro.mp4')
    device = inference_device()
    snapshots={name:(backend/name).read_bytes() for name in
               ('algorithm.py','dfine_segmenter.py','main.py','validate_entry_tracking.py')}
    if args.replay_from:
        with np.load(args.replay_from/'raw_detections.npz') as cache:
            raw=[cache[key].copy() for key in sorted(cache.files)[:args.frames]]
        print(f'Replaying {len(raw)} cached real detector frames.',flush=True)
    else:
        detector = DfineDetector(backend/'models/D-FINE/detection/best_stg1.pth', device)
        capture = cv2.VideoCapture(str(video));raw=[]
        for index in range(args.frames):
            ok, frame = capture.read()
            if not ok: break
            detector.track(frame)
            raw.append(detector.last_detection_rows.copy())
            if index % 40 == 0: print(f'Actual detector: frame {index}/{args.frames}', flush=True)
        capture.release()
    np.savez_compressed(output/'raw_detections.npz', **{f'frame_{i:05d}': row for i,row in enumerate(raw)})
    legacy_args=IterableSimpleNamespace(**YAML.load(check_yaml('tracktrack.yaml')))
    legacy_args.device=device
    legacy=TRACKTRACK(legacy_args);legacy.reset()
    capture=cv2.VideoCapture(str(video));fps=capture.get(cv2.CAP_PROP_FPS);baseline=[]
    for index,detections in enumerate(raw):
        ok,frame=capture.read()
        if not ok:raise RuntimeError('Replay video ended before cached detections')
        tracked=legacy.update(Boxes(detections,frame.shape[:2]),img=frame)
        baseline.append({'frame':index,'tracks':tracked[:,:7].tolist() if len(tracked) else []})
    capture.release()
    write(output/'baseline_three_detections.json', baseline)
    tracker = make_fruit_tracker(device)
    tracker.reset()
    pipeline = NaartjiePipeline(SimpleNamespace(names={0:'unused'}), defer_defect_segmentation=True)
    capture = cv2.VideoCapture(str(video))
    immediate = []
    typical_size=None
    for index, detections in enumerate(raw):
        ok, frame = capture.read()
        if not ok: raise RuntimeError('Replay video ended before cached detections')
        rows,typical_size=associate_fruit_detections(tracker,detections,frame,typical_size)
        immediate.append({'frame':index, 'tracks':rows.tolist()})
        for row in rows:
            pipeline.record_tracked_detection(frame, int(row[4]), row[:4], index)
    capture.release()
    write(output/'immediate_one_detection.json', immediate)
    # Match the same physical fruit to the existing full-run track 125 at frame 62.
    frozen = json.loads((backend/'diagnostics/pipeline-runs/original_video_symmetric_v1/tracking.json').read_text())
    reference = next(row[1:5] for frame in frozen if frame['frame']==62
                     for row in frame['tracks'] if row[0]==125)
    target = {}
    for name, rows in [('baseline',baseline),('immediate',immediate)]:
        at_frame = np.asarray(rows[62]['tracks'])
        overlaps = iou(at_frame[:,:4], reference)
        position = int(overlaps.argmax())
        if overlaps[position] < .8: raise RuntimeError(f'{name} cannot identify reference fruit at frame 62')
        identity = int(at_frame[position,4])
        history = [(record['frame'],row) for record in rows for row in record['tracks'] if int(row[4])==identity]
        target[name] = {'track_id':identity,'first_seen_frame':history[0][0],
                        'last_seen_frame':history[-1][0],'tracked_frames':len(history),
                        'reference_match_iou':float(overlaps[position]),
                        'history':[{'frame':index,'bbox_xyxy':row[:4]} for index,row in history]}
    identity = target['immediate']['track_id']
    # Exercise actual evidence saving for the entry-through-exit track. No geometry
    # or grading result is claimed by this detector-only diagnostic.
    application = output/'application_evidence';application.mkdir()
    row = api._finish_track(pipeline, identity, application)
    row.update(status='tracking_only', reason='Tracking-only diagnostic; reconstruction was not attempted.',
               mapping_was_executed=False)
    write(application/str(identity)/'result.json',row)
    for view in row['tracking_evidence']:
        view['crop'] = 'application_evidence/'+str(identity)+'/'+Path(view['crop']).name
    write(output/'tracking_evidence.json',row)
    first = target['immediate']['first_seen_frame'];last = target['immediate']['last_seen_frame']
    sample_frames = sorted(set([first,55,62,79,105,last]))
    history = {item['frame']:item['bbox_xyxy'] for item in target['immediate']['history']}
    samples={};capture=cv2.VideoCapture(str(video))
    movie=cv2.VideoWriter(str(output/'entry_to_exit.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),fps,(1920,1080))
    if not movie.isOpened():raise RuntimeError('Cannot create annotated tracking video')
    for index in range(last+1):
        ok, frame=capture.read()
        if not ok:raise RuntimeError('Video ended while saving tracking evidence')
        if index<first:continue
        if index in history:
            x1,y1,x2,y2=map(lambda x:int(round(x)),history[index])
            cv2.rectangle(frame,(x1,y1),(x2,y2),(60,255,80),3)
            label_y = min(1072,y2+26) if y1<40 else max(24,y1-7)
            cv2.putText(frame,f'Fruit {identity}',(max(0,x1),label_y),cv2.FONT_HERSHEY_SIMPLEX,.75,(60,255,80),2)
        banner_top = 1018 if index in history and history[index][3]<540 else 0
        cv2.rectangle(frame,(0,banner_top),(1200,banner_top+62),(0,0,0),-1)
        cv2.putText(frame,f'Frame {index} | Same tracked fruit from first accepted detection to last seen',
                    (18,banner_top+42),cv2.FONT_HERSHEY_SIMPLEX,.78,(255,255,255),2)
        movie.write(frame)
        if index in sample_frames:
            cv2.imwrite(str(output/f'frame_{index:05d}_tracked.png'),frame)
            samples[index]=frame
    movie.release();capture.release()
    fig,axes=plt.subplots(2,3,figsize=(12,8));fig.subplots_adjust(top=.87,bottom=.14,hspace=.28,wspace=.08)
    for panel,index in zip(axes.ravel(),sample_frames):
        image=samples[index];bbox=history.get(index)
        if bbox:
            x1,y1,x2,y2=bbox
            left=max(0,int((x1+x2)/2)-190);right=min(image.shape[1],left+380)
            top=max(0,int((y1+y2)/2)-170);bottom=min(image.shape[0],top+340)
            panel.imshow(cv2.cvtColor(image[top:bottom,left:right],cv2.COLOR_BGR2RGB))
        panel.set_title(f'Frame {index} / same ID {identity}');panel.axis('off')
    fig.suptitle('Real conveyor: tracking starts at entry and continues to last seen',fontsize=15,fontweight='bold',x=.04,ha='left')
    fig.text(.04,.035,f'Original full-run fruit 125, matched geometrically at frame 62. Three-detection confirmation: first frame {target["baseline"]["first_seen_frame"]}.\n'
             f'Immediate configuration: first frame {first}, last frame {last}. Partial edge observations are retained for tracking; no new grade is claimed.',fontsize=9)
    fig.savefig(output/'entry_tracking_comparison.png',dpi=300);fig.savefig(output/'entry_tracking_comparison.pdf');plt.close(fig)
    files={'video':video,'detection_model':backend/'models/D-FINE/detection/best_stg1.pth'}
    hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}
    result={'recorded_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
            'video':str(video),'frames_tested':len(raw),'fps':fps,'device':device,
            'input':'Actual user detector outputs cached once; both trackers receive identical boxes/scores/classes and original frames.',
            'baseline_min_track_len':3,'immediate_min_track_len':1,
            'new_track_threshold':tracker.new_track_thresh,'detection_threshold':.25,
            'cached_detection_source':str(args.replay_from) if args.replay_from else None,
            'edge_association':'Virtual full-sized extents for association only; actual detector boxes are returned and retained.',
            'edge_rebind':'Consecutive actual-box IoU >= 0.5 at a frame edge, with a 0.15 margin over other eligible lost identities.',
            'tracker_configuration':vars(tracker.args),
            'input_sha256':hashes,
            'source_sha256':{name:hashlib.sha256(payload).hexdigest() for name,payload in snapshots.items()},
            'target':target,'limitations':'This tests immediate tracking and evidence retention, not reconstruction/grade accuracy or all physical identities.'}
    write(output/'report.json',result)
    for name,payload in snapshots.items():(output/name).write_bytes(payload)
    print(json.dumps({key:value for key,value in result.items() if key!='target'},indent=2),flush=True)
    print(json.dumps({name:{k:v for k,v in info.items() if k!='history'} for name,info in target.items()},indent=2),flush=True)


if __name__=='__main__':main()
