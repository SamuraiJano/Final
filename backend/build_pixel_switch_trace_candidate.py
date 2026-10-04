"""Freeze truthful matcher-mode traces before a coarse/native search can fail."""
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parent / "diagnostics" / "algorithm-revision"
BASE = ROOT / "aligned_pixel_switch_source" / "algorithm_snapshot.py"
OUTPUT = ROOT / "aligned_pixel_switch_trace_source"
EXPECTED = "d57078ace090cd6aedaad97a614d0a3bb9d8045c2896141400c052e8aa7ce12c"


def main():
    baseline = BASE.read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == EXPECTED
    source = baseline.decode("utf-8").replace("\r\n", "\n")
    changes = [
        ("        details.update(image_downsample=s.image_downsample, highpass_sigma=s.highpass_sigma)",
         "        details.update(image_downsample=s.image_downsample, highpass_sigma=s.highpass_sigma,\n"
         "                       native_matching_cost_requested=s.native_matching_cost,\n"
         "                       matching_cost_used=s.matching_cost,\n"
         "                       estimated_rolling_movement_px=None, native_switch_threshold_px=1.)"),
        ("            details.update(image_downsample=1, highpass_sigma=native_sigma)",
         "            details.update(image_downsample=1, highpass_sigma=native_sigma,\n"
         "                           native_matching_cost=native_cost, matching_cost_used=native_cost)")]
    for before, after in changes:
        assert source.count(before) == 1
        source = source.replace(before, after, 1)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "algorithm_snapshot.py"
    assert not target.exists(), "Candidate is immutable; choose a new output folder."
    target.write_text(source, encoding="utf-8", newline="\n")
    metadata = {"baseline_sha256": EXPECTED,
        "candidate_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "changes": "Trace-only correction: initialize requested/actual mode,1pixelthreshold and unavailable estimatedmovement before coarse search; record chosen native mode before native search can raise. No mathematical, control-flow, search, threshold or decision changes to d570. Numeric equivalence must be checked separately. Experimental, not production.",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": str(target), **metadata}, indent=2))


if __name__ == "__main__":
    main()
