"""Known physical identities exercise the evaluator, not tracker heuristics."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.optimize import linear_sum_assignment

from evaluate_tracking_test import Observation, evaluate_tracking, main, read_mot, match_frame


def manifest(frames):
    return {"schema_version": 1, "frame_index_base": 1, "coordinate_format": "xywh",
            "frames": list(frames), "reviewed_frames": list(frames), "annotation_complete": True,
            "unresolved_annotations": []}


def obs(frame, identity, x=0, y=0, width=10, height=10):
    return Observation(frame, identity, (x, y, width, height))


def augmented_identity_reference(gt, pred, declared_frames, threshold=0.5):
    """Independent TrackEval-style dummy-assignment formulation of ID metrics.

    Uses scalar box intersection calculations, all potential matches, separate
    FP/FN matrices and dummy trajectory rows/columns. Production uses a reduced
    maximum-count assignment instead. See the official Identity reference URL
    recorded by the evaluator; no external package or source download needed.
    """
    gt_ids = sorted({row.identity for row in gt})
    pred_ids = sorted({row.identity for row in pred})
    n, m = len(gt_ids), len(pred_ids)
    potentials = np.zeros((n, m))
    gt_counts = np.zeros(n)
    pred_counts = np.zeros(m)
    for frame in declared_frames:
        for g in [row for row in gt if row.frame == frame]:
            gi = gt_ids.index(g.identity)
            gt_counts[gi] += 1
            for p in [row for row in pred if row.frame == frame]:
                pi = pred_ids.index(p.identity)
                a, b = g.box, p.box
                overlap_x = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
                overlap_y = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
                intersection = overlap_x * overlap_y
                similarity = intersection / (a[2] * a[3] + b[2] * b[3] - intersection)
                if similarity >= threshold:
                    potentials[gi, pi] += 1
        for p in [row for row in pred if row.frame == frame]:
            pred_counts[pred_ids.index(p.identity)] += 1
    fp_matrix = np.zeros((n + m, n + m))
    fn_matrix = np.zeros((n + m, n + m))
    fp_matrix[n:, :m] = 1e10
    fn_matrix[:n, m:] = 1e10
    for gi in range(n):
        fn_matrix[gi, :m] = gt_counts[gi]
        fn_matrix[gi, m + gi] = gt_counts[gi]
    for pi in range(m):
        fp_matrix[:n, pi] = pred_counts[pi]
        fp_matrix[n + pi, pi] = pred_counts[pi]
    fn_matrix[:n, :m] -= potentials
    fp_matrix[:n, :m] -= potentials
    assigned_rows, assigned_columns = linear_sum_assignment(fp_matrix + fn_matrix)
    idfn = int(fn_matrix[assigned_rows, assigned_columns].sum())
    idfp = int(fp_matrix[assigned_rows, assigned_columns].sum())
    idtp = len(gt) - idfn
    return idtp, idfp, idfn


class TrackingEvaluationTests(unittest.TestCase):
    def test_perfect_tracking_and_one_prediction_id_per_fruit(self):
        gt = [obs(frame, identity, x=identity * 30) for frame in range(1, 5) for identity in (1, 2)]
        pred = [obs(row.frame, row.identity + 100, x=row.box[0]) for row in gt]
        result = evaluate_tracking(gt, pred, manifest(range(1, 5)))
        self.assertEqual(result["detection"]["tp"], 8)
        self.assertEqual(result["identity"]["IDF1"], 1)
        self.assertEqual(result["fruit_tracking"]["strict_success_rate"], 1)
        self.assertEqual(result["validation_status"], "ground_truth_validated")
        self.assertTrue(result["acceptance_gate"]["numeric_window_pass"])
        self.assertEqual(result["acceptance_gate"]["final_tracking_acceptance"], "not_assessed")

    def test_one_physical_fruit_split_into_two_ids(self):
        gt = [obs(frame, 1) for frame in range(1, 5)]
        pred = [obs(frame, 10 if frame < 3 else 20) for frame in range(1, 5)]
        result = evaluate_tracking(gt, pred, manifest(range(1, 5)))
        self.assertEqual(result["detection"]["recall"], 1)
        self.assertEqual(result["identity"]["id_switches"], 1)
        self.assertEqual(result["identity"]["IDTP"], 2)
        self.assertEqual(result["identity"]["IDF1"], 0.5)
        self.assertFalse(result["per_fruit"][0]["strict_tracking_success"])

    def test_two_fruit_swap_predictions_and_both_fail(self):
        gt = [obs(frame, identity, x=identity * 30) for frame in range(1, 5) for identity in (1, 2)]
        pred = [obs(row.frame, row.identity + 10 if row.frame < 3 else 13 - row.identity,
                    x=row.box[0]) for row in gt]
        result = evaluate_tracking(gt, pred, manifest(range(1, 5)))
        self.assertEqual(result["identity"]["id_switches"], 2)
        self.assertEqual(result["identity"]["reused_prediction_ids"], 2)
        self.assertEqual(result["identity"]["IDF1"], 0.5)
        self.assertEqual(result["fruit_tracking"]["successful"], 0)

    def test_missed_frame_then_same_id_is_fragmentation_without_switch(self):
        result = evaluate_tracking([obs(f, 1) for f in (1, 2, 3)], [obs(f, 7) for f in (1, 3)], manifest((1, 2, 3)))
        self.assertEqual(result["detection"]["fn"], 1)
        self.assertEqual(result["identity"]["fragmentations"], 1)
        self.assertEqual(result["identity"]["id_switches"], 0)

    def test_missed_frame_does_not_hide_an_id_switch(self):
        result = evaluate_tracking([obs(f, 1) for f in (1, 2, 3)], [obs(1, 7), obs(3, 8)], manifest((1, 2, 3)))
        self.assertEqual(result["identity"]["fragmentations"], 1)
        self.assertEqual(result["identity"]["id_switches"], 1)
        self.assertEqual(result["events"]["id_switches"][0]["previous_prediction_id"], 7)

    def test_prefix_and_suffix_misses_do_not_create_fragmentations(self):
        result = evaluate_tracking([obs(f, 1) for f in range(1, 6)], [obs(f, 7) for f in (2, 3, 4)], manifest(range(1, 6)))
        self.assertEqual(result["identity"]["fragmentations"], 0)

    def test_gt_invisibility_does_not_count_as_tracker_fragmentation(self):
        result = evaluate_tracking([obs(1, 1), obs(3, 1)], [obs(1, 7), obs(3, 7)], manifest((1, 2, 3)))
        self.assertEqual(result["identity"]["fragmentations"], 0)
        self.assertEqual(result["fruit_tracking"]["successful"], 1)

    def test_same_prediction_id_reused_for_a_later_distinct_fruit(self):
        result = evaluate_tracking([obs(1, 1), obs(2, 2)], [obs(1, 7), obs(2, 7)], manifest((1, 2)))
        self.assertEqual(result["identity"]["id_switches"], 0)
        self.assertEqual(result["identity"]["reused_prediction_ids"], 1)
        self.assertEqual(result["fruit_tracking"]["successful"], 0)
        self.assertEqual(result["events"]["id_reuse"], {"7": [1, 2]})

    def test_two_ids_on_one_fruit_are_duplicate_even_with_perfect_recall(self):
        result = evaluate_tracking([obs(1, 1)], [obs(1, 7), obs(1, 8, x=0.1)], manifest((1,)))
        self.assertEqual(result["detection"]["tp"], 1)
        self.assertEqual(result["detection"]["fp"], 1)
        self.assertEqual(result["identity"]["duplicate_observations"], 1)
        self.assertIn("simultaneous_duplicate_boxes", result["per_fruit"][0]["failure_reasons"])

    def test_overlapping_correctly_matched_fruit_are_not_duplicates(self):
        result = evaluate_tracking([obs(1, 1), obs(1, 2, x=1)], [obs(1, 7), obs(1, 8, x=1)], manifest((1,)))
        self.assertEqual(result["detection"]["tp"], 2)
        self.assertEqual(result["identity"]["duplicate_observations"], 0)

    def test_reuse_as_an_extra_duplicate_also_contaminates_original_fruit(self):
        result = evaluate_tracking([obs(1, 1), obs(2, 2)],
                                   [obs(1, 7), obs(2, 8), obs(2, 7, x=0.1)], manifest((1, 2)))
        self.assertEqual(result["events"]["id_reuse"], {"7": [1, 2]})
        self.assertEqual(result["fruit_tracking"]["successful"], 0)
        self.assertEqual(result["per_fruit"][0]["dominant_id_prediction_purity"], 0.5)

    def test_explicit_empty_frame_keeps_false_positive(self):
        result = evaluate_tracking([obs(1, 1)], [obs(1, 7), obs(2, 8)], manifest((1, 2)))
        self.assertEqual(result["counts"]["reviewed_empty_frames"], 1)
        self.assertEqual(result["detection"]["fp"], 1)
        self.assertEqual(result["identity"]["IDFP"], 1)
        self.assertEqual(result["identity"]["IDF1"], 2 / 3)

    def test_missing_all_predictions_retains_all_fruit_in_denominator(self):
        result = evaluate_tracking([obs(1, 1), obs(2, 1), obs(2, 2)], [], manifest((1, 2)))
        self.assertEqual(result["identity"]["IDFN"], 3)
        self.assertEqual(result["identity"]["IDF1"], 0)
        self.assertEqual(result["fruit_tracking"], {"successful": 0, "total": 2, "strict_success_rate": 0})

    def test_default_empty_gt_is_rejected_but_explicit_empty_control_counts_fp(self):
        with self.assertRaisesRegex(ValueError, "empty ground truth"):
            evaluate_tracking([], [obs(1, 7)], manifest((1,)))
        result = evaluate_tracking([], [obs(1, 7)], manifest((1,)), allow_empty_ground_truth=True)
        self.assertEqual(result["identity"]["IDFP"], 1)
        self.assertIsNone(result["fruit_tracking"]["strict_success_rate"])
        self.assertEqual(result["validation_status"], "reviewed_empty_sequence")

    def test_threshold_boundary_and_cardinality_precede_total_iou(self):
        # Greedy or ordinary IoU-only assignment would choose one valid match.
        similarity = np.array([[1.0, 0.5], [0.5, 0.49]])
        self.assertEqual(set(match_frame(similarity, 0.5)), {(0, 1), (1, 0)})

    def test_idf1_uses_all_potential_matches_not_local_assignment_only(self):
        gt = [obs(f, 1) for f in (1, 2)] + [obs(f, 2, x=1) for f in (1, 2)]
        pred = [obs(1, 7, x=0.1), obs(2, 7, x=0.9)]
        result = evaluate_tracking(gt, pred, manifest((1, 2)))
        local_gt = [frame["matches"][0]["ground_truth_id"] for frame in result["per_frame"]]
        self.assertEqual(local_gt, [1, 2])
        self.assertEqual(result["identity"]["IDTP"], 2)
        self.assertEqual(result["identity"]["IDFN"], 2)
        self.assertEqual(result["identity"]["IDF1"], 2 / 3)

    def test_reduced_id_assignment_matches_official_augmented_formulation(self):
        rng = np.random.default_rng(8821)
        frames = list(range(1, 8))
        for trial in range(30):
            gt = [obs(frame, identity, x=float(rng.integers(0, 35)))
                  for frame in frames for identity in range(1, 5) if rng.random() > 0.15]
            pred = [obs(frame, identity, x=float(rng.integers(0, 35)))
                    for frame in frames for identity in range(10, 16) if rng.random() > 0.3]
            result = evaluate_tracking(gt, pred, manifest(frames))
            actual = tuple(result["identity"][name] for name in ("IDTP", "IDFP", "IDFN"))
            self.assertEqual(actual, augmented_identity_reference(gt, pred, frames), msg=f"trial {trial}")

    def test_strict_recall_boundary_is_fixed_and_not_partial_image_success(self):
        gt = [obs(frame, 1) for frame in range(1, 21)]
        result = evaluate_tracking(gt, [obs(frame, 7) for frame in range(2, 21)], manifest(range(1, 21)))
        self.assertEqual(result["per_fruit"][0]["visible_frame_recall"], 0.95)
        self.assertTrue(result["per_fruit"][0]["strict_tracking_success"])
        result = evaluate_tracking(gt, [obs(frame, 7) for frame in range(3, 21)], manifest(range(1, 21)))
        self.assertFalse(result["per_fruit"][0]["strict_tracking_success"])

    def test_majority_stable_id_does_not_hide_a_short_identity_swap(self):
        gt = [obs(frame, 1) for frame in range(1, 21)]
        pred = [obs(frame, 8 if frame == 10 else 7) for frame in range(1, 21)]
        result = evaluate_tracking(gt, pred, manifest(range(1, 21)))
        self.assertEqual(result["per_fruit"][0]["dominant_id_visible_frame_coverage"], 0.95)
        self.assertFalse(result["per_fruit"][0]["strict_tracking_success"])

    def test_unreviewed_incomplete_or_unresolved_manifest_rejected(self):
        for modification in ({"annotation_complete": False}, {"reviewed_frames": []},
                             {"unresolved_annotations": [{"frame": 1}]}, {"frames": [1, 1]},
                             {"frame_index_base": 0}, {"coordinate_format": "xyxy"}):
            invalid = {**manifest((1,)), **modification}
            with self.subTest(modification=modification), self.assertRaises(ValueError):
                evaluate_tracking([obs(1, 1)], [obs(1, 7)], invalid)

    def test_prediction_frame_outside_manifest_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, "outside the manifest"):
            evaluate_tracking([obs(1, 1)], [obs(2, 7)], manifest((1,)))

    def test_skipped_frames_and_non_one_start_cannot_claim_complete_review(self):
        for frames in ((1, 3), (7, 8), (2,)):
            with self.subTest(frames=frames), self.assertRaisesRegex(ValueError, "consecutive local numbers"):
                evaluate_tracking([obs(frames[0], 1)], [obs(frames[0], 7)], manifest(frames))

    def test_invalid_threshold_and_repeated_identity_rejected(self):
        for threshold in (0, -1, 1.1, float("nan")):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                evaluate_tracking([obs(1, 1)], [], manifest((1,)), iou_threshold=threshold)
        with self.assertRaisesRegex(ValueError, "repeated identity"):
            evaluate_tracking([obs(1, 1)], [obs(1, 7), obs(1, 7)], manifest((1,)))

    def test_mot_csv_rejects_invalid_rows_and_ignored_fruit(self):
        invalid_rows = ["0,1,0,0,10,10,1", "1,1.5,0,0,10,10,1", "1,1,0,0,0,10,1",
                        "1,1,nan,0,10,10,1", "1,1,0,0,10,10,0", "1,1,0,0,10,10",
                        "1,1,0,0,10,10,1\n1,1,5,0,10,10,1"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gt.csv"
            for content in invalid_rows:
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ValueError):
                    read_mot(path, ground_truth=True)

    def test_prediction_confidence_is_optional_and_no_filter_is_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pred.csv"
            path.write_text("1,7,0,0,10,10\n2,7,0,0,10,10,0.001,-1,-1,-1\n", encoding="utf-8")
            pred = read_mot(path, ground_truth=False)
            result = evaluate_tracking([obs(1, 1), obs(2, 1)], pred, manifest((1, 2)))
            self.assertEqual(result["detection"]["tp"], 2)

    def test_high_window_stability_alone_does_not_pass_detection_and_identity_gate(self):
        result = evaluate_tracking([obs(1, 1)], [obs(1, 7), obs(1, 8, x=30)], manifest((1,)))
        self.assertEqual(result["fruit_tracking"]["strict_success_rate"], 1)
        self.assertFalse(result["acceptance_gate"]["numeric_window_pass"])
        self.assertFalse(result["acceptance_gate"]["requirements"]["detection_precision"]["passed"])
        self.assertFalse(result["acceptance_gate"]["requirements"]["IDF1"]["passed"])

    def test_sensitivity_threshold_cannot_claim_primary_gate_pass(self):
        result = evaluate_tracking([obs(1, 1)], [obs(1, 7)], manifest((1,)), iou_threshold=0.3)
        self.assertIsNone(result["acceptance_gate"]["numeric_window_pass"])
        self.assertFalse(result["acceptance_gate"]["is_primary_threshold"])

    def test_cli_writes_input_hashes_and_rejects_unreviewed_ground_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            gt, pred, meta = directory / "gt.csv", directory / "pred.csv", directory / "manifest.json"
            gt.write_text("1,1,0,0,10,10,1,-1,-1,-1\n", encoding="utf-8")
            pred.write_text("1,7,0,0,10,10,0.9,-1,-1,-1\n", encoding="utf-8")
            meta.write_text(json.dumps(manifest((1,))), encoding="utf-8")
            argv = ["--ground-truth", str(gt), "--predictions", str(pred), "--manifest", str(meta), "--output-dir", str(directory / "out")]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(argv), 0)
            report = json.loads((directory / "out" / "tracking_evaluation.json").read_text(encoding="utf-8"))
            self.assertEqual(len(report["inputs"]["ground_truth"]["sha256"]), 64)
            meta.write_text(json.dumps({**manifest((1,)), "annotation_complete": False}), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(argv), 2)

    def test_cli_checks_imported_ground_truth_hash_before_scoring_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            gt, pred, meta = directory / "gt.csv", directory / "pred.csv", directory / "manifest.json"
            gt.write_text("1,1,0,0,10,10,1,-1,-1,-1\n", encoding="utf-8")
            pred.write_text("1,7,0,0,10,10,0.9,-1,-1,-1\n", encoding="utf-8")
            metadata = {"ground_truth_sha256": hashlib.sha256(gt.read_bytes()).hexdigest()}
            meta.write_text(json.dumps({**manifest((1,)), "annotation_metadata": metadata}), encoding="utf-8")
            argv = ["--ground-truth", str(gt), "--predictions", str(pred), "--manifest", str(meta), "--output-dir", str(directory / "out")]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(argv), 0)
            gt.write_text("1,1,30,0,10,10,1,-1,-1,-1\n", encoding="utf-8")
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                self.assertEqual(main(argv), 2)
            self.assertIn("hash differs", error.getvalue())


if __name__ == "__main__":
    unittest.main()
