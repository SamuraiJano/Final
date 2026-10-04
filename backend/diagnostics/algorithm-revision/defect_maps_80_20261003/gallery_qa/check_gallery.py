"""Read-only local gallery verification; no API, model or service operations."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(os.environ['TEMP']) / 'citrusvision-ui-tools-20261002'))
from playwright.sync_api import sync_playwright, expect

folder = Path(__file__).resolve().parent
gallery = folder.parent / 'index.html'
errors, requests = [], []
source_before = gallery.read_bytes()

with sync_playwright() as runtime:
    browser = runtime.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append({'method': request.method, 'url': request.url}))
    page.goto(gallery.as_uri(), wait_until='load')
    expect(page.get_by_role('heading', name='Preserved naartjie texture with coloured predicted defects', exact=True)).to_be_visible()
    images = page.locator('figure img')
    expect(images).to_have_count(4)
    images.evaluate_all('(images)=>Promise.all(images.map(image=>image.complete&&image.naturalWidth>0 ? true : new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject})))')
    image_info = images.evaluate_all('(images)=>images.map(image=>({src:image.getAttribute("src"),alt:image.alt,width:image.naturalWidth,height:image.naturalHeight,loaded:image.complete&&image.naturalWidth>0}))')
    assert all(image['loaded'] for image in image_info)
    desktop = page.evaluate('({width:innerWidth,content:document.documentElement.scrollWidth,bodyFont:getComputedStyle(document.body).fontSize})')
    assert desktop['content'] <= desktop['width']
    page.screenshot(path=folder / 'desktop_gallery.png', full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    mobile = page.evaluate('({width:innerWidth,content:document.documentElement.scrollWidth,bodyFont:getComputedStyle(document.body).fontSize})')
    assert mobile['content'] <= mobile['width']
    page.screenshot(path=folder / 'mobile_gallery.png', full_page=True)
    browser.close()

assert not errors, errors
assert all(request['method'] == 'GET' and request['url'].startswith('file:') for request in requests), requests
assert gallery.read_bytes() == source_before
report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'passed': True,
          'method': 'Local HTML in isolated headless Edge; no mocked responses, user browser profile, API or model operations.',
          'images': image_info, 'image_count': len(image_info), 'page_errors': errors,
          'desktop_dimensions': desktop, 'mobile_dimensions': mobile,
          'all_requests_local_file_GET': True, 'api_requests': 0,
          'source_sha256': hashlib.sha256(source_before).hexdigest(),
          'gallery_changed_by_check': False,
          'check_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'limitations': 'Checks gallery loading and layout; predictions and identity are not manually verified.'}
(folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
