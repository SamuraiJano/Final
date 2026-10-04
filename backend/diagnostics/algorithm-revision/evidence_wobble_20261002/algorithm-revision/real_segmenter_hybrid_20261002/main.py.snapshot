"""Video upload API for the Python fruit mapping pipeline."""

import json
import hashlib
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import cv2
from fastapi import FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from algorithm import MappingError, NaartjiePipeline, Settings
from dfine_segmenter import DfineDetector, DfineSegmenter, inference_device


BACKEND = Path(__file__).resolve().parent
MODELS = BACKEND / "models" / "D-FINE"
RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)
SOURCE_SNAPSHOTS = {name: (BACKEND/name).read_bytes()
                    for name in ('algorithm.py','main.py','dfine_segmenter.py')}
ALGORITHM_SHA256 = hashlib.sha256(SOURCE_SNAPSHOTS['algorithm.py']).hexdigest()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/results", StaticFiles(directory=RESULTS), name="results")


class CameraFeed:
    """Keep one capture open for the preview and optional live inspection."""

    def __init__(self) -> None:
        self.source = os.getenv("FRUIT_CAMERA_SOURCE", "").strip()
        self.condition = threading.Condition()
        self.started = False
        self.frame: bytes | None = None
        self.raw_frame = None
        self.sequence = 0
        self.last_frame_at: datetime | None = None

    def start(self) -> None:
        if not self.source:
            return
        with self.condition:
            if self.started:
                return
            self.started = True
        threading.Thread(target=self._capture, name="fruit-camera", daemon=True).start()

    def _capture(self) -> None:
        source = int(self.source) if self.source.isdecimal() else self.source
        while True:
            capture = cv2.VideoCapture(source)
            if not capture.isOpened():
                capture.release()
                time.sleep(2)
                continue
            try:
                while True:
                    ok, image = capture.read()
                    if not ok:
                        break
                    raw_image = image
                    height, width = image.shape[:2]
                    if width > 960:
                        image = cv2.resize(image, (960, max(1, round(height * 960 / width))))
                    encoded, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 78])
                    if encoded:
                        with self.condition:
                            self.frame = jpeg.tobytes()
                            self.raw_frame = raw_image
                            self.sequence += 1
                            self.last_frame_at = datetime.now(timezone.utc)
                            self.condition.notify_all()
                    time.sleep(1 / 12)
            finally:
                capture.release()
            time.sleep(2)

    def status(self) -> dict:
        self.start()
        with self.condition:
            last = self.last_frame_at
        connected = bool(last and (datetime.now(timezone.utc) - last).total_seconds() < 3)
        return {
            "configured": bool(self.source),
            "connected": connected,
            "source": (f"USB camera {self.source}" if self.source.isdecimal() else "Network camera")
                      if self.source else None,
            "last_frame_at": last.isoformat() if last else None,
        }

    def stream(self):
        self.start()
        sequence = 0
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.sequence > sequence, timeout=5)
                if self.sequence == sequence or self.frame is None:
                    continue
                sequence, frame = self.sequence, self.frame
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"


camera = CameraFeed()
analysis_lock = threading.Lock()
analysis_state_lock = threading.Lock()
analysis_state = {"state": "idle", "run_id": None, "frames_processed": 0,
                  "frames_total": None, "error": None}
analysis_control_lock = threading.Lock()
analysis_cancel_event = threading.Event()
active_analysis_id: str | None = None
pending_cancellations: dict[str, float] = {}
refresh_lock = threading.Lock()
refresh_pending = False


def _set_analysis_state(**changes) -> None:
    with analysis_state_lock:
        analysis_state.update(changes)


class AnalysisCancelled(Exception):
    """The operator stopped a video run before it could save a report."""


def _check_analysis_cancelled() -> None:
    if analysis_cancel_event.is_set():
        raise AnalysisCancelled()


def _model_metrics(model: object) -> dict:
    calls = model.inference_calls
    predictions = model.total_predictions
    return {
        "calls": calls,
        "instances": predictions,
        "mean_latency_ms": round(model.total_latency_ms / calls, 1) if calls else None,
        "mean_confidence": round(model.total_confidence / predictions, 3) if predictions else None,
    }


def _make_pipeline(capture_stride_frames: int = 3,
                   max_views_per_track: int = 120) -> tuple[NaartjiePipeline, DfineDetector, DfineSegmenter]:
    detector_weights = Path(os.getenv(
        "FRUIT_DETECTOR_WEIGHTS", MODELS / "detection" / "best_stg1.pth"
    ))
    segmenter_weights = Path(os.getenv(
        "DFINE_SEG_WEIGHTS", MODELS / "segmentation" / "model.pt"
    ))
    if not detector_weights.is_file() or not segmenter_weights.is_file():
        raise FileNotFoundError("D-FINE model weights are missing from backend/models/D-FINE")

    device = inference_device()
    segmenter = DfineSegmenter(segmenter_weights, device=device)
    detector = DfineDetector(detector_weights, device=device)
    pipeline = NaartjiePipeline(
        segmenter, detector,
        settings=Settings(spheroid_type="auto", defect_observations_complete=True,
                          select_rotating_views=True,
                          native_matching_cost="green_mad",
                          minimum_view_rotation_deg=8,
                          maximum_view_index_gap=capture_stride_frames,
                          bidirectional_matching=True,
                          rotation_axis=os.getenv("FRUIT_ROTATION_AXIS", "x"),
                          rotation_direction=int(os.getenv("FRUIT_ROTATION_DIRECTION", "1")),
                          minimum_rotation_coverage_deg=0,
                          minimum_longitude_coverage_deg=350,
                          maximum_pair_gap_deg=55),
        capture_stride_frames=capture_stride_frames,
        max_views_per_track=max_views_per_track,
        defer_defect_segmentation=True,
    )
    return pipeline, detector, segmenter


def _save_view_evidence(views, folder: Path, url_prefix: str) -> list[dict]:
    """Save representative source images for reviewing both passes and failures."""
    candidates=[view for view in views if view.defect_masks] or views
    evidence=[]
    for index in sorted({0,len(candidates)//2,len(candidates)-1}):
        view=candidates[index]
        stem=f'frame_{view.frame_index:05d}'
        cv2.imwrite(str(folder/f'{stem}_crop.png'),view.image)
        cv2.imwrite(str(folder/f'{stem}_fruit_mask.png'),view.object_mask*255)
        overlay=view.image.copy()
        color=overlay.copy(); color[:]=(0,0,255)
        tinted=cv2.addWeighted(overlay,.5,color,.5,0)
        for mask in view.defect_masks.values():
            overlay[mask>0]=tinted[mask>0]
        contours,_=cv2.findContours(view.object_mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay,contours,-1,(0,255,0),1)
        cv2.imwrite(str(folder/f'{stem}_overlay.png'),overlay)
        evidence.append({'frame':view.frame_index,'crop':f'{url_prefix}/{stem}_crop.png',
                         'fruit_mask':f'{url_prefix}/{stem}_fruit_mask.png',
                         'overlay':f'{url_prefix}/{stem}_overlay.png',
                         'defect_inference_ran':bool(view.defect_masks)})
    return evidence


def _finish_track(pipeline: NaartjiePipeline, track_id: int, output: Path) -> dict | None:
    views = pipeline.views_by_id.get(track_id, [])
    rejected = pipeline.rejected_views_by_id.get(track_id, {}).copy()
    history = getattr(pipeline, 'tracking_history_by_id', {}).get(track_id, []).copy()
    images = getattr(pipeline, 'tracking_images_by_id', {}).get(track_id, {}).copy()
    tracking = {}
    if history:
        tracking = {'first_seen_frame': history[0]['frame'],
                    'last_seen_frame': history[-1]['frame'],
                    'tracked_frames': len(history),
                    'tracking_history': history,
                    'tracking_evidence': []}
        folder = output / str(track_id)
        folder.mkdir(parents=True, exist_ok=True)
        for kind, (frame_index, crop) in images.items():
            filename = f'tracking_{kind}_frame_{frame_index:05d}.png'
            cv2.imwrite(str(folder / filename), crop)
            tracking['tracking_evidence'].append({'stage': kind, 'frame': frame_index,
                'crop': f'/results/{output.name}/{track_id}/{filename}'})
    if not views:
        pipeline.drop_track(track_id)
        if rejected or history:
            row = {"track_id": track_id, "views": 0, "status": "mapping_failed",
                   "grade": None, "reason": "No complete, usable fruit silhouettes were captured.",
                   "rejected_views": rejected, **tracking}
            if history:
                (folder / 'result.json').write_text(json.dumps(row, indent=2), encoding='utf-8')
            return row
        return None
    row = {"track_id": track_id, "views": len(views),
           "view_frames": [view.frame_index for view in views], "rejected_views": rejected,
           **tracking}
    folder = output / str(track_id)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if len(views) < 2:
            raise MappingError("At least two views are required")
        mapped = pipeline.finish_track(track_id)
        folder = output / str(track_id)
        folder.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(folder / "surface_map.png"), mapped.bgr_map)
        cv2.imwrite(str(folder / "observed.png"), mapped.observed_mask * 255)
        row.update(
            status=mapped.status, grade=mapped.grade,
            model_type=mapped.model_type,
            estimated_radii_px=mapped.estimated_radii_px,
            rotation_coverage_deg=mapped.rotation_coverage_deg,
            map_longitude_span_deg=mapped.map_longitude_span_deg,
            mapped_view_frames=mapped.view_frames,
            discarded_view_frames=mapped.discarded_view_frames,
            view_selection=mapped.selection_diagnostics,
            observed_surface_pct=mapped.observed_surface_pct,
            observed_longitude_deg=mapped.observed_longitude_deg,
            defect_pct_of_observed=mapped.defect_pct_of_observed,
            pair_rotations_deg=mapped.pair_rotations_deg,
            pair_rotation_vectors_deg=mapped.pair_rotation_vectors_deg,
            pair_errors=mapped.pair_errors,
            surface_map=f"/results/{output.name}/{track_id}/surface_map.png",
            observed_mask=f"/results/{output.name}/{track_id}/observed.png",
            defect_maps={},
        )
        if mapped.grade is None:
            row["reason"] = {
                "insufficient_surface_coverage": "Too little of the surface was observed to assign a class.",
                "insufficient_rotation_coverage": "The fruit did not rotate far enough for a reliable class.",
                "insufficient_longitude_coverage": "The views do not cover enough of the fruit's circumference for a reliable class.",
                "missing_defect_masks": "Defect segmentation did not provide enough evidence to assign a class.",
                "grade_thresholds_not_configured": "Quality class thresholds are not configured.",
            }.get(mapped.status, "The available views were insufficient to assign a class.")
        for name, mask in mapped.defect_maps.items():
            filename = f"defect_{name}.png"
            cv2.imwrite(str(folder / filename), mask * 255)
            row["defect_maps"][name] = f"/results/{output.name}/{track_id}/{filename}"
    except (MappingError, ValueError) as error:
        row.update(status="mapping_failed", grade=None, reason=str(error))
        row['view_selection'] = getattr(error, 'diagnostics', [])
        pipeline.drop_track(track_id)
    row['view_evidence']=_save_view_evidence(views,folder,f'/results/{output.name}/{track_id}')
    (folder / 'result.json').write_text(json.dumps(row,indent=2),encoding='utf-8')
    return row


def _analysis_metrics(frames: int, started: float, detector: DfineDetector,
                      segmenter: DfineSegmenter, fps: float | None = None) -> dict:
    return {
        "frames": frames,
        "video_duration_sec": round(frames / fps, 1) if fps and fps > 0 else None,
        "analysis_duration_sec": round(time.perf_counter() - started, 1),
        "detection": _model_metrics(detector),
        "segmentation": _model_metrics(segmenter),
    }


def _write_report(output: Path, report: dict) -> None:
    temporary = output / "report.tmp"
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output / "report.json")


def analyze_video(path: Path, output: Path, metrics: dict | None = None,
                  progress=None) -> list[dict]:
    """Track each fruit through a video and save its completed surface map."""
    started = time.perf_counter()
    for name,payload in SOURCE_SNAPSHOTS.items():
        (output/f'{name}.snapshot').write_bytes(payload)
    _check_analysis_cancelled()
    if progress:
        progress(state="loading_models")
    pipeline, detector, segmenter = _make_pipeline(
        capture_stride_frames=1, max_views_per_track=120)
    _check_analysis_cancelled()
    video = cv2.VideoCapture(str(path))
    if not video.isOpened():
        raise ValueError("Could not open the uploaded video")

    results = []

    def finish(track_id: int) -> None:
        _check_analysis_cancelled()
        row = _finish_track(pipeline, track_id, output)
        _check_analysis_cancelled()
        if row is not None:
            results.append(row)

    try:
        frame_index = 0
        fps = video.get(cv2.CAP_PROP_FPS)
        total = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        previous_sample = None
        sampled_frames = 0
        if progress:
            progress(state="processing", frames_total=total if total > 0 else None)
        while True:
            _check_analysis_cancelled()
            ok, frame = video.read()
            if not ok:
                break
            gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (320, 180),
                              interpolation=cv2.INTER_AREA)
            capture_views = (previous_sample is None or
                             cv2.mean(cv2.absdiff(gray, previous_sample))[0] >= 0.1)
            if capture_views:
                previous_sample = gray
                sampled_frames += 1
            pipeline.process_frame(frame, frame_index, capture_views=capture_views)
            _check_analysis_cancelled()
            for track_id, last_seen in list(pipeline.last_seen_frame.items()):
                if frame_index - last_seen > 30:
                    finish(track_id)
            frame_index += 1
            if progress and frame_index % 10 == 0:
                progress(frames_processed=frame_index)
        if frame_index == 0:
            raise ValueError("The video contains no readable frames")
        _check_analysis_cancelled()
        if progress:
            progress(state="building_maps", frames_processed=frame_index)
        for track_id in list(pipeline.last_seen_frame):
            finish(track_id)
        _check_analysis_cancelled()
    finally:
        video.release()
    if metrics is not None:
        metrics.update(_analysis_metrics(frame_index, started, detector, segmenter, fps))
        metrics.update(sampled_frames=sampled_frames, duplicate_frames=frame_index-sampled_frames,
                       algorithm_sha256=ALGORITHM_SHA256,
                       deferred_defect_segmentation=pipeline.defer_defect_segmentation,
                       rotation_axis=pipeline.settings.rotation_axis,
                       rotation_direction=pipeline.settings.rotation_direction,
                       tracker="TrackTrack", reid=detector.tracker.args.with_reid,
                       tracker_min_track_len=detector.tracker.min_track_len,
                       geometry_settings=asdict(pipeline.settings),
                       sampling={"strategy": "content_change", "difference_threshold": 0.1,
                                 "max_views_per_track": pipeline.max_views_per_track})
    return results


class LiveInspector:
    """Analyze the configured camera in one background inspection session."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state = "idle"
        self.job_id: str | None = None
        self.error: str | None = None
        self.stop_event = threading.Event()

    def status(self) -> dict:
        with self.lock:
            return {"state": self.state, "job_id": self.job_id, "error": self.error}

    def start(self) -> dict:
        if not camera.source:
            raise HTTPException(409, "Configure FRUIT_CAMERA_SOURCE before starting live inspection")
        if not analysis_lock.acquire(blocking=False):
            raise HTTPException(409, "Another video analysis is already running")
        with self.lock:
            self.state = "starting"
            self.job_id = uuid4().hex
            self.error = None
            self.stop_event = threading.Event()
            job_id = self.job_id
        camera.start()
        try:
            threading.Thread(target=self._run, args=(job_id,), name="live-inspection", daemon=True).start()
        except Exception:
            analysis_lock.release()
            raise
        return self.status()

    def stop(self) -> dict:
        with self.lock:
            if self.state in {"starting", "running"}:
                self.stop_event.set()
                self.state = "stopping"
        return self.status()

    def _run(self, job_id: str) -> None:
        output = RESULTS / job_id
        report = {
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_name": "Live camera",
            "mode": "live",
            "status": "starting",
            "metrics": {},
            "fruits": [],
        }
        try:
            output.mkdir(exist_ok=True)
            _write_report(output, report)
            started = time.perf_counter()
            pipeline, detector, segmenter = _make_pipeline()
            with self.lock:
                self.state = "running"
            report["status"] = "running"
            frame_index = 0
            sequence = 0
            last_save = 0.0
            while not self.stop_event.is_set():
                with camera.condition:
                    camera.condition.wait_for(
                        lambda: camera.sequence > sequence or self.stop_event.is_set(), timeout=2
                    )
                    if camera.sequence == sequence or camera.raw_frame is None:
                        continue
                    sequence, frame = camera.sequence, camera.raw_frame.copy()
                pipeline.process_frame(frame, frame_index)
                for track_id, last_seen in list(pipeline.last_seen_frame.items()):
                    if frame_index - last_seen > 20:
                        row = _finish_track(pipeline, track_id, output)
                        if row is not None:
                            report["fruits"].append(row)
                frame_index += 1
                if time.perf_counter() - last_save > 2:
                    report["metrics"] = _analysis_metrics(frame_index, started, detector, segmenter)
                    _write_report(output, report)
                    last_save = time.perf_counter()
            for track_id in list(pipeline.last_seen_frame):
                row = _finish_track(pipeline, track_id, output)
                if row is not None:
                    report["fruits"].append(row)
            report["metrics"] = _analysis_metrics(frame_index, started, detector, segmenter)
            report["status"] = "stopped"
            _write_report(output, report)
            with self.lock:
                self.state = "stopped"
        except Exception as error:
            report["status"] = "error"
            report["error"] = str(error)
            if output.is_dir():
                _write_report(output, report)
            with self.lock:
                self.state = "error"
                self.error = str(error)
        finally:
            analysis_lock.release()


live_inspector = LiveInspector()


@app.get("/api/health")
def health() -> dict:
    import torch

    detector = Path(os.getenv(
        "FRUIT_DETECTOR_WEIGHTS", MODELS / "detection" / "best_stg1.pth"
    ))
    segmenter = Path(os.getenv(
        "DFINE_SEG_WEIGHTS", MODELS / "segmentation" / "model.pt"
    ))
    return {
        "status": "ok",
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "requested_device": os.getenv("FRUIT_DEVICE", "cuda"),
        "models_present": {
            "detection": detector.is_file(),
            "segmentation": segmenter.is_file(),
            "segmentation_metadata": segmenter.with_suffix(".dfineseg.json").is_file(),
        },
    }


@app.get("/api/analysis/status")
def analysis_status() -> dict:
    with analysis_state_lock:
        return analysis_state.copy()


@app.post("/api/analysis/stop")
def stop_analysis(x_analysis_id: str | None = Header(default=None)) -> dict:
    if not x_analysis_id or len(x_analysis_id) > 64:
        raise HTTPException(400, "A valid analysis ID is required")
    with analysis_control_lock:
        if active_analysis_id == x_analysis_id:
            analysis_cancel_event.set()
            _set_analysis_state(state="cancelling")
        else:
            with analysis_state_lock:
                if (analysis_state["run_id"] == x_analysis_id and
                        analysis_state["state"] in {"complete", "cancelled", "error"}):
                    return {"state": analysis_state["state"], "run_id": x_analysis_id}
            now = time.monotonic()
            for run_id, created in list(pending_cancellations.items()):
                if now - created > 600:
                    del pending_cancellations[run_id]
            if len(pending_cancellations) >= 64:
                del pending_cancellations[next(iter(pending_cancellations))]
            pending_cancellations[x_analysis_id] = now
    return {"state": "cancelling", "run_id": x_analysis_id}


def _check_refresh_token(token: str | None) -> None:
    expected = os.getenv("FRUIT_REFRESH_TOKEN")
    if not expected or token != expected:
        raise HTTPException(403, "Backend refresh is only available through the local app launcher")


@app.post("/api/backend/prepare-refresh")
def prepare_backend_refresh(x_backend_refresh_token: str | None = Header(default=None)) -> dict:
    """Reserve the inference slot until the local launcher restarts this process."""
    global refresh_pending
    _check_refresh_token(x_backend_refresh_token)
    with refresh_lock:
        if refresh_pending:
            raise HTTPException(409, "Backend refresh is already in progress")
        if not analysis_lock.acquire(blocking=False):
            raise HTTPException(409, "An inference run is still active")
        refresh_pending = True
    _set_analysis_state(state="refreshing", frames_processed=0, frames_total=None, error=None)
    return {"status": "ready"}


@app.post("/api/backend/cancel-refresh")
def cancel_backend_refresh(x_backend_refresh_token: str | None = Header(default=None)) -> dict:
    global refresh_pending
    _check_refresh_token(x_backend_refresh_token)
    with refresh_lock:
        if refresh_pending:
            refresh_pending = False
            analysis_lock.release()
            _set_analysis_state(state="idle", frames_processed=0, frames_total=None, error=None)
    return {"status": "cancelled"}


@app.get("/api/camera/status")
def camera_status() -> dict:
    return camera.status()


@app.get("/api/camera/stream")
def camera_stream() -> StreamingResponse:
    if not camera.source:
        raise HTTPException(503, "Set FRUIT_CAMERA_SOURCE to a camera index or stream URL")
    return StreamingResponse(
        camera.stream(), media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/live/status")
def live_status() -> dict:
    return live_inspector.status()


@app.post("/api/live/start")
def live_start() -> dict:
    return live_inspector.start()


@app.post("/api/live/stop")
def live_stop() -> dict:
    return live_inspector.stop()


@app.get("/api/dashboard")
def dashboard() -> dict:
    reports = []
    for path in RESULTS.glob("*/report.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report, dict) or not isinstance(report.get("fruits"), list):
                continue
            report.setdefault("job_id", path.parent.name)
            report.setdefault(
                "created_at", datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            )
            reports.append(report)
        except (OSError, ValueError, TypeError):
            continue
    reports.sort(key=lambda report: report["created_at"], reverse=True)
    counts = {"Class 1": 0, "Class 2": 0, "Class 3": 0, "ungraded": 0}
    recent = []
    for report in reports:
        for fruit in report["fruits"]:
            grade = fruit.get("grade")
            counts[grade if grade in counts else "ungraded"] += 1
            # Filtering happens in the dashboard. Truncating before filtering
            # hid grades whenever the first 60 completed tracks were Review.
            # Keep bulky motion diagnostics in the downloadable report.
            detail_only = {"view_selection", "pair_rotation_vectors_deg",
                           "pair_rotations_deg", "pair_errors", "view_frames",
                           "discarded_view_frames", "tracking_history"}
            recent.append({
                **{key: value for key, value in fruit.items() if key not in detail_only},
                "job_id": report["job_id"],
                "created_at": report["created_at"],
                "source_name": report.get("source_name"),
            })
    return {
        "summary": {
            "runs": len(reports),
            "fruit_count": sum(counts.values()),
            "classes": counts,
        },
        "latest_run": ({key: reports[0].get(key) for key in
                        ("job_id", "created_at", "source_name", "mode", "status", "metrics")}) if reports else None,
        "recent_fruits": recent,
    }


@app.post("/api/analyze-video")
def analyze_upload(video: UploadFile,
                   x_analysis_id: str | None = Header(default=None)) -> dict:
    if not video.filename or Path(video.filename).suffix.lower() not in {".mp4", ".avi", ".mov", ".mkv"}:
        raise HTTPException(400, "Upload an MP4, AVI, MOV, or MKV video")
    if x_analysis_id is not None and (not x_analysis_id or len(x_analysis_id) > 64):
        raise HTTPException(400, "A valid analysis ID is required")
    if not analysis_lock.acquire(blocking=False):
        raise HTTPException(409, "Another video analysis is already running")
    global active_analysis_id
    run_id = x_analysis_id or uuid4().hex
    with analysis_control_lock:
        active_analysis_id = run_id
        analysis_cancel_event.clear()
        if pending_cancellations.pop(run_id, None) is not None:
            analysis_cancel_event.set()
    _set_analysis_state(state="uploading", run_id=run_id,
                        frames_processed=0, frames_total=None, error=None)
    temporary = None
    output = None
    try:
        _check_analysis_cancelled()
        job_id = uuid4().hex
        output = RESULTS / job_id
        output.mkdir()
        temporary = tempfile.NamedTemporaryFile(suffix=Path(video.filename).suffix, delete=False)
        with temporary:
            while chunk := video.file.read(1024 * 1024):
                _check_analysis_cancelled()
                temporary.write(chunk)
        _check_analysis_cancelled()
        metrics = {}
        fruits = analyze_video(Path(temporary.name), output, metrics, _set_analysis_state)
        _check_analysis_cancelled()
        report = {
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_name": Path(video.filename).name,
            "metrics": metrics,
            "fruits": fruits,
        }
        _write_report(output, report)
        with analysis_control_lock:
            _check_analysis_cancelled()
            active_analysis_id = None
            _set_analysis_state(state="complete", error=None)
        return report
    except AnalysisCancelled:
        if output is not None:
            shutil.rmtree(output, ignore_errors=True)
        with analysis_control_lock:
            active_analysis_id = None
            _set_analysis_state(state="cancelled", error=None)
        return {"status": "cancelled", "run_id": run_id}
    except RuntimeError as error:
        with analysis_control_lock:
            active_analysis_id = None
            _set_analysis_state(state="error", error=str(error))
        raise HTTPException(503, str(error)) from error
    except (FileNotFoundError, ValueError) as error:
        with analysis_control_lock:
            active_analysis_id = None
            _set_analysis_state(state="error", error=str(error))
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        with analysis_control_lock:
            active_analysis_id = None
            _set_analysis_state(state="error", error=str(error))
        raise
    finally:
        with analysis_control_lock:
            if active_analysis_id == run_id:
                active_analysis_id = None
            analysis_cancel_event.clear()
        video.file.close()
        if temporary is not None:
            Path(temporary.name).unlink(missing_ok=True)
        analysis_lock.release()
