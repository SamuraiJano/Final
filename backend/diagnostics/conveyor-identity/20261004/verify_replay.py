"""Independent replay/bookkeeping checks; no physical identity accuracy claim."""
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

folder=Path(__file__).resolve().parent
backend=folder.parents[2]
sys.path.insert(0,str(backend))
from conveyor_identity import ConveyorIdentityManager,ConveyorIdentitySettings

run=folder/'representative'
report=json.loads((run/'report.json').read_text())
raw=json.loads((run/'tracking.json').read_text())
decisions=json.loads((run/'guard_decisions.json').read_text())
captures=json.loads((run/'capture_tracking.json').read_text())
settings={key:value for key,value in report['identity_guard_configuration'].items()
          if key not in {'version','component','effective_lost_track_buffer_frames'}}
manager=ConveyorIdentityManager(replace(ConveyorIdentitySettings(**settings),debug_identity_overlay=False,debug_identity_csv=False),
                              report['identity_guard_configuration']['effective_lost_track_buffer_frames'])
manager.set_frame_rate(report['fps'])
expected=report['outputs_sha256']
assert all(hashlib.sha256((run/name).read_bytes()).hexdigest()==digest for name,digest in expected.items())
assert len(raw)==len(decisions)==len(captures)==795
started=time.perf_counter()
identical=0
maximum_numeric_difference=0.
for record,audit,capture in zip(raw,decisions,captures):
    frame=record['frame']
    assert frame==audit['frame']==capture['frame']
    rows=np.asarray(record['tracks']).reshape(-1,7)
    supplied=audit['decisions'][0]['timestamp'] if audit['decisions'] else frame/report['fps']
    # The run has observations in every frame and every timestamp is decoded PTS.
    assert audit['decisions']
    result=manager.update(rows[:,:4],rows[:,4].astype(int),frame,(report['height'],report['width']),supplied)
    for actual, original in zip(result,audit['decisions']):
        assert actual.keys()==original.keys()
        for key,value in actual.items():
            if isinstance(value,float):
                maximum_numeric_difference=max(maximum_numeric_difference,abs(value-original[key]))
                assert abs(value-original[key])<1e-9, f'Changed numeric {key} at {frame}'
            else:
                assert value==original[key], f'Changed {key} at {frame}'
    assert len({item['fruit_id'] for item in result})==len(result)
    guarded=np.asarray(capture['tracks']).reshape(-1,7)
    np.testing.assert_array_equal(rows[:,:4],guarded[:,:4])
    np.testing.assert_array_equal(rows[:,5:],guarded[:,5:])
    assert guarded[:,4].astype(int).tolist()==[item['fruit_id'] for item in result]
    identical+=len(result)
elapsed=time.perf_counter()-started
events=[item for record in decisions for item in record['decisions'] if item['identity_corrected']]
metadata=json.loads((run/'guard_metadata.json').read_text())
summary={'frames':len(raw),'identical_replayed_observations':identical,'one_to_one_every_frame':True,
         'current_manager_sha256':hashlib.sha256((backend/'conveyor_identity.py').read_bytes()).hexdigest(),
         'maximum_prediction_numeric_difference':maximum_numeric_difference,
         'actual_boxes_scores_classes_unchanged':True,'manager_replay_seconds':elapsed,
         'mean_manager_seconds_per_frame':elapsed/len(raw),'raw_tracker_ids':report['raw_tracker_ids'],
         'stable_fruit_ids':report['capture_ids'],'motion_supported_raw_id_corrections':len(events),
         'gap_recoveries_same_raw_id':sum(item['reason']=='recovered_after_gap' for record in decisions for item in record['decisions']),
         'uncertain_stable_segments':sum(item['identity_status']=='uncertain' for item in metadata.values()),
         'timestamp_sources':dict(Counter(item['timestamp_source'] for record in decisions for item in record['decisions'])),
         'accuracy_claim':'none; physical-fruit labels are required; all four raw-ID corrections concern clipped right-edge views'}
(folder/'replay_verification_batched.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2),flush=True)

# A sparse diagnostic mosaic of the actual raw-ID reconnections. It is not
# an annotation: the right-hand slivers contain very little visible fruit.
video=cv2.VideoCapture(report['video'])
try:
    for event in events:
        tiles=[]
        for frame in range(event['frame']-1,event['frame']+2):
            video.set(cv2.CAP_PROP_POS_FRAMES,frame)
            ok,image=video.read()
            assert ok
            own=next((item for item in decisions[frame]['decisions'] if item['fruit_id']==event['fruit_id']),None)
            centre_y=event['cy'] if own is None else own['cy']
            top=max(0,min(image.shape[0]-240,int(centre_y)-120))
            crop=image[top:top+240,image.shape[1]-320:].copy()
            if own is not None:
                row=next(row for row in raw[frame]['tracks'] if int(row[4])==own['tracker_id'])
                x1,y1,x2,y2=np.rint(row[:4]).astype(int)
                cv2.rectangle(crop,(x1-image.shape[1]+320,y1-top),(x2-image.shape[1]+320,y2-top),(60,255,100),2)
            cv2.rectangle(crop,(0,0),(320,45),(0,0,0),-1)
            label=f'Frame {frame} | '+(f'T:{own["tracker_id"]} F:{own["fruit_id"]}' if own else 'not observed')
            cv2.putText(crop,label,(8,28),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
            tiles.append(crop)
        cv2.imwrite(str(folder/f'correction_{event["frame"]:05d}.jpg'),np.concatenate(tiles,axis=1))
finally:
    video.release()
