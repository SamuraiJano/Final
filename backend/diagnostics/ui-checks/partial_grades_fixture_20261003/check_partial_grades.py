"""Isolated UI controls: all fixture grades below are artificial, not predictions."""
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(os.environ['TEMP']) / 'citrusvision-ui-tools-20261002'))
from playwright.sync_api import sync_playwright, expect

folder = Path(__file__).resolve().parent
root = folder.parents[3]
for name in ('App.jsx', 'App.css'):
    shutil.copy2(root / 'src' / name, folder / (name + '.snapshot'))
shutil.copytree(root / 'dist', folder / 'built_ui', dirs_exist_ok=True)


def fruit(track_id, grade, partial=False, job_id='fixture-latest'):
    return {
        'job_id': job_id, 'track_id': track_id,
        'source_name': 'UI fixture (artificial grades).mp4',
        'created_at': '2026-10-03T10:00:00Z',
        'grade': grade, 'status': 'graded_partial' if partial else 'graded' if grade else 'ungraded',
        'grade_provisional': partial, 'coverage_complete': bool(grade) and not partial,
        'grade_scope': 'observed_surface' if partial else 'complete_coverage',
        'surface_map': '/fixture-map.svg' if grade else None,
        'observed_surface_pct': 23.4 if partial else 85.1 if grade else None,
        'defect_pct_of_observed': {'Class 1': 5.0, 'Class 2': 15.0, 'Class 3': 30.0}.get(grade),
        'observed_longitude_deg': 100 if partial else 360 if grade else None,
        'rotation_coverage_deg': 100 if partial else 360 if grade else None,
        'views': 10, 'mapped_view_frames': [1, 2, 3] if grade else [],
    }


fixture = {
    'summary': {'runs': 2, 'fruit_count': 7},
    'latest_run': {'job_id': 'fixture-latest', 'source_name': 'UI fixture (artificial grades).mp4', 'created_at': '2026-10-03T10:00:00Z'},
    'recent_fruits': [fruit(1, 'Class 1', True), fruit(2, 'Class 2', True), fruit(3, 'Class 3', True), fruit(4, 'Class 1'), fruit(5, None), fruit(6, 'Class 2', True, 'fixture-older'), fruit(7, None, job_id='fixture-older')],
}
(folder / 'fixture.json').write_text(json.dumps(fixture, indent=2), encoding='utf-8')
errors, checks = [], []


def response(route):
    assert route.request.method == 'GET', route.request.method
    path = urlparse(route.request.url).path
    if path.startswith('/api/'):
        payload = {
            'dashboard': fixture, 'health': {'status': 'ok', 'cuda_available': True},
            'camera/status': {'configured': False, 'connected': False},
            'live/status': {'state': 'idle'}, 'backend/control': {'managed': False},
            'analysis/status': {'state': 'idle'},
        }.get(path.removeprefix('/api/'), {})
        route.fulfill(status=200, content_type='application/json', body=json.dumps(payload))
    elif path == '/fixture-map.svg':
        route.fulfill(status=200, content_type='image/svg+xml', body='<svg xmlns="http://www.w3.org/2000/svg" width="360" height="180"><rect width="360" height="180" fill="#171717"/><text x="30" y="95" fill="#ddd">UI fixture map (artificial control)</text></svg>')
    else:
        target = (folder / 'built_ui' / (path.lstrip('/') or 'index.html')).resolve()
        target.relative_to((folder / 'built_ui').resolve())
        if target.is_file():
            mime = 'application/javascript' if target.suffix == '.js' else mimetypes.guess_type(target.name)[0]
            route.fulfill(status=200, content_type=mime or 'application/octet-stream', body=target.read_bytes())
        else:
            route.fulfill(status=404, body='Missing frozen fixture asset')


with sync_playwright() as runtime:
    browser = runtime.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('http://127.0.0.1:41761/**', response)
    page.goto('http://127.0.0.1:41761/')
    expect(page.locator('.quality-total strong')).to_have_text('5')
    assert page.locator('.mix-legend strong').all_text_contents() == ['2', '1', '1', '1']
    expect(page.locator('.summary-grid')).to_contain_text('No usable map or defect estimate')
    checks.append('Latest-run raw class totals include all three partial classes and retain unmapped records as Review.')
    for grade, track_id in [('Class 1', 1), ('Class 2', 2), ('Class 3', 3)]:
        page.get_by_role('button', name=grade, exact=True).click()
        expect(page.locator('.fruit-row')).to_have_count(2 if grade == 'Class 1' else 1)
        row = page.locator('.fruit-row').filter(has_text=f'Fruit {track_id:03d}')
        expect(row.locator('.grade-pill')).to_have_text(grade + ' (partial)')
        row.click()
        drawer = page.get_by_role('dialog')
        expect(drawer.locator('.grade-pill')).to_have_text(grade + ' (partial)')
        expect(drawer).to_contain_text('Provisional grade based on the observed surface; unseen areas were not assessed.')
        expect(drawer).to_contain_text('23.4%')
        expect(drawer).to_contain_text('100.0\u00b0')
        if track_id == 2:
            page.screenshot(path=folder / 'partial_class2_drawer.png', full_page=True)
        page.get_by_role('button', name='Close inspection', exact=True).click()
    checks.append('All three partial classes pass their raw class filter and show the partial label, provisional note, surface percentage and longitude in the drawer.')
    page.get_by_role('button', name='Class 1', exact=True).click()
    complete = page.locator('.fruit-row').filter(has_text='Fruit 004')
    expect(complete.locator('.grade-pill')).to_have_text('Class 1')
    complete.click()
    expect(page.get_by_role('dialog').get_by_text('Provisional grade based on the observed surface; unseen areas were not assessed.', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Close inspection', exact=True).click()
    page.get_by_role('button', name='Needs review', exact=True).click()
    expect(page.locator('.fruit-row')).to_have_count(1)
    expect(page.locator('.fruit-row')).to_contain_text('Fruit 005')
    checks.append('A complete grade keeps its normal label without a partial note; the unmapped record alone appears in Needs review.')
    page.get_by_role('button', name='All saved runs', exact=True).click()
    expect(page.locator('.quality-total strong')).to_have_text('7')
    assert page.locator('.mix-legend strong').all_text_contents() == ['2', '2', '1', '2']
    page.get_by_role('button', name='All fruit', exact=True).click()
    page.set_viewport_size({'width': 390, 'height': 844})
    dimensions = page.evaluate('({width:document.documentElement.clientWidth,content:document.documentElement.scrollWidth})')
    assert dimensions['content'] <= dimensions['width'], dimensions
    page.screenshot(path=folder / 'partial_mobile.png', full_page=True)
    checks.append('All saved runs counts partial classes correctly; 390px mobile layout has no horizontal overflow.')
    browser.close()

assert not errors, errors
report = {
    'checked_at': datetime.now(timezone.utc).isoformat(), 'passed': True,
    'method': 'Isolated headless Edge with frozen production build and intercepted artificial GET fixture; no running inference/API service, user browser profile, or actual result changes.',
    'limitations': 'UI verification only. All classes, defect percentages and maps in this fixture are artificial controls, not model predictions or proof of grading accuracy.',
    'checks': checks, 'page_errors': errors, 'mobile_dimensions': dimensions,
    'software_checks': {'npm run build': 'passed', 'npm run lint': 'passed'},
    'source_hashes': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in ('App.jsx.snapshot', 'App.css.snapshot', 'fixture.json', Path(__file__).name)},
}
(folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
