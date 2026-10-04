"""Run the unchanged application pipeline and retain incremental evidence."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from uuid import uuid4

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))
import main

VIDEO = Path(sys.argv[1]).resolve()
JOB = uuid4().hex
OUTPUT = main.RESULTS / JOB
OUTPUT.mkdir()
started = time.perf_counter()
lock = threading.RLock()
stop = threading.Event()
rows = []
state = {'state': 'starting', 'frames_processed': 0, 'frames_total': None}

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

request = {
    'job_id': JOB, 'created_at': datetime.now(timezone.utc).isoformat(),
    'source_name': VIDEO.name, 'video': str(VIDEO), 'video_sha256': sha(VIDEO),
    'output': str(OUTPUT), 'method': 'Fresh main.analyze_video on the entire original video; no track subset or cached detections.',
    'source_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in main.SOURCE_SNAPSHOTS.items()},
    'runner_sha256': sha(__file__),
    'model_sha256': {name: sha(path) for name, path in {
        'detection': os.getenv('FRUIT_DETECTOR_WEIGHTS', main.MODELS / 'detection' / 'best_stg1.pth'),
        'segmentation': os.getenv('DFINE_SEG_WEIGHTS', main.MODELS / 'segmentation' / 'model.pt')}.items()},
    'environment': {k: v for k, v in os.environ.items() if k.startswith('FRUIT_') or k == 'DFINE_SEG_WEIGHTS'},
    'limitations': 'No independent manual fruit identities or grade labels; coverage is estimated by the production geometry model.'
}
(HERE / 'request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')

def checkpoint():
    with lock:
        current = {**state, 'job_id': JOB, 'elapsed_seconds': round(time.perf_counter()-started, 1),
                   'completed_tracks': len(rows), 'statuses': dict(Counter(r['status'] for r in rows))}
        temporary = HERE / 'progress.tmp'
        temporary.write_text(json.dumps(current, indent=2), encoding='utf-8')
        temporary.replace(HERE / 'progress.json')
        return current

def progress(**changes):
    with lock:
        state.update(changes)
        checkpoint()

original_finish = main._finish_track
def finish(*args, **kwargs):
    result = original_finish(*args, **kwargs)
    if result is not None:
        with lock:
            rows.append(result)
            checkpoint()
    return result
main._finish_track = finish

def heartbeat():
    while not stop.wait(30):
        print(json.dumps(checkpoint()), flush=True)

thread = threading.Thread(target=heartbeat, daemon=True)
main._write_report(OUTPUT, {**request, 'status': 'processing', 'metrics': {}, 'fruits': []})
thread.start()
metrics = {}
print(json.dumps({'job_id': JOB, 'video': str(VIDEO), 'output': str(OUTPUT)}), flush=True)
try:
    fruits = main.analyze_video(VIDEO, OUTPUT, metrics, progress)
    stop.set()
    thread.join(timeout=2)
    with lock:
        state.update(state='complete')
        rows[:] = fruits
        checkpoint()
        report = {**request, 'status': 'complete', 'finished_at': datetime.now(timezone.utc).isoformat(),
                  'metrics': metrics, 'fruits': fruits}
        main._write_report(OUTPUT, report)
        summary = {**request, **checkpoint(), 'metrics': metrics,
                   'grades': dict(Counter(r.get('grade') or 'ungraded' for r in fruits))}
        (HERE / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary, indent=2), flush=True)
except BaseException as error:
    with lock:
        state.update(state='error', error=repr(error))
        checkpoint()
        main._write_report(OUTPUT, {**request, 'status': 'error', 'metrics': metrics, 'fruits': rows,
                                  'error': repr(error)})
        (HERE / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
    raise
finally:
    stop.set()
    thread.join(timeout=2)
