"""Freeze logarithmic green intensities for the optional surface-pattern matcher."""
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parent / "diagnostics" / "algorithm-revision"
BASE = ROOT / "aligned_pattern_source" / "algorithm_snapshot.py"
OUTPUT = ROOT / "aligned_log_pattern_source"
EXPECTED = "9a5a3e13c8b9200958c678110640153022dbe8e59d4e3559ea1743ef579b5067"


def main():
    baseline = BASE.read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == EXPECTED
    source = baseline.decode("utf-8").replace("\r\n", "\n")
    for which in ("source", "target"):
        before = f"        {which}_green = {which}.image[:, :, 1].astype(np.float32) / 255.\n"
        after = before + f"        if s.matching_cost == 'aligned_mad':\n            {which}_green = np.log(np.maximum({which}_green, 1./255.))\n"
        assert source.count(before) == 1
        source = source.replace(before, after, 1)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "algorithm_snapshot.py"
    assert not target.exists(), "Candidate is immutable; choose a new output folder."
    target.write_text(source, encoding="utf-8", newline="\n")
    metadata = {"baseline_sha256": EXPECTED,
        "candidate_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "changes": "Only optional aligned_mad compares log(max(green/255,1/255)) with existingGaussian2preblur, then the unchanged full9 locally centered/RMS-scaled surface-neighborhood descriptor and weightedMAD. Multiplicative illumination becomes additive before smoothing when channels remain abovefloor; this does not guarantee invariance to spatially curved illumination after rotation. Constant additive exposure offsets are not invariant under logarithm. Original strong-point selection, visibility, two-axis grid, coarse gate/3degreeagreement/limits and MAD/normalized/green_mad modes unchanged. Experimental, not production.",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": str(target), **metadata}, indent=2))


if __name__ == "__main__":
    main()
