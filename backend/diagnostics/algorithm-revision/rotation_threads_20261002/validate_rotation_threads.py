"""Paired OpenCV thread timing on unchanged frozen real rotation inputs."""
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import sys
import time

import cv2
import numpy as np


HERE = Path(__file__).resolve().parent
BACKEND = next(p for p in HERE.parents if p.name == 'backend')
SOURCE = BACKEND / 'diagnostics/algorithm-revision/adjacent_observable_source/algorithm_snapshot.py'
FIXTURES = BACKEND / 'diagnostics/algorithm-revision/fixed_observable_conveyor_20261002'
EXPECTED = '863fd09cfa629c5b5b8ba7c73963fbe993441b3e3dd989f1e451d0a5f62c9db1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    assert digest(SOURCE) == EXPECTED
    shutil.copy2(SOURCE, HERE / 'algorithm_snapshot.py')
    spec = importlib.util.spec_from_file_location('thread_rotation_snapshot', SOURCE)
    algorithm = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = algorithm
    spec.loader.exec_module(algorithm)
    settings = algorithm.Settings(spheroid_type='auto', rotation_axis='x', rotation_direction=1,
        select_rotating_views=True, bidirectional_matching=True,
        minimum_longitude_coverage_deg=350, maximum_pair_gap_deg=55,
        maximum_view_index_gap=1, min_pair_angle_deg=.25)
    initial_threads = cv2.getNumThreads()
    report = dict(recorded_at=datetime.now().isoformat(), algorithm_sha256=EXPECTED,
        validator_sha256=digest(__file__), settings=asdict(settings), repetitions=3,
        hardware=dict(platform=platform.platform(), processor=platform.processor(),
            opencv_version=cv2.__version__, opencv_cpu_count=cv2.getNumberOfCPUs(),
            initial_threads=initial_threads, opencl_enabled=cv2.ocl.useOpenCL()),
        method='Three real adjacent pairs selected from previous frozen replay: two native rechecks and one coarse-only match. Exact full-track spheroid is fitted once outside timing; each pair uses the production selector subset helper. Each mode gets one untimed warm-up. Three paired estimator repetitions alternate mode order. Captured actual remap arrays are timed separately in three groups of 50 calls, after warm-up; setup, hashing and thread switching are excluded. No production change.',
        limitations='A short single-process microbenchmark under other machine load. These crops have no pose ground truth. Equality between thread modes establishes numerical agreement, not geometric accuracy or full-video throughput.',
        cases=[])
    actual_remap = cv2.remap
    try:
        for case_index, (track, source_frame, target_frame) in enumerate([(98,99,100), (1,4,5), (14,1,2)]):
            folder = FIXTURES / str(track) / 'inputs'
            rows = json.loads((folder / 'views.json').read_text())
            views = []
            for row in rows:
                with np.load(folder / row['file']) as data:
                    views.append(algorithm.FruitView(data['image'].copy(), data['mask'].copy(), {},
                        int(row['frame']), tuple(row['bbox'])))
            indices = [next(i for i,v in enumerate(views) if v.frame_index == f)
                       for f in (source_frame,target_frame)]
            assert indices[1] == indices[0] + 1
            model = algorithm.fit_spheroid(views, settings)
            pair_model = algorithm._subset_spheroid(model, indices)
            source, target = [views[i] for i in indices]
            case = dict(track=track, source_frame=source_frame, target_frame=target_frame,
                crop_shapes=[list(v.image.shape) for v in (source,target)], inputs=[], estimator_calls=[], remap_calls=[])
            for index in indices:
                source_path = folder / rows[index]['file']
                destination = HERE / 'inputs' / f'fruit_{track}_{rows[index]["file"]}'
                destination.parent.mkdir(exist_ok=True)
                shutil.copy2(source_path, destination)
                case['inputs'].append(dict(file=str(destination.relative_to(HERE)),
                    original=str(source_path), sha256=digest(source_path), metadata=rows[index]))

            captures = {}
            def capture_remap(src, map1, map2, interpolation, *args, **kwargs):
                # Retain the largest actual batch projection for each source resolution.
                key = tuple(src.shape)
                if key not in captures or map1.size > captures[key][1].size:
                    captures[key] = (src.copy(), map1.copy(), map2.copy(), interpolation, args, kwargs)
                return actual_remap(src,map1,map2,interpolation,*args,**kwargs)
            cv2.setNumThreads(16)
            cv2.remap = capture_remap
            capture_details = {}
            algorithm.estimate_rotation(source,target,pair_model,0,settings,capture_details)
            cv2.remap = actual_remap
            case['observed_path'] = capture_details
            for threads in (16,1):
                cv2.setNumThreads(threads)
                algorithm.estimate_rotation(source,target,pair_model,0,settings,{})
            matrices = {}
            for repetition in range(3):
                order = (16,1) if (case_index+repetition)%2 == 0 else (1,16)
                for threads in order:
                    cv2.setNumThreads(threads)
                    details = {}
                    started = time.perf_counter()
                    rotation,error = algorithm.estimate_rotation(source,target,pair_model,0,settings,details)
                    milliseconds = (time.perf_counter()-started)*1000
                    matrices[(repetition,threads)] = rotation
                    case['estimator_calls'].append(dict(repetition=repetition,threads=threads,
                        milliseconds=milliseconds, rotation_matrix=rotation.tolist(),
                        error=error, details=details, output_sha256=hashlib.sha256(rotation.tobytes()).hexdigest()))
            case['estimator_comparison'] = []
            for repetition in range(3):
                a,b = [matrices[(repetition,t)] for t in (16,1)]
                pair = [next(r for r in case['estimator_calls'] if r['repetition']==repetition and r['threads']==t) for t in (16,1)]
                case['estimator_comparison'].append(dict(repetition=repetition,
                    bit_identical=bool(np.array_equal(a,b)), maximum_matrix_difference=float(np.max(np.abs(a-b))),
                    residual_difference=abs(pair[0]['error']-pair[1]['error']),
                    details_identical=pair[0]['details']==pair[1]['details']))
            for shape, (src,map1,map2,interpolation,args,kwargs) in captures.items():
                outputs = {}
                for repetition in range(3):
                    order = (16,1) if (case_index+repetition)%2 == 0 else (1,16)
                    for threads in order:
                        cv2.setNumThreads(threads)
                        actual_remap(src,map1,map2,interpolation,*args,**kwargs)
                        started = time.perf_counter()
                        for _ in range(50):
                            output = actual_remap(src,map1,map2,interpolation,*args,**kwargs)
                        milliseconds = (time.perf_counter()-started)*1000/50
                        outputs[(repetition,threads)] = output
                        case['remap_calls'].append(dict(source_shape=list(shape),map_shape=list(map1.shape),
                            repetition=repetition,threads=threads,mean_milliseconds=milliseconds,
                            output_sha256=hashlib.sha256(output.tobytes()).hexdigest()))
                assert all(np.array_equal(outputs[(r,16)],outputs[(r,1)]) for r in range(3))
            case['remap_bit_identical'] = True
            case['estimator_mean_milliseconds'] = {str(t):float(np.mean([r['milliseconds'] for r in case['estimator_calls'] if r['threads']==t])) for t in (16,1)}
            report['cases'].append(case)
        report['estimator_mean_milliseconds'] = {str(t):float(np.mean([r['milliseconds'] for c in report['cases'] for r in c['estimator_calls'] if r['threads']==t])) for t in (16,1)}
        report['remap_mean_milliseconds'] = {str(t):float(np.mean([r['mean_milliseconds'] for c in report['cases'] for r in c['remap_calls'] if r['threads']==t])) for t in (16,1)}
        report['all_estimator_pairs_bit_identical'] = all(r['bit_identical'] and r['residual_difference']==0 and r['details_identical'] for c in report['cases'] for r in c['estimator_comparison'])
        report['all_remap_pairs_bit_identical'] = True
        report['estimator_speed_ratio_16_over_1'] = report['estimator_mean_milliseconds']['16']/report['estimator_mean_milliseconds']['1']
        report['completed_at'] = datetime.now().isoformat()
        (HERE / 'report.json').write_text(json.dumps(report,indent=2))
        lines = ['# OpenCV thread timing on real rotation pairs','', report['method'],'',
            f"Frozen algorithm SHA256: `{EXPECTED}`.",'',
            '| Fruit / frames | Search path | Mean 16 threads, ms | Mean 1 thread, ms |','| --- | --- | ---: | ---: |']
        for c in report['cases']:
            path = 'Coarse plus native' if c['observed_path']['image_downsample']==1 else 'Coarse only'
            lines.append(f"| {c['track']} / {c['source_frame']}–{c['target_frame']} | {path} | {c['estimator_mean_milliseconds']['16']:.3f} | {c['estimator_mean_milliseconds']['1']:.3f} |")
        lines += ['',f"All nine paired estimator outputs are bit-identical: {report['all_estimator_pairs_bit_identical']}; residuals and path details also match exactly. All captured remap output pairs are bit-identical.",'',
            f"Estimator overall means: 16 threads {report['estimator_mean_milliseconds']['16']:.3f} ms; 1 thread {report['estimator_mean_milliseconds']['1']:.3f} ms. Captured remap means: 16 threads {report['remap_mean_milliseconds']['16']:.4f} ms; 1 thread {report['remap_mean_milliseconds']['1']:.4f} ms.",'', report['limitations'],'',
            'Run from the project root: `backend/venv/Scripts/python.exe -B backend/diagnostics/algorithm-revision/rotation_threads_20261002/validate_rotation_threads.py`. Source, six unchanged NPZ crops, their hashes, complete settings, all timings, matrices and exact comparison results are retained in this folder. Full-track fit inputs remain in the referenced frozen replay.']
        (HERE / 'ROTATION_THREADS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        (HERE / 'opencv_build_information.txt').write_text(cv2.getBuildInformation())
        manifest = {str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file() and p.name!='sha256.json'}
        (HERE / 'sha256.json').write_text(json.dumps(manifest,indent=2))
        print(json.dumps({k:report[k] for k in ('estimator_mean_milliseconds','remap_mean_milliseconds','all_estimator_pairs_bit_identical','all_remap_pairs_bit_identical','estimator_speed_ratio_16_over_1')},indent=2))
    finally:
        cv2.remap = actual_remap
        cv2.setNumThreads(initial_threads)


if __name__ == '__main__':
    main()
