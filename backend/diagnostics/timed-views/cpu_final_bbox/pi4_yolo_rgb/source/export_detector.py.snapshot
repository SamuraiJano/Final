"""640px detector exports, with live RGB/HSV_FULL preprocessing and TrackTrack."""
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import os

import cv2
import numpy as np

from dfine_segmenter import make_fruit_tracker, associate_fruit_detections

MODEL_IDS = ('yolo_rgb', 'yolo_hsv', 'dfine_rgb', 'dfine_hsv')
ROOT = Path(__file__).resolve().parent / 'models'


def preprocess(frame, colour):
    """Canonical RGB geometry first, matching controlled detection training.

    H,S,V occupy the three channels; hue uses 0..255 (HSV_FULL). Conversion is
    performed for this incoming frame only, after RGB resizing and padding.
    """
    height, width = frame.shape[:2]
    ratio = min(640 / height, 640 / width)
    rw, rh = round(width * ratio), round(height * ratio)
    left, top = (640 - rw) // 2, (640 - rh) // 2
    resized = cv2.resize(frame, (rw, rh), interpolation=cv2.INTER_LINEAR)
    padded = cv2.copyMakeBorder(resized, top, 640 - rh - top, left, 640 - rw - left,
                               cv2.BORDER_CONSTANT, value=(114, 114, 114))
    channels = cv2.cvtColor(padded, cv2.COLOR_BGR2HSV_FULL if colour == 'hsv' else cv2.COLOR_BGR2RGB)
    tensor = np.ascontiguousarray(channels.transpose(2, 0, 1)[None], dtype=np.float32) / 255.
    return tensor, (rw / width, rh / height, left, top)


def decode(family, outputs, confidence, geometry, shape):
    if family == 'yolo':
        raw = outputs[0].reshape(-1, outputs[0].shape[-1])
        if raw.shape[1] == 5:  # NCNN raw xyxy + one-class scores
            order = np.argsort(raw[:, 4])[::-1][:300]
            rows = np.column_stack((raw[order, :5], np.zeros(len(order)))).astype(np.float32)
        elif raw.shape[1] == 6:  # TensorRT end-to-end TopK
            rows = raw.copy()
        else:
            raise ValueError(f'Unexpected YOLO output {raw.shape}')
    else:
        logits, boxes = outputs
        scores = 1. / (1. + np.exp(-np.clip(logits[0], -50., 50.)))
        flat = np.argsort(scores.ravel())[::-1][:300]
        queries, labels = flat // scores.shape[1], flat % scores.shape[1]
        chosen = boxes[0, queries] * 640.
        xyxy = np.column_stack((chosen[:, :2] - chosen[:, 2:] / 2, chosen[:, :2] + chosen[:, 2:] / 2))
        rows = np.column_stack((xyxy, scores[queries, labels], labels)).astype(np.float32)
    rows = rows[rows[:, 4] >= confidence].copy()
    gx, gy, left, top = geometry
    rows[:, [0, 2]] = np.clip((rows[:, [0, 2]] - left) / gx, 0, shape[1])
    rows[:, [1, 3]] = np.clip((rows[:, [1, 3]] - top) / gy, 0, shape[0])
    return rows[(rows[:, 2] > rows[:, 0]) & (rows[:, 3] > rows[:, 1])]


class ExportDetector:
    def __init__(self, model_id='yolo_rgb', device='cpu', threads=4, models=ROOT, backend=None):
        if model_id not in MODEL_IDS:
            raise ValueError(f'Unknown detector {model_id}; choose {MODEL_IDS}')
        self.model_id, self.device = model_id, device
        self.mixed_precision = False  # provided deployment exports are FP32
        self.family, self.colour = model_id.split('_')
        self.backend = backend or ('tensorrt' if device == 'cuda' else 'ncnn' if self.family == 'yolo' else 'onnx')
        folder = Path(models) / ('YOLO' if self.family == 'yolo' else 'D-FINE') / 'detection'
        stem = f'model_{self.colour}'
        self.names, self.input_size = {0: 'naartjie'}, (640, 640)
        self.tracker, self.tracking_size_px = make_fruit_tracker(device), None
        # Recordings and the inspection camera are fixed. Image-wide optical
        # flow is unnecessary for camera compensation, and measured ~30ms per
        # update in the profiling run. TrackTrack association itself is retained.
        if os.getenv('FRUIT_TRACKER_GMC', 'none') == 'none':
            self.tracker.gmc.method = None
        self.inference_calls = self.total_predictions = 0
        self.actual_last_seen = {}
        self.total_latency_ms = self.total_confidence = 0.
        self.preprocess_ms = self.backend_ms = self.association_ms = 0.
        if self.backend == 'ncnn':
            import ncnn
            self.ncnn, self.net = ncnn, ncnn.Net()
            self.net.opt.use_vulkan_compute = False
            self.net.opt.num_threads = threads
            self.net.opt.use_fp16_storage = self.net.opt.use_fp16_arithmetic = False
            self.paths = [folder / f'{stem}.ncnn.param', folder / f'{stem}.ncnn.bin']
            if self.net.load_param(str(self.paths[0])) or self.net.load_model(str(self.paths[1])):
                raise RuntimeError(f'Cannot load {model_id} NCNN export')
        elif self.backend == 'onnx':
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads, opts.inter_op_num_threads = threads, 1
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            opts.add_session_config_entry('session.intra_op.allow_spinning', '0')
            self.paths = [folder / f'{stem}.onnx']
            self.session = ort.InferenceSession(str(self.paths[0]), sess_options=opts, providers=['CPUExecutionProvider'])
            if self.session.get_inputs()[0].shape != [1, 3, 640, 640]:
                raise ValueError('Detector input must be static 1x3x640x640')
        elif self.backend == 'tensorrt':
            import sys
            runtime_python = Path(os.getenv('FRUIT_TENSORRT_PYTHON',
                Path(__file__).resolve().parents[2] / 'New Model Trainer/.venv/Lib/site-packages'))
            # Use the already-installed local exporter runtime when available;
            # append so the inspection environment keeps its own dependencies.
            if runtime_python.is_dir():
                sys.path.append(str(runtime_python))
            import tensorrt as trt
            import torch
            self.torch, self.trt = torch, trt
            self.logger = trt.Logger(trt.Logger.WARNING)
            trt.init_libnvinfer_plugins(self.logger, '')
            self.runtime = trt.Runtime(self.logger)
            self.paths = [folder / f'model_fp32_{self.colour}.engine']
            self.engine = self.runtime.deserialize_cuda_engine(self.paths[0].read_bytes())
            if self.engine is None:
                raise RuntimeError('TensorRT engine is incompatible; use matching runtime or CPU exports')
            self.context = self.engine.create_execution_context()
            names = [self.engine.get_tensor_name(i) for i in range(self.engine.num_io_tensors)]
            self.input_name = next(n for n in names if self.engine.get_tensor_mode(n) == trt.TensorIOMode.INPUT)
            self.output_names = (['output0'] if self.family == 'yolo' else ['logits', 'boxes'])
            self.buffers = {n: torch.empty(tuple(self.context.get_tensor_shape(n)), device='cuda',
                dtype=torch.from_numpy(np.empty((), dtype=trt.nptype(self.engine.get_tensor_dtype(n)))).dtype) for n in names}
            if tuple(self.buffers[self.input_name].shape) != (1, 3, 640, 640):
                raise ValueError('Detector input must remain 640x640')
            for name, value in self.buffers.items():
                self.context.set_tensor_address(name, value.data_ptr())
            self.stream = torch.cuda.Stream(priority=-1)
        else:
            raise ValueError('Backend must be ncnn, onnx or tensorrt')

    def raw(self, tensor):
        if self.backend == 'ncnn':
            with self.net.create_extractor() as extractor:
                if extractor.input('in0', self.ncnn.Mat(tensor[0]).clone()):
                    raise RuntimeError('NCNN input failed')
                status, output = extractor.extract('out0')
                if status:
                    raise RuntimeError('NCNN inference failed')
                return [np.array(output)]
        if self.backend == 'onnx':
            return self.session.run(None if self.family == 'yolo' else ['logits', 'boxes'],
                                    {self.session.get_inputs()[0].name: tensor})
        # All transfers and kernels for this independent detector use its own
        # stream. Waiting on Torch's default stream would serialize it behind
        # every defect batch, missing snapshot windows despite fast detection.
        with self.torch.cuda.stream(self.stream):
            self.buffers[self.input_name].copy_(self.torch.from_numpy(tensor))
            if not self.context.execute_async_v3(self.stream.cuda_stream):
                raise RuntimeError('TensorRT inference failed')
        self.stream.synchronize()
        return [self.buffers[name].cpu().numpy() for name in self.output_names]

    def predict_rows(self, frame, conf=.25):
        started = perf_counter()
        tensor, geometry = preprocess(frame, self.colour)
        prepared = perf_counter()
        outputs = self.raw(tensor)
        inferred = perf_counter()
        rows = decode(self.family, outputs, conf, geometry, frame.shape)
        self.preprocess_ms += (prepared - started) * 1000
        self.backend_ms += (inferred - prepared) * 1000
        self.inference_calls += 1
        self.total_latency_ms += (perf_counter() - started) * 1000
        self.total_predictions += len(rows); self.total_confidence += float(rows[:, 4].sum())
        self.last_detection_rows = rows.copy()
        return rows

    def track(self, frame, conf=.25, **kwargs):
        from ultralytics.engine.results import Boxes
        rows = self.predict_rows(frame, conf)
        started = perf_counter()
        timestamp = kwargs.get('source_timestamp')
        if timestamp is not None:
            stale = [t for t in self.tracker.lost_stracks if timestamp-self.actual_last_seen.get(t.track_id,timestamp)>1.]
            stale_ids = {t.track_id for t in stale}
            for track in stale: track.mark_removed()
            self.tracker.lost_stracks = [t for t in self.tracker.lost_stracks if t.track_id not in stale_ids]
            self.tracker.removed_stracks = (self.tracker.removed_stracks+stale)[-1000:]
        actual, self.tracking_size_px = associate_fruit_detections(self.tracker, rows, frame, self.tracking_size_px, conf)
        if timestamp is not None:
            alive={t.track_id for t in self.tracker.tracked_stracks+self.tracker.lost_stracks}
            self.actual_last_seen={k:v for k,v in self.actual_last_seen.items() if k in alive}
            self.actual_last_seen.update({int(row[4]):timestamp for row in actual})
        self.association_ms += (perf_counter() - started) * 1000
        return [SimpleNamespace(boxes=Boxes(actual, frame.shape[:2]))]

    def warmup(self):
        self.raw(np.zeros((1, 3, 640, 640), np.float32))


def configured_detector(device):
    return ExportDetector(os.getenv('FRUIT_DETECTOR_MODEL', 'yolo_rgb'), device,
                          int(os.getenv('FRUIT_DETECTOR_THREADS', os.getenv('FRUIT_CPU_THREADS', '4'))),
                          backend=os.getenv('FRUIT_DETECTION_BACKEND') or
                          ('onnx' if os.getenv('FRUIT_CPU_OPTIMIZED')=='1' else None))
