"""CPU ONNX execution of the existing FP32 segmentation checkpoint at 640."""
from pathlib import Path
import hashlib
import json
import os
from collections import Counter

from dfine_segmenter import DfineSegmenter


class OnnxDfineSegmenter(DfineSegmenter):
    def __init__(self,weights,threads=3,verify_parity=True):
        import onnxruntime as ort
        import torch
        # Reuse the exact source preprocessing/postprocessing contracts.
        super().__init__(weights,device='cpu')
        path=Path(weights).with_name('model_cpu_fp32.onnx')
        manifest_path=path.with_suffix('.json')
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if verify_parity and not manifest.get('postprocessing_parity_passed'):
            raise ValueError('Validate CPU segmentation prediction parity before enabling the export')
        for target,key in ((Path(weights),'checkpoint_sha256'),(path,'onnx_sha256')):
            with target.open('rb') as file:actual=hashlib.file_digest(file,'sha256').hexdigest()
            if actual!=manifest[key]:raise ValueError(f'CPU segmentation export provenance mismatch: {target}')
        opts=ort.SessionOptions();opts.intra_op_num_threads=threads;opts.inter_op_num_threads=1
        opts.add_session_config_entry('session.intra_op.allow_spinning','0')
        self.session=ort.InferenceSession(str(path),sess_options=opts,providers=['CPUExecutionProvider'])
        if self.session.get_inputs()[0].shape!=[1,3,640,640]:raise ValueError('CPU segmenter must retain 640 inputs')
        self.paths=[Path(weights),path,manifest_path]
        self.backend='onnx_cpu_fp32'
        self.model.model=None  # release native neural weights; retain source geometry functions
        self.model._predict=lambda inputs:dict(zip(('pred_logits','pred_boxes','pred_masks'),
            (torch.from_numpy(value) for value in self.session.run(None,{'images':inputs.numpy()}))))
        self.stage_seconds=Counter()

    def predict_batch(self,images,conf=.25):
        # The verified graph has fixed batch one. Keep source-size geometry per crop.
        results=[]
        for image in images:results.extend(super().predict_batch([image],conf=conf))
        return results


def configured_segmenter(weights,device,mixed_precision=False):
    backend=os.getenv('FRUIT_SEGMENTATION_BACKEND','onnx' if os.getenv('FRUIT_CPU_OPTIMIZED')=='1' else 'torch')
    if backend=='onnx':
        if device!='cpu':raise ValueError('ONNX segmentation profile is CPU-only')
        return OnnxDfineSegmenter(weights,int(os.getenv('FRUIT_SEGMENTATION_THREADS','3')))
    if backend!='torch':raise ValueError('FRUIT_SEGMENTATION_BACKEND must be torch or onnx')
    return DfineSegmenter(weights,device=device,mixed_precision=mixed_precision)
