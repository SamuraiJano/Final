"""Compare class-mask unions and grades, allowing harmless query permutations."""
from pathlib import Path
import json
import cv2
import numpy as np
import torch
import psutil
from benchmark_timed_views import four_core_affinity
from dfine_segmenter import DfineSegmenter
from optimized_segmenter import OnnxDfineSegmenter

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'diagnostics/cpu-optimization'


def unions(result,shape,names):
    maps={name:np.zeros(shape,bool) for name in names.values()}
    if result.masks is not None:
        for cls,mask in zip(result.boxes.cls,result.masks.data):maps[names[int(cls)]]|=np.asarray(mask)>0
    return maps


def run():
    psutil.Process().cpu_affinity(four_core_affinity()[0]);torch.set_num_threads(3);cv2.setNumThreads(1)
    weights=ROOT/'models/D-FINE/segmentation/model.pt'
    native=DfineSegmenter(weights,device='cpu');optimized=OnnxDfineSegmenter(weights,threads=3,verify_parity=False)
    rows=[]
    for path in sorted(OUT.glob('crop_*.png')):
        image=cv2.imread(str(path));shape=image.shape[:2]
        a=unions(native.predict_batch([image],conf=.5)[0],shape,native.names)
        b=unions(optimized.predict_batch([image],conf=.5)[0],shape,native.names)
        ious={name:float(np.count_nonzero(a[name]&b[name])/max(1,np.count_nonzero(a[name]|b[name])))
            if (a[name]|b[name]).any() else 1. for name in a}
        ua=np.logical_or.reduce(list(a.values()));ub=np.logical_or.reduce(list(b.values()))
        rows.append(dict(crop=path.name,mask_iou=ious,native_pixels=int(ua.sum()),onnx_pixels=int(ub.sum()),
            pixel_disagreement=int(np.count_nonzero(ua!=ub)),
            native_instances=native.total_predictions,onnx_instances=optimized.total_predictions))
        print(rows[-1],flush=True)
    # Empty inputs or all-negative inputs cannot establish mask agreement.
    passed=(len(rows)>=4 and any(row['native_pixels']>0 for row in rows)
        and all(min(row['mask_iou'].values())>=.98 for row in rows))
    report=dict(passed=passed,scope='Prediction agreement on source crops, not independent defect accuracy',
        rows=rows,positive_crops=sum(r['native_pixels']>0 for r in rows),native_stages=dict(native.stage_seconds),
        onnx_stages=dict(optimized.stage_seconds))
    (OUT/'segmentation_parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    path=weights.with_name('model_cpu_fp32.json')
    manifest=json.loads(path.read_text())
    manifest['postprocessing_parity_passed']=passed
    manifest['parity_scope']=report['scope']
    manifest['parity_crops']=len(rows)
    manifest['parity_positive_crops']=report['positive_crops']
    path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if not passed:raise RuntimeError('ONNX class-mask parity failed; do not enable this export')


if __name__=='__main__':run()
