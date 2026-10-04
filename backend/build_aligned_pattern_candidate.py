"""Freeze an experimental nine-sample matcher without changing production."""
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parent / "diagnostics" / "algorithm-revision"
BASE = ROOT / "aligned_contrast_source" / "algorithm_snapshot.py"
OUTPUT = ROOT / "aligned_pattern_source"
EXPECTED = "d3bf284a501351cf98a101a13f588f0b7d1ea02cb72774b2a9bb49397730d651"


def replace_once(source, before, after):
    assert source.count(before) == 1, before
    return source.replace(before, after, 1)


def main():
    baseline = BASE.read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == EXPECTED
    source = baseline.decode("utf-8").replace("\r\n", "\n")
    source = replace_once(source,
        "    response = (values[:, :, 4] - mean) / np.maximum(contrast, .005)",
        "    response = (values - mean[:, :, None]) / np.maximum(contrast[:, :, None], .005)")
    source = replace_once(source,
        "\n\ndef _cost(vector: np.ndarray, points: np.ndarray, source_values: np.ndarray,",
        '''

def _descriptor_cost_many(source_values, target_values, valid, min_points, normalize):
    """Weighted MAD of locally centered, contrast-scaled nine-sample patterns.

    Each pattern is already independent of a constant brightness offset. Keep
    all nine values so different neighborhood patterns cannot share one scalar
    response. The reported residual divides MAD by source plus target absolute
    magnitude; it lies in [0, 1] and does not change the search minimizer.
    """
    weights = np.array([1., 2., 1., 2., 4., 2., 1., 2., 1.]) / 16.
    counts = valid.sum(axis=1)
    difference = np.abs(source_values[None] - target_values) @ weights
    costs = np.where(valid, difference, 0.).sum(axis=1) / np.maximum(counts, 1)
    if normalize:
        magnitude = (np.abs(source_values)[None] + np.abs(target_values)) @ weights
        scale = np.where(valid, magnitude, 0.).sum(axis=1) / np.maximum(counts, 1)
        costs /= np.maximum(scale, .005)
    return np.where(counts >= min_points, costs, np.inf)


def _cost(vector: np.ndarray, points: np.ndarray, source_values: np.ndarray,''')
    source = replace_once(source,
        "        values = patch_values[0, valid]\n    delta = source_values[valid] - values",
        "        return float(_descriptor_cost_many(source_values, patch_values,\n"
        "                                           valid[None], min_points, normalize)[0])\n"
        "    delta = source_values[valid] - values")
    source = replace_once(source,
        "        counts = valid.sum(axis=1)\n    delta = source_values[None,:]-values",
        "        return _descriptor_cost_many(source_values, values, valid, min_points, normalize)\n"
        "    delta = source_values[None,:]-values")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "algorithm_snapshot.py"
    assert not target.exists(), "Candidate is immutable; choose a new output folder."
    target.write_text(source, encoding="utf-8", newline="\n")
    metadata = {
        "baseline_sha256": EXPECTED,
        "candidate_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "changes": "Optional aligned_mad now compares all nine locally weighted-mean-centered/RMS-scaled samples by weighted MAD, instead of a single center-minus-mean scalar. Residual is MAD divided by mean weighted absolute source-plus-target magnitude (floor0.005). No extra brightness median: each pattern is locally centered already. Neighborhood geometry/weights/contrast floor, feature points, visibility, two-axis search/grid, coarse gate and3degreeagreement remain unchanged. Legacy MAD/normalized/green modes unchanged. Experimental, not production.",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": str(target), **metadata}, indent=2))


if __name__ == "__main__":
    main()
