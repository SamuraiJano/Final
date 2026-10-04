"""Validate independent labels, completion state, and dataset preservation."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from import_tracking_annotations import AnnotationError, import_annotations, validate_bundle


class TrackingAnnotationImportTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "schema_version": 1,
            "dataset_id": "a" * 64,
            "frames": [{"frame": 1, "source_frame": 40}, {"frame": 2, "source_frame": 41}],
            "width": 100,
            "height": 80,
            "source_sha256": "b" * 64,
            "predictions_sha256": "c" * 64,
            "annotation_complete": False,
            "reviewed_frames": [],
            "unresolved_annotations": [],
            "split": "pilot",
        }
        self.bundle = {
            "schema_version": 1,
            "dataset_id": "a" * 64,
            "reviewed_frames": [1, 2],
            "rows": [[2, 19, 5, 8, 20, 25, 1, -1, -1, -1],
                     [1, 19, 0, 0, 100, 80, 1, -1, -1, -1]],
            "unresolved_annotations": [],
            "annotator": "Reviewer A",
        }

    def test_complete_bundle_uses_independent_physical_count(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["rows"].append([2, 31, 50, 50, 10, 15, 1, -1, -1, -1])
        validated = validate_bundle(self.manifest, bundle)
        self.assertTrue(validated["annotation_complete"])
        self.assertEqual(validated["physical_fruit_count"], 2)
        self.assertEqual(validated["labelled_observation_count"], 3)
        self.assertEqual([row[:2] for row in validated["rows"]], [[1, 19], [2, 19], [2, 31]])

    def test_partial_bundle_cannot_claim_complete(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["reviewed_frames"] = [1]
        bundle["rows"] = [bundle["rows"][1]]
        validated = validate_bundle(self.manifest, bundle)
        self.assertFalse(validated["annotation_complete"])
        self.assertEqual(validated["reviewed_frame_count"], 1)

    def test_unresolved_identity_prevents_complete_annotation(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["unresolved_annotations"] = [{"frame": 2, "reason": "Two fruit disappear behind one another."}]
        validated = validate_bundle(self.manifest, bundle)
        self.assertFalse(validated["annotation_complete"])
        self.assertEqual(validated["unresolved_count"], 1)

    def test_reviewed_empty_clip_is_not_claimed_complete(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["rows"] = []
        self.assertFalse(validate_bundle(self.manifest, bundle)["annotation_complete"])

    def test_duplicate_identity_box_is_rejected_and_unreviewed_backup_remains_incomplete(self):
        duplicate = copy.deepcopy(self.bundle)
        duplicate["rows"].append(duplicate["rows"][0])
        with self.assertRaisesRegex(AnnotationError, "two boxes"):
            validate_bundle(self.manifest, duplicate)
        unreviewed = copy.deepcopy(self.bundle)
        unreviewed["reviewed_frames"] = [1]
        validated = validate_bundle(self.manifest, unreviewed)
        self.assertFalse(validated["annotation_complete"])
        self.assertEqual(validated["labelled_unreviewed_frames"], [2])
        self.assertEqual(validated["labelled_observation_count"], 2)

    def test_numeric_physical_ids_are_strict_positive_integers(self):
        for value in (True, 0, -3, 1.0, "19"):
            with self.subTest(value=value):
                bundle = copy.deepcopy(self.bundle)
                bundle["rows"][0][1] = value
                with self.assertRaisesRegex(AnnotationError, "positive integer"):
                    validate_bundle(self.manifest, bundle)

    def test_dataset_provenance_and_schema_are_required(self):
        invalid_hash = copy.deepcopy(self.manifest)
        invalid_hash["dataset_id"] = "not-a-sha256"
        with self.assertRaisesRegex(AnnotationError, "SHA-256"):
            validate_bundle(invalid_hash, self.bundle)
        unrelated = copy.deepcopy(self.bundle)
        unrelated["dataset_id"] = "d" * 64
        with self.assertRaisesRegex(AnnotationError, "does not match"):
            validate_bundle(self.manifest, unrelated)
        wrong_schema = copy.deepcopy(self.bundle)
        wrong_schema["schema_version"] = 2
        with self.assertRaisesRegex(AnnotationError, "schema_version"):
            validate_bundle(self.manifest, wrong_schema)

    def test_invalid_or_outside_visible_boxes_are_rejected(self):
        boxes = ([0, 0, 0, 10], [-1, 0, 20, 10], [90, 0, 20, 10],
                 [0, 75, 20, 10], [0, 0, float("nan"), 10],
                 [0, 0, 20, float("inf")], [False, 0, 20, 10])
        for box in boxes:
            with self.subTest(box=box):
                bundle = copy.deepcopy(self.bundle)
                bundle["rows"][0][2:6] = box
                with self.assertRaises(AnnotationError):
                    validate_bundle(self.manifest, bundle)

    def test_reviewed_frame_numbers_and_unresolved_reasons_are_checked(self):
        for reviewed in ([1, 1, 2], [1, 3], [0, 1], [True, 2]):
            with self.subTest(reviewed=reviewed):
                bundle = copy.deepcopy(self.bundle)
                bundle["reviewed_frames"] = reviewed
                with self.assertRaises(AnnotationError):
                    validate_bundle(self.manifest, bundle)
        for issue in ({"frame": 3, "reason": "unknown"}, {"frame": 2, "reason": " "}):
            with self.subTest(issue=issue):
                bundle = copy.deepcopy(self.bundle)
                bundle["unresolved_annotations"] = [issue]
                with self.assertRaises(AnnotationError):
                    validate_bundle(self.manifest, bundle)

    def test_nonblank_annotator_and_mot_suffix_are_required(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["annotator"] = "  "
        with self.assertRaisesRegex(AnnotationError, "annotator"):
            validate_bundle(self.manifest, bundle)
        bundle = copy.deepcopy(self.bundle)
        bundle["rows"][0][6] = 0
        with self.assertRaisesRegex(AnnotationError, "must end"):
            validate_bundle(self.manifest, bundle)

    def test_plain_integer_frames_and_local_frame_records_are_supported(self):
        for records in ([1, 2], [{"local_frame": 1}, {"local_frame": 2}]):
            manifest = copy.deepcopy(self.manifest)
            manifest["frames"] = records
            self.assertTrue(validate_bundle(manifest, self.bundle)["annotation_complete"])

    def _write_dataset(self, root):
        dataset = root / "prepared"
        dataset.mkdir()
        (dataset / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        # Predictions can be unreadable: they must not influence validation.
        (dataset / "predictions.csv").write_bytes(b"independent frozen prediction bytes\x00")
        (dataset / "frames").mkdir()
        (dataset / "frames" / "000001.jpg").write_bytes(b"frozen frame bytes")
        annotations = root / "annotations.json"
        annotations.write_text(json.dumps(self.bundle), encoding="utf-8")
        return dataset, annotations

    def test_import_writes_integer_mot_csv_and_preserves_dataset_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset, annotations = self._write_dataset(root)
            retained = {name: (dataset / name).read_bytes()
                        for name in ("predictions.csv", "frames/000001.jpg")}
            annotations_before = annotations.read_bytes()
            result = import_annotations(dataset, annotations)
            self.assertTrue(result["annotation_complete"])
            csv_bytes = (dataset / "ground_truth.csv").read_bytes()
            self.assertEqual(csv_bytes, b"1,19,0,0,100,80,1,-1,-1,-1\n2,19,5,8,20,25,1,-1,-1,-1\n")
            rows = list(csv.reader(csv_bytes.decode().splitlines()))
            self.assertEqual(len(rows), 2)
            updated = json.loads((dataset / "manifest.json").read_text())
            self.assertTrue(updated["annotation_complete"])
            self.assertEqual(updated["reviewed_frames"], [1, 2])
            self.assertEqual(updated["unresolved_annotations"], [])
            for key, value in self.manifest.items():
                if key not in ("annotation_complete", "reviewed_frames", "unresolved_annotations"):
                    self.assertEqual(updated[key], value)
            self.assertEqual(updated["annotation_metadata"]["physical_fruit_count"], 1)
            self.assertEqual(annotations.read_bytes(), annotations_before)
            for name, payload in retained.items():
                self.assertEqual((dataset / name).read_bytes(), payload)

    def test_partial_reimport_resets_previously_complete_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset, annotations = self._write_dataset(Path(temporary))
            import_annotations(dataset, annotations)
            partial = copy.deepcopy(self.bundle)
            partial["reviewed_frames"] = [1]
            partial["rows"] = [partial["rows"][1]]
            annotations.write_text(json.dumps(partial), encoding="utf-8")
            result = import_annotations(dataset, annotations)
            self.assertFalse(result["annotation_complete"])
            updated = json.loads((dataset / "manifest.json").read_text())
            self.assertFalse(updated["annotation_complete"])
            self.assertEqual(updated["reviewed_frames"], [1])
            self.assertEqual(updated["unresolved_annotations"], [])

    def test_import_publishes_unresolved_state_at_manifest_top_level(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset, annotations = self._write_dataset(Path(temporary))
            unresolved = copy.deepcopy(self.bundle)
            unresolved["unresolved_annotations"] = [{"frame": 2, "reason": "Identity cannot be resolved."}]
            annotations.write_text(json.dumps(unresolved), encoding="utf-8")
            import_annotations(dataset, annotations)
            updated = json.loads((dataset / "manifest.json").read_text())
            self.assertFalse(updated["annotation_complete"])
            self.assertEqual(updated["reviewed_frames"], [1, 2])
            self.assertEqual(updated["unresolved_annotations"], unresolved["unresolved_annotations"])

    def test_prepare_import_evaluate_complete_dataset(self):
        import cv2
        import numpy as np
        from evaluate_tracking_test import evaluate_tracking, read_mot
        from prepare_tracking_test import prepare

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "two_frames.avi"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (64, 48))
            self.assertTrue(writer.isOpened(), "OpenCV must support the MJPG test video")
            try:
                for value in (50, 80):
                    writer.write(np.full((48, 64, 3), value, dtype=np.uint8))
            finally:
                writer.release()
            cached = root / "tracking.json"
            cached.write_text(json.dumps([
                {"frame": 0, "tracks": [[10, 10, 30, 30, 93, 0.9, 0]]},
                {"frame": 1, "tracks": [[11, 10, 31, 30, 93, 0.9, 0]]},
            ]), encoding="utf-8")
            dataset = root / "prepared"
            manifest = prepare(video, cached, dataset, 0, 1)
            self.assertFalse(manifest["annotation_complete"])
            bundle = {
                "schema_version": 1, "dataset_id": manifest["dataset_id"],
                "reviewed_frames": [1, 2], "unresolved_annotations": [],
                "annotator": "Synthetic integration control",
                "rows": [[1, 7, 10, 10, 20, 20, 1, -1, -1, -1],
                         [2, 7, 11, 10, 20, 20, 1, -1, -1, -1]],
            }
            annotations = root / "annotation_bundle.json"
            annotations.write_text(json.dumps(bundle), encoding="utf-8")
            import_annotations(dataset, annotations)
            updated = json.loads((dataset / "manifest.json").read_text())
            result = evaluate_tracking(
                read_mot(dataset / "ground_truth.csv", ground_truth=True),
                read_mot(dataset / "predictions.csv", ground_truth=False), updated,
            )
            self.assertEqual(updated["reviewed_frames"], [1, 2])
            self.assertEqual(updated["unresolved_annotations"], [])
            self.assertEqual(result["identity"]["IDF1"], 1.0)
            self.assertEqual(result["fruit_tracking"]["successful"], 1)
            self.assertEqual(result["counts"]["physical_fruit"], 1)

    def test_invalid_import_leaves_previous_results_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset, annotations = self._write_dataset(Path(temporary))
            old_manifest = (dataset / "manifest.json").read_bytes()
            (dataset / "ground_truth.csv").write_bytes(b"previous approved annotation")
            invalid = copy.deepcopy(self.bundle)
            invalid["dataset_id"] = "d" * 64
            annotations.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaises(AnnotationError):
                import_annotations(dataset, annotations)
            self.assertEqual((dataset / "manifest.json").read_bytes(), old_manifest)
            self.assertEqual((dataset / "ground_truth.csv").read_bytes(), b"previous approved annotation")

    def test_failed_manifest_replace_restores_previous_ground_truth(self):
        import import_tracking_annotations as importer
        with tempfile.TemporaryDirectory() as temporary:
            dataset, annotations = self._write_dataset(Path(temporary))
            old_manifest = (dataset / "manifest.json").read_bytes()
            (dataset / "ground_truth.csv").write_bytes(b"previous approved annotation")
            real_replace = importer.os.replace

            def replace(source, destination):
                if Path(destination).name == "manifest.json":
                    raise OSError("simulated manifest write failure")
                return real_replace(source, destination)

            with patch.object(importer.os, "replace", side_effect=replace):
                with self.assertRaisesRegex(OSError, "simulated"):
                    import_annotations(dataset, annotations)
            self.assertEqual((dataset / "manifest.json").read_bytes(), old_manifest)
            self.assertEqual((dataset / "ground_truth.csv").read_bytes(), b"previous approved annotation")
            self.assertEqual(sorted(path.name for path in dataset.iterdir()),
                             ["frames", "ground_truth.csv", "manifest.json", "predictions.csv"])


if __name__ == "__main__":
    unittest.main()
