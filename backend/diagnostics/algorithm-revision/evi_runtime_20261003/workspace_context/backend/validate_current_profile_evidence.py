"""Verify a sealed current-profile pack and render its actual local gallery."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zipfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        parser.error("Use a simple evidence-directory label")
    backend = Path(__file__).resolve().parent
    target = backend / "diagnostics/algorithm-revision" / args.label
    output = backend / "diagnostics/ui-checks" / args.label
    checks, count = [], 0
    for line in (target / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        count += 1
        if digest(target / relative) != expected:
            checks.append(relative)
    if checks:
        raise RuntimeError(f"Evidence manifest mismatches: {checks}")
    archive = target.with_suffix(".zip")
    with zipfile.ZipFile(archive) as package:
        if package.testzip(): raise RuntimeError("Archive CRC check failed")
        entries = len(package.infolist())
        names = package.namelist()
        expected_names = {f"{target.name}/{path.relative_to(target).as_posix()}" for path in target.rglob("*") if path.is_file()}
        if len(names) != len(set(names)) or set(names) != expected_names:
            raise RuntimeError("Archive member set differs from the frozen directory payloads")
        archived_manifest = package.read(f"{target.name}/SHA256SUMS.txt").decode("utf-8")
        if archived_manifest != (target / "SHA256SUMS.txt").read_text(encoding="utf-8"):
            raise RuntimeError("Archived checksum manifest differs from the frozen directory")
        for line in archived_manifest.splitlines():
            expected, relative = line.split("  ", 1)
            with package.open(f"{target.name}/{relative}") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise RuntimeError(f"Archived payload hash mismatch: {relative}")
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(Path(os.environ["TEMP"]) / "citrusvision-ui-tools-20261002"))
    from playwright.sync_api import sync_playwright
    errors = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1360, "height": 1020}, device_scale_factor=2)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((target / "index.html").as_uri())
        page.wait_for_function("Array.from(document.images).every(image=>image.complete&&image.naturalWidth>0)")
        if page.get_by_role("heading", name="Current algorithm profile: testing evidence", exact=True).count() != 1:
            raise RuntimeError("Evidence gallery heading missing")
        figures = page.locator("figure")
        if figures.count() < 3: raise RuntimeError("Expected control, actual author and real-model figures")
        page.screenshot(path=output / "gallery_top.png", full_page=False)
        for index in range(figures.count()):
            figures.nth(index).screenshot(path=output / f"figure_{index}.png")
        image_count = page.locator("img").count()
        browser.close()
    if errors: raise RuntimeError(f"Gallery script errors: {errors}")
    record = {"checked_at": datetime.now(timezone(timedelta(hours=2))).isoformat(),
              "method": "Isolated headless Edge local gallery; no user browser profile or estimator/model inference.",
              "target": str(target), "gallery_sha256": digest(target / "index.html"),
              "images_loaded": image_count, "page_errors": errors,
              "manifest_files_verified": count, "manifest_mismatches": checks,
              "archive_sha256": digest(archive), "archive_entries": entries, "archive_crc_verified": True,
              "archive_payload_hashes_verified": True, "archive_member_set_matches_directory": True,
              "visual_review_required": True,
              "scope": "Evidence rendering and archive integrity only; inspect originals before reporting field/model conclusions."}
    (output / "report.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
