"""Retain dated test/build/lint output and source hashes for report evidence."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    out = root / 'backend' / 'diagnostics' / 'software-checks' / args.label
    out.mkdir(parents=True, exist_ok=False)
    checks = [('python_tests', [sys.executable, '-B', '-m', 'unittest', 'discover',
                               '-s', 'backend', '-p', 'test_*.py', '-v']),
              ('frontend_build', [shutil.which('npm.cmd') or 'npm', 'run', 'build']),
              ('frontend_lint', [shutil.which('npm.cmd') or 'npm', 'run', 'lint'])]
    results = []
    for name, command in checks:
        started = datetime.now(timezone(timedelta(hours=2))).isoformat()
        result = subprocess.run(command, cwd=root, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        (out / f'{name}.txt').write_text(result.stdout, encoding='utf-8')
        results.append({'name': name, 'command': command, 'started_at': started,
                        'exit_code': result.returncode, 'log': f'{name}.txt'})
        print(f'{name}: exit {result.returncode}', flush=True)
    sources = ['backend/algorithm.py', 'backend/main.py', 'backend/dfine_segmenter.py',
               'src/App.jsx', 'src/App.css', 'scripts/dev.mjs',
               'scripts/stop_process_tree.py', 'backend/requirements.txt',
               'vite.config.js', 'eslint.config.js', 'backend/validate_api_video.py']
    summary = {'checks': results, 'source_sha256': {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sources}}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    if any(row['exit_code'] for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
