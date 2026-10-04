"""Expose every frozen pair for fruit 98, with its actual selection diagnostics."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT/'diagnostics/algorithm-revision/debug_fruit_98_20261002'


def main():
    global OUTPUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',default='debug_fruit_98_20261002')
    parser.add_argument('--replay',default='fixed_hybrid_conveyor_20261002')
    parser.add_argument('--model-run')
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    OUTPUT=ROOT/'diagnostics/algorithm-revision'/args.label
    OUTPUT.mkdir(parents=True,exist_ok=args.refresh)
    replay=ROOT/'diagnostics/algorithm-revision'/args.replay/'98'
    donor=ROOT/'results/272fb3d439e04f3ab86065a99b686545/98'
    tracked=json.loads((donor/'result.json').read_text(encoding='utf-8'))
    manifest=json.loads((replay/'inputs/views.json').read_text(encoding='utf-8'))
    attempts=json.loads((replay/'adjacent_native/motion_attempts.json').read_text(encoding='utf-8'))
    result=json.loads((replay/'adjacent_native/result.json').read_text(encoding='utf-8'))
    replay_report=json.loads((replay.parent/'report.json').read_text(encoding='utf-8'))
    track=replay_report['tracks'][0]
    algorithm_sha256=hashlib.sha256((replay.parent/'sources/adjacent_native.py').read_bytes()).hexdigest()
    assert algorithm_sha256 == replay_report['source_sha256']['adjacent_native.py']
    variant=track['variants'][0]
    selected=variant['selected_frames']
    model_result=None
    if args.model_run:
        model_folder=ROOT/'diagnostics/algorithm-revision'/args.model_run/'98'
        model_report=json.loads((model_folder.parent/'report.json').read_text(encoding='utf-8'))
        assert model_report['algorithm_sha256'] == algorithm_sha256
        model_result=json.loads((model_folder/'result.json').read_text(encoding='utf-8'))
        (OUTPUT/'model').mkdir(exist_ok=args.refresh)
        for source in model_folder.iterdir():
            if source.is_file():shutil.copy2(source,OUTPUT/'model'/source.name)
    images={}
    for item in manifest:
        with np.load(replay/'inputs'/item['file']) as data:
            image,mask=data['image'],data['mask']
            images[item['frame']]=image.copy()
            cv2.imwrite(str(OUTPUT/f'frame_{item["frame"]}.png'),image)
            overlay=image.copy()
            contours,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(overlay,contours,-1,(48,220,95),1)
            cv2.imwrite(str(OUTPUT/f'frame_{item["frame"]}_mask.png'),overlay)
    entry=[]
    for row in tracked['tracking_evidence']:
        path=donor/Path(row['crop']).name
        shutil.copy2(path,OUTPUT/path.name)
        entry.append(dict(stage=row['stage'],frame=row['frame'],image=path.name))
    shutil.copy2(replay/'adjacent_native/surface_map.png',OUTPUT/'surface_map.png')
    for name in ('motion_attempts.json','longitude_trace.json','result.json'):
        shutil.copy2(replay/'adjacent_native'/name,OUTPUT/name)
    payload=dict(track_id=98,first=tracked['first_seen_frame'],last=tracked['last_seen_frame'],
                 tracked_frames=tracked['tracked_frames'],captured=[r['frame'] for r in manifest],
                 selected=selected,longitude_deg=variant['longitude_deg'],entry=entry,
                 attempts=attempts,algorithm_sha256=algorithm_sha256,
                 status=model_result['status'] if model_result else result['status'],
                 grade=model_result.get('grade') if model_result else None,
                 defect_pct=model_result.get('defect_pct_of_observed') if model_result else None,
                 model_evidence=model_result.get('view_evidence',[]) if model_result else [],
                 provenance='Tracking images come from the actual detector/TrackTrack full-video source863 run. '
                            f'Motion decisions replay identical archived crops/masks on source {algorithm_sha256}. '
                            'Defect overlays, when present, use the actual local segmentation checkpoint. '
                            'This example has no manually labelled motion or grade truth.')
    baseline_folder=ROOT/'diagnostics/algorithm-revision/fixed_hybrid_conveyor_20261002/98/adjacent_native'
    baseline_result=json.loads((baseline_folder/'result.json').read_text(encoding='utf-8'))
    baseline_attempts=json.loads((baseline_folder/'motion_attempts.json').read_text(encoding='utf-8'))
    payload['bound_comparison']=dict(baseline_longitude_deg=baseline_result.get('longitude_deg'),
        baseline_transition=next(row for row in baseline_attempts if row['source_frame']==85),
        current_transition=next(row for row in attempts if row['source_frame']==85))
    (OUTPUT/'walkthrough.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    html='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fruit 98: step through tracking and mapping</title><style>
body{font:17px/1.5 system-ui;background:#f4f6f2;color:#19382a;margin:0}main{max-width:1100px;margin:auto;padding:30px}
h1,h2{line-height:1.2}section{background:white;padding:22px;border:1px solid #ccd5c9;border-radius:12px;margin:20px 0}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}.image{height:250px;width:100%;object-fit:contain;background:#172a22}
button,select{font:inherit;padding:7px;margin:4px}pre{font:14px/1.5 monospace;white-space:pre-wrap;background:#edf2eb;padding:14px}
.badge{padding:5px 10px;border-radius:7px;background:#e5eadd}.failed{background:#f7e4d4}small{display:block;color:#526452}
@media(max-width:650px){.grid{grid-template-columns:1fr}main{padding:14px}}</style></head><body><main>
<h1>Follow one naartjie: fruit 98</h1><p id="summary"></p>
<section id="comparison"><h2>Current decision at frames 85–86</h2>
<p id="comparisonText"></p>
<p>This is a calculation on real crops, with no independently labelled pose or grade.
The page includes every failed transition too.</p></section>
<section><h2>1. Tracking starts at entry</h2><div class="grid" id="entry"></div>
<p>Tracking retains partial edge detections. Reconstruction waits for a usable complete silhouette.</p></section>
<section><h2>2. Inspect one captured transition</h2><p>Choose a pair or move through the original frame numbers.</p>
<button id="previous">Previous</button><select id="pairs" aria-label="Captured frame pair"></select><button id="next">Next</button>
<label><input id="mask" type="checkbox" checked> Show extracted fruit boundary</label>
<div class="grid"><div><h3 id="source"></h3><img id="sourceImage" class="image" alt="Actual source crop"></div>
<div><h3 id="target"></h3><img id="targetImage" class="image" alt="Actual target crop"></div></div>
<p><span class="badge" id="status"></span></p><p id="decision"></p><p id="matcher"></p><pre id="trace"></pre>
<small>The match residual is a rejection signal, not a measured accuracy. Green outlines show GrabCut boundaries, not defect predictions.</small></section>
<section><h2>3. Coverage determines whether a class can be assigned</h2><img src="surface_map.png" style="width:100%" alt="Actual reconstructed partial surface map">
<p id="coverage"></p><p>All views and decisions remain available here, including discarded views. Measured motion outside the chosen connected sequence is not automatically wrong; the mapper keeps the sequence with the largest valid longitude span.</p></section>
<section id="modelSection" hidden><h2>4. Inspect the actual defect predictions</h2>
<p id="modelSummary"></p><div class="grid" id="modelImages"></div>
<p>Green outlines show the extracted fruit silhouette. Red pixels show predicted defects. These are model outputs, not human labels.</p>
<a href="model/result.json">Model integration result</a></section>
<small id="provenance"></small><p><a href="walkthrough.json">Input and result metadata</a> · <a href="motion_attempts.json">Every attempted match</a> · <a href="one_fruit_steps.png">Report figure</a></p>
</main><script>const data=PAYLOAD;
const picker=document.querySelector('#pairs'),mask=document.querySelector('#mask');
document.querySelector('#summary').textContent=`Tracked from frame ${data.first} to ${data.last}: ${data.tracked_frames} observations. Captured ${data.captured.length} usable views. Mapped ${data.selected.length} views.`;
const comparison=data.bound_comparison.current_transition;
document.querySelector('#comparisonText').textContent=`Current vector: ${JSON.stringify(comparison.final_vector_deg)} degrees. Residual: ${comparison.final_error===null?'unavailable':comparison.final_error}. Observed map longitude: ${data.longitude_deg.toFixed(3)} degrees; required: 350 degrees. The residual is a rejection signal, not an accuracy measurement.`;
document.querySelector('#entry').innerHTML=data.entry.map(row=>`<div><h3>${row.stage==='entry'?'First accepted detection':'Last tracked observation'}: frame ${row.frame}</h3><img class="image" src="${row.image}" alt="Actual tracked fruit crop"></div>`).join('');
data.attempts.forEach((row,index)=>{const option=document.createElement('option');option.value=index;option.textContent=`${row.source_frame} → ${row.target_frame} (${row.status})`;picker.appendChild(option)});
const boundary=data.attempts.findIndex(row=>row.source_frame===85);if(boundary>=0)picker.value=boundary;
function render(){const row=data.attempts[Number(picker.value)],suffix=mask.checked?'_mask':'';
document.querySelector('#source').textContent=`Source frame ${row.source_frame}`;document.querySelector('#target').textContent=`Target frame ${row.target_frame}`;
document.querySelector('#sourceImage').src=`frame_${row.source_frame}${suffix}.png`;document.querySelector('#targetImage').src=`frame_${row.target_frame}${suffix}.png`;
const retained=data.selected.includes(row.source_frame)&&data.selected.includes(row.target_frame);
const status=document.querySelector('#status');status.textContent=row.status==='accepted'?'Motion measured':'Motion unavailable';status.className='badge'+(row.status==='accepted'?'':' failed');
document.querySelector('#decision').textContent=row.status==='accepted'?(retained?'Both frames belong to the retained sequence.':'This measured pair is outside the retained connected sequence.'):`This transition ends a connected sequence. ${row.reason||''}`;
const info=row.estimator_details||{},pixels=info.estimated_rolling_movement_px;
document.querySelector('#matcher').textContent=info.matching_cost_used==='green_mad'?`Noise-smoothed green comparison. Estimated rolling movement: ${Number(pixels).toFixed(3)} pixels; the current switch uses this method below one pixel.`:info.matching_cost_used==='aligned_mad'?`Projected texture-pattern comparison. Estimated rolling movement: ${Number(pixels).toFixed(3)} pixels; the current switch uses this method from one pixel upward.`:'Quarter-resolution paper texture comparison. A failed coarse match is not replaced with another estimate.';
document.querySelector('#trace').textContent=JSON.stringify({searches:row.searches,final_vector_deg:row.final_vector_deg,final_residual:row.final_error,details:row.estimator_details},null,2);
}
picker.addEventListener('change',render);mask.addEventListener('change',render);
document.querySelector('#previous').onclick=()=>{picker.value=Math.max(0,Number(picker.value)-1);render()};
document.querySelector('#next').onclick=()=>{picker.value=Math.min(data.attempts.length-1,Number(picker.value)+1);render()};
document.querySelector('#coverage').textContent=`Retained frames ${data.selected[0]}–${data.selected.at(-1)}. Observed longitude ${data.longitude_deg.toFixed(3)}°. Required longitude 350°. Result: ${data.grade||'Review'} (${data.status}).`;
if(data.grade){document.querySelector('#modelSection').hidden=false;
document.querySelector('#modelSummary').textContent=`Predicted defect area: ${data.defect_pct.toFixed(3)}% of observed surface. Current rule: below 10% → Class 1. These rules have not been validated against conveyor grade labels.`;
document.querySelector('#modelImages').innerHTML=data.model_evidence.map(row=>{const path=(row.overlay||'').split('/').at(-1);return path?`<div><img class="image" src="model/${path}" alt="Actual predicted-defect overlay"><small>Frame ${row.frame}</small></div>`:''}).join('');}
document.querySelector('#provenance').textContent=data.provenance;render();</script></body></html>'''
    html=html.replace('PAYLOAD',json.dumps(payload).replace('</','<\\/'))
    (OUTPUT/'index.html').write_text(html,encoding='utf-8')
    fig,axes=plt.subplots(1,5,figsize=(15,4),layout='constrained')
    panels=[(cv2.imread(str(OUTPUT/entry[0]['image'])),'Entry: frame 51\nTracked; partial fruit'),
            (images[62],'Frame 62\nComplete captured view'),
            (images[66],'Frame 66\nStart of retained sequence'),
            (images[selected[-1]],f'Frame {selected[-1]}\nEnd of retained sequence'),
            (cv2.imread(str(OUTPUT/entry[-1]['image'])),'Last seen: frame 138\nStill the same tracked ID')]
    for ax,(image,title) in zip(axes,panels):
        ax.imshow(cv2.cvtColor(image,cv2.COLOR_BGR2RGB));ax.set_title(title,fontsize=10);ax.axis('off')
    fig.suptitle('Actual fruit 98: tracking continuity is different from usable reconstruction coverage\n'
                 f'{tracked["tracked_frames"]} tracked observations; {len(manifest)} captured views; '
                 f'{len(selected)} mapped views; {variant["longitude_deg"]:.3f}° observed longitude → '
                 f'{payload["grade"] or "Review"}',fontsize=12)
    fig.savefig(OUTPUT/'one_fruit_steps.png',dpi=300);fig.savefig(OUTPUT/'one_fruit_steps.pdf');plt.close(fig)
    (OUTPUT/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (OUTPUT/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(OUTPUT).as_posix()
        for p in sorted(OUTPUT.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt')+'\n',encoding='utf-8')
    print(OUTPUT/'index.html')


if __name__=='__main__':
    main()
