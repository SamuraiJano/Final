"""Adapters for the local D-FINE detection and segmentation checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from time import perf_counter
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np


def inference_device() -> str:
    """Use CUDA by default, and explain a CPU-only PyTorch install clearly."""
    import torch

    requested = os.getenv("FRUIT_DEVICE", "cuda").lower()
    if requested == "cpu":
        return "cpu"
    if requested != "cuda":
        raise ValueError("FRUIT_DEVICE must be 'cuda' or 'cpu'")
    if not torch.cuda.is_available():
        raise RuntimeError(
            f"CUDA is unavailable in this Python environment (torch {torch.__version__}). "
            "Install CUDA-enabled PyTorch or set FRUIT_DEVICE=cpu explicitly."
        )
    return "cuda"


class DfineDetector:
    """Run the local D-FINE nano checkpoint and feed its boxes to TrackTrack."""

    def __init__(self, weights: str | Path, device: str):
        from ultralytics.trackers.track_tracker import TRACKTRACK
        from ultralytics.utils import YAML, IterableSimpleNamespace
        from ultralytics.utils.checks import check_yaml

        runner_python = Path(__file__).resolve().parents[2] / "Inference Runner" / "backend" / "python"
        if not (runner_python / "dfine_checkpoint.py").is_file():
            raise FileNotFoundError(f"D-FINE checkpoint loader is missing: {runner_python}")
        sys.path.insert(0, str(runner_python))
        from dfine_checkpoint import load_dfine_nano

        self.processor, self.model, labels = load_dfine_nano(Path(weights), device)
        self.names = dict(enumerate(labels))
        self.device = device
        config = IterableSimpleNamespace(**YAML.load(check_yaml("tracktrack.yaml")))
        config.device = device
        self.tracker = TRACKTRACK(config)
        self.inference_calls = 0
        self.total_latency_ms = 0.0
        self.total_predictions = 0
        self.total_confidence = 0.0

    def track(self, frame, conf: float = 0.25, **_kwargs):
        import torch
        from PIL import Image
        from ultralytics.engine.results import Boxes

        started = perf_counter()
        height, width = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        inputs = self.processor(images=Image.fromarray(rgb), return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            outputs = self.model(**inputs)
            detected = self.processor.post_process_object_detection(
                outputs, threshold=conf, target_sizes=[(height, width)]
            )[0]
        boxes = detected["boxes"].detach().cpu().numpy()
        scores = detected["scores"].detach().cpu().numpy()
        classes = detected["labels"].detach().cpu().numpy()
        self.inference_calls += 1
        self.total_latency_ms += (perf_counter() - started) * 1000
        self.total_predictions += len(scores)
        self.total_confidence += float(scores.sum())
        rows = np.column_stack((boxes, scores, classes)).astype(np.float32)
        tracked = self.tracker.update(Boxes(rows, (height, width)), img=frame)
        tracked_rows = tracked[:, :7] if len(tracked) else np.empty((0, 7), np.float32)
        return [SimpleNamespace(boxes=Boxes(tracked_rows, (height, width)))]


class DfineSegmenter:
    def __init__(self, weights: str | Path, source_root: str | Path | None = None,
                 device: str | None = None):
        import torch

        weights = Path(weights).resolve()
        manifest = json.loads(weights.with_suffix(".dfineseg.json").read_text(encoding="utf-8"))
        if manifest.get("format") != "dfine-seg" or manifest.get("task") != "segment":
            raise ValueError("Expected D-FINE SEG metadata beside the weights")
        labels = manifest["labels"]
        self.names = {index: name for index, name in enumerate(labels)}
        self.inference_calls = 0
        self.total_latency_ms = 0.0
        self.total_predictions = 0
        self.total_confidence = 0.0

        with weights.open("rb") as checkpoint:
            digest = hashlib.file_digest(checkpoint, "sha256").hexdigest()
        if digest.lower() != manifest["checkpointSha256"].lower():
            raise ValueError("D-FINE SEG weights do not match their metadata")

        default_source = Path(__file__).resolve().parents[2] / "New Model Trainer" / "model_training" / "third_party" / "D-FINE-seg"
        source = Path(source_root or os.getenv("DFINE_SEG_SOURCE", default_source)).resolve()
        if not (source / "src" / "infer" / "torch_model.py").is_file():
            raise FileNotFoundError(f"D-FINE SEG source not found: {source}")
        sys.path.insert(0, str(source))
        from src.infer.torch_model import Torch_model

        self.model = Torch_model(
            model_name=manifest["modelSize"], model_path=str(weights),
            n_outputs=len(labels), input_width=manifest["inputWidth"],
            input_height=manifest["inputHeight"], conf_thresh=0.5,
            keep_ratio=True, apply_nms=False, enable_mask_head=True,
            binarize_masks=False, device=device or inference_device(),
            task="segment",
        )
        state = torch.load(weights, map_location="cpu", weights_only=True)
        state.pop("decoder.anchors", None)
        state.pop("decoder.valid_mask", None)
        self.model.model.load_state_dict(state, strict=True)

    def predict(self, bgr, conf: float = 0.25, **_kwargs):
        import torch

        started = perf_counter()
        self.model.conf_threshs = [conf] * len(self.names)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        inputs, processed_sizes, original_sizes = self.model._prepare_inputs(rgb, bgr=False)
        with torch.inference_mode():
            raw = self.model._predict(inputs)
            result = self.model._postprocess(raw, processed_sizes, original_sizes)[0]
        labels = result["labels"]
        masks = result.get("masks")
        scores = result.get("scores")
        self.inference_calls += 1
        self.total_latency_ms += (perf_counter() - started) * 1000
        self.total_predictions += len(labels)
        if scores is not None:
            self.total_confidence += float(scores.sum().item())
        if masks is None or len(labels) == 0:
            return [SimpleNamespace(masks=None, boxes=None)]
        return [SimpleNamespace(
            masks=SimpleNamespace(data=masks),
            boxes=SimpleNamespace(cls=labels, conf=scores),
        )]
