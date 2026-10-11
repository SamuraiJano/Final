"""Headless dashboard verification using isolated, explicitly synthetic results.

Uses the repository's local Playwright tool installation and Edge. Operator
configuration, camera, running API and saved fruit reports are never changed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time

import cv2
import numpy as np
import requests
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/runtime/ui-tools'))
sys.path.insert(0, str(Path(os.environ.get('TEMP', tempfile.gettempdir())) / 'citrusvision-ui-tools-20261002'))
from playwright.sync_api import sync_playwright, expect
from fastapi.staticfiles import StaticFiles
from inspection_config import InspectionConfiguration
import main


def run():
    output = ROOT / 'backend/diagnostics/timed-views/available-views/ui'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        sandbox = Path(temporary)
        assert sandbox.resolve().is_relative_to(ROOT.resolve())
        main.RESULTS = sandbox / 'results'
        main.RESULTS.mkdir()
        main.inspection_configuration = InspectionConfiguration(sandbox / 'inspection.json')
        main.tracking_config_path = sandbox / 'tracking.json'
        for route in main.app.routes:
            if getattr(route, 'path', None) == '/results':
                route.app = StaticFiles(directory=main.RESULTS)
        folder = main.RESULTS / 'synthetic-ui-only'
        folder.mkdir()
        cv2.imwrite(str(folder / 'contact.png'), np.full((540, 540, 3), (35, 120, 230), np.uint8))
        prefix = f'/results/{folder.name}'
        rows = [dict(track_id=1, algorithm='nine_view', configuration_version=2,
            status='graded_nine_view', grade='Class 3', grade_provisional=True,
            evidence_complete=True, calibration_status='experimental', processed_crops=4, required_crops=4,
            selected_crops=4, views=4, acquisition='timed', worst_view_defect_pct=35., worst_view_frame=8,
            deadline_missed=False, contact_sheet=f'{prefix}/contact.png',
            whole_surface_coverage_known=False),
            dict(track_id=2, algorithm='nine_view', configuration_version=2,
            status='graded_nine_view', grade='Class 2', grade_provisional=True, evidence_complete=False, views=3,
            processed_crops=3, calibration_status='experimental', deadline_missed=True,
            grading_policy='available_views', worst_view_defect_pct=15.,
            reason=None, whole_surface_coverage_known=False)]
        main._write_report(folder, dict(job_id=folder.name, created_at='2026-10-09T12:00:00+00:00',
            source_name='Synthetic UI fixture; no accuracy evidence', status='complete', metrics={}, fruits=rows))
        main.app.mount('/', StaticFiles(directory=ROOT / 'dist', html=True), name='isolated-dashboard')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(main.app, host='127.0.0.1', port=port, log_level='error'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{port}'
        errors, checks = [], []
        try:
            for _ in range(100):
                try:
                    if requests.get(base + '/api/inspection/config', timeout=1).ok: break
                except requests.RequestException: pass
                time.sleep(.1)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='msedge', headless=True, args=['--disable-gpu'])
                page = browser.new_page(viewport={'width': 1440, 'height': 1100})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base, wait_until='networkidle')
                section = page.get_by_role('region', name='Inspection algorithm')
                expect(section.get_by_role('button', name='Surface mapping', exact=True)).to_have_attribute('aria-pressed', 'true')
                main.analysis_lock.acquire()
                section.get_by_role('button', name='Multiview grading', exact=True).click()
                expect(section.get_by_role('button', name='Multiview grading', exact=True)).to_have_attribute('aria-pressed', 'true')
                expect(section.get_by_role('alert')).to_contain_text('Set an inspection region')
                section.locator('summary').click()
                section.get_by_label('Left', exact=True).fill('0.1')
                section.get_by_label('Top', exact=True).fill('0.1')
                section.get_by_label('Right', exact=True).fill('0.9')
                section.get_by_label('Bottom', exact=True).fill('0.9')
                section.get_by_label('Decision deadline after entry (seconds)').fill('4')
                section.get_by_role('button', name='Save for entering fruit', exact=True).click()
                expect(section.get_by_role('status')).to_contain_text('Saved for newly entering fruit')
                stored = requests.get(base + '/api/inspection/config').json()['config']
                assert stored['algorithm'] == 'nine_view' and stored['nine_view']['region'] == [.1, .1, .9, .9]
                assert stored['nine_view']['decision_deadline_seconds'] == 4
                checks.append('Switch and future-fruit configuration work while analysis lock is active')
                section.get_by_role('button', name=re.compile('Use measured timing')).click()
                expect(section.get_by_label('Views per fruit (4–9)')).to_have_value('4')
                stored = requests.get(base + '/api/inspection/config').json()['config']
                assert stored['nine_view']['acquisition'] == 'timed'
                assert stored['nine_view']['region'] == [.1, .1, .9, .9]
                checks.append('Measured timed preset saves 4 views and preserves the configured region')
                for mode in ['surface_mapping', 'nine_view', 'surface_mapping', 'nine_view']:
                    section.get_by_role('button', name='Surface mapping' if mode == 'surface_mapping' else 'Multiview grading', exact=True).click()
                    expect(section.get_by_role('button', name='Surface mapping' if mode == 'surface_mapping' else 'Multiview grading', exact=True)).to_have_attribute('aria-pressed', 'true')
                checks.append('Rapid switches work in both directions')
                main.analysis_lock.release()
                section.screenshot(path=str(output / 'mode-and-settings.png'))
                page.get_by_role('button', name=re.compile('Fruit 001')).click()
                dialog = page.get_by_role('dialog')
                expect(dialog).to_contain_text('Graded from 4 snapshots')
                expect(dialog).to_contain_text('Whole-surface coverage is unknown')
                expect(dialog).to_contain_text('35.0%')
                expect(dialog.get_by_role('img', name='Chronological inspection views of fruit 1')).to_be_visible()
                expect(dialog.get_by_text('Provisional grade from the worst supported', exact=False)).to_be_visible()
                dialog.screenshot(path=str(output / 'complete-provisional-result.png'))
                dialog.get_by_role('button', name='Close inspection').click()
                page.get_by_role('button', name=re.compile('Fruit 002')).click()
                dialog=page.get_by_role('dialog')
                expect(dialog).to_contain_text('Class 2')
                expect(dialog).to_contain_text('Graded from 3 snapshots')
                expect(dialog).not_to_contain_text('incomplete')
                expect(dialog).not_to_contain_text('insufficient')
                dialog.screenshot(path=str(output / 'available-view-grade.png'))
                checks.append('Captured snapshots show a grade without insufficient-frame messages')
                browser.close()
            assert not errors, errors
            hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                      ['src/InspectionMode.jsx', 'src/App.jsx', 'src/App.css', 'backend/main.py']}
            (output / 'checks.json').write_text(json.dumps(dict(passed=True, checks=checks,
                page_errors=errors, fixture='Synthetic; no model or accuracy evidence', source_sha256=hashes), indent=2), encoding='utf-8')
            print(json.dumps(dict(passed=True, checks=checks)))
        finally:
            if main.analysis_lock.locked(): main.analysis_lock.release()
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == '__main__':
    run()
