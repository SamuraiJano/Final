"""Freeze a geometry-based one-pixel switch between existing native matchers."""
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parent / "diagnostics" / "algorithm-revision"
BASE = ROOT / "aligned_log_detrended_unblurred_source" / "algorithm_snapshot.py"
OUTPUT = ROOT / "aligned_pixel_switch_source"
EXPECTED = "25d14c1be4321bc6d031eee948d48bd32785a4528d3f45a2eb078fef72a1be04"


def once(source, before, after):
    assert source.count(before) == 1, before
    return source.replace(before, after, 1)


def main():
    baseline = BASE.read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == EXPECTED
    source = baseline.decode("utf-8").replace("\r\n", "\n")
    source = once(source,
        "    resolution = s.image_downsample\n    if s.refine_small_motion and resolution > 1 and coarse_angle < s.minimum_view_rotation_deg:",
        """    resolution = s.image_downsample
    native_cost = s.native_matching_cost
    # Approximate the largest native-pixel displacement from the rolling
    # component and fitted full-resolution fruit radius (sphere chord length).
    pixel_movement = 2. * model.A * np.sin(np.deg2rad(coarse_angle) / 2.)
    if details is not None:
        details.update(native_matching_cost_requested=s.native_matching_cost,
                       matching_cost_used=s.matching_cost,
                       estimated_rolling_movement_px=float(pixel_movement),
                       native_switch_threshold_px=1.)
    if s.refine_small_motion and resolution > 1 and coarse_angle < s.minimum_view_rotation_deg:
        # Smooth green handles subpixel movement and noise; larger movements
        # use the existing surface-aligned pattern without image-plane blur.
        if native_cost == 'aligned_mad' and pixel_movement < 1.:
            native_cost = 'green_mad'""")
    source = once(source,
        "matching_cost=s.native_matching_cost))",
        "matching_cost=native_cost))")
    source = once(source,
        "            details['native_matching_cost'] = s.native_matching_cost",
        "            details['native_matching_cost'] = native_cost\n            details['matching_cost_used'] = native_cost")
    source = once(source,
        "        if s.native_matching_cost in ('green_mad', 'aligned_mad') and abs(angle-coarse_angle) > 3.:",
        "        if native_cost in ('green_mad', 'aligned_mad') and abs(angle-coarse_angle) > 3.:")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "algorithm_snapshot.py"
    assert not target.exists(), "Candidate is immutable; choose a new output folder."
    target.write_text(source, encoding="utf-8", newline="\n")
    metadata = {"baseline_sha256": EXPECTED,
        "candidate_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "changes": "Only when optional native aligned_mad is requested and a successful coarse estimate qualifies for native rechecking: choose existingGaussian2green_mad when 2*A*sin(abs(rolling_axis_angle)/2)<1nativepixel; otherwise existinglog/unblurred/locallydetrendedfull9aligned_mad. A is fitted full-resolution maximum spheroid radius; chord gives approximate maximum projected displacement, not a calibrated true motion. Threshold1nativepixel is derived from sampling geometry. Actual rolling Rodrigues component used, not vector norm. Coarse failure, recheck threshold,3degreeagreement, visibility, all confidence/accuracy limits unchanged. Trace records requested/actualmode/pixelmovement/threshold. Legacy requested green/MAD stays numerically unchanged. Experimental, not production.",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": str(target), **metadata}, indent=2))


if __name__ == "__main__":
    main()
