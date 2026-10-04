"""Create report-ready evidence from a completed real-video tracking diagnostic."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np


def encode_browser_videos(directory):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg is required to encode browser-compatible evidence videos')
    encoding=[]
    for filename in ('entry_to_exit.mp4','all_fruit_tracking.mp4'):
        target=directory/filename
        source=target.with_suffix('.mpeg4.mp4')
        target.rename(source)
        command=[ffmpeg,'-hide_banner','-loglevel','error','-i',str(source),'-an',
                 '-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',
                 '-movflags','+faststart',str(target)]
        subprocess.run(command,check=True)
        probe=Path(ffmpeg).with_name('ffprobe.exe')
        verification=subprocess.run([str(probe),'-v','error','-count_frames','-select_streams','v:0',
                         '-show_entries','stream=codec_name,width,height,nb_read_frames,r_frame_rate',
                         '-of','json',str(target)],check=True,capture_output=True,text=True)
        encoding.append({'file':filename,'command':command,'verification':json.loads(verification.stdout)})
    (directory/'VIDEO_ENCODING.json').write_text(json.dumps(encoding,indent=2),encoding='utf-8')


def build(directory):
    backend = Path(__file__).resolve().parent
    report = json.loads((directory/'report.json').read_text())
    checks = json.loads((directory/'all_frame_tracking_checks.json').read_text())
    evidence = json.loads((directory/'tracking_evidence.json').read_text())
    before, after = report['target']['baseline'], report['target']['immediate']
    baseline = checks['baseline_three_detections.json']
    revised = checks['immediate_one_detection.json']
    consistency = checks['cross_replay_identity_consistency']
    video = Path(report['video'])
    sequence = json.loads((directory/'immediate_one_detection.json').read_text())
    capture = cv2.VideoCapture(str(video))
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(directory/'all_fruit_tracking.mp4'), cv2.VideoWriter_fourcc(*'mp4v'),
                             report['fps'], (width, height))
    if not writer.isOpened():
        raise RuntimeError('Cannot write all-fruit evidence video')
    for item in sequence:
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError('Source video ended before retained tracking sequence')
        for x1, y1, x2, y2, identity, confidence, _category in item['tracks']:
            x1, y1, x2, y2 = map(lambda value:int(round(value)), (x1,y1,x2,y2))
            color = (70,255,100) if int(identity)==after['track_id'] else (255,210,40)
            cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
            cv2.putText(frame,f'{int(identity)} / {confidence:.2f}',
                        (max(0,x1),min(height-8,y2+20) if y1<30 else max(22,y1-5)),
                        cv2.FONT_HERSHEY_SIMPLEX,.5,color,1)
        cv2.putText(frame,f'Frame {item["frame"]} | Detection + tracking only',
                    (18,48),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2)
        writer.write(frame)
    writer.release();capture.release()
    encode_browser_videos(directory)
    sources = directory/'software_checks'
    shutil.copytree(backend/'diagnostics/software-checks/tracking_entry_20261002', sources)
    for name in ('test_tracking.py','test_entry_tracking.py','audit_entry_tracking.py',
                 'build_entry_tracking_evidence.py'):
        shutil.copy2(backend/name,directory/name)
    shutil.copy2(backend.parent/'src/App.jsx',directory/'App.jsx')
    shutil.copy2(backend.parent/'src/App.css',directory/'App.css')
    package_license=next((backend/'venv/Lib/site-packages').glob('ultralytics-*.dist-info/licenses/LICENSE'),None)
    if package_license is not None and package_license.is_file():
        shutil.copy2(package_license,directory/'ultralytics_LICENSE')
    raw = np.load(directory/'raw_detections.npz')
    timeline=[]
    for index in range(48,56):
        candidates = [row for row in raw[f'frame_{index:05d}']
                      if row[1]<=2 and 250 < (row[0]+row[2])/2 < 430 and row[3]<80]
        row=max(candidates,key=lambda row:row[4]) if candidates else None
        timeline.append({'frame':index,'strongest_target_entry_detection_score':float(row[4]) if row is not None else None,
                         'bbox_xyxy':row[:4].tolist() if row is not None else None})
    raw.close()
    (directory/'entry_detection_timeline.json').write_text(json.dumps(timeline,indent=2),encoding='utf-8')
    software=json.loads((sources/'summary.json').read_text())
    tested_hashes={Path(name).name:value for name,value in software['source_sha256'].items()}
    for name in ('algorithm.py','dfine_segmenter.py','main.py'):
        assert report['source_sha256'][name]==tested_hashes[name], f'{name} test/replay source mismatch'
    frozen=(backend/'diagnostics/authors-benchmark/evidence_20261002/algorithm.py.snapshot').read_bytes()
    current=(directory/'algorithm.py').read_bytes()
    math_unchanged=frozen.split(b'class NaartjiePipeline:')[0]==current.split(b'class NaartjiePipeline:')[0]
    assert math_unchanged
    trials=[]
    decisions={'first_detection_v1':'Rejected: first target ID still starts at 53.',
               'first_detection_v2':'Rejected: weak interior initialization and duplicate predictions.',
               'first_detection_v3':'Rejected: excess weak interior tracks.',
               'first_detection_v4':'Earlier candidate: entry passes; size-transition regression fails.',
               'first_detection_v5':'Rejected: smaller-fruit transition regression still fails.',
               'first_detection_v6':'Rejected: artificial control passes but real tracking fragments more.',
               'first_detection_v7':'Pre-final edge rebind candidate; final ambiguity guard follows.'}
    for label,decision in decisions.items():
        folder=directory.parent/label
        trial=json.loads((folder/'report.json').read_text())
        target=trial['target']['immediate']
        row={'label':label,'first_seen_frame':target['first_seen_frame'],
             'last_seen_frame':target['last_seen_frame'],'decision':decision}
        audit_path=folder/'all_frame_tracking_checks.json'
        if audit_path.is_file():
            row['all_frame_checks']=json.loads(audit_path.read_text())
        trials.append(row)
    (directory/'trial_decisions.json').write_text(json.dumps(trials,indent=2),encoding='utf-8')
    timeline_table='\n'.join(f'| {row["frame"]} | {row["strongest_target_entry_detection_score"]:.3f} |'
                             if row['strongest_target_entry_detection_score'] is not None else
                             f'| {row["frame"]} | No accepted target detection in the inspected entry region |' for row in timeline)
    document=f'''# Entry-to-exit tracking validation — 2 October 2026

The detector must start a fruit identity on its first accepted visible entry detection.
That identity must continue while the fruit moves through the frame, including partial
entry and exit views. The revised tracker was tested on all {report['frames_tested']} frames
of the original conveyor video, using the user's actual D-FINE detection checkpoint.

## Direct before/after evidence

| Same physical fruit | First published frame (zero-based) | Last seen | Observations |
| --- | ---: | ---: | ---: |
| Original configuration, ID {before['track_id']} | {before['first_seen_frame']} | {before['last_seen_frame']} | {before['tracked_frames']} |
| Revised configuration, ID {after['track_id']} | {after['first_seen_frame']} | {after['last_seen_frame']} | {after['tracked_frames']} |

The reference fruit was matched to the earlier full application's fruit 125 at
frame 62 by box IoU ({after['reference_match_iou']:.6f}) and inspected in the saved
contact sheet. ID numbers are local to each run; a different number between runs
does not imply an identity switch within a run. The revised ID has an observation
on every frame from {after['first_seen_frame']} through {after['last_seen_frame']}.

![Entry, movement and last-seen observations](entry_tracking_comparison.png)

- [Selected-fruit annotated video](entry_to_exit.mp4)
- [All-fruit annotated video, complete original clip](all_fruit_tracking.mp4)
- [300-dpi contact sheet](entry_tracking_comparison.png) and [PDF figure](entry_tracking_comparison.pdf)
- Six full-resolution frame PNGs and original first/last crops in `application_evidence/`.

## What happened, step by step

1. Decode each original video frame; call the trained detector on every frame.
2. Keep the actual predicted boxes, confidence scores and classes at confidence ≥ 0.25.
3. Suppress overlapping same-class duplicate predictions at box IoU > 0.7.
4. Publish accepted new edge detections immediately (`min_track_len=1`), including
   low-confidence partial entries. The stronger 0.7 initialization threshold remains
   for previously unseen interior detections.
5. Use an estimated full-size box for association of clipped observations. A growing
   visible arc otherwise has little overlap with its own earlier detection. The prior
   comes from complete interior fruit sizes, or a circular-cap bootstrap at startup.
6. At an edge transition, recover an existing lost identity only when consecutive
   actual detected boxes have IoU ≥ 0.5 and the best candidate exceeds other eligible
   identities by ≥ 0.15. This addresses a smaller fruit's change from the virtual
   edge box to its complete detected box. It uses the official track's reactivation.
7. Return and retain the actual detector coordinates. Virtual extents never become
   observed pixels, inferred silhouettes or reconstruction inputs.
8. Record first/last seen, frame-by-frame boxes, and first/last source crops BEFORE
   any capture stride, view budget, or silhouette suitability check.
9. Complete-outline views from that same identity may enter reconstruction. Partial
   entry/exit detections still preserve tracking and evidence when unsuitable for
   the paper's spheroid fitting.
10. Save tracking evidence even if reconstruction fails. Future application reports
    expose first/last tracked frame, observed frame count and entry/last-seen crops.
11. Evaluate tracking separately before making any new surface-map or grade claim.

The target entry predictions were inspected in the top-edge region:

| Frame | Actual detector confidence |
| ---: | --- |
{timeline_table}

This proves tracking from the first accepted detection in this example; it does
not prove detection from the first visible pixel for every fruit. A tracker cannot
assign a measured box before the model produces an accepted detection.

## Full-clip checks

Both configurations received the same cached actual boxes/scores/classes and the
same original image frames. The final diagnostic recomputed detection on all
{report['frames_tested']} frames; earlier exploratory trials reused a 160-frame cache.

| Tracking consistency indicator | Original | Revised |
| --- | ---: | ---: |
| Published track IDs | {baseline['track_ids']} | {revised['track_ids']} |
| IDs with at most two observations | {baseline['ids_with_at_most_two_observations']} | {revised['ids_with_at_most_two_observations']} |
| Median observations per ID | {baseline['median_observed_frames_per_id']} | {revised['median_observed_frames_per_id']} |
| Concurrent output box pairs with IoU > 0.7 | {baseline['coincident_box_pairs_iou_above_0_7']} | {revised['coincident_box_pairs_iou_above_0_7']} |

Cross-replay matching considered {consistency['eligible_baseline_ids']} baseline IDs
with at least 10 matched frames. {consistency['ids_with_multiple_substantial_matches']}
matched multiple revised IDs substantially; details and thresholds are retained in
`all_frame_tracking_checks.json`. The old tracker is not ground truth. These
numbers can flag fragmentation or disagreement, but do not measure true identity
accuracy, false detections, or unique physical fruit counts. Earlier starts and
weak edge candidates can increase the revised ID count. Full-clip identity
reliability remains unverified without manually labelled tracks.

## Software checks and source provenance

All 30 Python tests passed, including immediate publication, thin low-confidence
entries, mixed fruit size at entry, nearby separate fruit, strong replacement
reactivation, duplicate suppression, and evidence retention despite mapping failure.
The frontend production build and ESLint passed. Exact commands, stdout,
timestamps and source SHA-256 hashes are in `software_checks/`.

The reconstruction/geometry code preceding `class NaartjiePipeline` is byte-identical
to the earlier validated algorithm snapshot. Changes inside the pipeline record
tracking observations and evidence; the tracker adapter and inspection UI changed.
The earlier full grading run and author-data results remain historical evidence,
not tests of the new tracker. No new reconstruction or commercial grading accuracy
result is claimed by this tracking-only diagnostic. The supplied segmentation model
and its weights were not changed or tested in this follow-up.

Original input: `{video}`

Video SHA-256: `{report['input_sha256']['video']}`

Detection checkpoint SHA-256: `{report['input_sha256']['detection_model']}`

The final replay's frozen source/settings/hashes are in `report.json` and the Python
snapshots alongside it. `trial_decisions.json` retains the successful and rejected
development decisions; all exploratory runs remain in sibling directories.

## Reproduce

From the project root in PowerShell, choose new labels each time:

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_entry_tracking.py --label new_tracking_run --frames 515
./backend/venv/Scripts/python.exe -B backend/audit_entry_tracking.py backend/diagnostics/entry-tracking/new_tracking_run
```

To compare tracking again without rerunning the neural network, add
`--replay-from backend/diagnostics/entry-tracking/{directory.name}` to the first
command. Reconstruction and defect grading require separate full-pipeline tests.

Recorded diagnostic time: {report['recorded_at']}.
'''
    (directory/'TRACKING_FOLLOWUP.md').write_text(document,encoding='utf-8')
    crops=''.join(f'<figure><img src="{html.escape(item["crop"])}" alt="Original {item["stage"]} crop">'
                  f'<figcaption>{html.escape(item["stage"])}: frame {item["frame"]}</figcaption></figure>'
                  for item in evidence['tracking_evidence'])
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Naartjie entry-to-exit tracking evidence</title><style>
body{{font:17px/1.6 system-ui,sans-serif;background:#f5f6f3;color:#14231b;margin:0}}main{{max-width:1100px;margin:auto;padding:38px 24px}}
h1{{font-size:38px;line-height:1.2}}h2{{margin-top:40px}}p{{max-width:900px}}a{{color:#176847}}video,.sheet{{width:100%;background:#15221a;border-radius:8px}}
.crops{{display:flex;gap:30px;flex-wrap:wrap}}figure{{margin:0;min-width:200px}}figure img{{max-width:400px;image-rendering:pixelated}}
table{{border-collapse:collapse}}td,th{{text-align:left;padding:12px 24px 12px 0;border-bottom:1px solid #ccd3ce}}
</style><main><p>Actual model outputs · Original conveyor footage · Tracking-only validation</p>
<h1>Follow the naartjie from its first detection</h1>
<p>The revised ID <strong>{after['track_id']}</strong> starts at frame <strong>{after['first_seen_frame']}</strong>
and continues through frame <strong>{after['last_seen_frame']}</strong>: {after['tracked_frames']} consecutive observations.
The earlier configuration first published this fruit at frame {before['first_seen_frame']}.</p>
<p><a href="TRACKING_FOLLOWUP.md">Testing report and limitations</a> · <a href="entry_tracking_comparison.pdf">Report-ready PDF figure</a>
 · <a href="report.json">Run settings and source hashes</a> · <a href="all_frame_tracking_checks.json">Full-clip checks</a></p>
<h2>One fruit: entry through last seen</h2><video controls preload="metadata" src="entry_to_exit.mp4"></video>
<h2>Six observed frames, same identity</h2><a href="entry_tracking_comparison.png"><img class="sheet" src="entry_tracking_comparison.png" alt="Six frames following the same naartjie"></a>
<h2>Complete clip: all published IDs</h2><video controls preload="metadata" src="all_fruit_tracking.mp4"></video>
<p>{report['frames_tested']} original frames checked. ID numbers are local to each run.
Overlapping duplicates and consistency against the old tracker were checked; manually labelled physical identities are still needed to measure accuracy.</p>
<h2>Original source crops</h2><div class="crops">{crops}</div>
<p>Partial observations preserve tracking. Reconstruction requires usable silhouettes from that identity.
These videos do not claim new surface-map or grade accuracy.</p></main></html>'''
    (directory/'index.html').write_text(page,encoding='utf-8')
    manifest={'built_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'geometry_code_unchanged':math_unchanged,'test_and_replay_source_hashes_match':True,
              'frames_tested':report['frames_tested'],'selected_id':after['track_id']}
    (directory/'evidence_build.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    build(args.directory)
