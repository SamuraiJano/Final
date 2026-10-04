"""Score the SAME four historical author chains against retained adjacent poses.

This check is separate from the zero-nonadjacent-bridge count. A chain can remain
connected through intermediate retained views and still have accumulated error.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

import cv2
import numpy as np


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[3]
sys.path.insert(0, str(PROJECT / "backend"))
import benchmark_authors as benchmark

spec = importlib.util.spec_from_file_location("fixed_chain_algorithm", HERE / "algorithm_snapshot.py")
algorithm = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = algorithm
spec.loader.exec_module(algorithm)
for name in ("FruitView", "MappingError", "_height", "_ellipse", "_largest_component"):
    setattr(benchmark, name, getattr(algorithm, name))


def main():
    original_path = (PROJECT / "backend/diagnostics/algorithm-audit/decision_20261002"
                     "/author_bridge_baseline/report.json")
    retained_path = (benchmark.ROOT / "bridge_runs/adjacent_native_retained_20261002/report.json")
    original = json.loads(original_path.read_text(encoding="utf-8"))
    retained = json.loads(retained_path.read_text(encoding="utf-8"))
    settings = algorithm.Settings(**retained["settings"])
    rows = []
    for old in original["bridge_endpoint_pairs"]:
        row = {name: old[name] for name in ("group", "object", "source", "target",
                                           "source_xy", "target_xy", "author_annotation_lines")}
        row.update(baseline_error_px=old["error_px"], baseline_prediction=old["prediction"])
        track = next(t for t in retained["tracks"]
                     if t["group"] == old["group"] and t["object"] == old["object"])
        frames = track.get("selected_frames", [])
        row["selected_frames"] = frames
        if old["source"] not in frames or old["target"] not in frames:
            row.update(status="unavailable", reason="Endpoint excluded from retained connected segment")
        else:
            folder = benchmark.DATA / "rotation/data" / old["group"] / old["object"]
            views = benchmark.load_views(folder, original["settings"].get("mask_threshold", 0))
            model = algorithm.fit_spheroid(views, settings)
            selected_model = algorithm._subset_spheroid(model, frames)
            by_pair = {(r["source_frame"],r["target_frame"]): r
                       for r in track["selection_diagnostics"]
                       if r["method"] == "adjacent_measurement" and r["status"] == "accepted"}
            rotations = {i: cv2.Rodrigues(np.deg2rad(by_pair[(a,b)]["rotation_vector_deg"]))[0]
                         for i,(a,b) in enumerate(zip(frames[:-1],frames[1:]))}
            adjusted = {**row, "source": frames.index(old["source"]),
                        "target": frames.index(old["target"])}
            try:
                prediction = benchmark.predict_point(adjusted,selected_model,rotations)
                row.update(status="predicted",prediction=prediction.tolist(),
                           error_px=float(np.linalg.norm(prediction-np.asarray(old["target_xy"]))))
            except algorithm.MappingError as error:
                row.update(status="unavailable",reason=str(error))
        rows.append(row)

    good = [r for r in rows if r["status"] == "predicted"]
    result = {"method": "Reuse the SAME four exact author chains previously accepted as bad direct bridges. "
                        "Score their endpoints using composed retained adjacent matrices whenever both endpoints survive. "
                        "No labels are used to fit motion and no absent prediction is counted as correct.",
              "limitations": "Correlated development labels, not held-out motion or grade accuracy. "
                              "Rejected/unavailable chains document exclusion rather than accurate reconstruction.",
              "algorithm_sha256": hashlib.sha256((HERE / "algorithm_snapshot.py").read_bytes()).hexdigest(),
              "original_report_sha256": hashlib.sha256(original_path.read_bytes()).hexdigest(),
              "retained_report_sha256": hashlib.sha256(retained_path.read_bytes()).hexdigest(),
              "chains_total": len(rows), "predicted_chains": len(good),
              "unavailable_chains": len(rows)-len(good),
              "errors_px_conditional_on_prediction": benchmark.stats([r["error_px"] for r in good]),
              "fraction_all_chains_within_5px": sum(r["error_px"] <= 5 for r in good)/len(rows),
              "rows": rows}
    (HERE / "fixed_chain_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
