"""Summarize measured CPU stages without presenting partial grading as real time."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'diagnostics/cpu-optimization'


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def aggregate(clips):
    calls=sum(c['detector_calls'] for c in clips)
    crops=sum(c['segmentation_crops'] for c in clips)
    records=sum(c['terminal_results'] for c in clips)
    seconds=sum(c['source_seconds'] for c in clips)
    neural=sum(c['segmentation_stages_seconds']['neural_inference'] for c in clips)
    total_seg=sum(c['segmentation_effective_ms_per_crop']*c['segmentation_crops']/1000 for c in clips)
    return dict(source_seconds=seconds,wall_seconds=sum(c['pipeline_wall_seconds'] for c in clips),
        detector_ms=sum(c['detector_mean_ms']*c['detector_calls'] for c in clips)/calls,
        detector_hz=calls/seconds,
        association_ms=sum(c['association_mean_ms']*c['detector_calls'] for c in clips)/calls,
        identity_ms=sum(c['runtime']['stage_seconds']['identity_validation'] for c in clips)*1000/calls,
        segmentation_ms=total_seg*1000/crops,neural_ms=neural*1000/crops,neural_fraction=neural/total_seg,
        segmentation_crops=crops,records=records,grades=sum(c['grades_produced'] for c in clips),
        timely_grades=sum(c['graded'] for c in clips),complete_sequences=sum(c['complete_evidence'] for c in clips),
        decode_ms=sum(c['decode_seconds'] for c in clips)*1000/sum(c['source_frames'] for c in clips),
        publication_ms=sum(c['publication_stages_seconds']['evidence_and_publication'] for c in clips)*1000/records,
        peak_rss_gib=max(c['peak_rss_bytes'] for c in clips)/1024**3,
        all_clips_keep_up=all(c['accurate_real_time_pass'] for c in clips))


def run():
    reference_path=ROOT/'diagnostics/timed-views/cpu_reference_final/pi4_yolo_rgb'
    optimized_path=ROOT/'diagnostics/timed-views/cpu_final_bbox/pi4_yolo_rgb'
    before=read(reference_path/'summary.json')['clips'];after=read(optimized_path/'summary.json')['clips']
    a,b=aggregate(before),aggregate(after)
    probe=read(OUT/'runtime_probe.json');masks=read(OUT/'fruit_mask_probe.json')
    parity=read(OUT/'segmentation_parity.json')
    isolated_seconds=probe['onnx_fp32']['4']['median_ms']/1000
    report=dict(reference=a,optimized=b,checkpoint_sha256=probe['checkpoint_sha256'],
        input_size=[640,640],cpu_only=True,
        source_scope='Three ten-second moving sections, original FPS schedule, stopped tails excluded',
        hardware_scope='Four physical workstation cores; 3 GiB RSS watchdog, not measured ARM Pi performance',
        grading_policy='available_views',target_views=4,interval_seconds=.4,
        fastest_isolated_neural_ms=isolated_seconds*1000,
        isolated_four_view_fruit_rate_ceiling=1/(4*isolated_seconds),
        prediction_parity_crops=len(parity['rows']),prediction_parity_positive_crops=parity['positive_crops'],
        hsv_silhouette_median_iou=masks['median_iou'],
        independently_labelled_accuracy=False,
        source_hashes={key:read(path/'request.json')['sources'] for key,path in
            [('reference',reference_path),('optimized',optimized_path)]})
    (OUT/'comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    stages=[('Segmentation, complete call','snapshot','segmentation_ms'),
        ('Segmentation neural inference (inside the call above)','snapshot','neural_ms'),
        ('Object detection, including input conversion','update','detector_ms'),
        ('TrackTrack association','update','association_ms'),
        ('Physical identity validation','update','identity_ms'),
        ('Video grab/retrieve','original source frame','decode_ms'),
        ('Evidence and result publication','result record','publication_ms')]
    stage_table='\n'.join(f'| {name} | {unit} | {a[key]:.2f} | {b[key]:.2f} |' for name,unit,key in stages)
    clip_table='\n'.join(f"| {c['video']} | {c['detector_updates_per_source_second']:.2f} | "
        f"{c['segmentation_effective_ms_per_crop']:.1f} | {c['grades_produced']} / {c['graded']} | "
        f"{c['complete_evidence']} | {c['pipeline_wall_seconds']:.2f} |" for c in after)
    runtime_table='\n'.join(f"| {n} | {probe['torch_original'][str(n)]['median_ms']:.1f} | "
        f"{probe['onnx_fp32'][str(n)]['median_ms']:.1f} |" for n in (1,2,4))
    text=f'''# CPU optimization measurements — 640, original segmentation weights

**The optimized pipeline does not keep up with the supplied moving conveyor footage.**
Segmentation improved from {a['segmentation_ms']:.0f} to {b['segmentation_ms']:.0f} ms/snapshot
in the paired whole-pipeline runs ({a['segmentation_ms']/b['segmentation_ms']:.2f}x faster per call).
It produced {b['grades']} grades, {b['timely_grades']} published before the five-second deadline,
among {b['records']} tracked association records over {b['source_seconds']:.2f} source seconds.
There were {b['complete_sequences']} fully processed four-view sequences. The reference produced
{a['grades']} grades. These counts include boundary truncation and tracker fragmentation;
they are not ground-truth physical-fruit counts or accuracy measurements.

## Processes taking the longest

These are weighted mean elapsed times inside the actual paced pipeline. Stages run
concurrently; adding their times does not give wall time. Startup/warmup is recorded
separately. Both complete segmentation time and its neural component are shown.

| Process | Unit | Reference ms | Optimized ms |
|---|---|---:|---:|
{stage_table}

The segmentation neural network consumes {100*b['neural_fraction']:.1f}% of segmentation time.
Snapshot timing arithmetic, preprocessing and mask fusion cannot remove that compute.
Source playback plus export/model drain took {b['wall_seconds']:.2f} seconds for
{b['source_seconds']:.2f} source seconds. Queues reached their bounds and work expired.
All three scenarios failed the timing/capacity acceptance check.

| Moving clip | Detector updates/source second | Segmentation ms/snapshot | Grades produced / timely | Complete four-view sequences | Wall s including drain |
|---|---:|---:|---:|---:|---:|
{clip_table}

## Implemented CPU profile

- Original segmentation checkpoint and all five defect classes, FP32, 640 x 640.
  SHA256: `{probe['checkpoint_sha256']}`. No retraining or quantization.
- Verified ONNX export of those weights, retaining source preprocessing and
  postprocessing. Class-mask unions matched exactly on {len(parity['rows'])} source crops;
  only {parity['positive_crops']} contained predicted defects. This is limited prediction
  agreement, not labelled small-defect recall or validated grading accuracy.
  Query ordering can differ between runtimes, so raw query indices are not a parity test.
- YOLO RGB ONNX CPU execution. On the isolated detector probe, two-thread ONNX
  took 94.5 ms versus 131.9 ms for NCNN; outputs matched to less than 0.001 pixel
  on that frame. This runtime ranking is for this desktop CPU, not proven for ARM.
- Two detector threads, two segmenter threads, OpenCV one thread; idle ONNX worker
  spinning disabled. A tested 1/3 detector/segmenter split improved segmentation
  but reduced detector cadence and did not deliver real-time grading.
- Four target views at 0, 0.4, 0.8 and 1.2 seconds after the first accepted observation.
  Selection uses source timestamps, without the progress/box-centre function.
  Process accepted timed snapshots immediately while remaining views are collected.
  Grade any successful available views, keeping the worst supported severity.
- One in-flight CPU segmentation request, bounded state/queues, repeated full-set
  expiry checks removed from individual readiness lookups.
- HSV contour silhouette instead of iterative GrabCut in the optimized profile.
  Filled contours retain dark interior defect pixels; bounding-box clipping prevents
  growth into adjacent fruit or rollers. HSV is used for the fruit silhouette;
  the trained defect segmenter still receives RGB. The silhouette is approximate:
  median agreement with GrabCut across {len(masks['rows'])} raw crops was
  {masks['median_iou']:.3f} IoU, minimum {masks['minimum_iou']:.3f}. Its effect on grade
  thresholds is not independently validated. Use `FRUIT_MASK_BACKEND=grabcut` to retain
  the previous silhouette preprocessing.
- Lightweight tracking history for contact-sheet evidence; JPEG contact-sheet
  previews, unchanged full-resolution model inputs and lossless full evidence;
  preview refresh capped at 2 Hz. Encoding/publication stays on the export worker.
- For this replay, decode/grab sequential incoming video at its original frame
  rate, retrieve BGR at 10 Hz, retain the latest two frames, and convert HSV only
  as frames/crops are processed. There is no preconverted video cache.

The isolated silhouette medians were {masks['median_grabcut_ms']:.2f} ms for GrabCut
and {masks['median_hsv_ms']:.2f} ms for HSV. This is a secondary cost, much smaller
than the trained segmentation network.

## Fixed-model compute limit

| CPU threads | Native complete segmentation call, isolated median ms | ONNX neural inference alone, isolated median ms |
|---:|---:|---:|
{runtime_table}

Fastest measured isolated neural execution: {isolated_seconds*1000:.1f} ms/snapshot.
Even allocating all four desktop cores only to segmentation gives an upper ceiling
of {1/(4*isolated_seconds):.2f} fruit/second for four views. Detection, capture, tracking,
grading and publication lower that ceiling. During the complete pipeline the measured
segmentation ceiling is about {1000/(4*b['segmentation_ms']):.2f} fruit/second before
accounting for views that expire. A timer changes when work is requested; it does not
make the required neural inferences disappear.

Keeping these weights, 640 inputs, four views, the recorded conveyor load and CPU-only
Pi 4 hardware leaves no demonstrated path to real-time grading. More compute or a
lower physical fruit rate would be needed under that fixed-model constraint.
No cheap colour filter has been used to invent clean-fruit grades or skip defect inference.

## Reproduce

From the project root:

```powershell
backend/venv/Scripts/python.exe backend/benchmark_timed_views.py --model yolo_rgb --hardware pi4 --optimized --capture-hz 10 --interval .4 --label my_cpu_run
```

For the backend, set `FRUIT_HARDWARE_PROFILE=pi4`, `FRUIT_DEVICE=cpu`,
`FRUIT_DETECTOR_MODEL=yolo_rgb`, `FRUIT_CPU_OPTIMIZED=1`, `FRUIT_CPU_THREADS=2`,
`FRUIT_DETECTOR_THREADS=2`, `FRUIT_SEGMENTATION_THREADS=2`,
`FRUIT_TRACKING_PREVIEW_HZ=2`, and `FRUIT_DETECTION_INTERVAL=0.1` before startup.
Use timed four-view acquisition at 0.4 seconds in the existing settings panel.
The live camera retains its shared capture; `--capture-hz` is the video replay setting.
No existing server was restarted or its saved configuration changed for these tests.

To regenerate the segmentation export, install `onnx` in the backend environment,
run `probe_cpu_optimizations.py --export`, then `validate_cpu_segmentation.py`.
Regeneration clears the parity flag; the runtime refuses an unvalidated export.
The original D-FINE SEG source remains needed through `DFINE_SEG_SOURCE` on the Pi.

## Scope and evidence

Only CPU execution was used: four physical workstation cores, no CUDA or Vulkan.
The RSS watchdog reserves roughly 1 GiB for the OS; optimized measured peak RSS
was {b['peak_rss_gib']:.2f} GiB. It is a watchdog after processed frames, not a hard
OS memory cap. ARM instructions, clocks, cache, decoder, temperature and throttling
are not emulated. These numbers must not be presented as Raspberry Pi FPS.

The three moving sections are 0.4–10.4 seconds from the dense, mixed and sparse
recordings, using the existing calibration of all 50 videos. Stopped tails are excluded.
This short preliminary benchmark is not a sustained field test. No independently
labelled fruit identities, defect masks or grades are available in this comparison.

Primary raw data: [`cpu_reference_final`](../timed-views/cpu_reference_final/pi4_yolo_rgb/summary.json),
[`cpu_final_bbox`](../timed-views/cpu_final_bbox/pi4_yolo_rgb/summary.json),
[`runtime_probe.json`](runtime_probe.json), [`detection_probe.json`](detection_probe.json),
[`segmentation_parity.json`](segmentation_parity.json),
[`fruit_mask_probe.json`](fruit_mask_probe.json), and [`comparison.json`](comparison.json).
Each replay records model/source hashes and retains matching source snapshots.
Earlier profile probes, including the rejected silhouette that included rollers,
remain preserved separately. Historical four-model comparisons used another grading
policy and must not be combined with these measurements.

Validation: **307 backend tests passed** in 195.431 seconds. Added controls cover
progressive four-view timing without centre-based selection, dark defect pixels
inside HSV silhouettes, rejection of adjacent fruit/background, and JPEG evidence
metadata. The checkpoint hash and all 24 source snapshots for the primary paired
replays were verified. See [`validation.json`](validation.json) and
[`backend-tests.log`](backend-tests.log).
'''
    (OUT/'RESULTS.md').write_text(text,encoding='utf-8')
    print(json.dumps(dict(reference=a,optimized=b),indent=2))


if __name__=='__main__':run()
