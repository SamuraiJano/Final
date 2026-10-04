"""Freeze local linear shading removal for the experimental full-pattern matcher."""
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parent / "diagnostics" / "algorithm-revision"
BASE = ROOT / "aligned_pattern_source" / "algorithm_snapshot.py"
OUTPUT = ROOT / "aligned_detrended_pattern_source"
EXPECTED = "9a5a3e13c8b9200958c678110640153022dbe8e59d4e3559ea1743ef579b5067"


def main():
    baseline = BASE.read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == EXPECTED
    source = baseline.decode("utf-8").replace("\r\n", "\n")
    before = """    mean = values @ weights
    contrast = np.sqrt((values - mean[:, :, None])**2 @ weights)
    response = (values - mean[:, :, None]) / np.maximum(contrast[:, :, None], .005)"""
    after = """    mean = values @ weights
    centered = values - mean[:, :, None]
    x, y = np.tile([-1., 0., 1.], 3), np.repeat([-1., 0., 1.], 3)
    # Remove the local linear brightness slope before measuring the pattern.
    # These symmetric weighted coordinates have variance 0.5 on both axes.
    slope_x, slope_y = centered @ (weights*x) / .5, centered @ (weights*y) / .5
    detrended = centered - slope_x[:, :, None]*x - slope_y[:, :, None]*y
    contrast = np.sqrt(detrended**2 @ weights)
    response = detrended / np.maximum(contrast[:, :, None], .005)"""
    assert source.count(before) == 1
    source = source.replace(before, after, 1)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "algorithm_snapshot.py"
    assert not target.exists(), "Candidate is immutable; choose a new output folder."
    target.write_text(source, encoding="utf-8", newline="\n")
    metadata = {"baseline_sha256": EXPECTED,
        "candidate_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "changes": "Optional aligned_mad locally removes weighted constant and x/y linear brightness slopes from the same nine surface-neighborhood samples, then divides by weighted detrended RMS contrast (existingfloor0.005). Weighted symmetric x/y variances0.5. Same full9 weightedMAD and normalized magnitude residual, same geometry/points/visibility/grid/coarse agreement. No global brightness plane, production changes or acceptance tuning. Legacy MAD/green branches unchanged. Experimental.",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": str(target), **metadata}, indent=2))


if __name__ == "__main__":
    main()
