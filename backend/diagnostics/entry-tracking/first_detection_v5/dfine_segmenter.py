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


def make_fruit_tracker(device: str, detection_conf: float = .25):
    """Publish a fruit ID on its first accepted detection, including edge views."""
    from ultralytics.trackers.track_tracker import TRACKTRACK
    from ultralytics.utils import YAML, IterableSimpleNamespace
    from ultralytics.utils.checks import check_yaml

    config = IterableSimpleNamespace(**YAML.load(check_yaml("tracktrack.yaml")))
    config.device = device
    config.min_track_len = 1
    # Known edge tracks may continue through lower-confidence partial views.
    # Low-confidence entry is handled explicitly below; interior initialization
    # retains the library's stronger confidence requirement.
    config.track_low_thresh = min(config.track_low_thresh, detection_conf)
    config.penalty_p = 0.0
    return TRACKTRACK(config)


def suppress_duplicate_detections(rows, iou_threshold=.7):
    """Keep the strongest overlapping query for each fruit class before tracking."""
    if not len(rows):
        return rows
    keep=[]
    for category in np.unique(rows[:,5]):
        candidates=np.flatnonzero(rows[:,5]==category)
        candidates=candidates[np.argsort(rows[candidates,4])[::-1]]
        while len(candidates):
            index=int(candidates[0]);keep.append(index);candidates=candidates[1:]
            if not len(candidates):break
            box=rows[index,:4];others=rows[candidates,:4]
            intersection=np.maximum(0,np.minimum(others[:,2:],box[2:])-
                                     np.maximum(others[:,:2],box[:2])).prod(axis=1)
            area=np.maximum(0,box[2:]-box[:2]).prod()
            areas=np.maximum(0,others[:,2:]-others[:,:2]).prod(axis=1)
            iou=intersection/np.maximum(area+areas-intersection,1e-6)
            candidates=candidates[iou<=iou_threshold]
    return rows[sorted(keep)]


def associate_fruit_detections(tracker, rows, frame, typical_size=None, entry_conf=.25):
    """Associate clipped entries using virtual extents; return actual detected boxes.

    A thin visible arc expands rapidly as fruit enters. Its IoU with the next
    visible box can be tiny even for the same fruit. Full-sized virtual extents
    stabilize association only; they are never supplied as observed surface.
    """
    from ultralytics.engine.results import Boxes
    from ultralytics.trackers.track_tracker import TTSTrack
    from ultralytics.trackers.basetrack import TrackState

    rows=suppress_duplicate_detections(rows)
    height, width = frame.shape[:2]
    virtual = rows.copy()
    if len(rows):
        boxes = rows[:, :4]
        full = ((boxes[:, 0] > 2) & (boxes[:, 1] > 2) &
                (boxes[:, 2] < width-2) & (boxes[:, 3] < height-2) &
                (rows[:, 4] >= .6))
        dimensions = boxes[full, 2:] - boxes[full, :2]
        if len(dimensions):
            measured = np.median(dimensions, axis=0)
            typical_size = measured if typical_size is None else .9*np.asarray(typical_size)+.1*measured
        if typical_size is None:
            # Bootstrap an initially empty scene from a circular-arc estimate.
            # This is an association prior, not an inferred observed silhouette.
            for position in np.argsort(rows[:, 4])[::-1]:
                left, top, right, bottom = boxes[position]
                visible_w, visible_h = right-left, bottom-top
                if (top <= 2 or bottom >= height-2) and visible_h > 0:
                    diameter = visible_w**2/(4*visible_h)+visible_h if visible_h < visible_w/2 else visible_w
                elif (left <= 2 or right >= width-2) and visible_w > 0:
                    diameter = visible_h**2/(4*visible_w)+visible_w if visible_w < visible_h/2 else visible_h
                else:
                    continue
                diameter = min(max(diameter, visible_w, visible_h), min(width,height))
                typical_size = np.array([diameter, diameter], np.float32)
                break
        if typical_size is not None:
            expected_w, expected_h = typical_size
            for box in virtual[:, :4]:
                left, top, right, bottom = box.copy()
                clips_x = left <= 2 or right >= width-2
                clips_y = top <= 2 or bottom >= height-2
                # Retain the same association scale when a smaller-than-median
                # fruit becomes fully visible. Otherwise its virtual edge box
                # suddenly shrinks and can lose the identity at that boundary.
                extent_w, extent_h = max(right-left, expected_w), max(bottom-top, expected_h)
                if clips_x:
                    if left <= 2 and right < width-2: box[0] = right-extent_w
                    elif right >= width-2 and left > 2: box[2] = left+extent_w
                else:
                    center_x = (left+right)/2
                    box[0], box[2] = center_x-extent_w/2, center_x+extent_w/2
                if clips_y:
                    if top <= 2 and bottom < height-2: box[1] = bottom-extent_h
                    elif bottom >= height-2 and top > 2: box[3] = top+extent_h
                else:
                    center_y = (top+bottom)/2
                    box[1], box[3] = center_y-extent_h/2, center_y+extent_h/2
    tracked = tracker.update(Boxes(virtual, (height, width)), img=frame)
    tracked = tracked if len(tracked) else np.empty((0, 8), np.float32)
    assigned = set(tracked[:, 7].astype(int))
    # Start accepted low-confidence detections at the physical image boundary.
    # Keep the strong initialization threshold for previously unseen interior
    # boxes, where lowering it created many spurious short-lived identities.
    for index in np.argsort(rows[:,4])[::-1]:
        if index in assigned or rows[index,4] < entry_conf:
            continue
        left,top,right,bottom=rows[index,:4]
        if not (left<=2 or top<=2 or right>=width-2 or bottom>=height-2):
            continue
        candidate=virtual[index,:4]
        active=[track.xyxy for track in tracker.tracked_stracks+tracker.lost_stracks
                if track.state in (TrackState.Tracked,TrackState.Lost)]
        if active:
            boxes=np.asarray(active)
            intersection=np.maximum(0,np.minimum(boxes[:,2:],candidate[2:])-
                                     np.maximum(boxes[:,:2],candidate[:2])).prod(axis=1)
            area=np.maximum(0,candidate[2:]-candidate[:2]).prod()
            areas=np.maximum(0,boxes[:,2:]-boxes[:,:2]).prod(axis=1)
            if np.any(intersection/np.maximum(area+areas-intersection,1e-6)>tracker.tai_thr):
                continue
        x1,y1,x2,y2=candidate
        track=TTSTrack(np.array([(x1+x2)/2,(y1+y2)/2,x2-x1,y2-y1,index],np.float32),
                       float(rows[index,4]),int(rows[index,5]))
        track.min_track_len=1
        track.activate(tracker.kalman_filter,tracker.frame_id)
        tracker.tracked_stracks.append(track)
        tracked=np.vstack((tracked,np.asarray(track.result,np.float32)))
    if not len(tracked):
        return np.empty((0, 7), np.float32), typical_size
    indices = tracked[:, 7].astype(int)
    if np.any(indices < 0) or np.any(indices >= len(rows)):
        raise RuntimeError('Tracker returned an invalid source-detection index')
    actual = tracked[:, :7].copy()
    actual[:, :4] = rows[indices, :4]
    return actual, typical_size


class DfineDetector:
    """Run the local D-FINE nano checkpoint and feed its boxes to TrackTrack."""

    def __init__(self, weights: str | Path, device: str):
        runner_python = Path(__file__).resolve().parents[2] / "Inference Runner" / "backend" / "python"
        if not (runner_python / "dfine_checkpoint.py").is_file():
            raise FileNotFoundError(f"D-FINE checkpoint loader is missing: {runner_python}")
        sys.path.insert(0, str(runner_python))
        from dfine_checkpoint import load_dfine_nano

        self.processor, self.model, labels = load_dfine_nano(Path(weights), device)
        self.names = dict(enumerate(labels))
        self.device = device
        self.tracker = make_fruit_tracker(device)
        self.tracking_size_px = None
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
        self.last_detection_rows = rows.copy()
        tracked_rows, self.tracking_size_px = associate_fruit_detections(
            self.tracker, rows, frame, self.tracking_size_px, entry_conf=conf)
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
