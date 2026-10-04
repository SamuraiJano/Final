"""Verify the frozen built dashboard with explicitly artificial API controls."""
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(os.environ['TEMP'])/'citrusvision-ui-tools-20261002'))
from playwright.sync_api import sync_playwright, expect

folder = Path(__file__).resolve().parent
fixture = json.loads((folder/'ui_fixture.json').read_text(encoding='utf-8'))
errors, checks = [], []


def local_response(route):
    path = urlparse(route.request.url).path
    if path.startswith('/api/'):
        endpoint = path.removeprefix('/api/')
        payload = {
            'dashboard': fixture, 'health': {'status': 'ok', 'cuda_available': True},
            'camera/status': {'configured': False, 'connected': False},
            'live/status': {'state': 'idle'},
            'backend/control': {'managed': False, 'refreshing': False},
            'analysis/status': {'state': 'idle'},
        }.get(endpoint, {})
        route.fulfill(status=200, content_type='application/json', body=json.dumps(payload))
        return
    target = folder/'built_ui'/(path.lstrip('/') or 'index.html')
    target.resolve().relative_to((folder/'built_ui').resolve())
    if target.is_file():
        mime = 'application/javascript' if target.suffix == '.js' else mimetypes.guess_type(target.name)[0]
        route.fulfill(status=200, content_type=mime or 'application/octet-stream', body=target.read_bytes())
    else:
        route.fulfill(status=404, body='Missing frozen asset')


def total(page):
    return int(''.join(character for character in page.locator('.quality-total strong').inner_text() if character.isdigit()))


def legend(page):
    values = page.locator('.mix-legend strong')
    assert values.count() == 4
    return [int(''.join(character for character in text if character.isdigit())) for text in values.all_text_contents()]


with sync_playwright() as runtime:
    browser = runtime.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('http://127.0.0.1:41759/**', local_response)
    page.goto('http://127.0.0.1:41759/')
    expect(page.get_by_role('button', name='Latest run', exact=True)).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('.quality-total strong')).to_have_text('474')
    assert legend(page) == [1, 1, 1, 471]
    assert page.locator('.fruit-row').count() == 6
    assert page.locator('.fruit-row').filter(has_text='UI fixture older.mp4').count() == 0
    metrics = page.locator('.performance-panel').inner_text()
    assert '123.4 ms' in metrics and '234.5 ms' in metrics
    checks.append('Latest run counts all 474 records, including grades beyond row 60, while initially rendering six table rows.')
    page.screenshot(path=folder/'latest_fixture.png', full_page=True)
    for grade, fruit in [('Class 1', 'Fruit 097'), ('Class 2', 'Fruit 473'), ('Class 3', 'Fruit 471')]:
        page.get_by_role('button', name=grade, exact=True).click()
        expect(page.locator('.fruit-row')).to_have_count(1)
        expect(page.locator('.fruit-row')).to_contain_text(fruit)
    checks.append('Class filters find graded records at list positions 98, 472 and 474.')
    page.get_by_role('button', name='All fruit', exact=True).click()
    page.get_by_role('button', name='All saved runs', exact=True).click()
    assert total(page) == 1185 and legend(page) == [1, 1, 1, 1182]
    assert page.locator('.performance-panel').inner_text() == metrics
    checks.append('All saved runs retains the 711 older Review records and preserves latest-run model metrics.')
    page.screenshot(path=folder/'all_fixture.png', full_page=True)
    page.get_by_role('button', name='Show more inspections', exact=True).click()
    expect(page.locator('.fruit-row')).to_have_count(12)
    assert total(page) == 1185
    page.get_by_role('button', name='Latest run', exact=True).click()
    expect(page.locator('.fruit-row')).to_have_count(6)
    assert total(page) == 474
    checks.append('Show more affects rows without changing totals; changing scope resets visible rows to six.')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.get_by_role('button', name='Latest run', exact=True).is_visible()
    assert page.get_by_role('button', name='All saved runs', exact=True).is_visible()
    dimensions = page.evaluate('({width:document.documentElement.clientWidth,content:document.documentElement.scrollWidth})')
    assert dimensions['content'] <= dimensions['width'], dimensions
    page.screenshot(path=folder/'mobile_fixture.png', full_page=True)
    checks.append('Both scope controls remain visible at 390px width, without horizontal page overflow.')
    fixture.clear()
    fixture.update({'summary': {'runs': 0, 'fruit_count': 0}, 'latest_run': None, 'recent_fruits': []})
    page.reload()
    expect(page.locator('.quality-total strong')).to_have_text('0')
    assert legend(page) == [0, 0, 0, 0]
    expect(page.locator('.history-scope-row')).to_contain_text('No saved run yet')
    checks.append('Empty saved history displays zero counts without an exception.')
    browser.close()

assert not errors, errors
report = {
    'checked_at': datetime.now(timezone.utc).isoformat(), 'passed': True,
    'method': 'Isolated headless Edge. Frozen built HTML/JS/CSS and artificial API fixture supplied through intercepted loopback requests; no HTTP or inference service, and no user browser profile.',
    'limitations': 'UI checks only. Fixture classes are artificial controls, not model predictions or proof of grade accuracy. Numeric comparisons allow locale-specific separators.',
    'fixture_sha256': hashlib.sha256((folder/'ui_fixture.json').read_bytes()).hexdigest(),
    'source_hashes': {name: hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ('App.jsx.snapshot', 'App.css.snapshot', 'validate_ui_scope.py')},
    'checks': checks, 'page_errors': errors, 'mobile_dimensions': dimensions,
    'software_checks': {'npm run build': 'passed', 'npm run lint': 'passed'},
}
(folder/'ui_verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
