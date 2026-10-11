"""Headless local-report fallback check when the in-app browser tool is unavailable."""
import argparse
import json
from pathlib import Path
import sys


def check(report: Path, output: Path):
    from playwright.sync_api import sync_playwright, expect

    data = json.loads((report.parent/'comparison_summary.json').read_text(encoding='utf-8'))
    modes = sorted({r['mode'] for r in data['results']})
    selected = [r for r in data['results'] if r['mode'] == ('full' if 'full' in modes else modes[0])]
    output.mkdir(parents=True, exist_ok=True)
    errors, requests, checks = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True,
                                             args=['--disable-background-networking'])
        context = browser.new_context(viewport=dict(width=1440, height=1000), accept_downloads=True)
        context.set_offline(True)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        page.goto(report.resolve().as_uri())
        expect(page.get_by_role('heading', name='Naartjie tracker comparison', exact=True)).to_be_visible()
        assert page.locator('#cards .card').count() == 6
        assert page.locator('#summary tbody tr').count() == len(selected)
        assert page.locator('#charts svg').count() == 7
        checks.append('Offline cards, complete tracker table and seven SVG charts render')
        page.get_by_role('button', name='Sort by Processing FPS', exact=True).click()
        values = [float(text.replace(',', '')) for text in page.locator('#summary tbody tr td:nth-child(2)').all_text_contents()]
        assert values == sorted(values)
        checks.append('Comparison columns sort by measured processing values')
        if len(modes) == 2:
            page.get_by_role('button', name='Cached tracker-only replay', exact=True).click()
            expect(page.locator('#scope')).to_contain_text('detector time is excluded')
            selected = [r for r in data['results'] if r['mode'] == 'cached']
            assert page.locator('#summary tbody tr').count() == len(selected)
            expect(page.get_by_role('img', name='Tracker-only processing FPS', exact=True)).to_be_visible()
            checks.append('Timing mode switches table/charts and explicitly excludes detector time')
        target_key = 'tracktrack' if any(r['tracker_key'] == 'tracktrack' for r in selected) else selected[0]['tracker_key']
        page.get_by_label('Tracker', exact=True).select_option(target_key)
        current = next(r for r in selected if r['tracker_key'] == target_key)
        expect(page.locator('#track-count')).to_contain_text(f"of {current['unique_raw_ids']} raw IDs")
        assert page.locator('#tracks-download').get_attribute('href').startswith(target_key+'/')
        if current['unique_raw_ids']:
            with (report.parent/page.locator('#tracks-download').get_attribute('href')).open(encoding='utf-8') as file:
                import csv
                target = next(csv.DictReader(file))['track_id']
            page.get_by_placeholder('Filter raw ID', exact=True).fill(target)
            assert page.locator('#tracks tbody tr').count() > 0
            assert all(target in text for text in page.locator('#tracks tbody tr td:first-child').all_text_contents())
        checks.append('Tracker selection, per-ID filter and export paths work')
        with page.expect_download() as download_info:
            page.get_by_role('link', name='Comparison CSV', exact=True).click()
        download = download_info.value
        download.save_as(output/'comparison_summary.csv')
        assert (output/'comparison_summary.csv').read_bytes() == (report.parent/'comparison_summary.csv').read_bytes()
        checks.append('Local CSV download preserves exported bytes')
        page.screenshot(path=str(output/'desktop-full.png'), full_page=True)
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=str(output/'desktop.png'))
        page.set_viewport_size(dict(width=390, height=844))
        expect(page.get_by_role('heading', name='Naartjie tracker comparison', exact=True)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(output/'mobile-full.png'), full_page=True)
        page.screenshot(path=str(output/'mobile.png'))
        checks.append('Mobile layout contains wide tables in local scroll areas')
        assert not errors, errors
        assert all(url.startswith('file:') for url in requests), requests
        checks.append('No browser errors or external asset/network requests')
        browser.close()
    result = dict(passed=True, checks=checks, report=str(report), browser='headless installed Edge', offline=True)
    (output/'checks.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('report', type=Path)
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--playwright-path', type=Path, help='Optional existing Playwright Python package directory')
    args = cli.parse_args()
    if args.playwright_path:
        sys.path.insert(0, str(args.playwright_path))
    check(args.report.resolve(), args.output.resolve())
