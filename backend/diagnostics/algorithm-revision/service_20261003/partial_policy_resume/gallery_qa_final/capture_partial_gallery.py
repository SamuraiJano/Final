"""Read-only visual QA for the saved partial-grading evidence gallery."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(os.environ['TEMP'])/'citrusvision-ui-tools-20261002'))
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[5]
GALLERY = ROOT/'backend/diagnostics/algorithm-revision/partial_grades_20261003/index.html'
OUTPUT = Path(__file__).parent/'gallery_qa_final'
OUTPUT.mkdir(exist_ok=False)
errors = []
with sync_playwright() as runtime:
    browser = runtime.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050})
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(GALLERY.as_uri(), wait_until='load')
    images = page.locator('img').evaluate_all('(images)=>images.map(image=>({src:image.getAttribute("src"),loaded:image.complete&&image.naturalWidth>0,width:image.naturalWidth,height:image.naturalHeight}))')
    assert len(images) == 7 and all(image['loaded'] for image in images), images
    page.screenshot(path=OUTPUT/'gallery_desktop.png', full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
    assert not overflow
    page.screenshot(path=OUTPUT/'gallery_mobile.png', full_page=True)
    assert not errors, errors
    browser.close()
report = {'captured_at': datetime.now(timezone.utc).isoformat(), 'passed': True,
          'scope': 'Saved file gallery; separate from actual live app UI screenshots.',
          'gallery': str(GALLERY), 'gallery_sha256': hashlib.sha256(GALLERY.read_bytes()).hexdigest(),
          'images': images, 'page_errors': errors, 'mobile_width': 390,
          'horizontal_overflow': overflow, 'network_transmission': False,
          'inference_requested': False, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(OUTPUT/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
(OUTPUT/'capture_partial_gallery.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(report, indent=2))
