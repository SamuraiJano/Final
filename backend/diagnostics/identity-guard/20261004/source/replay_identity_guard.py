"""Replay frozen real tracking boxes; no inference or saved report mutation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from fruit_identity import FruitIdentityGuard


def main():
    backend = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=backend/'diagnostics/entry-tracking/entry_full_20261002')
    parser.add_argument('--output', type=Path, default=backend/'diagnostics/identity-guard/20261004')
    args = parser.parse_args()
    report = json.loads((args.source/'report.json').read_text())
    path = args.source/'immediate_one_detection.json'
    sequence = json.loads(path.read_text())
    capture = cv2.VideoCapture(report['video'])
    ok, image = capture.read()
    capture.release()
    if not ok:
        raise RuntimeError('Cannot read source video dimensions')
    guard = FruitIdentityGuard()
    before, after, reasons = Counter(), Counter(), Counter()
    decisions = []
    started = time.perf_counter()
    for record in sequence:
        rows = np.asarray(record['tracks'], float).reshape(-1, 7)
        batch = guard.update(rows[:, :4], rows[:, 4].astype(int), record['frame'], image.shape)
        assert len({item['capture_id'] for item in batch}) == len(batch)
        before.update(rows[:, 4].astype(int).tolist())
        after.update(item['capture_id'] for item in batch)
        reasons.update(item['reason'] for item in batch)
        decisions.extend(batch)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'decisions.json').write_text(json.dumps(decisions, indent=2))
    summary = {
        'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'guard_sha256': hashlib.sha256((backend/'fruit_identity.py').read_bytes()).hexdigest(),
        'configuration': guard.configuration(), 'frame_shape': list(image.shape),
        'frames': len(sequence), 'observations': sum(before.values()),
        'raw_tracker_ids': len(before), 'capture_segments': len(after),
        'raw_ids_with_at_most_two_observations': sum(n <= 2 for n in before.values()),
        'capture_segments_with_at_most_two_observations': sum(n <= 2 for n in after.values()),
        'uncertain_segments': sum(m['identity_status'] == 'uncertain' for m in guard.metadata.values()),
        'decisions': dict(reasons), 'elapsed_seconds': time.perf_counter()-started,
        'limitations': ['No physical identity labels: these are continuity indicators, not IDSW/IDF1 accuracy.',
                        'Separate capture segments are not a unique physical fruit count.',
                        'No detector, segmenter or map reconstruction was run.'],
    }
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2))
    (args.output/'segments.json').write_text(json.dumps(guard.metadata, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
