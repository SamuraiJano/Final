"""Check the development gallery, archived payloads and report figures locally."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(os.environ["TEMP"]) / "citrusvision-ui-tools-20261002"))
from playwright.sync_api import sync_playwright


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    backend = Path(__file__).resolve().parent
    target = backend / "diagnostics/algorithm-revision/development_followup_20261002"
    output = backend / "diagnostics/ui-checks/development_followup_20261002"
    output.mkdir(parents=True, exist_ok=False)
    mismatches, payloads = [], 0
    for line in (target / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        payloads += 1
        if digest(target / relative) != expected: mismatches.append(relative)
    assert not mismatches, mismatches
    archive = target.with_suffix(".zip")
    with zipfile.ZipFile(archive) as package:
        bad_entry = package.testzip()
        assert bad_entry is None, bad_entry
        archived_entries = len(package.infolist())
    errors = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1000}, device_scale_factor=2)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((target / "index.html").as_uri())
        page.wait_for_function("Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)")
        image_count = page.locator("img").count()
        assert image_count == 3, image_count
        assert page.get_by_role("heading", name="Continued algorithm testing: failures preserved", exact=True).count() == 1
        page.screenshot(path=output / "gallery_top.png", full_page=False)
        figures = page.locator("figure")
        assert figures.count() == 3
        # The generated gallery orders the comparison, false-eligible maps, inputs.
        figures.nth(1).screenshot(path=output / "false_eligible_card.png")
        browser.close()
    assert not errors, errors
    record = {"checked_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
        "method": "Isolated headless Edge; saved local gallery, no user browser profile.",
        "target": str(target), "gallery_sha256": digest(target / "index.html"),
        "gallery_images_loaded": image_count, "page_errors": errors,
        "sha256_payloads_checked": payloads, "sha256_mismatches": mismatches,
        "archive_sha256": digest(archive), "archive_entries": archived_entries, "archive_crc_verified": True,
        "visual_figures_reviewed": ["camera_shading_comparison.png", "false_eligible_maps.png"],
        "scope": "Gallery rendering and archive integrity; no new algorithm accuracy test."}
    (output / "report.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps(record, indent=2))


if __name__ == "__main__": main()
