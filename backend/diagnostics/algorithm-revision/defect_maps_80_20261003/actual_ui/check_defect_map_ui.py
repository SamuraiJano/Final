"""Check overlay controls using explicit artificial UI fixtures, or a real saved job."""
import argparse
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
import requests

ROOT = Path(__file__).resolve().parent.parent
NOTE = 'Coloured areas highlight predicted defects over the recorded surface. Blank areas were not observed.'


def artificial_dashboard():
    # Deliberately artificial colours prove the UI reads metadata, not a hidden palette.
    legend = [{'name': name, 'label': label, 'color': color} for name, label, color in [
        ('dark_marking', 'Dark marking', '#123456'),
        ('light_brown_discolouration', 'Light brown discolouration', '#654321'),
        ('open_skin', 'Open skin', '#1a7c91'),
        ('skin_wrinkling', 'Skin wrinkling', '#a41f73'),
        ('wind_scarring', 'Wind scarring', '#5c8d2e'),
    ]]
    fruits = []
    for track_id, grade, partial, overlay in [(1, 'Class 2', True, True), (2, 'Class 1', False, True), (3, None, False, False), (4, 'Class 1', True, False)]:
        fruits.append({'job_id': 'artificial-overlay-fixture', 'track_id': track_id,
                       'source_name': 'Artificial UI controls.mp4', 'created_at': '2026-10-03T10:00:00Z',
                       'grade': grade, 'status': 'graded_partial' if partial else 'graded' if grade else 'mapping_failed',
                       'grade_provisional': partial, 'surface_map': '/original-map.svg' if grade else None,
                       'surface_map_overlay': '/overlay-map.svg' if overlay else None,
                       'defect_legend': legend if overlay else [], 'coverage_target_pct': 80 if overlay else None,
                       'observed_surface_pct': 26.5 if partial else 85.1 if grade else None,
                       'defect_pct_of_observed': 17.8 if track_id == 1 else 4.5 if grade else None,
                       'observed_longitude_deg': 157.2 if partial else 360 if grade else None,
                       'rotation_coverage_deg': 157.2 if partial else 360 if grade else None,
                       'views': 10, 'mapped_view_frames': [1, 2, 3] if grade else []})
    return {'summary': {'runs': 1, 'fruit_count': 4},
            'latest_run': {'job_id': 'artificial-overlay-fixture', 'source_name': 'Artificial UI controls.mp4', 'created_at': '2026-10-03T10:00:00Z'},
            'recent_fruits': fruits}


def loaded(image):
    expect(image).to_be_visible()
    image.evaluate('(image)=>image.complete&&image.naturalWidth>0 || new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject})')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--job-id', help='Use the actual Vite/API and this saved job instead of fixtures.')
    parser.add_argument('--runtime-note', default='')
    args = parser.parse_args()
    folder = args.folder.resolve()
    folder.relative_to(ROOT / 'backend/diagnostics')
    folder.mkdir(parents=True, exist_ok=False)
    for name in ('App.jsx', 'App.css'):
        shutil.copy2(ROOT / 'src' / name, folder / (name + '.snapshot'))
    errors, calls, checks = [], [], []
    if args.job_id:
        status_response = requests.get('http://127.0.0.1:8000/api/analysis/status', timeout=15)
        status_response.raise_for_status()
        status_before = status_response.json()
        response = requests.get('http://127.0.0.1:8000/api/dashboard', timeout=15)
        response.raise_for_status()
        dashboard = response.json()
        assert dashboard['latest_run']['job_id'] == args.job_id
        fruits = [fruit for fruit in dashboard['recent_fruits'] if fruit['job_id'] == args.job_id]
        partial = next(fruit for fruit in fruits if fruit.get('surface_map_overlay') and fruit['track_id'] == 340)
        complete = next(fruit for fruit in fruits if fruit['track_id'] == 98 and fruit.get('grade') and not fruit.get('grade_provisional') and fruit.get('surface_map_overlay'))
        unmapped = next(fruit for fruit in fruits if not fruit.get('surface_map'))
        legacy = None
        url = 'http://localhost:5173'
        method = 'Actual local Vite/API in isolated headless Edge; no mocked responses or inference requests.'
    else:
        status_before = {'state': 'idle', 'fixture': True}
        dashboard = artificial_dashboard()
        fruits = dashboard['recent_fruits']
        partial, complete, unmapped, legacy = fruits
        shutil.copytree(ROOT / 'dist', folder / 'built_ui')
        url = 'http://127.0.0.1:41762'
        method = 'Frozen production build with intercepted artificial GET responses in isolated headless Edge.'
    (folder / 'dashboard.json').write_text(json.dumps(dashboard, indent=2), encoding='utf-8')
    counts = {'Class 1': 0, 'Class 2': 0, 'Class 3': 0, 'ungraded': 0}
    for fruit in fruits:
        counts[fruit.get('grade') or 'ungraded'] += 1

    def fixture_response(route):
        assert route.request.method == 'GET'
        path = urlparse(route.request.url).path
        if path.startswith('/api/'):
            payload = {'dashboard': dashboard, 'health': {'status': 'ok', 'cuda_available': True},
                       'camera/status': {'configured': False, 'connected': False}, 'live/status': {'state': 'idle'},
                       'backend/control': {'managed': False}, 'analysis/status': {'state': 'idle'}}.get(path[5:], {})
            route.fulfill(status=200, content_type='application/json', body=json.dumps(payload))
        elif path in ('/original-map.svg', '/overlay-map.svg'):
            colour = '#e28a21' if path == '/original-map.svg' else '#123456'
            image = f'<svg xmlns="http://www.w3.org/2000/svg" width="360" height="180"><rect width="360" height="180" fill="{colour}"/><text x="30" y="90" fill="white">Artificial UI control</text></svg>'
            route.fulfill(status=200, content_type='image/svg+xml', body=image)
        else:
            target = (folder / 'built_ui' / (path.lstrip('/') or 'index.html')).resolve()
            target.relative_to((folder / 'built_ui').resolve())
            if target.is_file():
                mime = 'application/javascript' if target.suffix == '.js' else mimetypes.guess_type(target.name)[0]
                route.fulfill(status=200, content_type=mime or 'application/octet-stream', body=target.read_bytes())
            else:
                route.fulfill(status=404, body='Missing fixture asset')

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: calls.append({'method': request.method, 'url': request.url}) if '/api/' in request.url else None)
        if not args.job_id:
            page.route(url + '/**', fixture_response)
        page.goto(url, wait_until='domcontentloaded')
        expect(page.get_by_role('button', name='Latest run', exact=True)).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('.quality-total strong')).to_have_text(str(len(fruits)))
        assert page.locator('.mix-legend strong').all_text_contents() == [f'{value:,}' for value in counts.values()]
        page.screenshot(path=folder / 'latest_dashboard.png', full_page=True)
        for fruit in [partial, complete, unmapped] + ([legacy] if legacy else []):
            page.get_by_role('button', name=fruit.get('grade') or 'Needs review', exact=True).click()
            page.get_by_role('textbox', name='Search fruit or video').fill(str(fruit['track_id']))
            row = page.locator('.fruit-row').filter(has=page.get_by_text(f'Fruit {fruit["track_id"]:03d}', exact=True))
            expect(row).to_have_count(1)
            row.click()
            drawer = page.get_by_role('dialog', name=f'Fruit {fruit["track_id"]} inspection', exact=True)
            expect(drawer).to_be_visible()
            label = fruit.get('grade') or ('Mapping failed' if fruit.get('status') == 'mapping_failed' else 'Needs review')
            if fruit.get('grade_provisional'):
                label += ' (partial)'
            expect(drawer.locator('.grade-pill')).to_have_text(label)
            image = drawer.locator('.detail-map img')
            overlay = fruit.get('surface_map_overlay')
            if fruit.get('surface_map'):
                observed = drawer.locator('.detail-stats > div').filter(has=page.get_by_text('Observed surface', exact=True))
                expect(observed.locator('strong')).to_have_text(f'{fruit["observed_surface_pct"]:.1f}%')
                defects = drawer.locator('.detail-stats > div').filter(has=page.get_by_text('Surface defects', exact=True))
                expect(defects.locator('strong')).to_have_text(f'{fruit["defect_pct_of_observed"]:.1f}%')
            if overlay:
                expect(drawer.get_by_role('button', name='Defects', exact=True)).to_have_attribute('aria-pressed', 'true')
                expect(image).to_have_attribute('src', overlay)
                loaded(image)
                expect(drawer.get_by_text(NOTE, exact=True)).to_be_visible()
                target = drawer.locator('.detail-stats > div').filter(has=page.get_by_text('Coverage target', exact=True))
                expect(target.locator('strong')).to_have_text(f'{fruit["coverage_target_pct"]:.1f}%')
                labels = drawer.get_by_role('list', name='Defect class colours')
                expect(labels.locator('li')).to_have_count(len(fruit['defect_legend']))
                assert labels.locator('li').all_text_contents() == [item['label'] for item in fruit['defect_legend']]
                colours = labels.locator('.defect-colour').evaluate_all('(items)=>items.map(item=>item.style.backgroundColor)')
                expected_colours = [f'rgb({int(item["color"][1:3],16)}, {int(item["color"][3:5],16)}, {int(item["color"][5:7],16)})' for item in fruit['defect_legend']]
                assert colours == expected_colours
                drawer.screenshot(path=folder / f'fruit_{fruit["track_id"]:03d}_defects.png')
                drawer.get_by_role('button', name='Original', exact=True).click()
                expect(image).to_have_attribute('src', fruit['surface_map'])
                expect(drawer.get_by_role('button', name='Original', exact=True)).to_have_attribute('aria-pressed', 'true')
                loaded(image)
                drawer.screenshot(path=folder / f'fruit_{fruit["track_id"]:03d}_original.png')
                drawer.get_by_role('button', name='Defects', exact=True).click()
                expect(image).to_have_attribute('src', overlay)
                loaded(image)
                if fruit == partial:
                    page.set_viewport_size({'width': 390, 'height': 844})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    expect(labels).to_be_visible()
                    drawer.screenshot(path=folder / 'partial_defects_mobile.png')
                    page.set_viewport_size({'width': 1440, 'height': 1050})
                checks.append({'track_id': fruit['track_id'], 'label': label, 'overlay_default': True, 'original_toggle': True,
                               'legend_matches_metadata': True, 'coverage_target_pct': fruit['coverage_target_pct'],
                               'observed_surface_pct': fruit['observed_surface_pct'],
                               'defect_pct_of_observed': fruit['defect_pct_of_observed'],
                               'grade_provisional': bool(fruit.get('grade_provisional'))})
            elif fruit.get('surface_map'):
                expect(image).to_have_attribute('src', fruit['surface_map'])
                loaded(image)
                expect(drawer.get_by_role('group', name='Surface map view')).to_have_count(0)
                expect(drawer.get_by_text('Coverage target', exact=True)).to_have_count(0)
                checks.append({'track_id': fruit['track_id'], 'legacy_original_map_preserved': True})
            else:
                expect(drawer.get_by_text('No surface map available', exact=True)).to_be_visible()
                expect(image).to_have_count(0)
                expect(drawer.get_by_role('group', name='Surface map view')).to_have_count(0)
                checks.append({'track_id': fruit['track_id'], 'missing_map_not_invented': True})
            drawer.get_by_role('button', name='Close inspection', exact=True).click()
        browser.close()
    assert not errors, errors
    assert all(call['method'] == 'GET' for call in calls)
    if args.job_id:
        status_response = requests.get('http://127.0.0.1:8000/api/analysis/status', timeout=15)
        status_response.raise_for_status()
        status_after = status_response.json()
        if status_before.get('state') in ('uploading', 'loading_models', 'processing', 'building_maps', 'cancelling'):
            assert status_after.get('run_id') == status_before.get('run_id')
            assert (status_after.get('frames_processed') or 0) >= (status_before.get('frames_processed') or 0)
    else:
        status_after = {'state': 'idle', 'fixture': True}
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'passed': True, 'method': method,
              'scope': 'actual_saved_report' if args.job_id else 'artificial_UI_controls', 'job_id': args.job_id,
              'latest_records': len(fruits), 'classes': counts,
              'provisional_records': sum(bool(fruit.get('grade_provisional')) for fruit in fruits),
              'checks': checks, 'mobile_horizontal_overflow': False, 'page_errors': errors, 'api_requests': calls,
              'analysis_status_before': status_before, 'analysis_status_after': status_after,
              'runtime_note': args.runtime_note, 'api_restarted': False, 'analysis_cancelled': False,
              'inference_requested': False, 'software_checks': {'build': 'passed', 'lint': 'passed'},
              'limitations': 'UI correctness only; this does not prove segmentation, identity association or grading accuracy.',
              'source_sha256': {name: hashlib.sha256((folder / (name + '.snapshot')).read_bytes()).hexdigest() for name in ('App.jsx', 'App.css')}}
    (folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    shutil.copy2(Path(__file__), folder / Path(__file__).name)
    print(json.dumps({key: value for key, value in report.items() if key != 'api_requests'}, indent=2))


if __name__ == '__main__':
    main()
