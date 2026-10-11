"""Isolated four-core CPU probes, conversion and prediction-equivalence evidence."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import time

os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import cv2
import numpy as np
import psutil
import torch
import onnxruntime as ort
from benchmark_timed_views import four_core_affinity
from dfine_segmenter import DfineSegmenter
from export_detector import ExportDetector, preprocess
from algorithm import _grabcut

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'diagnostics/cpu-optimization'
WEIGHTS=ROOT/'models/D-FINE/segmentation/model.pt'
ONNX=ROOT/'models/D-FINE/segmentation/model_cpu_fp32.onnx'


def save(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf-8')


def measure(operation,repeats=3):
    operation()
    values=[]
    for _ in range(repeats):
        began=time.perf_counter();operation();values.append((time.perf_counter()-began)*1000)
    return dict(median_ms=float(np.median(values)),samples_ms=values)


def samples():
    detector=ExportDetector('yolo_rgb','cpu',2)
    images=[]
    for stamp in ('13_05_49','13_35_37','13_52_31'):
        path=next((ROOT.parent/'videos').glob(f'*{stamp}*'))
        cap=cv2.VideoCapture(str(path));cap.set(cv2.CAP_PROP_POS_MSEC,1400)
        ok,frame=cap.read();cap.release()
        if not ok:raise RuntimeError(path)
        rows=detector.predict_rows(frame)
        for row in sorted(rows,key=lambda r:-r[4]):
            x0,y0,x1,y1=map(int,row[:4]);h,w=frame.shape[:2]
            if min(x0,y0)<=2 or x1>=w-2 or y1>=h-2:continue
            pad=round(max(x1-x0,y1-y0)*.12)
            l,t=max(0,x0-pad),max(0,y0-pad);r,b=min(w,x1+pad),min(h,y1+pad)
            image=frame[t:b,l:r].copy()
            mask=_grabcut(image,3,(x0-l,y0-t,x1-l,y1-t))
            image=cv2.bitwise_and(image,image,mask=mask)
            images.append(image)
            if len(images)%3==0:break
    for k,image in enumerate(images):cv2.imwrite(str(OUT/f'crop_{k}.png'),image)
    return images


class Raw(torch.nn.Module):
    def __init__(self,model):super().__init__();self.model=model
    def forward(self,images):
        output=self.model(images)
        return output['pred_logits'],output['pred_boxes'],output['pred_masks']


def session(path,threads):
    opts=ort.SessionOptions();opts.intra_op_num_threads=threads;opts.inter_op_num_threads=1
    opts.add_session_config_entry('session.intra_op.allow_spinning','0')
    return ort.InferenceSession(str(path),sess_options=opts,providers=['CPUExecutionProvider'])


def run(args):
    OUT.mkdir(parents=True,exist_ok=True)
    affinity,method=four_core_affinity();psutil.Process().cpu_affinity(affinity)
    torch.set_num_threads(2);cv2.setNumThreads(1)
    images=[cv2.imread(str(p)) for p in sorted(OUT.glob('crop_*.png'))] or samples()
    segmenter=DfineSegmenter(WEIGHTS,device='cpu');segmenter.warmup()
    tensor=torch.from_numpy(segmenter.model._preprocess(images[0])[None]).float()/255.
    report=dict(affinity=affinity,affinity_method=method,input_size=[640,640],
        checkpoint_sha256=hashlib.sha256(WEIGHTS.read_bytes()).hexdigest(),cpu_only=True)
    with torch.inference_mode():
        reference=segmenter.model._predict(tensor)
        report['torch_original']={}
        for threads in (1,2,4):
            torch.set_num_threads(threads)
            report['torch_original'][threads]=measure(lambda:segmenter.predict_batch([images[0]],conf=.5))
            print('torch original',threads,report['torch_original'][threads],flush=True)
        segmenter.model.model.deploy()
        deployed=segmenter.model._predict(tensor)
        report['deploy_max_absolute_error']={k:float((reference[k]-deployed[k]).abs().max()) for k in reference if isinstance(reference[k],torch.Tensor)}
        report['torch_deployed']={}
        for threads in (1,2,4):
            torch.set_num_threads(threads)
            report['torch_deployed'][threads]=measure(lambda:segmenter.predict_batch([images[0]],conf=.5))
            print('torch deployed',threads,report['torch_deployed'][threads],flush=True)
        if args.export or not ONNX.is_file():
            torch.set_num_threads(2)
            print('Exporting unchanged deployed checkpoint at 640',flush=True)
            torch.onnx.export(Raw(segmenter.model.model).eval(),tensor,str(ONNX),opset_version=17,
                input_names=['images'],output_names=['logits','boxes','masks'],dynamo=False)
            import onnx
            onnx.checker.check_model(str(ONNX))
        segmenter.model.model.eval()
    save('runtime_probe.json',report)
    report['onnx_fp32']={}
    for threads in (1,2,4):
        engine=session(ONNX,threads)
        report['onnx_fp32'][threads]=measure(lambda:engine.run(None,{'images':tensor.numpy()}))
        print('onnx',threads,report['onnx_fp32'][threads],flush=True)
    engine=session(ONNX,2)
    report['onnx_parity']=[]
    with torch.inference_mode():
        for image in images:
            input=torch.from_numpy(segmenter.model._preprocess(image)[None]).float()/255.
            expected=segmenter.model._predict(input)
            actual=engine.run(None,{'images':input.numpy()})
            report['onnx_parity'].append({name:float(np.max(np.abs(expected[key].numpy()-value)))
                for name,key,value in zip(('logits','boxes','masks'),('pred_logits','pred_boxes','pred_masks'),actual)})
    report['onnx_sha256']=hashlib.sha256(ONNX.read_bytes()).hexdigest()
    save('segmentation_export.json',dict(checkpoint_sha256=report['checkpoint_sha256'],
        onnx_sha256=report['onnx_sha256'],input_size=[640,640],precision='fp32',outputs=['logits','boxes','masks']))
    ONNX.with_suffix('.json').write_text((OUT/'segmentation_export.json').read_text(),encoding='utf-8')
    save('runtime_probe.json',report)
    print('Saved runtime_probe.json',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--export',action='store_true')
    run(parser.parse_args())
