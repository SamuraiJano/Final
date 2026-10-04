"""Recheck saved audit crops without rerunning either neural model."""
import json
from collections import Counter
from pathlib import Path

import numpy as np

from algorithm import FruitView, Settings, _validate_capture_mask, fit_spheroid


def main():
    root = Path(__file__).parent / 'diagnostics/current-upload'
    changes = json.loads((root / 'frame_changes.json').read_text())['change_frames']
    tracks = json.loads((root / 'tracks.json').read_text())
    outcomes = {}
    for folder in root.iterdir():
        if not folder.is_dir() or not folder.name.isdecimal():
            continue
        track_id = int(folder.name)
        views, seen, rejected = [], set(), Counter()
        for item in json.loads((folder / 'views.json').read_text()):
            scene = int(np.searchsorted(changes, item['frame'], side='right'))
            if scene in seen:
                continue
            seen.add(scene)
            with np.load(folder / item['file']) as data:
                view = FruitView(data['image'], data['mask'], {}, item['frame'], tuple(item['bbox']))
            box = next(row[1:5] for row in tracks[item['frame']]['tracks'] if row[0] == track_id)
            try:
                if box[0] <= 2 or box[1] <= 2 or box[2] >= 1918 or box[3] >= 1078:
                    raise RuntimeError('Fruit is cut off by the video frame')
                _validate_capture_mask(view.object_mask, view.fruit_bbox, Settings())
                views.append(view)
            except RuntimeError as error:
                rejected[str(error)] += 1
        fits = {}
        for axis in ('x', 'y'):
            for direction in (-1, 1):
                settings = Settings(spheroid_type='auto', rotation_axis=axis, rotation_direction=direction)
                try:
                    model = fit_spheroid(views, settings)
                    fits[f'{axis}_{direction}'] = {'A': model.A, 'B': model.B}
                except RuntimeError as error:
                    fits[f'{axis}_{direction}'] = {'error': str(error)}
        outcomes[folder.name] = {'usable_views': len(views), 'rejected': dict(rejected), 'fits': fits}
    (root / 'post_fix_audit.json').write_text(json.dumps(outcomes, indent=2), encoding='utf-8')
    print(json.dumps(outcomes, indent=2))


if __name__ == '__main__':
    main()
