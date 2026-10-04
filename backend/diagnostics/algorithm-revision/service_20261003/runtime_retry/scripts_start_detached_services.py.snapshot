"""Start a frozen local API/dashboard and an independent resource monitor."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import psutil
import requests

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FOLDER = ROOT / 'backend/diagnostics/algorithm-revision/service_20261003/runtime_retry'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def process_tree(process):
    parent = psutil.Process(process.pid)
    return [{'pid': child.pid, 'ppid': child.ppid(), 'name': child.name(),
             'command': child.cmdline(), 'created_at': child.create_time()}
            for child in [parent] + parent.children(recursive=True)]


def wait_ready(url, process, predicate):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'Service exited with code {process.returncode}: {url}')
        try:
            response = requests.get(url, timeout=2)
            if response.ok and predicate(response):
                return response
        except requests.RequestException:
            pass
        time.sleep(.5)
    raise RuntimeError(f'Service did not become ready within 60 seconds: {url}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=DEFAULT_FOLDER)
    parser.add_argument('--expected-algorithm-sha256', required=True)
    parser.add_argument('--expected-main-sha256', required=True)
    args = parser.parse_args()
    for relative, expected in [('backend/algorithm.py', args.expected_algorithm_sha256),
                               ('backend/main.py', args.expected_main_sha256)]:
        if digest(ROOT / relative) != expected:
            raise RuntimeError(f'The approved source hash does not match {relative}')
    for host, port in [('127.0.0.1', 8000), ('127.0.0.1', 5173), ('::1', 5173)]:
        with socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET) as connection:
            connection.settimeout(.5)
            if connection.connect_ex((host, port)) == 0:
                raise RuntimeError(f'Refusing to replace an existing service at {host}:{port}')
    folder = args.folder.resolve()
    folder.relative_to(ROOT / 'backend' / 'diagnostics')
    folder.mkdir(parents=True, exist_ok=False)
    config = ROOT / 'backend/runtime/ultralytics'
    config.mkdir(parents=True, exist_ok=True)
    overrides = {'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                 'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'YOLO_CONFIG_DIR': str(config)}
    environment = {**os.environ, **overrides}
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
    python = str(ROOT / 'backend/venv/Scripts/python.exe')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node is not on PATH')
    metadata = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'preparing',
                'workspace': str(ROOT), 'expected_algorithm_sha256': args.expected_algorithm_sha256,
                'expected_main_sha256': args.expected_main_sha256,
                'child_environment_overrides': overrides, 'creation_flags': flags,
                'hidden': True, 'detached': True, 'inference_requested': False,
                'architecture': 'Detached API first; separate Node manager attaches and owns Vite only. Refresh backend is disabled.',
                'source_manifest': [], 'models': []}
    for relative in ['backend/algorithm.py', 'backend/main.py', 'backend/dfine_segmenter.py',
                     'backend/requirements.txt', 'scripts/dev.mjs', 'scripts/stop_process_tree.py',
                     'scripts/start_detached_services.py', 'scripts/monitor_analysis.py',
                     'src/App.jsx', 'src/App.css', 'src/main.jsx', 'src/index.css',
                     'vite.config.js', 'package.json', 'package-lock.json', 'index.html']:
        path = ROOT / relative
        snapshot = relative.replace('/', '_') + '.snapshot'
        (folder / snapshot).write_bytes(path.read_bytes())
        metadata['source_manifest'].append({'path': relative, 'sha256': digest(path),
                                            'bytes': path.stat().st_size, 'snapshot': snapshot})
    for relative in ['backend/models/D-FINE/detection/best_stg1.pth',
                     'backend/models/D-FINE/segmentation/model.pt']:
        path = ROOT / relative
        metadata['models'].append({'path': relative, 'sha256': digest(path), 'bytes': path.stat().st_size})

    def save():
        temporary = folder / 'launch.tmp'
        temporary.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        temporary.replace(folder / 'launch.json')

    def launch(command, role):
        with (folder / f'{role}_stdout.log').open('wb') as stdout, (folder / f'{role}_stderr.log').open('wb') as stderr:
            process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, creationflags=flags)
        metadata[role] = {'pid': process.pid, 'command': command,
                          'stdout': f'{role}_stdout.log', 'stderr': f'{role}_stderr.log'}
        save()
        return process

    save()
    try:
        print('Starting the approved API with workspace runtime settings.', flush=True)
        api = launch([python, '-B', '-m', 'uvicorn', 'main:app', '--app-dir', 'backend',
                      '--host', '127.0.0.1', '--port', '8000'], 'api')
        health = wait_ready('http://127.0.0.1:8000/api/health', api,
                            lambda response: response.json().get('status') == 'ok').json()
        metadata['api'].update(health=health, process_tree=process_tree(api),
                               ready_at=datetime.now(timezone.utc).isoformat())
        (folder / 'health.json').write_text(json.dumps(health, indent=2), encoding='utf-8')
        save()
        print('API ready. Starting the separate dashboard manager.', flush=True)
        dashboard = launch([node, 'scripts/dev.mjs'], 'dashboard')
        wait_ready('http://localhost:5173', dashboard, lambda response: 'Citrusvision' in response.text)
        control = requests.get('http://localhost:5173/api/backend/control', timeout=10)
        control.raise_for_status()
        control = control.json()
        if control['managed']:
            raise RuntimeError('The dashboard unexpectedly owns another API')
        metadata['dashboard'].update(process_tree=process_tree(dashboard), backend_control=control,
                                     ready_at=datetime.now(timezone.utc).isoformat(), url='http://localhost:5173')
        for relative, expected in [('backend/algorithm.py', args.expected_algorithm_sha256),
                                   ('backend/main.py', args.expected_main_sha256)]:
            if digest(ROOT / relative) != expected:
                raise RuntimeError(f'Source changed during startup: {relative}')
        metadata.update(status='ready', ready_at=datetime.now(timezone.utc).isoformat())
        save()
        monitor = launch([python, '-B', 'scripts/monitor_analysis.py', str(folder)], 'monitor')
        metadata['monitor'].update(process_tree=process_tree(monitor), interval_seconds=25, max_hours=4)
        save()
        print(json.dumps({'status': 'ready', 'api_pid': api.pid, 'dashboard_pid': dashboard.pid,
                          'monitor_pid': monitor.pid, 'provenance': str(folder / 'launch.json'),
                          'inference_requested': False}), flush=True)
    except Exception as error:
        metadata.update(status='startup_error', error=str(error))
        save()
        raise


if __name__ == '__main__':
    main()
