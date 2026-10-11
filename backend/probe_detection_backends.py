"""Choose CPU detector runtime using the same trained RGB weights and frames."""
from pathlib import Path
import json
import time
import cv2
import numpy as np
import psutil
from scipy.optimize import linear_sum_assignment
from benchmark_timed_views import four_core_affinity
from export_detector import ExportDetector

ROOT=Path(__file__).resolve().parent


def run():
    psutil.Process().cpu_affinity(four_core_affinity()[0]);cv2.setNumThreads(1)
    path=next((ROOT.parent/'videos').glob('*13_05_49*'))
    cap=cv2.VideoCapture(str(path));cap.set(cv2.CAP_PROP_POS_MSEC,1400)
    ok,frame=cap.read();cap.release()
    if not ok:raise RuntimeError('Cannot read operation sample')
    rows=[];reference=None
    for backend in ('ncnn','onnx'):
        for threads in (1,2,3,4):
            model=ExportDetector('yolo_rgb','cpu',threads,backend=backend)
            model.predict_rows(frame);times=[]
            for _ in range(5):
                started=time.perf_counter();predictions=model.predict_rows(frame)
                times.append((time.perf_counter()-started)*1000)
            if reference is None:reference=predictions.copy()
            distances=np.abs(reference[:,None,:4]-predictions[None,:,:4]).max(axis=-1)
            i,j=linear_sum_assignment(distances)
            row=dict(backend=backend,threads=threads,median_ms=float(np.median(times)),samples_ms=times,
                detections=len(predictions),reference_detections=len(reference),matched_box_max_error_px=float(distances[i,j].max()),
                max_score_error=float(np.abs(reference[i,4]-predictions[j,4]).max()))
            rows.append(row);print(row,flush=True)
    output=ROOT/'diagnostics/cpu-optimization/detection_probe.json'
    output.write_text(json.dumps(dict(input_size=[640,640],cpu_only=True,rows=rows),indent=2),encoding='utf-8')


if __name__=='__main__':run()
