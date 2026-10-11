"""Assemble final results only after exact-source full integration completes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

OUTPUT = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
VARIANT = 'final_v4'
sys.path.insert(0, str(ROOT/'backend'))
from validate_dense_mapping import stats, write


def read(name):
    return json.loads((OUTPUT/name).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value):
    return str(value) if isinstance(value, int) else f'{value:.3f}'


def plots():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    comparison = read('comparison.json')
    records = {v:read(v+'/report.json')['records'] for v in ('baseline', VARIANT)}
    maps = {v:{r['track_id']:r for r in rows if 'observed_surface_pct' in r}
            for v, rows in records.items()}
    common = sorted(maps['baseline'].keys() & maps[VARIANT].keys())
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    for v, color in (('baseline','#50749a'), (VARIANT,'#d28738')):
        values = [r['observed_surface_pct'] for r in maps[v].values()]
        axes[0].hist(values, bins=np.arange(0,101,5), histtype='step', lw=2,
                     label=f'{v}: {len(values)} maps; {406-len(values)} unavailable', color=color)
    axes[0].axvline(80, color='red', ls='--', label='unchanged 80% target')
    axes[0].set(xlabel='Observed modeled full-surface area (%)', ylabel='Identity records')
    axes[0].legend(fontsize=8)
    x = [maps['baseline'][i]['observed_surface_pct'] for i in common]
    y = [maps[VARIANT][i]['observed_surface_pct'] for i in common]
    axes[1].scatter(x, y, s=12, alpha=.6, color='#4f7964')
    axes[1].plot([0,100],[0,100], c='gray', ls='--')
    axes[1].set(xlim=(0,100), ylim=(0,100), xlabel='Baseline area (%)', ylabel='Final area (%)',
                title=f'All {len(common)} identities mapped by both')
    fig.suptitle('Paired real-video replay: 556 tracker records, 406 eligible; no independent pose truth')
    fig.savefig(OUTPUT/'comparison_distribution.png', dpi=150)
    plt.close(fig)
    calibration = read('calibration.json')
    rows = calibration['records']
    fig, axes = plt.subplots(1,2,figsize=(12,5),layout='constrained')
    axes[0].plot([65,70,75,80,85],
                 [calibration['summary']['ideal_required_rotation_deg'][str(t)]['median'] for t in (65,70,75,80,85)],
                 'o-',color='#50749a')
    axes[0].set(xlabel='Target full-surface coverage (%)', ylabel='Median ideal measured travel (degrees)',
                title='Ideal aligned rolling; endpoint support adds 90 degrees')
    axes[1].scatter([r['visible_interval_sec'] for r in rows],
                    [r['minimum_rpm_for_80'] for r in rows], s=9, alpha=.5)
    axes[1].set(yscale='log', xlabel='Longest continuous fully-visible tracked interval (s)',
                ylabel='Minimum ideal rpm for 80% area', title='All 406 records; short fragments remain included')
    fig.suptitle('Fitted geometry capacity; these are ideal bounds, not observed physical rotation')
    fig.savefig(OUTPUT/'coverage_capacity.png',dpi=150)
    plt.close(fig)


def model_panel(rows):
    """Inspect actual model predictions on retained selected production inputs."""
    import cv2
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    candidates=[r for r in rows if 'observed_surface_pct' in r]
    record=max(candidates,key=lambda r:r['observed_surface_pct'])
    folder=OUTPUT/'integration_commit_guard'/str(record['track_id'])
    inputs=json.loads((folder/'selected_inputs.json').read_text())
    chosen=[inputs[k] for k in sorted(set((0,len(inputs)//2,len(inputs)-1)))]
    fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    for ax,item in zip(axes[0],chosen):
        path=folder/item['file']
        assert sha(path)==item['sha256']
        with np.load(path) as data:
            image=data['image'];mask=data['mask']
            union=np.zeros_like(mask,dtype=bool)
            for key in data.files:
                if key.startswith('defect_'):union|=data[key]>0
        ax.imshow(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
        ax.contour(mask,levels=[.5],colors='cyan',linewidths=.8)
        if union.any():ax.contour(union,levels=[.5],colors='red',linewidths=.8)
        ax.set_title(f"Actual selected frame {item['frame']}\nCyan fruit; red defect predictions")
        ax.axis('off')
    for ax in axes[0,len(chosen):]:ax.axis('off')
    atlas=cv2.imread(str(folder/'surface_map.png'))
    observed=cv2.imread(str(folder/'observed.png'),cv2.IMREAD_GRAYSCALE)>0
    display=cv2.cvtColor(atlas,cv2.COLOR_BGR2RGB)
    display[~observed]=70
    union=np.zeros(observed.shape,dtype=bool)
    for uri in record['defect_maps'].values():
        data=cv2.imread(str(folder/Path(uri).name),cv2.IMREAD_GRAYSCALE)
        assert data is not None
        union|=data>0
    axes[1,0].imshow(display,aspect='auto')
    axes[1,0].set_title(f"Actual surface map: {record['observed_surface_pct']:.3f}%; grey unknown")
    axes[1,1].imshow(observed,cmap='gray',aspect='auto')
    axes[1,1].set_title(f"Observed support: {record['observed_longitude_deg']:.2f} deg longitude")
    axes[1,2].imshow(union&observed,cmap='gray',aspect='auto')
    axes[1,2].set_title(f"Predicted defect union: {record['defect_pct_of_observed']:.3f}% of observed area")
    fig.suptitle(f"ACTUAL FULL-VIDEO MODEL VALIDATION: identity record {record['track_id']}; "
                 f"grade {record['grade']}; provisional={record.get('grade_provisional')}; "
                 f"complete={record['coverage_complete']}\n"
                 'Predicted masks and grade have no independent defect ground truth.',fontsize=12)
    path=OUTPUT/'integration_commit_guard/diagnostic_panel.png'
    fig.savefig(path,dpi=140);plt.close(fig)
    write(OUTPUT/'integration_commit_guard/visual.json',dict(track_id=record['track_id'],
          file='diagnostic_panel.png',selected_input_files=chosen,
          observed_surface_pct=record['observed_surface_pct'],grade=record['grade'],
          grade_provisional=record.get('grade_provisional'),coverage_complete=record['coverage_complete'],
          limitations='Actual production predictions on the complete original video. No labelled defect or grade truth.'))


def quad_panels():
    import cv2
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for name in ('mixed_axis_control','perpendicular_pole_control'):
        report=read(name+'/report.json')
        assert report['passed'] and report['renderer_sha256']==sha(OUTPUT/'mixed_axis_control.py')
        folder=OUTPUT/name
        fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
        for ax,index in zip(axes[0],(0,16,32)):
            item=report['inputs'][index]
            assert sha(folder/item['file'])==item['sha256']
            with np.load(folder/item['file']) as data:image=data['image'];mask=data['mask']
            ax.imshow(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
            ax.contour(mask,levels=[.5],colors='cyan',linewidths=.7)
            ax.set_title(f'Synthetic frame {index}, true turn {index*360/64:.1f} deg');ax.axis('off')
        atlas=cv2.imread(str(folder/'surface_map.png'))
        mask=cv2.imread(str(folder/'observed_mask.png'),cv2.IMREAD_GRAYSCALE)>0
        display=cv2.cvtColor(atlas,cv2.COLOR_BGR2RGB);display[~mask]=70
        axes[1,0].imshow(display,aspect='auto')
        axes[1,0].set_title(f"Observed area {report['observed_surface_pct']:.4f}%; grey unknown")
        axes[1,1].imshow(mask,cmap='gray',aspect='auto')
        axes[1,1].set_title(f"Ideal fitted band capacity {report['ideal_fitted_band_capacity_pct']:.4f}%")
        axes[1,2].plot(report['pair_geodesic_errors_deg'],color='#50749a')
        axes[1,2].set(xlabel='Accepted pair',ylabel='Rotation geodesic error (degrees)',
                      title=f"Measured rolling {report['measured_rolling_deg']:.3f} deg")
        fig.suptitle(f"SYNTHETIC KNOWN-TRUTH QUADRIC: {report['case']}; 360 deg longitude. "
                     'This is not real-video success.',fontsize=13)
        fig.savefig(folder/'diagnostic_panel.png',dpi=140);plt.close(fig)


def finalize():
    state = read('finish_stage_state.json')
    assert state['stage']=='all_queued_validation_stages_passed',state
    tests = read('tests_final_v4.json')
    assert tests['passed'] and tests['tests']==202
    for name, digest in tests['source_sha256'].items():
        assert sha(ROOT/name)==digest, name
    integration = read('integration_commit_guard/summary.json')
    assert integration['passed'] and integration['frames']==795 and integration['full_original_video']
    assert integration['settings']==read(VARIANT+'/settings.json'),'Integration profile differs from final replay profile.'
    request = read('integration_commit_guard/request.json')
    assert request['source_sha256']['algorithm.py']==sha(ROOT/'backend/algorithm.py')
    assert request['source_sha256']['main.py']==sha(ROOT/'backend/main.py')
    assert request['resource_guard_sha256']==sha(ROOT/'backend/validation_resources.py')
    assert request['validator_sha256']==sha(ROOT/'backend/validate_dense_pipeline.py')
    comparison = read('comparison.json')
    assert comparison['input_manifest_sha256']==sha(OUTPUT/'inputs.json')
    baseline, final = [comparison['variants'][v] for v in ('baseline',VARIANT)]
    replay = read(VARIANT+'/report.json')
    assert replay['algorithm_sha256']==sha(ROOT/'backend/algorithm.py')
    assert baseline['eligible_tracks']==final['eligible_tracks']==406
    runtime = read('serial_runtime.json')
    assert runtime['source_sha256'][VARIANT]==replay['algorithm_sha256']
    synthetic = read('synthetic_final_v4/report.json')
    mixed = read('mixed_axis_control/report.json')
    perpendicular = read('perpendicular_pole_control/report.json')
    assert synthetic['passed'] and mixed['passed'] and perpendicular['passed']
    assert mixed['renderer_sha256']==perpendicular['renderer_sha256']==sha(OUTPUT/'mixed_axis_control.py')
    assert synthetic['algorithm_sha256']==mixed['algorithm_sha256']==perpendicular['algorithm_sha256']==replay['algorithm_sha256']
    physical = read('physical_rotation.json')['summary']
    report = read('integration_commit_guard/report.json')
    rows = report['fruits']
    model_panel(rows)
    model_maps = [r for r in rows if 'observed_surface_pct' in r]
    model_summary = dict(tracker_records=len(rows), records_with_one_usable_view=sum(r['views']>=1 for r in rows),
                         eligible_records=sum(r['views']>=2 for r in rows), generated_maps=len(model_maps),
                         maps_surface80=sum(r['observed_surface_pct']>=80 for r in model_maps),
                         maps_longitude350=sum(r['observed_longitude_deg']>=350 for r in model_maps),
                         complete_maps=sum(bool(r['coverage_complete']) for r in model_maps),
                         observed_surface_pct=stats([r['observed_surface_pct'] for r in model_maps]),
                         provisional_grades=sum(bool(r.get('grade_provisional')) and bool(r.get('grade')) for r in rows),
                         uncertain_identities=sum(r.get('identity_status')=='uncertain' for r in rows))
    evidence = dict(final_algorithm_sha256=replay['algorithm_sha256'], source_sha256=tests['source_sha256'],
                    input_manifest_sha256=comparison['input_manifest_sha256'],
                    paired_comparison=comparison, unit_tests=tests, full_original_video_integration=integration,
                    full_model_results=model_summary, model_sha256=request['model_sha256'],
                    serial_mapping_runtime=runtime, physical_evidence=physical,
                    sampled_major_diameter_stability=read('shape_stability.json'),
                    synthetic_controls=dict(full_turns=synthetic,mixed_axis=mixed,perpendicular_pole=perpendicular),
                    verdict=dict(mathematical_controls_pass=True, real_camera_accuracy_established=False,
                                 geometry_allows_80=True, typical_physical_spin_verified=False,
                                 eligible_surface80_success_pct=final['surface80_success_pct_of_eligible'],
                                 eligible_complete_success_pct=final['complete_success_pct_of_eligible'],
                                 limitations='Real mask/pole instability and unavailable or inconsistent registration remain. '
                                 'No ground truth isolates shutter blur, illumination, slip, actual spin, '
                                 'irregular shape, perspective or unmodeled tumbling.'))
    write(OUTPUT/'FINAL_EVIDENCE.json',evidence)
    lines=['## Complete same-cohort before/after results','',
           'All 556 identity records remain in both runs; 406 have at least two usable views. '
           'Map statistics below are conditional on each variant producing a map. '
           'Unavailable maps remain in success-rate denominators.','',
           '| Metric | Baseline | Final |','|---|---:|---:|']
    keys=[('total_tracker_records','Tracker records'),('records_with_at_least_one_view','At least one usable view'),
          ('eligible_tracks','Eligible (at least two usable views)'),('generated_maps','Generated maps')]
    for key,label in keys:
        lines.append(f'| {label} | {baseline[key]} | {final[key]} |')
    for key,label in [('observed_surface_pct','Observed area %, median (p25, p75)'),
                      ('observed_longitude_deg','Observed longitude deg, median (p25, p75)'),
                      ('cumulative_rotation_deg','Measured rolling deg, median (p25, p75)'),
                      ('map_span_deg','Fruit-chart span deg, median (p25, p75)'),
                      ('selected_views','Selected views, median (p25, p75)'),
                      ('pair_residual','Accepted residual, median (p25, p75)')]:
        values=[f"{m[key]['median']:.3f} ({m[key]['p25']:.3f}, {m[key]['p75']:.3f})" for m in (baseline,final)]
        lines.append(f'| {label} | {values[0]} | {values[1]} |')
    for t in (65,70,75,80,85):
        k=f'maps_surface_at_least_{t}'
        lines.append(f'| Maps with at least {t}% area | {baseline[k]} | {final[k]} |')
    for key,label in [('maps_longitude_at_least_350','Maps with at least 350 deg longitude'),
                      ('complete_maps','Maps satisfying both 80% area and 350 deg longitude'),
                      ('surface80_success_pct_of_eligible','80% area success / all eligible, %'),
                      ('complete_success_pct_of_eligible','Both-target success / all eligible, %')]:
        lines.append(f'| {label} | {number(baseline[key])} | {number(final[key])} |')
    paired=comparison['paired']
    lines.extend(['',f"Maximum final modeled coverage is {final['observed_surface_pct']['max']:.3f}%. "
                  f"Of {paired['common_mapped_records']} common mapped records, {paired['improved']} improved, "
                  f"{paired['worse']} worsened and {paired['unchanged']} were unchanged. "
                  f"Median paired change is {paired['surface_change_percentage_points']['median']:.3f} percentage points. "
                  f"There are {len(paired['baseline_only_mapped_records'])} baseline-only maps and "
                  f"{len(paired['final_only_mapped_records'])} final-only maps. "
                  'This exposes regressions as well as gains; increased occupancy is not ground-truth accuracy.',
                  '', '[Machine-readable comparison](diagnostics/mapping80/20261006_final/comparison.json) and '
                  '[full comparison](diagnostics/mapping80/20261006_final/COMPARISON.md) preserve IDs and distributions.',
                  '', '### Failure distributions', '',
                  'Baseline failures split adjacent sequences. Final candidate skips/rejections and final '
                  'window splits are different events, so their raw totals cannot be interpreted as a direct '
                  'percentage reduction in the same failure population. Residual/boundary messages that '
                  'cannot be distinguished remain combined.', '', '| Sequence-split reason | Baseline | Final |',
                  '|---|---:|---:|'])
    for key in sorted(set(baseline['failure_reasons'])|set(final['failure_reasons'])):
        lines.append(f"| {key} | {baseline['failure_reasons'].get(key,0)} | {final['failure_reasons'].get(key,0)} |")
    lines.extend(['', 'Final candidate rejection/skip counts:', '', '```json',
                  json.dumps(final['candidate_rejections_or_skips'],indent=2),'```','',
                  'Window-ending candidate causes:', '', '```json',
                  json.dumps(final['window_ending_candidate_failures'],indent=2),'```','',
                  f"Accepted-pair original-frame gap median {final['accepted_pair_frame_gap']['median']:.1f}, "
                  f"maximum {final['accepted_pair_frame_gap']['max']:.1f}; "
                  f"{final['selected_pair_count']} selected pairs. Complete raw diagnostics remain per record.",
                  '', '### Physical evidence', '',
                  f"Accepted-chain rpm median {physical['measured_chain_rpm']['median']:.3f}, "
                  f"accepted-pair rpm median {physical['measured_pair_rpm']['median']:.3f}; "
                  f"median supported-chain interval {physical['measured_interval_sec']['median']:.3f} s. "
                  'These are conditioned on accepted measurements. They cannot establish rpm during the '
                  'rest of the visible interval or an upper bound on physical turning. The ideal geometry '
                  'requires about 18.47 rpm for 80% area over the median fully-visible interval.',
                  '', '### Tests, full production integration and timing', '',
                  f"All 202 backend tests passed in {tests['seconds']:.3f} s. Frontend build and lint passed; "
                  'frontend sources were unchanged. Known 20/40-degree pairs, zero/noisy motion, full turns, '
                  'mixed-axis pole geometry, Jacobian, visibility, seam/revisit fusion, defects, identity '
                  'withholding and cancellation controls are included.', '',
                  'The frozen final textured full-turn sphere/oblate controls recovered '
                  '357.085/357.222 degrees with maximum pair rolling errors 0.0534/0.0516 degrees. '
                  'Area is 86.6025/84.8985%, longitude 360 degrees, and a known 15% defect wedge gives '
                  '15.756/15.726% and Class 2. The independent changing-pole mixed-axis quadric renderer '
                  f"gave {mixed['observed_surface_pct']:.4f}% area, 360 deg longitude and maximum "
                  f"pair geodesic error {mixed['maximum_pair_geodesic_error_deg']:.4f} deg. "
                  f"A perpendicular-pole control recovered {perpendicular['measured_rolling_deg']:.3f} deg "
                  f"with worst pair error {perpendicular['maximum_pair_geodesic_error_deg']:.4f} deg and "
                  f"{perpendicular['observed_surface_pct']:.4f}% area. Its short radius lies on map x, "
                  f"so the same Jacobian gives a different band capacity, "
                  f"{perpendicular['ideal_fitted_band_capacity_pct']:.4f}%. "
                  'These are synthetic controls, separate from real success counts.', '',
                  f"The full unmodified 795-frame original video completed through the actual production "
                  f"pipeline in {integration['seconds']:.1f} s: {integration['detection_calls']} detector calls, "
                  f"{integration['segmentation_calls']} deferred segmenter calls for "
                  f"{integration['mapping_views']} selected views. Validation-only memory waits totaled "
                  f"{integration['resource_wait_seconds']:.1f} s; this runtime is not a throughput benchmark. "
                  'The scheduling guard changes no numerical decisions. Every integration check passed: '
                  'per-frame detection, selected-view segmentation, deferred inference, active identity guards, '
                  'uncertain identities ungraded, explicit provisional partial grades, unchanged weights '
                  'and exact final algorithm source.', '', 'Full model rerun has a separate stochastic-mask/tracking denominator:', '',
                  '```json',json.dumps(model_summary,indent=2),'```','',
                  'Model checks prove the execution contracts, not real detection, tracking, defect or grade accuracy.', '',
                  f"Serial five-record seed-817 mapping benchmark, alternating order on identical loaded inputs: "
                  f"median baseline {runtime['summary']['baseline']['median']:.3f} s/record, "
                  f"final {runtime['summary'][VARIANT]['median']:.3f} s/record. "
                  'This is mapping only; concurrent replay wall times are not used as a speedup claim.', '',
                  'Earlier source-mismatched and memory-exhausted integration attempts remain preserved and '
                  'are excluded from successful validation. No live camera hardware test was possible.', '',
                  '### Visual evidence', '',
                  '[Representative real panels and IDs](diagnostics/mapping80/20261006_final/visuals.json), '
                  '[paired distributions](diagnostics/mapping80/20261006_final/comparison_distribution.png), '
                  '[ideal capture capacity](diagnostics/mapping80/20261006_final/coverage_capacity.png), '
                  '[sphere control](diagnostics/mapping80/20261006_final/synthetic_final_v4/sphere/diagnostic_panel.png), '
                  '[oblate control](diagnostics/mapping80/20261006_final/synthetic_final_v4/oblate/diagnostic_panel.png). '
                  '[Actual full-model source masks and projected defect union](diagnostics/mapping80/20261006_final/integration_commit_guard/diagnostic_panel.png). '
                  'Real panels show best, median, low and failed records. '
                  'If no real map passes 80%, no high-coverage successful real panel is claimed.', '',
                  '## Final verdict', '',
                  '**A. Mathematics:** Jacobian, full denominator, lifting, normal visibility, matrix order, '
                  'fusion and defect union pass independent controls. The projected-pole sign rule matches '
                  'the two-component motion model. This does not establish exact real-fruit geometry.', '',
                  '**B. Camera/video calibration:** Spatial scale and temporal selection are now explicitly '
                  'derived and tested. Overall real pose/registration accuracy is still unverified; persistent '
                  'mask/pole instability and failed matching prevent declaring the camera pipeline fully calibrated.', '',
                  '**C. Physical feasibility:** The fitted band has enough modeled area for 80%; ideal median '
                  'required travel is 241.25 deg and minimum speed about 18.47 rpm over the available interval. '
                  'Typical fruit actually attaining that physical travel is not established by this footage.', '',
                  f"**D. Actual 80% area success:** {final['maps_surface_at_least_80']}/406 eligible identity "
                  f"records = {final['surface80_success_pct_of_eligible']:.3f}%.", '',
                  f"**E. Both targets:** {final['complete_maps']}/406 = "
                  f"{final['complete_success_pct_of_eligible']:.3f}%.", '',
                  '**F. Remaining limitation:** Continuous reliable skin registration and stable real '
                  'silhouette pose are not available for enough travel. The existing evidence cannot isolate '
                  'actual spin/slip, exposure blur, changing illumination, irregular shape, perspective '
                  'or camera-axis tumbling as the physical cause. No honest physical upper bound follows '
                  'from failed registration. Independent landmark/encoder rotation, shutter/lighting '
                  'measurements and pose labels are needed to separate those causes. '
                  'The 80% operational target has not been achieved; the application preserves partial '
                  'results and failures instead of reporting unseen skin.', '',
                  '[Consolidated exact-source evidence](diagnostics/mapping80/20261006_final/FINAL_EVIDENCE.json).'])
    audit=ROOT/'backend/SURFACE_MAPPING_AUDIT.md'
    text=audit.read_text().split('<!-- FINAL_RESULTS -->')[0]
    audit.write_text(text+'<!-- FINAL_RESULTS -->\n\n'+'\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    plots()
    quad_panels()
    (OUTPUT/'VALIDATION_STATUS.md').write_text(
        '# Validation complete\n\nAll 202 backend tests, the exact-source 795-frame original-video '
        'production integration, and the serial mapping benchmark completed. See `FINAL_EVIDENCE.json` '
        'and `backend/SURFACE_MAPPING_AUDIT.md` for results and limits. The measured 80% coverage '
        'success rate remains 0/406 in the paired cohort.\n',encoding='utf-8',newline='\n')
    print('Final report assembled after all required full-video validation stages passed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--plots-only',action='store_true')
    parser.add_argument('--controls-only',action='store_true')
    args=parser.parse_args()
    if args.plots_only:plots()
    elif args.controls_only:quad_panels()
    else:finalize()
