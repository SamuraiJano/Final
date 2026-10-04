"""Restart one recorded idle API tree while preserving its separate Vite manager."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import psutil
import requests

from start_detached_services import ROOT, digest, process_tree, wait_ready


def get(endpoint):
    response = requests.get('http://127.0.0.1:8000/api/' + endpoint, timeout=10)
    response.raise_for_status()
    return response.json()


def verified_tree(record):
    parent = psutil.Process(record['pid'])
    actual = [parent] + parent.children(recursive=True)
    expected = {item['pid']: item for item in record['process_tree']}
    if {process.pid for process in actual} != set(expected):
        raise RuntimeError('The current process tree differs from the recorded owned tree')
    rows = []
    for process in actual:
        saved = expected[process.pid]
        if abs(process.create_time() - saved['created_at']) > .001:
            raise RuntimeError(f'Recorded PID was reused: {process.pid}')
        if process.cmdline() != saved['command']:
            raise RuntimeError(f'Recorded process command changed: {process.pid}')
        cwd = Path(process.cwd()).resolve()
        wanted = Path(os.environ['SystemRoot']).resolve() if process.name().lower() == 'conhost.exe' else ROOT
        if cwd != wanted:
            raise RuntimeError(f'Recorded process cwd changed: {process.pid}')
        rows.append({**saved, 'cwd': str(cwd), 'running': process.is_running()})
    return actual, rows


def check_source(algorithm_sha256, main_sha256):
    for relative, expected in [('backend/algorithm.py', algorithm_sha256), ('backend/main.py', main_sha256)]:
        if digest(ROOT / relative) != expected:
            raise RuntimeError(f'Approved source hash does not match {relative}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-launch', type=Path, required=True)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--expected-algorithm-sha256', required=True)
    parser.add_argument('--expected-main-sha256', required=True)
    parser.add_argument('--check-only', action='store_true', help='Verify source and idle process ownership without stopping or starting services')
    args = parser.parse_args()
    previous_path, folder = args.previous_launch.resolve(), args.folder.resolve()
    previous_path.relative_to(ROOT / 'backend' / 'diagnostics')
    folder.relative_to(ROOT / 'backend' / 'diagnostics')
    previous = json.loads(previous_path.read_text(encoding='utf-8'))
    if Path(previous['workspace']).resolve() != ROOT or previous['status'] != 'ready':
        raise RuntimeError('The previous launch does not describe this ready workspace')
    check_source(args.expected_algorithm_sha256, args.expected_main_sha256)
    api_processes, api_before = verified_tree(previous['api'])
    dashboard_processes, dashboard_before = verified_tree(previous['dashboard'])
    if {process.pid for process in api_processes} & {process.pid for process in dashboard_processes}:
        raise RuntimeError('The API and dashboard process trees overlap')
    analysis, live = get('analysis/status'), get('live/status')
    if analysis['state'] not in ('idle', 'complete', 'cancelled', 'error'):
        raise RuntimeError('An analysis is active; refusing to restart it')
    if live['state'] in ('starting', 'running', 'stopping'):
        raise RuntimeError('Live inspection is active; refusing to restart it')
    listeners = [process.pid for process in api_processes for connection in process.net_connections(kind='tcp')
                 if connection.status == psutil.CONN_LISTEN and connection.laddr.port == 8000]
    if len(listeners) != 1:
        raise RuntimeError('Port 8000 does not have exactly one recorded API listener')
    if args.check_only:
        print(json.dumps({'status': 'guards_passed', 'api': api_before, 'dashboard': dashboard_before,
                          'analysis': analysis, 'live': live, 'api_listener_pid': listeners[0],
                          'services_stopped': False, 'services_started': False, 'inference_requested': False}, indent=2))
        return
    folder.mkdir(parents=True, exist_ok=False)
    config = ROOT / 'backend/runtime/ultralytics'
    config.mkdir(parents=True, exist_ok=True)
    overrides = {'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                 'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'YOLO_CONFIG_DIR': str(config)}
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
    metadata = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'preparing',
                'workspace': str(ROOT), 'previous_launch': str(previous_path),
                'previous_launch_sha256': digest(previous_path), 'reason': 'Load the approved partial-map grading policy after software checks.',
                'expected_algorithm_sha256': args.expected_algorithm_sha256, 'expected_main_sha256': args.expected_main_sha256,
                'child_environment_overrides': overrides, 'creation_flags': flags, 'hidden': True, 'detached': True,
                'analysis_before_restart': analysis, 'live_before_restart': live, 'api_before': api_before,
                'api_listener_pid_before': listeners[0], 'dashboard_before': dashboard_before,
                'source_manifest': [], 'models': [], 'inference_requested': False, 'analysis_cancelled': False,
                'dashboard_restarted': False}
    for relative in ['backend/algorithm.py', 'backend/main.py', 'backend/dfine_segmenter.py', 'backend/requirements.txt',
                     'scripts/restart_owned_api.py', 'scripts/start_detached_services.py', 'scripts/dev.mjs',
                     'src/App.jsx', 'src/App.css', 'src/main.jsx', 'src/index.css', 'vite.config.js', 'package.json', 'index.html']:
        path = ROOT / relative
        snapshot = relative.replace('/', '_') + '.snapshot'
        (folder / snapshot).write_bytes(path.read_bytes())
        metadata['source_manifest'].append({'path': relative, 'sha256': digest(path), 'snapshot': snapshot})
    for relative in ['backend/models/D-FINE/detection/best_stg1.pth', 'backend/models/D-FINE/segmentation/model.pt']:
        path = ROOT / relative
        metadata['models'].append({'path': relative, 'sha256': digest(path), 'bytes': path.stat().st_size})

    def save():
        temporary = folder / 'launch.tmp'
        temporary.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        temporary.replace(folder / 'launch.json')

    save()
    try:
        # Repeat the guards immediately before touching the recorded idle API tree.
        check_source(args.expected_algorithm_sha256, args.expected_main_sha256)
        api_processes, _ = verified_tree(previous['api'])
        verified_tree(previous['dashboard'])
        if get('analysis/status')['state'] not in ('idle', 'complete', 'cancelled', 'error'):
            raise RuntimeError('An analysis started during preparation')
        if get('live/status')['state'] in ('starting', 'running', 'stopping'):
            raise RuntimeError('Live inspection started during preparation')
        print('Stopping only the verified idle API tree; dashboard stays running.', flush=True)
        for process in reversed(api_processes):
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(api_processes, timeout=10)
        if alive:
            raise RuntimeError('An owned API process did not stop; no replacement launched')
        with socket.socket() as connection:
            connection.settimeout(.5)
            if connection.connect_ex(('127.0.0.1', 8000)) == 0:
                raise RuntimeError('Port 8000 remains occupied; refusing a replacement')
        metadata['api_stopped_at'] = datetime.now(timezone.utc).isoformat()
        save()
        check_source(args.expected_algorithm_sha256, args.expected_main_sha256)
        command = [str(ROOT/'backend/venv/Scripts/python.exe'), '-B', '-m', 'uvicorn', 'main:app',
                   '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000']
        with (folder/'api_stdout.log').open('wb') as stdout, (folder/'api_stderr.log').open('wb') as stderr:
            api = subprocess.Popen(command, cwd=ROOT, env={**os.environ, **overrides}, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, creationflags=flags)
        metadata['api'] = {'pid': api.pid, 'command': command, 'stdout': 'api_stdout.log', 'stderr': 'api_stderr.log'}
        save()
        health = wait_ready('http://127.0.0.1:8000/api/health', api,
                            lambda response: response.json().get('status') == 'ok').json()
        metadata['api'].update(process_tree=process_tree(api), health=health)
        _, dashboard_after = verified_tree(previous['dashboard'])
        response = requests.get('http://localhost:5173', timeout=10)
        response.raise_for_status()
        control = requests.get('http://localhost:5173/api/backend/control', timeout=10)
        control.raise_for_status()
        if control.json()['managed']:
            raise RuntimeError('The separate manager unexpectedly owns the API')
        check_source(args.expected_algorithm_sha256, args.expected_main_sha256)
        metadata.update(status='ready', ready_at=datetime.now(timezone.utc).isoformat(),
                        dashboard=previous['dashboard'], dashboard_after=dashboard_after,
                        frontend_http_status=response.status_code, backend_control=control.json(),
                        analysis_after_restart=get('analysis/status'))
        save()
        print(json.dumps({'status': 'ready', 'old_api_pid': previous['api']['pid'], 'new_api_pid': api.pid,
                          'dashboard_pid_unchanged': previous['dashboard']['pid'], 'inference_requested': False,
                          'provenance': str(folder/'launch.json')}, indent=2), flush=True)
    except Exception as error:
        metadata.update(status='restart_error', error=str(error))
        save()
        raise


if __name__ == '__main__':
    main()
