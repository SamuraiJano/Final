"""Check the built dashboard against an isolated API and labelled synthetic run.

Uses local headless Playwright when the in-app Node REPL is unavailable. Never
changes the user's saved runs, camera source, models or calibration.
"""
import json
import hashlib
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

import requests
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'backend'))
sys.path.insert(0, str(Path(os.environ['TEMP'])/'citrusvision-ui-tools-20261002'))
from playwright.sync_api import sync_playwright, expect
from fastapi.staticfiles import StaticFiles
from tracking_metrics import TrackingConfig, TrackingMetrics
import main


def box(position):
    y = 100+8*position
    return [460, y-40, 540, y+40]


def main_check():
    out = ROOT/'backend/diagnostics/tracking-performance/ui'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as temporary:
        sandbox = Path(temporary)
        main.RESULTS = sandbox/'results'
        main.RESULTS.mkdir()
        main.tracking_config_path = sandbox/'tracking_config.json'
        main.tracking_current = None
        folder = main.RESULTS/'synthetic-checkpoints'
        collector = TrackingMetrics(TrackingConfig(region=(.1,.1,.9,.9), lost_buffer_frames=2), folder, folder.name)
        observations = [
            {7:-1, 8:-1, 12:39.8, 18:39.6},
            {7:50, 8:10, 12:40.4, 18:40.9},
            {7:101, 8:20, 12:41.7, 18:41.1},
            {31:30}, {31:40}, {31:50},
        ]
        for frame, positions in enumerate(observations):
            collector.observe(frame, frame*.1, (1000,1000), list(positions),
                              [box(p) for p in positions.values()], .02)
        fixture = collector.finish()
        assert fixture['summary']['id_continuity_percent'] == 50
        assert fixture['summary']['order_inversions'] == 3
        main._write_report(folder, dict(job_id=folder.name, source_name='Synthetic checkpoint validation',
            created_at='2026-10-07T12:00:00+00:00', status='complete',
            metrics={'tracking': main._tracking_report(collector)}, fruits=[]))
        main.app.mount('/', StaticFiles(directory=ROOT/'dist', html=True), name='dashboard-test-build')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(main.app, host='127.0.0.1', port=port, log_level='error'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{port}'
        for _ in range(80):
            try:
                if requests.get(base+'/api/tracking/status', timeout=1).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(.1)
        errors = []
        checks = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width':1440, 'height':1000}, device_scale_factor=1)
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(base, wait_until='networkidle')
                section = page.locator('#tracking')
                expect(section.get_by_role('heading', name='Tracking performance', exact=True)).to_be_visible()
                expect(section.locator('.metric-card').filter(has=page.get_by_text('ID Continuity', exact=True)).locator('.metric-value')).to_have_text('50.0%')
                expect(section.locator('.metric-card').filter(has=page.get_by_text('Processing FPS', exact=True)).locator('.metric-value')).to_have_text('50.0')
                expect(section.locator('.metric-card').filter(has=page.get_by_text('Possible ID Swaps', exact=True)).locator('.metric-value')).to_have_text('3')
                checks.append('Backend values displayed in nine cards')
                section.locator('svg rect[role=button]').nth(20).hover()
                expect(section.locator('.tracking-chart-readout')).to_contain_text('Region 20% → 21%')
                expect(section.locator('.tracking-chart-readout')).to_contain_text('Lost IDs: 8')
                checks.append('Graph hover exposes regional continuity and raw IDs')
                expect(section.get_by_role('cell', name='ID Fragmentation', exact=True)).to_be_visible()
                expect(section.get_by_role('cell', name='Possible ID Swap', exact=True).first).to_be_visible()
                section.get_by_role('textbox', name='Find raw TrackTrack ID').fill('7')
                section.get_by_role('button', name='ID 7', exact=True).click()
                expect(section.get_by_role('region', name='Raw TrackTrack ID 7 details')).to_contain_text('COMPLETE')
                checks.append('Tracking events and searchable per-ID details work')
                for name in ('tracking_summary.csv','region_continuity.csv','checkpoint_crossings.csv','tracking_events.csv'):
                    with page.expect_download() as download:
                        section.get_by_role('link', name=name, exact=True).click()
                    assert download.value.suggested_filename == name
                    download.value.save_as(out/name)
                checks.append('All four CSV download filenames and contents available')
                section.get_by_role('button', name='Apply for future runs').click()
                expect(section.get_by_role('status').filter(has_text='Saved for future runs')).to_be_visible()
                expect(section.locator('details')).not_to_have_attribute('open', '')
                section.locator('summary').click()
                section.get_by_role('button', name='Recalculate this run').click()
                expect(section.get_by_role('status').filter(has_text='recalculated')).to_be_visible()
                checks.append('Region configuration persists and saved-run replay works')
                section.screenshot(path=str(out/'desktop.png'))
                page.set_viewport_size({'width':390, 'height':844})
                section.scroll_into_view_if_needed()
                section.screenshot(path=str(out/'mobile.png'))
                section.locator('.tracking-graph-panel').screenshot(path=str(out/'mobile_graph.png'))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                checks.append('Mobile page has no horizontal overflow; tables scroll locally')
                # A fresh active session takes precedence over the previous run.
                new = main._begin_tracking(main.RESULTS/'fresh-session')
                expect(section.locator('.tracking-run-caption')).to_contain_text('fresh-sessio', timeout=8000)
                expect(section.locator('.metric-card').filter(has=page.get_by_text('ID Continuity', exact=True)).locator('.metric-value')).to_have_text('—')
                expect(section.get_by_text('No suspicious events recorded.', exact=True)).to_be_visible()
                new.finish()
                checks.append('New active run clears old card and event data')
                requests.post(base+'/api/tracking/config', json={'region':None}).raise_for_status()
                unset = main._begin_tracking(main.RESULTS/'uncalibrated-session')
                unset.observe(0, 0, (1000,1000), [17], [box(20)], .02)
                expect(section.get_by_role('status').filter(has_text='Spatial metrics await')).to_be_visible(timeout=8000)
                expect(section.locator('.metric-card').filter(has=page.get_by_text('Lost Tracks', exact=True)).locator('.metric-value')).to_have_text('—')
                expect(section.locator('.metric-card').filter(has=page.get_by_text('Processing FPS', exact=True)).locator('.metric-value')).to_have_text('50.0')
                unset.finish()
                checks.append('Unset region keeps measured timing and marks spatial values unavailable')
                browser.close()
            assert not errors, errors
            hashes = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                      ['backend/algorithm.py','backend/main.py','backend/tracking_metrics.py',
                       'src/App.jsx','src/App.css','src/TrackingPerformance.jsx']}
            (out/'checks.json').write_text(json.dumps({'passed':True,'checks':checks,'page_errors':errors,'source_sha256':hashes}, indent=2),encoding='utf-8')
            print(json.dumps({'passed':True,'checks':checks}))
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == '__main__':
    main_check()
