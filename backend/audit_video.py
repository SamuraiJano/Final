"""Capture real tracker evidence for inspecting reconstruction failures."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from algorithm import NaartjiePipeline, Settings, fit_spheroid
from dfine_segmenter import DfineDetector, inference_device


class NoDefects:
    names = {0: 'diagnostic'}

    def predict(self, *args, **kwargs):
        return [SimpleNamespace(masks=None, boxes=None)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video', type=Path)
    parser.add_argument('--frames', type=int, default=240)
    parser.add_argument('--out', type=Path, default=Path('backend/diagnostics/current-upload'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    detector = DfineDetector(Path(__file__).parent / 'models/D-FINE/detection/best_stg1.pth', inference_device())
    pipeline = NaartjiePipeline(NoDefects(), detector, capture_stride_frames=3)
    selected = {1, 14, 108, 123}
    capture = cv2.VideoCapture(str(args.video))
    records = []
    try:
        for index in range(args.frames):
            ok, frame = capture.read()
            if not ok:
                break
            boxes = detector.track(frame)[0].boxes
            rows = []
            for row in boxes.data:
                x1, y1, x2, y2, track_id, confidence, category = map(float, row)
                track_id = int(track_id)
                rows.append([track_id, x1, y1, x2, y2, confidence])
                if track_id in selected:
                    try:
                        pipeline.add_tracked_detection(frame, track_id, (x1, y1, x2, y2), index)
                    except RuntimeError:
                        pass
            records.append({'frame': index, 'tracks': rows})
            if index % 30 == 0:
                print('frame', index, 'tracks', len(rows), flush=True)
    finally:
        capture.release()
    (args.out / 'tracks.json').write_text(json.dumps(records), encoding='utf-8')
    summary = {'tracker': type(detector.tracker).__name__, 'reid': detector.tracker.args.with_reid, 'tracks': {}}
    for track_id, views in pipeline.views_by_id.items():
        folder = args.out / str(track_id)
        folder.mkdir(exist_ok=True)
        manifest = []
        for i, view in enumerate(views):
            np.savez_compressed(folder / f'{i}.npz', image=view.image, mask=view.object_mask)
            manifest.append({'file': f'{i}.npz', 'frame': view.frame_index, 'bbox': view.fruit_bbox})
        (folder / 'views.json').write_text(json.dumps(manifest), encoding='utf-8')
        outcomes = {}
        for stride in (1, 5):
            for axis in ('x', 'y'):
                for direction in (-1, 1):
                    key = f'frames_{3*stride}_{axis}_{direction}'
                    try:
                        model = fit_spheroid(views[::stride], Settings(spheroid_type='auto', rotation_axis=axis, rotation_direction=direction))
                        outcomes[key] = {'A': model.A, 'B': model.B}
                    except (ValueError, RuntimeError) as error:
                        outcomes[key] = str(error)
        summary['tracks'][str(track_id)] = {'views': len(views), 'first_frame': views[0].frame_index, 'last_frame': views[-1].frame_index, 'fits': outcomes}
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
