"""Check the saved fruit debugger in an isolated, headless Edge session."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import sys


sys.path.insert(0, str(Path(os.environ['TEMP'])/'citrusvision-ui-tools-20261002'))
from playwright.sync_api import sync_playwright


def main():
    root=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--page-label',default='debug_fruit_98_wobble_20261002')
    parser.add_argument('--label',default='walkthrough_wobble_20261002')
    args=parser.parse_args()
    folder=root/'diagnostics/algorithm-revision'/args.page_label
    output=root/'diagnostics/ui-checks'/args.label
    output.mkdir(parents=True,exist_ok=False)
    errors=[]
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1280,'height':1000},device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto((folder/'index.html').as_uri())
        picker=page.get_by_label('Captured frame pair')
        count=picker.locator('option').count()
        assert count==65,count
        initial=page.locator('#source').inner_text()
        assert initial=='Source frame 85',initial
        assert page.locator('#status').inner_text()=='Motion measured'
        page.get_by_role('button',name='Next',exact=True).click()
        assert page.locator('#source').inner_text()=='Source frame 86'
        page.get_by_role('button',name='Previous',exact=True).click()
        assert page.locator('#source').inner_text()==initial
        boundary=page.locator('#sourceImage').get_attribute('src')
        page.get_by_label('Show extracted fruit boundary').uncheck()
        raw=page.locator('#sourceImage').get_attribute('src')
        assert boundary.endswith('_mask.png') and raw=='frame_85.png'
        page.get_by_label('Show extracted fruit boundary').check()
        # Every archived pair should show the actual two images without errors.
        checked=[]
        for index in range(count):
            picker.select_option(str(index))
            page.wait_for_function("Array.from(document.querySelectorAll('#sourceImage,#targetImage')).every(i=>i.complete&&i.naturalWidth>0)")
            checked.append({'source':page.locator('#source').inner_text(),
                            'target':page.locator('#target').inner_text(),
                            'decision':page.locator('#status').inner_text()})
        picker.select_option('23')
        assert page.locator('#source').inner_text()==initial
        page.wait_for_function("Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)")
        assert 'Class 1' in page.locator('#coverage').inner_text()
        assert page.locator('#modelImages img').count()==3
        page.screenshot(path=output/'walkthrough.png',full_page=True)
        page.pdf(path=output/'walkthrough.pdf',print_background=True,format='A4')
        report={'method':'Isolated headless Edge; saved local HTML, no user browser profile.',
                'page':str(folder/'index.html'),'source_sha256':hashlib.sha256((folder/'index.html').read_bytes()).hexdigest(),
                'pair_count':count,'all_pair_images_loaded':len(checked)==65,
                'next_previous_pass':True,'mask_toggle_pass':True,
                'actual_model_overlays_loaded':3,'page_errors':errors,'checked_pairs':checked}
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        (output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
        browser.close()
        assert not errors,errors
    print(json.dumps({k:v for k,v in report.items() if k!='checked_pairs'},indent=2))


if __name__=='__main__':main()
