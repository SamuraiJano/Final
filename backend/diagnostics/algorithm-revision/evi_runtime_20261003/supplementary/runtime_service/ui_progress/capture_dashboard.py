"""Capture the real running dashboard without uploading or controlling analysis."""
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


def get(endpoint):
    response = requests.get('http://127.0.0.1:8000/api/' + endpoint, timeout=15)
    response.raise_for_status()
    return response.json()


def values(page):
    result = page.locator('.mix-legend strong')
    assert result.count() == 4
    return [int(''.join(character for character in text if character.isdigit()))
            for text in result.all_text_contents()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('progress', 'completed'), required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--expected-job-id')
    args = parser.parse_args()
    if args.stage == 'completed' and not args.expected_job_id:
        parser.error('A completed capture requires --expected-job-id')
    folder = Path(__file__).resolve().parent
    output = folder / ('ui_' + args.stage)
    output.mkdir(exist_ok=False)
    status = get('analysis/status')
    dashboard = get('dashboard')
    launch = json.loads((folder/'launch.json').read_text(encoding='utf-8'))
    latest_job = dashboard['latest_run']['job_id']
    if args.stage == 'progress':
        assert status['state'] in ('uploading', 'loading_models', 'processing', 'building_maps'), status
    else:
        assert status['state'] == 'complete', status
        assert latest_job == args.expected_job_id, latest_job
        assert dashboard['latest_run']['metrics']['algorithm_sha256'] == launch['expected_algorithm_sha256']
    latest = [fruit for fruit in dashboard['recent_fruits'] if fruit['job_id'] == latest_job]
    classes = {'Class 1': 0, 'Class 2': 0, 'Class 3': 0, 'ungraded': 0}
    for fruit in latest:
        classes[fruit.get('grade') or 'ungraded'] += 1
    (output/'dashboard.json').write_text(json.dumps(dashboard, indent=2), encoding='utf-8')
    errors, api_requests = [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: api_requests.append({'method': request.method, 'url': request.url})
                if '/api/' in request.url else None)
        page.goto('http://localhost:5173', wait_until='domcontentloaded')
        expect(page.get_by_role('button', name='Latest run', exact=True)).to_have_attribute('aria-pressed', 'true')
        page.wait_for_function('(count)=>Number(document.querySelector(".quality-total strong")?.textContent.replace(/[^0-9]/g,""))===count', arg=len(latest))
        assert values(page) == list(classes.values())
        assert page.get_by_role('button', name='Refresh backend', exact=True).is_disabled()
        if args.stage == 'progress':
            expect(page.locator('.analysis-progress')).to_be_visible()
        page.locator('#video-upload').set_input_files(str(args.video.resolve()))
        page.wait_for_function('document.querySelector("video")?.readyState>=2')
        page.locator('video').evaluate('(video)=>new Promise(resolve=>{video.pause();video.addEventListener("seeked",()=>requestAnimationFrame(()=>requestAnimationFrame(resolve)),{once:true});video.currentTime=2.9})')
        page.screenshot(path=output/'latest_run.png', full_page=True)
        progress_text = page.locator('.analysis-progress').inner_text() if args.stage == 'progress' else None
        page.get_by_role('button', name='All saved runs', exact=True).click()
        assert values(page) == list(dashboard['summary']['classes'].values())
        page.screenshot(path=output/'all_saved_runs.png', full_page=True)
        page.get_by_role('button', name='Latest run', exact=True).click()
        if classes['Class 1']:
            page.get_by_role('button', name='Class 1', exact=True).click()
            assert page.locator('.fruit-row').count() == min(6, classes['Class 1'])
            page.screenshot(path=output/'class1_filter.png', full_page=True)
        assert not errors, errors
        browser.close()
    assert all(request['method'] == 'GET' for request in api_requests), api_requests
    report = {'captured_at': datetime.now(timezone.utc).isoformat(), 'passed': True, 'stage': args.stage,
              'method': 'Actual Vite/API in isolated headless Edge; no mocked responses or user browser profile.',
              'status_before_capture': status, 'status_after_capture': get('analysis/status'),
              'progress_text': progress_text, 'latest_saved_job_id': latest_job,
              'latest_saved_records': len(latest), 'latest_saved_classes': classes,
              'all_saved_summary': dashboard['summary'], 'page_errors': errors, 'api_requests': api_requests,
              'expected_runtime_algorithm_sha256': launch['expected_algorithm_sha256'],
              'expected_runtime_main_sha256': launch['expected_main_sha256'],
              'video': str(args.video.resolve()), 'local_preview_only': True, 'preview_seek_sec': 2.9,
              'analysis_requested': False, 'analysis_cancelled': False,
              'limitations': 'During progress, displayed counts belong to the previous completed report. Completed model/algorithm class outputs do not establish manually verified field accuracy.',
              'capture_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'api_requests'}, indent=2))


if __name__ == '__main__':
    main()
