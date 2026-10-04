"""GET-only check that Vite delivers the same complete dashboard as the API."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import requests


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--expected-job', required=True)
    args = parser.parse_args()
    folder = args.folder.resolve()
    folder.relative_to(ROOT / 'backend' / 'diagnostics')
    folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    checks = []
    contents = []
    for url in ('http://127.0.0.1:8000/api/dashboard', 'http://localhost:5173/api/dashboard'):
        start = time.perf_counter()
        response = session.get(url, timeout=(3, 12))
        response.raise_for_status()
        content = response.content
        data = response.json()
        checks.append(dict(url=url, status=response.status_code, bytes=len(content),
                           announced_bytes=int(response.headers['Content-Length']),
                           sha256=hashlib.sha256(content).hexdigest(),
                           seconds=round(time.perf_counter() - start, 3),
                           rows=len(data['recent_fruits']), summary=data['summary']))
        contents.append(content)
    assert contents[0] == contents[1], 'Proxy changed or truncated the dashboard JSON'
    assert all(row['bytes'] == row['announced_bytes'] for row in checks)
    assert data['latest_run']['job_id'] == args.expected_job
    fruits = [fruit for fruit in data['recent_fruits'] if fruit['job_id'] == args.expected_job]
    counts = dict(Counter(fruit.get('grade') or 'ungraded' for fruit in fruits))
    assert len(fruits) == 474
    assert counts == {'Class 1': 293, 'Class 2': 1, 'ungraded': 180}
    assert sum(bool(fruit.get('grade_provisional')) for fruit in fruits) == 292
    result = dict(captured_at=datetime.now(timezone.utc).isoformat(), status='pass',
                  checks=checks, raw_response_byte_identical=True,
                  latest_job=args.expected_job, latest_records=len(fruits),
                  latest_grades=counts, provisional_grades=292,
                  methods=['GET'], inference_requested=False,
                  source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                 for name in ('vite.config.js', 'backend/algorithm.py',
                                              'backend/main.py', 'src/App.jsx')})
    (folder / 'get_only_check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (folder / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
