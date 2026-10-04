"""Freeze log-green, unblurred local-gradient patterns as an isolated candidate."""
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parent / "diagnostics" / "algorithm-revision"
BASE = ROOT / "aligned_detrended_pattern_source" / "algorithm_snapshot.py"
OUTPUT = ROOT / "aligned_log_detrended_unblurred_source"
EXPECTED = "6f2c56ac6edbdc3cc72fecd995055f01a6690113c54115c304b7e29595c20961"


def main():
    baseline = BASE.read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == EXPECTED
    source = baseline.decode("utf-8").replace("\r\n", "\n")
    for which in ("source", "target"):
        before = (f"        {which}_green = {which}.image[:, :, 1].astype(np.float32) / 255.\n"
                  f"        {which}_green = cv2.GaussianBlur({which}_green, (0, 0), 2.)")
        after = (f"        {which}_green = {which}.image[:, :, 1].astype(np.float32) / 255.\n"
                 f"        if s.matching_cost == 'aligned_mad':\n"
                 f"            {which}_green = np.log(np.maximum({which}_green, 1./255.))\n"
                 f"        else:\n"
                 f"            {which}_green = cv2.GaussianBlur({which}_green, (0, 0), 2.)")
        assert source.count(before) == 1
        source = source.replace(before, after, 1)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "algorithm_snapshot.py"
    assert not target.exists(), "Candidate is immutable; choose a new output folder."
    target.write_text(source, encoding="utf-8", newline="\n")
    metadata = {"baseline_sha256": EXPECTED,
        "candidate_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "changes": "Optional aligned_mad only: log(max(green/255,1/255)), noGaussian2camera-plane preblur for descriptor sampling, then same local weighted mean/x/y linear slope removal and weightedRMS normalization of9projected surface-neighborhood samples, weightedMAD/magnitude residual. Multiplicative illumination becomes additive abovefloor; local log-gradient removal is approximate for curved lighting. Additive exposure offsets are not invariant under logarithm. Original green_mad retainsGaussian2; feature selection, geometry, visibility, search, coarse agreement, limits and legacy cost modes unchanged. Experimental, not production.",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": str(target), **metadata}, indent=2))


if __name__ == "__main__":
    main()
