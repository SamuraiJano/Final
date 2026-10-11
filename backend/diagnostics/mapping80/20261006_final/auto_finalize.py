"""Finalize reviewable evidence once the queued full-model checks pass."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

OUTPUT=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[4]
while True:
    state=json.loads((OUTPUT/'finish_stage_state.json').read_text())
    if state['stage']=='failed':
        raise RuntimeError(state)
    if state['stage']=='all_queued_validation_stages_passed':
        break
    time.sleep(15)
subprocess.run([sys.executable,'-B',str(OUTPUT/'finalize_evidence.py')],cwd=ROOT,
               check=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
