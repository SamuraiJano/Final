"""Compare the frozen candidate's public-author benchmark to its saved profile."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
BENCH=ROOT/'diagnostics/authors-benchmark/runs'
OLD=BENCH/'pixel_switch_trace_author_profile_20261002'
NEW=BENCH/'fruit340_native_3d_retry_author_profile_20261004'
old=json.loads((OLD/'report.json').read_text())
oldtracks={(t['group'],t['object']):t for t in old['tracks']}
newreport=json.loads((NEW/'report.json').read_text()) if (NEW/'report.json').exists() else None
newtracks=newreport['tracks'] if newreport else [json.loads(p.read_text()) for p in sorted(NEW.glob('*/*/result.json'))]
report={'scope':'Same public-author input sequences/profile. Source is frozen d2a490; compare conditional and all-label denominators.', 'complete':newreport is not None,'completed_tracks':len(newtracks),'historical_tracks':len(oldtracks),'changed_pairs':[],'changed_maps':[],'common_ok_pair_exact_rotation':0,'common_ok_pair_changed_rotation':0}
for track in newtracks:
    previous=oldtracks[(track['group'],track['object'])]
    beforepairs={p['pair']:p for p in previous['pairs']}
    for pair in track['pairs']:
        before=beforepairs[pair['pair']]
        key={'group':track['group'],'object':track['object'],'pair':pair['pair']}
        if before['status']=='ok' and pair['status']=='ok':
            same=(before['rotation_vector_deg']==pair['rotation_vector_deg'] and before['cost']==pair['cost'])
            report['common_ok_pair_exact_rotation' if same else 'common_ok_pair_changed_rotation']+=1
            if not same:
                report['changed_pairs'].append({**key,'before':before,'after':pair})
        elif before['status']!=pair['status']:
            report['changed_pairs'].append({**key,'before':before,'after':pair})
    beforemap,aftermap=previous['map'],track['map']
    if (beforemap.get('view_frames')!=aftermap.get('view_frames') or beforemap['status']!=aftermap['status'] or beforemap.get('observed_surface_pct')!=aftermap.get('observed_surface_pct')):
        report['changed_maps'].append({'group':track['group'],'object':track['object'],'before':{k:v for k,v in beforemap.items() if k not in ('selection_diagnostics',)},'after':{k:v for k,v in aftermap.items() if k not in ('selection_diagnostics',)}})
if newreport:
    report['settings_changed']={k:{'historical':v,'new':newreport['settings'].get(k)} for k,v in old['settings'].items() if newreport['settings'].get(k)!=v}
    report['settings_added']={k:v for k,v in newreport['settings'].items() if k not in old['settings']}
    report['mask_threshold_equal']=old['mask_threshold']==newreport['mask_threshold']
    report['historical_summary']=old['summary']
    report['new_summary']=newreport['summary']
    report['new_source_sha256']=newreport['algorithm_sha256']
    report['snapshot_sha256']=hashlib.sha256((NEW/'algorithm_snapshot.py').read_bytes()).hexdigest()
    previousrows={(r['group'],r['line']):r for r in old['correspondences']}
    changed=[]
    same=0
    common_before=[]
    common_after=[]
    rescued=[]
    for row in newreport['correspondences']:
        before=previousrows[(row['group'],row['line'])]
        if before['status']=='ok' and row['status']=='ok':
            common_before.append(before['error_px'])
            common_after.append(row['error_px'])
            if before['prediction']==row['prediction'] and before['error_px']==row['error_px']:
                same+=1
            else:
                changed.append({'before':before,'after':row})
        elif before['status']!=row['status']:
            changed.append({'before':before,'after':row})
            if row['status']=='ok':
                rescued.append(row)
    report.update(common_ok_labels_unchanged=same,changed_labels=changed,rescued_labels=rescued,common_ok_label_count=len(common_before),common_before_mean_px=float(np.mean(common_before)),common_after_mean_px=float(np.mean(common_after)))
target=OUT/('author_profile_comparison.json' if newreport else 'author_profile_progress.json')
target.write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('changed_pairs','changed_maps','historical_summary','new_summary','changed_labels','rescued_labels')},indent=2))
print('changed pairs',[(r['group'],r['object'],r['pair'],r['before']['status'],r['after']['status']) for r in report['changed_pairs']])
if newreport:
    print('all-label summaries',old['summary']['all'],newreport['summary']['all'])
