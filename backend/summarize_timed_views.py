"""Summarize recorded paced replays without rerunning models or changing evidence."""
from collections import Counter
from pathlib import Path
import csv
import json


ROOT = Path(__file__).resolve().parent / 'diagnostics' / 'timed-views'


def summarize():
    rows = []
    for hardware in ('laptop', 'pi4'):
        for model in ('yolo_rgb', 'yolo_hsv', 'dfine_rgb', 'dfine_hsv'):
            folder = ROOT / 'final_comparison' / f'{hardware}_{model}'
            summary = json.loads((folder/'summary.json').read_text())
            request = json.loads((folder/'request.json').read_text())
            clips = summary['clips']
            total = lambda name: sum(c[name] for c in clips)
            weighted = lambda name, weight: sum(c[name]*c[weight] for c in clips)/total(weight)
            statuses, selected, processed = Counter(), Counter(), Counter()
            for clip in clips:
                statuses.update(clip['statuses'])
                selected.update(clip['selected_view_histogram'])
                processed.update(clip['processed_view_histogram'])
            row = dict(profile=hardware,model=model,views=summary['views'],interval_seconds=summary['interval'],
                clips=len(clips),source_seconds=total('source_seconds'),pipeline_wall_seconds=total('pipeline_wall_seconds'),
                detector_updates_per_source_second=total('detector_calls')/total('source_seconds'),
                detector_updates_per_wall_second=total('detector_calls')/total('pipeline_wall_seconds'),
                detector_mean_ms=weighted('detector_mean_ms','detector_calls'),
                association_mean_ms=weighted('association_mean_ms','detector_calls'),
                segmentation_effective_ms_per_crop=weighted('segmentation_effective_ms_per_crop','segmentation_crops'),
                segmentation_crops=total('segmentation_crops'),arrivals=total('arrivals'),
                terminal_results=total('terminal_results'),complete_evidence=total('complete_evidence'),
                timely_grades=total('graded'),timely_grade_fraction=total('graded')/total('terminal_results'),
                timely_grades_per_wall_second=total('graded')/total('pipeline_wall_seconds'),
                deadline_misses=total('deadline_misses'),peak_rss_gib=max(c['peak_rss_bytes'] for c in clips)/2**30,
                max_clip_frame_age_p95_ms=max(c['frame_age_p95_ms'] for c in clips),
                max_clip_publication_p95_seconds=max(c['publication_p95_seconds'] for c in clips),
                source_frames=total('source_frames'),capture_overwritten_frames=total('capture_overwritten_frames'),
                timer_skipped_detector_frames=total('timer_skipped_detector_frames'),
                duplicate_terminal_uids=total('duplicate_terminal_uids'),
                strict_real_time_pass=all(c['accurate_real_time_pass'] for c in clips),
                statuses=dict(statuses),selected_view_histogram=dict(selected),processed_view_histogram=dict(processed),
                cpu_affinity=request['cpu_affinity'],request=str(folder.relative_to(ROOT)/'request.json'))
            rows.append(row)
    (ROOT/'comparison.json').write_text(json.dumps(dict(
        protocol='640 FP32; unchanged segmentation; source-paced operation only; 4 views at .4 s; .15 s lateness; 5 s deadline',
        independent_accuracy_labels=False,repetitions_per_model_profile=1,rows=rows),indent=2),encoding='utf-8')
    flat = [{k:v for k,v in row.items() if not isinstance(v,(dict,list))} for row in rows]
    with (ROOT/'comparison.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    lines = ['# Timed-view full-pipeline benchmark — 11 October 2026', '',
        'This records the earlier complete-sequence grading policy. Grading now uses '
        'available processed snapshots at the user\'s request; missing scheduled views no '
        'longer block a grade. These recorded comparisons were not rerun under that policy.', '',
        '**The current pipeline did not pass real-time grading in any of the eight comparisons.** '
        'Timed capture is implemented at 640 pixels. Four views reduced the work, but the unchanged '
        'segmenter, tracking, missed capture windows and publication load still prevent grading every arrival.', '',
        '## Timing measured before benchmarking', '',
        'All 50 recordings were screened for moving fruit. Conservative full-operation ranges retain '
        '717.260 seconds across 43 videos and exclude stopped tails, speed transitions and insufficiently '
        'long/empty sections. The five operation-review contact sheets were visually inspected. '
        'These are motion-based ranges rather than motor telemetry.', '',
        'The offline timing fit uses 2,491 uncensored, quality-accepted tracker associations from '
        '267.087 seconds across 30 recordings. Median usable dwell is **2.305 seconds** '
        '(5th/95th percentiles: 1.004/2.611 seconds). Four views at **0.2-second spacing** with '
        '0.15-second lateness fit 95.50% of these associations; at **0.4 seconds** they fit 91.37%. '
        'Four views one or two seconds apart fit none. The fruit leaves the usable field before the fourth capture.', '',
        'The same-implementation dense-scene pilot published 14 grades at 0.4-second spacing versus '
        '8 at 0.2 seconds. Thus **four snapshots at 0.4 seconds** is the tested performance compromise '
        '(nominal times 0, 0.4, 0.8, 1.2 seconds after the first accepted crop). The UI measured preset '
        'uses 0.2 seconds for acquisition fit; enter 0.4 to reproduce this performance comparison. '
        'This is preliminary tuning, not proof of optimal timing or angular coverage.', '',
        '## Common protocol', '',
        '- Three operation-only scenes per model/profile: dense `WIN_20260818_13_05_49_Pro.mp4`, '
        'mixed `WIN_20260818_13_35_37_Pro.mp4`, sparse `WIN_20260818_13_52_31_Pro.mp4`; '
        'each replays 0.4–10.4 seconds at its original approximately 29.9 FPS.',
        '- Four distinct source crops, 0.4-second spacing, 0.15-second lateness, 5-second decision deadline. '
        'Requested detection/tracking cadence: 10 updates/second. Missing crops, uncertain identity '
        'and late publication withhold the grade.',
        '- Both model inputs remain 640 × 640 and FP32. HSV_FULL is converted after RGB letterboxing '
        'on each detector invocation; incoming video is decoded BGR and never preconverted as a whole.',
        '- The existing native Torch segmentation checkpoint is unchanged. Complete fruit sequences '
        'receive bounded inference admission and earliest-deadline priority. Contact-sheet evidence '
        'reduces PNG export work; mask inference and defect fusion still run.',
        '- Laptop: RTX 4060 Laptop GPU, supplied FP32 TensorRT detector engines. CPU rehearsal: '
        'NCNN YOLO / ONNX Runtime D-FINE, CUDA/Vulkan disabled, affinity to four physical cores '
        '`[0, 2, 4, 6]`, two Torch/two detector threads, one OpenCV thread, 3 GiB RSS watchdog.',
        '- One replay per model/profile, with startup/warmup reported separately. Pipeline wall time '
        'includes processing, expired inference, evidence writes and drain. Background desktop load '
        'and run-to-run variance were not controlled. This is a preliminary benchmark.', '',
        '## Results', '',
        'Detector Hz below is actual detector calls divided by source duration. It is **not grading FPS** '
        'and does not mean every camera frame was processed. Timely grades are published, complete '
        'provisional decisions. Denominators are terminal tracker associations, including clip-boundary '
        'truncation and uncertain IDs; they are not ground-truth physical fruit counts.', '',
        '| Profile | Detector | Detector Hz | Timely grades / associations | Complete evidence | Segmentation ms/crop | Peak RSS GiB | Deadline misses |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f"| {'Laptop CUDA' if row['profile']=='laptop' else 'Four-core CPU proxy'} | {row['model']} | "
            f"{row['detector_updates_per_source_second']:.2f} | {row['timely_grades']}/{row['terminal_results']} | "
            f"{row['complete_evidence']} | {row['segmentation_effective_ms_per_crop']:.1f} | "
            f"{row['peak_rss_gib']:.2f} | {row['deadline_misses']} |")
    lines += ['', 'Segmentation ms/crop is measured effective inference-plus-mask wall cost divided by '
        'submitted crops, including batched work; it is not isolated model latency. Complete evidence '
        'can still be ungraded because identity is uncertain or publication is late.', '',
        '**D-FINE RGB published the most timely laptop grades: 47/477 associations (9.85%).** '
        'Every CPU rehearsal published **zero** complete timely grades. The four-core runs spent '
        'roughly 1.5–2.0 seconds per segmentation crop; four views therefore exceed the five-second '
        'budget even before the rest of the pipeline at that effective rate. Laptop tracking and '
        'segmentation/export contention also reduce detector cadence below the requested 10 Hz. '
        'Changing snapshot arithmetic alone cannot remove these costs.', '',
        '## Drops and latency', '',
        'Capture overwrites discard older frames when the consumer falls behind. Timer skips are '
        'intentional cadence skips and counted separately. The latency columns below are the '
        '**largest per-clip 95th percentile**, not a pooled percentile.', '',
        '| Profile / model | Source frames | Capture overwritten | Timer skips | Wall seconds incl. drain | Frame age p95 ms | Publication p95 s |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f"| {row['profile']} / {row['model']} | {row['source_frames']} | "
            f"{row['capture_overwritten_frames']} | {row['timer_skipped_detector_frames']} | "
            f"{row['pipeline_wall_seconds']:.1f} | {row['max_clip_frame_age_p95_ms']:.1f} | "
            f"{row['max_clip_publication_p95_seconds']:.2f} |")
    lines += ['', 'All runs reported zero duplicate terminal UIDs. The machine-readable '
        '[comparison.json](comparison.json) includes selected/processed view histograms and status '
        'counts; [comparison.csv](comparison.csv) contains the aggregate numeric table. Each '
        '[model/profile folder](final_comparison/) retains request settings, source/model hashes, '
        'per-clip measurements, resource samples and links to actual result jobs.', '',
        '## Interpretation and next test', '',
        'Timing chooses snapshots without the centre-progress calculation. Shared tracking still '
        'uses boxes to preserve identity. Timers alone cannot associate simultaneous fruit or '
        'certify distinct skin angles. No independently labelled identities, defects or grades '
        'were available; these results measure workload and decision completion, not accuracy. '
        'The differing association counts also prevent declaring a detector accuracy winner.', '',
        'The four-core run is **not ARM emulation or a prediction of Raspberry Pi FPS**. Desktop '
        'CPU instructions, clock, cache, memory, decoder, Windows and thermal behaviour differ. '
        'The 3 GiB check is a watchdog after processed frames, not a hard OS limit. Test the same '
        'paced script on the actual Pi before making deployment claims.', '',
        'With this segmentation checkpoint retained, the tested settings are not sufficient for '
        'real-time sorting. A materially faster segmentation runtime/model or more inference '
        'capacity is needed for the measured arrival load. Raising deadlines does not solve '
        'sustained throughput overload. The planned replacement segmenter should be benchmarked '
        'using this same replay protocol.', '',
        'Segmentation checkpoint SHA-256: '
        '`2869048b1bba2ca0e5cfb0416bf9977f79f851dd8907ffa8b07b54e8c6d049c0`. '
        'The corrupt HSV D-FINE ONNX copy was replaced by the locally verified original binary '
        'without retraining; see [repair provenance](model_repair.json). Recorded benchmark source '
        'snapshots were checked against their hashes; see '
        '[source verification](final_comparison/source_verification.json). Later metadata and '
        'mixed-mode cadence fixes do not alter these fixed timed replays.', '',
        'Reproducible commands, calibration procedure and dashboard settings: '
        '[TIMED_VIEW_GRADING.md](../../TIMED_VIEW_GRADING.md).', '']
    (ROOT/'RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps([dict(profile=r['profile'],model=r['model'],grades=r['timely_grades'],
                           associations=r['terminal_results']) for r in rows]))


if __name__ == '__main__':
    summarize()
