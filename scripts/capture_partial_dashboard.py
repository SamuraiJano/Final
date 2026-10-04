"""Verify a saved partial-map grading report against the real local dashboard."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(os.environ['TEMP'])/'citrusvision-ui-tools-20261002'))
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent


def get(endpoint):
    response = requests.get('http://127.0.0.1:8000/api/' + endpoint, timeout=15)
    response.raise_for_status()
    return response.json()


def displayed_classes(page):
    return [int(''.join(character for character in value if character.isdigit()))
            for value in page.locator('.mix-legend strong').all_text_contents()]


def open_fruit(page, fruit, filter_name):
    page.get_by_role('button', name=filter_name, exact=True).click()
    page.get_by_role('textbox', name='Search fruit or video').fill(str(fruit['track_id']))
    row = page.locator('.fruit-row').filter(has=page.get_by_text(f'Fruit {fruit["track_id"]:03d}', exact=True))
    expect(row).to_have_count(1)
    row.click()
    drawer = page.get_by_role('dialog', name=f'Fruit {fruit["track_id"]} inspection', exact=True)
    expect(drawer).to_be_visible()
    return row, drawer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--expected-job-id', required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--expected-class1', type=int, required=True)
    parser.add_argument('--expected-class2', type=int, required=True)
    parser.add_argument('--expected-review', type=int, required=True)
    parser.add_argument('--expected-provisional', type=int, required=True)
    parser.add_argument('--class2-track-id', type=int, required=True)
    parser.add_argument('--class1-track-id', type=int)
    parser.add_argument('--output-name', default='ui_partial_policy')
    parser.add_argument('--expected-vite-sha256')
    args = parser.parse_args()
    folder = args.folder.resolve()
    folder.relative_to(ROOT/'backend/diagnostics')
    launch = json.loads((folder/'launch.json').read_text(encoding='utf-8'))
    assert launch['status'] == 'ready'
    for relative, expected in [('backend/algorithm.py', launch['expected_algorithm_sha256']),
                               ('backend/main.py', launch['expected_main_sha256'])]:
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() == expected
    vite_source = (ROOT/'vite.config.js').read_bytes()
    vite_sha256 = hashlib.sha256(vite_source).hexdigest()
    if args.expected_vite_sha256:
        assert vite_sha256 == args.expected_vite_sha256
    status = get('analysis/status')
    direct_response = requests.get('http://127.0.0.1:8000/api/dashboard', timeout=15)
    direct_response.raise_for_status()
    proxy_response = requests.get('http://localhost:5173/api/dashboard', timeout=15)
    proxy_response.raise_for_status()
    assert proxy_response.content == direct_response.content
    dashboard = direct_response.json()
    assert status['state'] in ('idle', 'complete')
    latest = dashboard['latest_run']
    assert latest['job_id'] == args.expected_job_id
    fruits = [fruit for fruit in dashboard['recent_fruits'] if fruit['job_id'] == args.expected_job_id]
    assert len(fruits) == 474
    counts = {'Class 1': 0, 'Class 2': 0, 'Class 3': 0, 'ungraded': 0}
    for fruit in fruits:
        counts[fruit.get('grade') or 'ungraded'] += 1
    assert list(counts.values()) == [args.expected_class1, args.expected_class2, 0, args.expected_review]
    partial = [fruit for fruit in fruits if fruit.get('grade_provisional')]
    assert len(partial) == args.expected_provisional
    assert all(fruit['status'] == 'graded_partial' and fruit.get('grade') and fruit.get('surface_map')
               and fruit['observed_surface_pct'] > 0 for fruit in partial)
    no_map = [fruit for fruit in fruits if not fruit.get('surface_map')]
    assert len(no_map) == args.expected_review
    assert all(not fruit.get('grade') and not fruit.get('grade_provisional') for fruit in no_map)
    class2 = next(fruit for fruit in fruits if fruit['track_id'] == args.class2_track_id)
    assert class2['grade'] == 'Class 2' and class2['grade_provisional']
    class1 = next(fruit for fruit in partial if fruit['grade'] == 'Class 1'
                  and (args.class1_track_id is None or fruit['track_id'] == args.class1_track_id))
    complete = next(fruit for fruit in fruits if fruit.get('grade') and not fruit.get('grade_provisional'))
    if Path(args.output_name).name != args.output_name:
        parser.error('--output-name must be a single folder name')
    output = folder/args.output_name
    output.mkdir(exist_ok=False)
    (output/'dashboard.json').write_text(json.dumps(dashboard, indent=2), encoding='utf-8')
    (output/'vite.config.js.snapshot').write_bytes(vite_source)
    page_errors, api_requests = [], []
    note = 'Provisional grade based on the observed surface; unseen areas were not assessed.'
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
        page.on('pageerror', lambda error: page_errors.append(str(error)))
        page.on('request', lambda request: api_requests.append({'method': request.method, 'url': request.url})
                if '/api/' in request.url else None)
        page.goto('http://localhost:5173', wait_until='domcontentloaded')
        expect(page.get_by_role('button', name='Latest run', exact=True)).to_have_attribute('aria-pressed', 'true')
        try:
            page.wait_for_function('(count)=>Number(document.querySelector(".quality-total strong")?.textContent.replace(/[^0-9]/g,""))===count', arg=len(fruits))
        except Exception as error:
            page.screenshot(path=output/'load_failure.png', full_page=True)
            (output/'page_accessibility.txt').write_text(page.locator('body').aria_snapshot(), encoding='utf-8')
            (output/'failure.json').write_text(json.dumps({
                'captured_at': datetime.now(timezone.utc).isoformat(), 'passed': False,
                'stage': 'loading_latest_run', 'error': str(error),
                'expected_job_id': args.expected_job_id, 'expected_records': len(fruits),
                'page_errors': page_errors, 'api_requests': api_requests,
                'inference_requested': False, 'analysis_cancelled': False,
            }, indent=2), encoding='utf-8')
            browser.close()
            raise
        assert displayed_classes(page) == list(counts.values())
        assert page.get_by_role('button', name='Refresh backend', exact=True).is_disabled()
        assert page.locator('.analysis-progress').count() == 0
        page.locator('#video-upload').set_input_files(str(args.video.resolve()))
        page.wait_for_function('document.querySelector("video")?.readyState>=2')
        page.locator('video').evaluate('(video)=>new Promise(resolve=>{video.pause();video.addEventListener("seeked",()=>requestAnimationFrame(()=>requestAnimationFrame(resolve)),{once:true});video.currentTime=2.9})')
        page.screenshot(path=output/'latest_run.png', full_page=True)
        page.get_by_role('button', name='All saved runs', exact=True).click()
        assert displayed_classes(page) == list(dashboard['summary']['classes'].values())
        page.screenshot(path=output/'all_saved_runs.png', full_page=True)
        page.get_by_role('button', name='Latest run', exact=True).click()
        inspection_checks = []
        for fruit in (class2, class1, complete):
            row, drawer = open_fruit(page, fruit, fruit['grade'])
            label = fruit['grade'] + (' (partial)' if fruit.get('grade_provisional') else '')
            expect(row.locator('.grade-pill')).to_have_text(label)
            expect(drawer.locator('.grade-pill')).to_have_text(label)
            if fruit.get('grade_provisional'):
                expect(drawer.get_by_text(note, exact=True)).to_be_visible()
            else:
                expect(drawer.get_by_text(note, exact=True)).to_have_count(0)
            observed = drawer.locator('.detail-stats > div').filter(has=page.get_by_text('Observed surface', exact=True))
            expect(observed.locator('strong')).to_have_text(f'{fruit["observed_surface_pct"]:.1f}%')
            defects = drawer.locator('.detail-stats > div').filter(has=page.get_by_text('Surface defects', exact=True))
            expect(defects.locator('strong')).to_have_text(f'{fruit["defect_pct_of_observed"]:.1f}%')
            longitude = drawer.locator('.detail-stats > div').filter(has=page.get_by_text('Circumference observed', exact=True))
            expect(longitude.locator('strong')).to_have_text(f'{fruit["observed_longitude_deg"]:.1f}\N{DEGREE SIGN}')
            image = drawer.get_by_alt_text(f'Surface map of fruit {fruit["track_id"]}')
            expect(image).to_be_visible()
            image.evaluate('(image)=>image.complete&&image.naturalWidth>0 || new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject})')
            drawer.screenshot(path=output/f'fruit_{fruit["track_id"]:03d}_inspection.png')
            inspection_checks.append({'track_id': fruit['track_id'], 'grade': fruit['grade'],
                                      'label': label, 'grade_provisional': bool(fruit.get('grade_provisional')),
                                      'observed_surface_pct': fruit['observed_surface_pct'],
                                      'observed_longitude_deg': fruit['observed_longitude_deg'],
                                      'defect_pct_of_observed': fruit['defect_pct_of_observed'],
                                      'surface_map_loaded': True})
            if fruit == class2:
                page.set_viewport_size({'width': 390, 'height': 844})
                expect(drawer.get_by_text(note, exact=True)).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                drawer.screenshot(path=output/'partial_class2_mobile.png')
                page.set_viewport_size({'width': 1440, 'height': 1050})
            drawer.get_by_role('button', name='Close inspection').click()
        fruit = no_map[0]
        row, drawer = open_fruit(page, fruit, 'Needs review')
        expect(drawer.get_by_text('No surface map available', exact=True)).to_be_visible()
        expect(drawer.get_by_text(note, exact=True)).to_have_count(0)
        assert '(partial)' not in drawer.locator('.grade-pill').inner_text()
        drawer.screenshot(path=output/f'fruit_{fruit["track_id"]:03d}_no_map.png')
        assert not page_errors, page_errors
        browser.close()
    assert all(request['method'] == 'GET' for request in api_requests), api_requests
    report = {'captured_at': datetime.now(timezone.utc).isoformat(), 'passed': True,
              'method': 'Actual Vite/API in isolated headless Edge; no mocked responses or user profile.',
              'latest_job_id': args.expected_job_id, 'latest_records': len(fruits), 'classes': counts,
              'provisional_records': len(partial), 'no_map_ungraded_records': len(no_map),
              'all_saved_summary': dashboard['summary'], 'inspection_checks': inspection_checks,
              'no_map_track_id_checked': fruit['track_id'], 'partial_note_checked': note,
              'mobile_partial_class2_width': 390, 'mobile_horizontal_overflow': False,
              'status_before': status, 'status_after': get('analysis/status'),
              'page_errors': page_errors, 'api_requests': api_requests,
              'runtime_algorithm_sha256': launch['expected_algorithm_sha256'],
              'runtime_main_sha256': launch['expected_main_sha256'],
              'runtime_vite_sha256': vite_sha256,
              'dashboard_response_bytes': len(direct_response.content),
              'dashboard_response_sha256': hashlib.sha256(direct_response.content).hexdigest(),
              'proxy_response_bytes': len(proxy_response.content),
              'proxy_response_sha256': hashlib.sha256(proxy_response.content).hexdigest(),
              'direct_and_proxy_response_identical': True,
              'inference_requested': False, 'analysis_cancelled': False, 'local_video_preview_only': True,
              'limitations': 'The saved report regrades existing maps. This UI test does not rerun detection, segmentation or reconstruction, and does not measure manual grading accuracy.',
              'capture_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output/'capture_partial_dashboard.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: value for key, value in report.items() if key != 'api_requests'}, indent=2))


if __name__ == '__main__':
    main()
