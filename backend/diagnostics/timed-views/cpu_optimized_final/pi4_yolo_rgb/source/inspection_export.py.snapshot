"""Nine-view evidence encoding, outside the model/capture workers."""
from pathlib import Path
import json
import os
import time
import cv2
import numpy as np
from map_visualization import render_defect_overlay


def write_nine_view(frozen, track_id, output):
    started=time.perf_counter()
    row = dict(frozen.nine_view_result)
    folder = output / str(track_id)
    folder.mkdir(parents=True, exist_ok=True)
    prefix = f'/results/{output.name}/{track_id}'
    evidence, tiles = [], []
    full = getattr(frozen, 'evidence_level', 'full') == 'full'
    row['evidence_level'] = 'full' if full else 'contact_sheet'
    for view in sorted(frozen.nine_view_images, key=lambda v: v.frame):
        stem = f'bin_{view.bin}_frame_{view.frame:05d}'
        mask = view.mask if view.mask is not None else np.zeros(view.image.shape[:2], np.uint8)
        overlay = render_defect_overlay(view.image, mask, view.defect_masks)[0] if full else view.image
        # Fast lossless encoding: compression work must not stall acquisition.
        if full:
            cv2.imwrite(str(folder / f'{stem}_crop.png'), view.image, [cv2.IMWRITE_PNG_COMPRESSION, 0])
            cv2.imwrite(str(folder / f'{stem}_fruit_mask.png'), mask * 255, [cv2.IMWRITE_PNG_COMPRESSION, 1])
            cv2.imwrite(str(folder / f'{stem}_overlay.png'), overlay, [cv2.IMWRITE_PNG_COMPRESSION, 0])
        evidence.append(dict(frame=view.frame, bin=view.bin, timestamp=view.timestamp,
            quality=view.quality, inference=view.inference, error=view.error,
            crop=f'{prefix}/{stem}_crop.png' if full else None, fruit_mask=f'{prefix}/{stem}_fruit_mask.png' if full else None,
            overlay=f'{prefix}/{stem}_overlay.png' if full else None, defect_inference_ran=view.inference is not None))
        if frozen.contact_sheet:
            tile = np.zeros((180, 180, 3), np.uint8)
            scale = min(180 / overlay.shape[1], 154 / overlay.shape[0])
            image = cv2.resize(overlay, (max(1, round(overlay.shape[1] * scale)), max(1, round(overlay.shape[0] * scale))))
            y, x = (154 - image.shape[0]) // 2, (180 - image.shape[1]) // 2
            tile[y:y + image.shape[0], x:x + image.shape[1]] = image
            label = 'Shot' if row.get('acquisition') == 'timed' else 'Bin'
            cv2.putText(tile, f'{label} {view.bin + 1} / frame {view.frame}', (4, 171), cv2.FONT_HERSHEY_SIMPLEX, .36, (240, 240, 240), 1)
            tiles.append(tile)
    row['view_evidence'] = evidence
    if tiles:
        sheet = np.zeros((540, 540, 3), np.uint8)
        for i, tile in enumerate(tiles):
            y, x = (i // 3) * 180, (i % 3) * 180
            sheet[y:y + 180, x:x + 180] = tile
        # A contact sheet is a preview. Full evidence retains lossless crops
        # and masks; CPU previews use fast JPEG encoding.
        jpeg = not full and os.getenv('FRUIT_CPU_OPTIMIZED') == '1'
        filename = 'contact_sheet.jpg' if jpeg else 'contact_sheet.png'
        options = [cv2.IMWRITE_JPEG_QUALITY, 85] if jpeg else [cv2.IMWRITE_PNG_COMPRESSION, 1]
        cv2.imwrite(str(folder / filename), sheet, options)
        row['contact_sheet'] = f'{prefix}/{filename}'
    history = frozen.tracking_history_by_id.get(track_id, [])
    row['tracking_evidence'] = []
    if history:
        row.update(first_seen_frame=history[0]['frame'], last_seen_frame=history[-1]['frame'],
                   tracked_frames=len(history), tracking_history=history)
    for kind, (frame, crop) in (frozen.tracking_images_by_id.get(track_id, {}) if full else {}).items():
        filename = f'tracking_{kind}_frame_{frame:05d}.png'
        cv2.imwrite(str(folder / filename), crop, [cv2.IMWRITE_PNG_COMPRESSION, 0])
        row['tracking_evidence'].append(dict(stage=kind, frame=frame, crop=f'{prefix}/{filename}'))
    row.update(frozen.algorithm_assignment)
    published_at = time.monotonic()
    row['publication_monotonic'] = published_at
    row['evidence_write_seconds']=time.perf_counter()-started
    if row.get('entry_capture_monotonic') is not None:
        row['publication_latency_seconds'] = published_at - row['entry_capture_monotonic']
        if published_at >= row['decision_deadline_monotonic']:
            row['deadline_missed'] = True
            if row.get('grade') and row.get('grading_policy') != 'available_views':
                row.update(status='nine_view_timeout', grade=None, grade_provisional=False, grade_scope=None,
                           reason='Result publication missed the configured decision deadline')
    (folder / 'result.json').write_text(json.dumps(row, indent=2, allow_nan=False), encoding='utf-8')
    return row
