"""Save lightweight resource/progress samples without controlling inference."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import psutil
import requests

ROOT = Path(__file__).resolve().parent.parent


def gpu_usage():
    executable = shutil.which('nvidia-smi')
    if not executable:
        return {'error': 'nvidia-smi is unavailable'}
    try:
        result = subprocess.run(
            [executable, '--query-gpu=index,memory.total,memory.used,memory.free,utilization.gpu',
             '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=8,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        result.check_returncode()
        keys = ('index', 'total_memory_mib', 'used_memory_mib', 'free_memory_mib', 'utilization_pct')
        devices = []
        for line in result.stdout.splitlines():
            values = [value.strip() for value in line.split(',')]
            devices.append({key: float(value) if value.replace('.', '', 1).isdigit() else None
                            for key, value in zip(keys, values)})
        return {'devices': devices}
    except (OSError, subprocess.SubprocessError) as error:
        return {'error': str(error)}


def owned_processes(services):
    rows = []
    for role in ('api', 'dashboard'):
        recorded = services[role]
        try:
            parent = psutil.Process(recorded['pid'])
            if abs(parent.create_time() - recorded['process_tree'][0]['created_at']) > .001:
                rows.append({'role': role, 'pid': parent.pid, 'error': 'Recorded PID was reused'})
                continue
            for process in [parent] + parent.children(recursive=True):
                try:
                    memory = process.memory_info()
                    rows.append({'role': role, 'pid': process.pid, 'name': process.name(),
                                 'rss_bytes': memory.rss, 'private_bytes': getattr(memory, 'private', None),
                                 'peak_rss_bytes': getattr(memory, 'peak_wset', None)})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
            rows.append({'role': role, 'pid': recorded['pid'], 'error': str(error)})
    return rows


def sample(services):
    memory = psutil.virtual_memory()
    row = {'time': datetime.now(timezone.utc).isoformat(),
           'system_memory': {'total_bytes': memory.total, 'available_bytes': memory.available,
                             'used_pct': memory.percent},
           'owned_processes': owned_processes(services), 'gpu': gpu_usage()}
    try:
        response = requests.get('http://127.0.0.1:8000/api/analysis/status', timeout=8)
        response.raise_for_status()
        row['analysis'] = response.json()
    except (requests.RequestException, ValueError) as error:
        row['analysis_error'] = str(error)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--interval-seconds', type=float, default=25)
    parser.add_argument('--max-hours', type=float, default=4)
    args = parser.parse_args()
    if not 20 <= args.interval_seconds <= 30 or not 0 < args.max_hours <= 4:
        parser.error('Use a 20–30 second interval and a positive limit of at most four hours')
    folder = args.folder.resolve()
    folder.relative_to(ROOT / 'backend' / 'diagnostics')
    services = json.loads((folder / 'launch.json').read_text(encoding='utf-8'))
    started = time.monotonic()
    deadline = started + args.max_hours * 3600
    samples, failures, run_id = 0, 0, None
    reason = 'time_limit'
    print(f'Monitoring resources and API progress every {args.interval_seconds:g} seconds.', flush=True)
    with (folder / 'resource_samples.jsonl').open('x', encoding='utf-8') as stream:
        while time.monotonic() < deadline:
            before = time.monotonic()
            row = sample(services)
            state = row.get('analysis', {})
            if state.get('run_id'):
                run_id = state['run_id']
            failures = failures + 1 if 'analysis_error' in row else 0
            stream.write(json.dumps(row) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
            samples += 1
            if run_id and state.get('state') in ('complete', 'cancelled', 'error'):
                reason = state['state']
                # One final sample distinguishes the returned state from cleanup.
                time.sleep(2)
                final = sample(services)
                final['phase'] = 'after_terminal_state'
                stream.write(json.dumps(final) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
                samples += 1
                break
            if failures >= 3:
                reason = 'api_unavailable'
                break
            time.sleep(max(0, min(args.interval_seconds - (time.monotonic() - before),
                                  deadline - time.monotonic())))
    summary = {'finished_at': datetime.now(timezone.utc).isoformat(), 'stop_reason': reason,
               'samples': samples, 'analysis_id': run_id,
               'duration_sec': round(time.monotonic() - started, 1),
               'services_stopped': False, 'inference_cancelled': False,
               'method': 'Python requests/psutil and hidden nvidia-smi; only owned service process memory, no unrelated command lines.'}
    (folder / 'monitor_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
