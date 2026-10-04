"""Paired OpenCV thread timings on twelve frozen real crops; no model calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import time

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import psutil

from validate_motion_resolution import sha256, write_json

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'diagnostics/algorithm-revision/observable_motion_controls_20261002/algorithm_snapshot.py'
INPUT = ROOT/'diagnostics/algorithm-revision/fixed_conveyor_20261002'


def choose_inputs(output):
    cases = []
    folder = output/'inputs'; folder.mkdir()
    for identity in ('98', '1', '14', '491'):
        root = INPUT/identity/'inputs'
        manifest = json.loads((root/'views.json').read_text(encoding='utf-8'))
        for index in (0, (len(manifest)-1)//2, len(manifest)-1):
            item = manifest[index]; source = root/item['file']
            key = f'fruit_{identity}_view_{index:03d}_frame_{item["frame"]:05d}'
            retained = folder/f'{key}.npz'; retained.write_bytes(source.read_bytes())
            with np.load(source) as stored: image = stored['image'].copy()
            cv2.imwrite(str(folder/f'{key}_crop.png'), image)
            cases.append({'id': key, 'fruit': int(identity), 'source_view_index': index,
                          'frame': item['frame'], 'bbox': item['bbox'], 'image_shape': list(image.shape),
                          'source_file': str(source), 'source_file_sha256': sha256(source),
                          'retained_input': str(retained.relative_to(output)), 'retained_input_sha256': sha256(retained),
                          'image_bgr_array_sha256': hashlib.sha256(image.tobytes()).hexdigest(), '_image': image})
    return cases


def summarize(rows):
    native = np.array([row['timing_ms']['native_default'] for row in rows])
    single = np.array([row['timing_ms']['single_thread'] for row in rows])
    return {'paired_calls': len(rows), 'native_default_mean_ms': float(native.mean()),
            'native_default_median_ms': float(np.median(native)),
            'single_thread_mean_ms': float(single.mean()), 'single_thread_median_ms': float(np.median(single)),
            'aggregate_timed_native_ms': float(native.sum()), 'aggregate_timed_single_ms': float(single.sum()),
            'aggregate_speedup': float(native.sum()/single.sum()),
            'median_paired_speedup': float(np.median(native/single)),
            'minimum_mask_iou': min(row['mask_iou'] for row in rows),
            'maximum_mask_pixel_xor': max(row['mask_pixel_xor'] for row in rows),
            'all_masks_bit_identical': all(row['mask_pixel_xor'] == 0 for row in rows)}


def figures(output, cases, report):
    fig, panel = plt.subplots(figsize=(12, 5))
    labels = [f'{case["fruit"]}: frame {case["frame"]}' for case in cases]
    native, single = [], []
    for case in cases:
        pairs = [row for row in report['pairs'] if row['case'] == case['id']]
        native.append(np.median([row['timing_ms']['native_default'] for row in pairs]))
        single.append(np.median([row['timing_ms']['single_thread'] for row in pairs]))
    x = np.arange(len(cases))
    panel.bar(x-.2, native, .4, label=f'Native default: {report["native_default_threads"]} threads', color='#b47735')
    panel.bar(x+.2, single, .4, label='One thread', color='#297b52')
    panel.set(xticks=x, xticklabels=labels, ylabel='Median GrabCut time, milliseconds',
              title='Same real crop, same box, same iterations and paired random seed')
    panel.tick_params(axis='x', labelrotation=35); panel.legend(); panel.grid(axis='y', alpha=.2)
    fig.tight_layout(); fig.savefig(output/'grabcut_threads_timing.png', dpi=300)
    fig.savefig(output/'grabcut_threads_timing.pdf'); plt.close(fig)
    fig, axes = plt.subplots(3, 4, figsize=(12, 9))
    for panel, case in zip(axes.ravel(), cases):
        panel.imshow(cv2.cvtColor(case['_image'], cv2.COLOR_BGR2RGB))
        mask = cv2.imread(str(output/'masks'/f'{case["id"]}_rep0_single_thread.png'), cv2.IMREAD_GRAYSCALE)
        panel.contour(mask>0, levels=[.5], colors=['#55e07a'], linewidths=.7)
        paired = next(row for row in report['pairs'] if row['case'] == case['id'] and row['repetition'] == 0)
        panel.set_title(f'Fruit {case["fruit"]}, frame {case["frame"]}\nIoU {paired["mask_iou"]:.5f}; XOR {paired["mask_pixel_xor"]}', fontsize=9)
        panel.axis('off')
    fig.suptitle('Frozen real BGR inputs and one-thread mask outline; paired mask agreement shown')
    fig.tight_layout(); fig.savefig(output/'grabcut_masks_comparison.png', dpi=300)
    fig.savefig(output/'grabcut_masks_comparison.pdf'); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='grabcut_threads_20261002')
    args = parser.parse_args()
    output = ROOT/'diagnostics/algorithm-revision'/args.label
    output.mkdir(parents=True, exist_ok=False)
    frozen = output/'algorithm_snapshot.py'; frozen.write_bytes(SOURCE.read_bytes())
    (output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    spec = importlib.util.spec_from_file_location('grabcut_thread_algorithm', frozen)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    native_threads = cv2.getNumThreads()
    cases = choose_inputs(output)
    masks_folder = output/'masks'; masks_folder.mkdir()
    build = cv2.getBuildInformation()
    (output/'opencv_build_information.txt').write_text(build, encoding='utf-8')
    frequency = psutil.cpu_freq()
    hardware = {'platform': platform.platform(), 'processor': platform.processor(),
                'logical_cpu_count': os.cpu_count(), 'physical_cpu_count': psutil.cpu_count(logical=False),
                'cpu_frequency_mhz': frequency._asdict() if frequency else None,
                'memory_total_bytes': psutil.virtual_memory().total, 'opencv_version': cv2.__version__,
                'opencv_cpu_count': cv2.getNumberOfCPUs(),
                'opencv_parallel_framework': next((line.strip() for line in build.splitlines() if 'Parallel framework' in line), None),
                'opencv_opencl_available': cv2.ocl.haveOpenCL(), 'opencv_opencl_enabled': cv2.ocl.useOpenCL()}
    report = {'recorded_at': datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'algorithm_sha256': sha256(frozen), 'validator_sha256': sha256(Path(__file__)),
              'hardware': hardware, 'native_default_threads': native_threads, 'candidate_threads': 1,
              'grabcut_iterations': 3, 'repetitions': 3,
              'method': 'First/middle/last preserved real crops for each frozen fruit98/1/14/491. '
                        'Three paired repetitions with identical per-pair RNG seeds. Native/default and1-thread order '
                        'alternates by case and repetition. setNumThreads and setRNGSeed occur outside timing. '
                        'The exact frozen _grabcut, bbox, three iterations and BGR pixels are unchanged. '
                        'One untimed warm-up call per mode precedes measured calls.',
              'limitations': 'Concurrent full API analysis and other diagnostic processes can affect wall time. '
                            'Single-process paired microbenchmark, not end-to-end speed or grade accuracy. '
                            'Thread-mode changes can have initialization costs; timings exclude the setting call '
                            'but may include lazy worker behavior. Twelve complete crops do not cover all masks, '
                            'trackers, camera scheduling, detector or segmenter runtime.',
              'cases': [{key: value for key, value in case.items() if not key.startswith('_')} for case in cases],
              'pairs': []}
    write_json(output/'report.json', report)
    try:
        for threads in (native_threads, 1):
            cv2.setNumThreads(threads); cv2.setRNGSeed(73019)
            module._grabcut(cases[0]['_image'], 3, tuple(cases[0]['bbox']))
        for repetition in range(3):
            for index, case in enumerate(cases):
                seed = 73019+1000*repetition+index
                modes = [('native_default', native_threads), ('single_thread', 1)]
                if (repetition+index)%2: modes.reverse()
                row = {'case': case['id'], 'repetition': repetition, 'rng_seed': seed,
                       'mode_order': [name for name, _ in modes], 'timing_ms': {}, 'masks': {}}
                masks = {}
                for name, threads in modes:
                    cv2.setNumThreads(threads); cv2.setRNGSeed(seed)
                    started = time.perf_counter()
                    mask = module._grabcut(case['_image'], 3, tuple(case['bbox']))
                    row['timing_ms'][name] = (time.perf_counter()-started)*1000
                    masks[name] = mask>0
                    saved = masks_folder/f'{case["id"]}_rep{repetition}_{name}.png'
                    cv2.imwrite(str(saved), mask*255)
                    row['masks'][name] = str(saved.relative_to(output))
                a, b = masks['native_default'], masks['single_thread']
                union, intersection = int((a|b).sum()), int((a&b).sum())
                row.update(mask_iou=intersection/union if union else 1., mask_pixel_xor=int((a^b).sum()),
                           mask_foreground_pixels={name: int(mask.sum()) for name, mask in masks.items()})
                report['pairs'].append(row); write_json(output/'report.json', report)
            print(json.dumps({'repetition': repetition, **summarize(report['pairs'][-len(cases):])}), flush=True)
    finally:
        cv2.setNumThreads(native_threads)
    report['summary'] = summarize(report['pairs'])
    report['completed_at'] = datetime.now(timezone(timedelta(hours=2))).isoformat()
    report['restored_diagnostic_process_threads'] = cv2.getNumThreads()
    figures(output, cases, report); write_json(output/'report.json', report)
    write_json(output/'sha256.json', {str(path.relative_to(output)): sha256(path) for path in output.rglob('*') if path.is_file()})
    print(json.dumps({'completed': str(output), **report['summary']}), flush=True)


if __name__ == '__main__': main()
