"""Measure silhouette speed/agreement on raw crops from moving video sections."""
from pathlib import Path
from types import SimpleNamespace
import json
import time
import cv2
import numpy as np
import psutil
from benchmark_timed_views import four_core_affinity
from export_detector import ExportDetector
from algorithm import _grabcut
from nine_view import hsv_fruit_mask

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'diagnostics/cpu-optimization'


def run():
    affinity,method=four_core_affinity();psutil.Process().cpu_affinity(affinity);cv2.setNumThreads(1)
    detector=ExportDetector('yolo_rgb','cpu',2,backend='onnx')
    rows=[];tiles=[]
    for stamp in ('13_05_49','13_35_37','13_52_31'):
        path=next((ROOT.parent/'videos').glob(f'*{stamp}*'))
        cap=cv2.VideoCapture(str(path));cap.set(cv2.CAP_PROP_POS_MSEC,1400)
        ok,frame=cap.read();cap.release()
        if not ok:raise RuntimeError(path)
        taken=0
        for detection in sorted(detector.predict_rows(frame),key=lambda r:-r[4]):
            x0,y0,x1,y1=map(int,detection[:4]);h,w=frame.shape[:2]
            if min(x0,y0)<=2 or x1>=w-2 or y1>=h-2:continue
            pad=round(max(x1-x0,y1-y0)*.12)
            l,t=max(0,x0-pad),max(0,y0-pad);r,b=min(w,x1+pad),min(h,y1+pad)
            image=frame[t:b,l:r].copy();box=(x0-l,y0-t,x1-l,y1-t)
            started=time.perf_counter();a=_grabcut(image,3,box)>0
            grabcut_ms=(time.perf_counter()-started)*1000
            started=time.perf_counter();b=hsv_fruit_mask(SimpleNamespace(image=image,box=box))>0
            hsv_ms=(time.perf_counter()-started)*1000
            union=np.count_nonzero(a|b)
            rows.append(dict(video=path.name,source_seconds=1.4,box=[x0,y0,x1,y1],
                grabcut_ms=grabcut_ms,hsv_ms=hsv_ms,
                mask_iou=np.count_nonzero(a&b)/max(1,union),
                grabcut_pixels=int(a.sum()),hsv_pixels=int(b.sum())))
            if taken<2:
                def tile(value):return cv2.resize(value,(200,180))
                tiles.append(np.hstack((tile(image),tile(cv2.bitwise_and(image,image,mask=a.astype(np.uint8))),
                    tile(cv2.bitwise_and(image,image,mask=b.astype(np.uint8))))))
            taken+=1
            if taken==10:break
    report=dict(cpu_affinity=affinity,affinity_method=method,rows=rows,
        scope='Silhouette agreement with GrabCut, not labelled silhouette or defect accuracy',
        median_grabcut_ms=float(np.median([r['grabcut_ms'] for r in rows])),
        median_hsv_ms=float(np.median([r['hsv_ms'] for r in rows])),
        median_iou=float(np.median([r['mask_iou'] for r in rows])),
        minimum_iou=min(r['mask_iou'] for r in rows))
    (OUT/'fruit_mask_probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    cv2.imwrite(str(OUT/'fruit_masks.jpg'),np.vstack(tiles))
    print({k:v for k,v in report.items() if k!='rows'})


if __name__=='__main__':run()
