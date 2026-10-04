"""One new seeded texture under two fixed-camera lighting conditions.

Freeze the seed, waveform, known 360-degree motion, inputs and acceptance before
loading the candidate. This limited new synthetic control is not a held-out
real-fruit dataset. Do not tune or regenerate it in response to its outcomes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import time

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import validate_full_turn_motion as full
from validate_native_prefilter import load_module
from validate_motion_resolution import sha256, write_json


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "diagnostics/algorithm-revision/aligned_pattern_source/algorithm_snapshot.py"
SOURCE_SHA = "9a5a3e13c8b9200958c678110640153022dbe8e59d4e3559ea1743ef579b5067"
SEED = 20261002771
LIGHT = np.array([.45, -.35, 1.])
LIGHT /= np.linalg.norm(LIGHT)
ACCEPTANCE = {"all_30_pairs_measured": True, "maximum_pose_error_deg": 5.,
              "maximum_front_visible_landmark_rms_px": 5.}


def now():
    return datetime.now(timezone(timedelta(hours=2))).isoformat()


def waveform():
    rng = np.random.default_rng(SEED)
    directions = rng.normal(size=(14, 3))
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    frequencies = rng.uniform(.14, .36, 14)
    phases = rng.uniform(-np.pi, np.pi, 14)
    amplitudes = rng.uniform(.75, 1.25, 14)
    return directions * frequencies[:, None], phases, amplitudes


def render(mode, vectors, phases, amplitudes):
    # Reuse only the independently defined sphere, truth poses and landmarks.
    # Replace every image with this fresh analytical body texture.
    inputs = full.render([12.] * 30, "a", axis="x")
    yy, xx = np.mgrid[:150, :150]
    x, y = xx - 74.5, yy - 74.5
    z = np.sqrt(np.maximum(55.**2 - x*x - y*y, 0.))
    camera = np.stack((x, y, z), axis=-1)
    mask = inputs["mask"].astype(bool)
    scale = np.sqrt(np.sum(amplitudes**2) / 2.)
    images, extrema = [], []
    for pose in inputs["poses"]:
        body = camera @ pose
        mixture = np.sin(body @ vectors.T + phases) @ amplitudes
        reflectance = 125. + 55. * np.tanh(mixture / scale)
        if mode == "linear_additive":
            values = reflectance + .30 * camera[:, :, 0] + .20 * camera[:, :, 1]
        else:
            diffuse = np.maximum((camera / 55.) @ LIGHT, 0.)
            values = reflectance * (.55 + .45 * diffuse)
        extrema.append((float(values[mask].min()), float(values[mask].max())))
        assert np.all((values[mask] > 0.) & (values[mask] < 255.)), "Fruit pixels must not saturate."
        channel = np.uint8(values)
        channel[~mask] = 0
        images.append(np.repeat(channel[:, :, None], 3, axis=2))
    inputs.update(images=np.array(images), texture_seed=SEED, texture_vectors=vectors,
                  texture_phases=phases, texture_amplitudes=amplitudes,
                  lighting_mode=mode, lighting_direction=LIGHT)
    return inputs, {"fruit_float_min": min(v[0] for v in extrema),
                    "fruit_float_max": max(v[1] for v in extrema), "saturated_fruit_pixels": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="fresh_texture_pattern20_20261002")
    parser.add_argument("--algorithm-source", type=Path, default=SOURCE)
    parser.add_argument("--expected-sha256", default=SOURCE_SHA)
    parser.add_argument("--frozen-input-directory", type=Path)
    args = parser.parse_args()
    output = ROOT / "diagnostics/algorithm-revision" / args.label
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"prepared_at": now(), "seed": SEED, "acceptance": ACCEPTANCE,
        "motion": "Known horizontal x-axis 360-degree turn:30 successive12-degree increments,31frames.",
        "waveform": "Fourteen seeded independent3D directions/frequencies/phases/amplitudes; reflectance125+55*tanh(sum(a*sin(body dot k+phase))/sqrt(sum(a^2)/2)). Frequencies are continuous random values; no repeated angular tile.",
        "illumination_equations": {"linear_additive": "I=reflectance+0.30*camera_x+0.20*camera_y",
            "lambertian_multiplicative": "I=reflectance*(0.55+0.45*max(camera_normal dot normalized[0.45,-0.35,1.0],0))"},
        "scope": "Limited fresh synthetic control after candidate design; not a formally held-out dataset or neural-model/field-grade accuracy test. One new texture, two lighting scenes, ideal sphere/masks, no translation/perspective/occlusion/specular glare. No tuning based on this control's outputs.",
        "scoring": "Independent truth poses and36body landmarks. Compose actual adjacent measured rotations without correction/extrapolation. Score only truth landmarks with camera_z>10pixels. Any unavailable pair fails completeness.",
        "cases": {}}
    if args.frozen_input_directory is None:
        write_json(output / "acceptance_before_execution.json", manifest)
        vectors, phases, amplitudes = waveform()
        for mode in ("lambertian_multiplicative", "linear_additive"):
            name = f"full_turn_x12_{mode}_fresh_texture_c"
            inputs, metadata = render(mode, vectors, phases, amplitudes)
            path = output / f"{name}_inputs.npz"
            np.savez_compressed(path, **inputs)
            image_folder = output / f"{name}_frames"
            image_folder.mkdir()
            for frame, image in enumerate(inputs["images"]):
                cv2.imwrite(str(image_folder / f"frame_{frame:03d}.png"), image)
            manifest["cases"][name] = {"lighting": mode, "input_file": path.name,
                "input_sha256": sha256(path), "frames": 31, "seed": SEED, **metadata}
        manifest["all_inputs_frozen_at"] = now()
        write_json(output / "input_manifest.json", manifest)
    else:
        origin = args.frozen_input_directory.resolve()
        manifest = json.loads((origin / "input_manifest.json").read_text())
        assert manifest["acceptance"] == ACCEPTANCE and manifest["seed"] == SEED
        for name in ("acceptance_before_execution.json", "input_manifest.json"):
            (output / name).write_bytes((origin / name).read_bytes())
        for name, reference in manifest["cases"].items():
            input_path = origin / reference["input_file"]
            assert sha256(input_path) == reference["input_sha256"]
            (output / input_path.name).write_bytes(input_path.read_bytes())
            shutil.copytree(origin / f"{name}_frames", output / f"{name}_frames")
    candidate = args.algorithm_source.resolve()
    assert sha256(candidate) == args.expected_sha256
    (output / "algorithm_snapshot.py").write_bytes(candidate.read_bytes())
    for name in (Path(__file__).name, "validate_full_turn_motion.py", "validate_extended_motion_controls.py",
                 "validate_motion_resolution.py", "validate_native_prefilter.py"):
        (output / name).write_bytes((ROOT / name).read_bytes())
    report = {"started_at": now(), "algorithm_sha256": args.expected_sha256,
              "validator_sha256": sha256(Path(__file__)), "input_manifest_sha256": sha256(output / "input_manifest.json"),
              "frozen_input_directory": str(args.frozen_input_directory.resolve()) if args.frozen_input_directory else None,
              "acceptance": ACCEPTANCE, "seed": SEED, "scope": manifest["scope"], "cases": {}}
    write_json(output / "report.json", report)
    module = load_module(output / "algorithm_snapshot.py", "fresh_pattern_candidate")
    full.OUTPUT = output
    previous_threads = cv2.getNumThreads()
    cv2.setNumThreads(1)
    try:
        for name, reference in manifest["cases"].items():
            path = output / reference["input_file"]
            assert sha256(path) == reference["input_sha256"]
            with np.load(path) as stored:
                inputs = {key: stored[key] for key in stored.files}
            inputs["case"] = name
            started = time.perf_counter()
            result = full.evaluate(module, inputs, hybrid=True, transverse_angle=20.,
                                   recheck_angle=20., native_cost="aligned_mad", max_pair_angle=20.)
            summary = result["summary"]
            complete = summary["measured_pairs"] == 30
            checks = {"all_30_pairs_measured": complete,
                "maximum_pose_within_5deg": complete and summary["maximum_pose_error_deg"] <= 5.,
                "maximum_front_visible_landmarks_within_5px": complete and summary["maximum_landmark_rms_px"] <= 5.}
            report["cases"][name] = {**reference, "result": result, "checks": checks,
                                     "passed": all(checks.values()), "seconds": time.perf_counter()-started}
            write_json(output / "report.json", report)
            print(json.dumps({"case": name, **summary, "checks": checks}), flush=True)
    finally:
        cv2.setNumThreads(previous_threads)
    report["completed_at"] = now()
    report["all_controls_passed"] = all(c["passed"] for c in report["cases"].values())
    write_json(output / "report.json", report)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for panels, (name, case) in zip(axes, report["cases"].items()):
        trace = case["result"]["trace"]
        for panel, key, title in zip(panels, ("pose_error_deg", "landmark_rms_px"),
                                    ("Pose error (degrees)", "Visible landmark RMS (pixels)")):
            panel.plot([r["true_angle_deg"] for r in trace], [r.get(key, np.nan) for r in trace], color="#286b55")
            panel.axhline(5., color="#b47136", ls="--", label="Predeclared5-unitlimit")
            panel.set(title=case["lighting"].replace("_", " "), xlabel="Known rotation (degrees)", ylabel=title)
            panel.grid(alpha=.2)
            panel.legend(fontsize=8)
    fig.suptitle(f"Fresh seeded texture C: actual motion outcomes (seed {SEED})")
    fig.savefig(output / "fresh_texture_accuracy.png", dpi=300)
    fig.savefig(output / "fresh_texture_accuracy.pdf")
    plt.close(fig)
    fig, axes = plt.subplots(2, 5, figsize=(10, 4.5), layout="constrained")
    for row, (name, reference) in zip(axes, manifest["cases"].items()):
        with np.load(output / reference["input_file"]) as stored:
            for panel, frame in zip(row, (0, 7, 15, 22, 30)):
                panel.imshow(stored["images"][frame][:, :, ::-1])
                panel.set(title=f"Frame {frame}: {frame*12}°")
                panel.axis("off")
    fig.suptitle("Fresh texture C, camera-fixed curved (top) and linear (bottom) illumination")
    fig.savefig(output / "fresh_texture_inputs.png", dpi=300)
    fig.savefig(output / "fresh_texture_inputs.pdf")
    plt.close(fig)
    rows = []
    for case in report["cases"].values():
        summary = case["result"]["summary"]
        rows.append(f"| {case['lighting']} | {summary['measured_pairs']}/30 | {summary['maximum_pose_error_deg']:.6f} | {summary['maximum_landmark_rms_px']:.6f} | {'PASS' if case['passed'] else 'FAIL'} |")
    (output / "FRESH_TEXTURE_CONTROL.md").write_text(
        "# Fresh texture C motion control\n\n" + manifest["scope"] + "\n\n"
        f"Seed `{SEED}` and both scenes' waveform, known motion, images, truth and 5°/5px acceptance were frozen before candidate loading. Source `{args.expected_sha256}`; no subsequent tuning.\n\n"
        "| Camera-fixed lighting | Measured pairs | Maximum pose error (degrees) | Maximum visible landmark RMS (pixels) | Outcome |\n"
        "|---|---:|---:|---:|---|\n" + "\n".join(rows) + "\n\n"
        "All-clear maps exercise mapping/class arithmetic only; they do not prove segmentation or real fruit grade accuracy. Complete measured coverage does not itself prove correct pose.\n",
        encoding="utf-8")
    write_json(output / "sha256.json", {str(p.relative_to(output)): sha256(p) for p in output.rglob("*") if p.is_file()})
    print(json.dumps({"output": str(output), "all_controls_passed": report["all_controls_passed"]}), flush=True)


if __name__ == "__main__":
    main()
