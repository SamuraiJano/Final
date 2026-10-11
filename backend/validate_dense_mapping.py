"""Reproducible dense-video audit on every record of a frozen real tracker run.

Capture silhouettes once from the original video and saved detection history;
both variants consume those exact hashed inputs. No tracker rerun, invented
rotation, defect labels, or assertion of physical-fruit ground truth is made.
Use the separate production integration check for neural-model execution.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BACKEND / 'diagnostics/mapping80/20261006_final'
SOURCE_REPORT = BACKEND / 'results/b23fe12db90e41dbae9928e3fbcf55cf/report.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def load_module(path, name='dense_audit_algorithm'):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prepare(output, workers):
    algorithm = load_module(output/'baseline_source/algorithm.py', 'capture_baseline_algorithm')
    report = json.loads(SOURCE_REPORT.read_text(encoding='utf-8'))
    request = json.loads((BACKEND / 'diagnostics/pipeline-runs/identity_full_20261004/request.json').read_text())
    video = Path(request['video'])
    if sha(video) != request['video_sha256']:
        raise ValueError('Original video hash differs from the frozen tracker run')
    baseline = output / 'baseline_source/algorithm.py'
    if sha(baseline) != report['metrics']['algorithm_sha256']:
        raise ValueError('Saved complete run is not the active baseline source')
    settings = algorithm.Settings(**report['metrics']['geometry_settings'])
    records, by_frame = [], defaultdict(list)
    for row in report['fruits']:
        history = {r['frame']: r for r in row['tracking_history']}
        record = {k: row.get(k) for k in ('track_id', 'fruit_id', 'identity_status', 'source_tracker_ids',
                   'first_seen_frame', 'last_seen_frame', 'tracked_frames', 'rejected_views')}
        record.update(original_usable_views=row['views'], views=[], tracking_history=row['tracking_history'])
        records.append(record)
        for frame in row.get('view_frames', []):
            by_frame[frame].append((record, history[frame]['bbox_xyxy']))
    cv2.setNumThreads(1)

    def capture(frame, index, record, bounds):
        identity = record['track_id']
        folder = output / 'inputs' / str(identity)
        folder.mkdir(parents=True, exist_ok=True)
        file = f'frame_{index:05d}.npz'
        path = folder / file
        if path.exists():
            with np.load(path) as data:
                bbox = data['bbox'].tolist()
            return record, dict(file=file, frame=index, bbox=bbox, sha256=sha(path))
        x1, y1, x2, y2 = bounds
        h, w = frame.shape[:2]
        px, py = .12*(x2-x1), .12*(y2-y1)
        left, top = max(0, int(np.floor(x1-px))), max(0, int(np.floor(y1-py)))
        right, bottom = min(w, int(np.ceil(x2+px))), min(h, int(np.ceil(y2+py)))
        image = frame[top:bottom, left:right].copy()
        bbox = (max(0, int(np.floor(x1))-left), max(0, int(np.floor(y1))-top),
                min(right-left, int(np.ceil(x2))-left), min(bottom-top, int(np.ceil(y2))-top))
        # Explicit per-capture seed freezes stochastic GrabCut; exact masks in
        # this paired experiment need not equal the earlier unsaved masks.
        cv2.setRNGSeed((identity*1009 + index*9176) % 2147483647)
        try:
            mask = algorithm._grabcut(image, settings.grabcut_iterations, bbox)
            algorithm._validate_capture_mask(mask, bbox, settings)
        except algorithm.MappingError as error:
            return record, dict(frame=index, rejection=str(error))
        np.savez_compressed(path, image=image, mask=mask, bbox=bbox)
        return record, dict(file=file, frame=index, bbox=bbox, sha256=sha(path))

    cap = cv2.VideoCapture(str(video))
    fps, count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    started = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            index = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                futures = [pool.submit(capture, frame, index, record, bounds)
                           for record, bounds in by_frame.get(index, [])]
                for future in futures:
                    record, item = future.result()
                    if 'rejection' in item:
                        record.setdefault('recapture_rejections', []).append(item)
                    else:
                        record['views'].append(item)
                index += 1
                if index % 50 == 0:
                    print(f'Frozen {index}/{count} frames, {sum(len(r["views"]) for r in records)} views, '
                          f'{time.perf_counter()-started:.1f}s', flush=True)
    finally:
        cap.release()
    for record in records:
        record['views'].sort(key=lambda item: item['frame'])
    write(output/'inputs.json', dict(video=str(video), video_sha256=sha(video), fps=fps,
          frames=count, source_report=str(SOURCE_REPORT), source_report_sha256=sha(SOURCE_REPORT),
          baseline_algorithm_sha256=sha(baseline), records=records,
          limitations='All frozen tracker records; no independent identity/rotation/grade labels. '
                       'Re-extracted deterministic silhouettes are shared by both runs.'))
    print('Input preparation complete', len(records), sum(len(r['views']) for r in records), flush=True)


def load_views(module, output, record):
    views = []
    for item in record['views']:
        with np.load(output/'inputs'/str(record['track_id'])/item['file']) as data:
            views.append(module.FruitView(data['image'], data['mask'], frame_index=item['frame'],
                                          fruit_bbox=tuple(item['bbox'])))
    return views


def verify_inputs(output,workers):
    manifest=json.loads((output/'inputs.json').read_text())
    tasks=[(output/'inputs'/str(record['track_id'])/view['file'],view['sha256'])
           for record in manifest['records'] for view in record['views']]
    def check(item):
        path,digest=item
        if not path.resolve().is_relative_to((output/'inputs').resolve()):
            raise ValueError('Input path escaped frozen input directory')
        return None if sha(path)==digest else str(path)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        mismatches=[value for value in pool.map(check,tasks) if value is not None]
    result=dict(passed=not mismatches,tracker_records=len(manifest['records']),files=len(tasks),
                input_manifest_sha256=sha(output/'inputs.json'),mismatches=mismatches)
    write(output/'input_verification.json',result)
    print(json.dumps(result,indent=2))
    if mismatches:
        raise AssertionError('Frozen replay inputs changed')


def run_record(task):
    output, variant, record, parameters = task
    output = Path(output)
    cv2.setNumThreads(1)
    module = load_module(output/variant/'algorithm.py')
    settings = module.Settings(**parameters)
    # Geometry replay has no segmentation evidence and must never issue grades.
    settings.defect_observations_complete = False
    settings.grade_partial_maps = False
    folder = output/variant/str(record['track_id'])
    result_path = folder/'result.json'
    if result_path.exists():
        return json.loads(result_path.read_text())
    views = load_views(module, output, record)
    row = dict(track_id=record['track_id'], usable_views=len(views), identity_status=record['identity_status'])
    started = time.perf_counter()
    try:
        mapped = module.build_surface_map(views, settings)
        row.update({k:v for k,v in asdict(mapped).items() if k not in
                   ('bgr_map','observed_mask','defect_maps','longitude_deg','latitude_deg')})
        folder.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(folder/'surface_map.png'), mapped.bgr_map)
        cv2.imwrite(str(folder/'observed_mask.png'), mapped.observed_mask*255)
        np.savez_compressed(folder/'map_coordinates.npz', longitude=mapped.longitude_deg, latitude=mapped.latitude_deg)
        assert mapped.grade is None
    except module.MappingError as error:
        row.update(status='mapping_failed', reason=str(error), selection_diagnostics=error.diagnostics,
                   grade=None, view_frames=[])
    row['seconds'] = time.perf_counter()-started
    write(result_path, row)
    return row


def replay(output, variant, source, parameters, workers, limit=None):
    inputs = json.loads((output/'inputs.json').read_text())
    folder = output/variant
    folder.mkdir(parents=True, exist_ok=True)
    frozen = folder/'algorithm.py'
    if frozen.exists() and sha(frozen) != sha(source):
        raise ValueError('Variant label already belongs to a different source')
    frozen.write_bytes(source.read_bytes())
    existing = folder/'settings.json'
    if existing.exists() and json.loads(existing.read_text()) != parameters:
        raise ValueError('Variant label already belongs to different settings')
    write(existing, parameters)
    records = inputs['records'][:limit] if limit else inputs['records']
    tasks = [(str(output), variant, record, parameters) for record in records]
    rows = []
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(run_record, task) for task in tasks]):
            row = future.result()
            rows.append(row)
            if len(rows)%10 == 0 or len(rows)==len(tasks):
                print(f'{variant}: {len(rows)}/{len(tasks)} records; {time.perf_counter()-started:.1f}s', flush=True)
                write(folder/'progress.json', dict(completed=len(rows), total=len(tasks), seconds=time.perf_counter()-started))
    rows.sort(key=lambda r:r['track_id'])
    write(folder/'report.json', dict(algorithm_sha256=sha(frozen), settings=parameters,
          input_manifest_sha256=sha(output/'inputs.json'), seconds=time.perf_counter()-started, records=rows))


def stats(values):
    return dict(zip(('min','p25','median','p75','max'), map(float,np.percentile(values,[0,25,50,75,100])))) if values else {}


def reason(text):
    text=text.lower()
    for needle, category in [('window exhausted','direct_measurement_window_exhausted'),
         ('window exceeded','direct_measurement_window_exceeded'),
         ('keyframe minimum','measured_below_keyframe_minimum'),
         ('missing','missing_original_frames'),('too small','motion_below_minimum'),
         ('unobservable','motion_below_minimum'),('disagree','coarse_native_or_inverse_disagreement'),
         ('longitude','longitude_order_failure'),('texture','insufficient_texture'),
         ('point','insufficient_points'),('boundary','search_boundary'),('error','pair_residual_or_boundary')]:
        if needle in text:
            return category
    return text or 'unspecified'


def metrics(rows):
    maps=[r for r in rows if 'observed_surface_pct' in r]
    eligible=[r for r in rows if r['usable_views']>=2]
    diagnostics=[d for r in rows for d in r['selection_diagnostics']]
    failures=Counter(reason(d.get('reason','')) for d in diagnostics if d.get('status')=='split')
    rejected=Counter(reason(d.get('reason','')) for d in diagnostics if d.get('status') in ('rejected','skipped'))
    result=dict(total_tracker_records=len(rows),records_with_at_least_one_view=sum(r['usable_views']>=1 for r in rows),
        eligible_tracks=len(eligible),generated_maps=len(maps),failure_reasons=dict(failures),
        candidate_rejections_or_skips=dict(rejected),selected_views=stats([len(r['view_frames']) for r in maps]),
        observed_surface_pct=stats([r['observed_surface_pct'] for r in maps]),
        observed_longitude_deg=stats([r['observed_longitude_deg'] for r in maps]),
        cumulative_rotation_deg=stats([r['rotation_coverage_deg'] for r in maps]),
        map_span_deg=stats([r['map_longitude_span_deg'] for r in maps]),
        pair_residual=stats([e for r in maps for e in r['pair_errors']]),
        seconds_per_eligible_track=stats([r['seconds'] for r in eligible]))
    result['failed_track_reasons']=dict(Counter(reason(r.get('reason','')) for r in eligible if 'observed_surface_pct' not in r))
    result['measured_zero_hypotheses']=sum('rotation 0.00 deg is too small' in d.get('reason','') for d in diagnostics)
    result['selected_pair_count']=sum(len(r['pair_errors']) for r in maps)
    result['pair_measurement_attempts']=sum(d.get('status') in ('accepted','rejected','skipped') for d in diagnostics)
    result['accepted_pair_frame_gap']=stats([d['source_frame_gap'] for d in diagnostics if d.get('status')=='accepted'])
    result['window_ending_candidate_failures']=dict(Counter(reason(d['last_candidate_reason'])
        for d in diagnostics if 'last_candidate_reason' in d))
    for threshold in (65,70,75,80,85):
        result[f'maps_surface_at_least_{threshold}']=sum(r['observed_surface_pct']>=threshold for r in maps)
    result['maps_longitude_at_least_350']=sum(r['observed_longitude_deg']>=350 for r in maps)
    result['complete_maps']=sum(r['observed_surface_pct']>=80 and r['observed_longitude_deg']>=350 for r in maps)
    result['surface80_success_pct_of_eligible']=100*result['maps_surface_at_least_80']/len(eligible) if eligible else 0
    result['complete_success_pct_of_eligible']=100*result['complete_maps']/len(eligible) if eligible else 0
    return result


def compare(output, variants):
    reports={v:json.loads((output/v/'report.json').read_text()) for v in variants}
    if len({r['input_manifest_sha256'] for r in reports.values()})!=1:
        raise ValueError('Comparison inputs differ')
    ids=[{r['track_id'] for r in report['records']} for report in reports.values()]
    if any(i!=ids[0] for i in ids):
        raise ValueError('Comparison tracker denominators differ')
    result={v:metrics(r['records']) for v,r in reports.items()}
    first,last=variants[0],variants[-1]
    left={r['track_id']:r for r in reports[first]['records'] if 'observed_surface_pct' in r}
    right={r['track_id']:r for r in reports[last]['records'] if 'observed_surface_pct' in r}
    common=sorted(left.keys()&right.keys())
    deltas=[right[i]['observed_surface_pct']-left[i]['observed_surface_pct'] for i in common]
    paired=dict(common_mapped_records=len(common),
        before_surface=stats([left[i]['observed_surface_pct'] for i in common]),
        after_surface=stats([right[i]['observed_surface_pct'] for i in common]),
        surface_change_percentage_points=stats(deltas),
        improved=sum(d>1e-9 for d in deltas),worse=sum(d< -1e-9 for d in deltas),
        unchanged=sum(abs(d)<=1e-9 for d in deltas),
        baseline_only_mapped_records=sorted(left.keys()-right.keys()),
        final_only_mapped_records=sorted(right.keys()-left.keys()))
    write(output/'comparison.json',dict(input_manifest_sha256=sha(output/'inputs.json'),variants=result,paired=paired,
        replay_execution_overrides=dict(defect_observations_complete=False,grade_partial_maps=False),
        runtime_interpretation='Replay durations reflect different worker concurrency and machine load. '
        'They are not a fair baseline/final speed comparison; use the separate serial_runtime.json benchmark.',
        replay_contract='Identical frozen inputs and tracker IDs. No defect inference or grades. '
        'Report settings identify the application profile; the above worker overrides isolate geometry.'))
    lines=['# Paired full-video mapping comparison','',
        'All records use identical frozen crops, masks, frame numbers and tracker identities. '
        'Geometry replay contains no defect inference or grades. Coverage is model-estimated; '
        'there are no independent real rotation labels.','',
        '| Metric | '+' | '.join(variants)+' |','|---|'+'---:|'*len(variants)]
    for name in next(iter(result.values())):
        values=[]
        for variant in variants:
            value=result[variant][name]
            if isinstance(value,dict):
                value=(f"{value['median']:.4f} ({value['p25']:.4f}, {value['p75']:.4f})" if 'median' in value else json.dumps(value))
            values.append(str(value))
        lines.append('| '+name+' | '+' | '.join(values)+' |')
    lines.extend(['','## Common mapped records','',
        'The above conditional map medians have different map denominators. The common-record '
        'comparison below exposes improvements and regressions; unmapped identities remain '
        'in each variant\'s eligible success denominator.','',
        '```json',json.dumps(paired,indent=2),'```'])
    lines.extend(['','Recorded replay durations reflect different worker concurrency and machine load. '
                  'They are not a fair speed comparison. The separate serial_runtime.json benchmark '
                  'uses the same loaded inputs, alternating order and no saved-result cache.'])
    (output/'COMPARISON.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','replay','compare','verify'))
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--variant',default='baseline')
    parser.add_argument('--source',type=Path)
    parser.add_argument('--settings',type=Path)
    parser.add_argument('--limit',type=int)
    parser.add_argument('--variants',nargs='+',default=['baseline','final'])
    args=parser.parse_args()
    output=args.output.resolve()
    if args.mode=='prepare':
        prepare(output,args.workers)
    elif args.mode=='verify':
        verify_inputs(output,args.workers)
    elif args.mode=='replay':
        params=json.loads(args.settings.read_text()) if args.settings else json.loads(SOURCE_REPORT.read_text())['metrics']['geometry_settings']
        replay(output,args.variant,args.source or output/'baseline_source/algorithm.py',params,args.workers,args.limit)
    else:
        compare(output,args.variants)


if __name__=='__main__':
    main()
