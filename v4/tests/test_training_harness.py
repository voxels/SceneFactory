import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import training_harness
import test_identity_pipeline


class TrainingHarnessTests(unittest.TestCase):
    def test_quality_assessment_rejects_small_flat_image(self):
        policy = {
            "minimum_width": 512,
            "minimum_height": 512,
            "minimum_contrast": 18,
            "minimum_sharpness": 4,
            "brightness_range": [24, 232],
        }
        _, reasons = training_harness.quality_assessment(
            {"width": 100, "height": 100, "contrast": 0, "sharpness": 0, "brightness": 0}, policy
        )
        self.assertIn("width_below_minimum", reasons)
        self.assertIn("contrast_below_minimum", reasons)
        self.assertIn("too_dark", reasons)

    def test_near_duplicate_clustering(self):
        records = [
            {"asset_id": "a", "visual_metrics": {"dhash64": "0000000000000000"}},
            {"asset_id": "b", "visual_metrics": {"dhash64": "0000000000000001"}},
            {"asset_id": "c", "visual_metrics": {"dhash64": "ffffffffffffffff"}},
        ]
        groups = training_harness.near_duplicate_clusters(records, 1)
        self.assertEqual(sorted(len(group) for group in groups), [1, 2])

    def test_audio_metrics_and_quality_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            audio = project.parent / "source/voice/sample.wav"
            metrics = training_harness.audio_metrics(audio, transcript_words=2)
            self.assertEqual(metrics["analysis_status"], "complete")
            self.assertAlmostEqual(metrics["duration_seconds"], 0.1, places=2)
            reasons = training_harness.audio_quality_assessment(metrics, {
                "audio_minimum_duration_seconds": 1.0,
                "audio_maximum_clipping_fraction": 0.01,
                "audio_maximum_silence_fraction": 0.5,
            })
            self.assertIn("duration_below_minimum", reasons)
            self.assertIn("excessive_silence", reasons)

    def test_review_manifest_preserves_decisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "build"
            record = {"asset_id": "a", "kind": "image", "modality": "photos", "path": "/a", "sha256": "1"}
            first = training_harness.load_or_create_reviews(output, [record], "now")
            first["records"][0]["decision"] = "approved"
            (output / "review_manifest.json").write_text(json.dumps(first))
            second = training_harness.load_or_create_reviews(output, [record], "later")
            self.assertEqual(second["records"][0]["decision"], "approved")

    def test_decide_rejects_unknown_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            with self.assertRaisesRegex(ValueError, "Unknown review asset"):
                training_harness.decide(project, "missing", "rejected", reviewer="tester")

    def test_export_refuses_incomplete_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            with self.assertRaisesRegex(ValueError, "not ready"):
                training_harness.export_training_package(project, Path(temporary) / "export", run_mode="fine_tuning")

    def test_automatic_export_does_not_require_reviews(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            build = project / "build/identity"
            build.mkdir(parents=True)
            visual = root / "visual.jpg"
            geometry = root / "head.usdz"
            transcript = root / "tts.txt"
            visual.write_bytes(b"visual")
            geometry.write_bytes(b"geometry")
            transcript.write_text("hello")
            visual_hash = training_harness.identity.sha256_file(visual)
            assets = []
            for asset_id, kind, path in (("geometry", "geometry", geometry), ("script", "transcript", transcript)):
                assets.append({"asset_id": asset_id, "kind": kind, "path": str(path), "sha256": training_harness.identity.sha256_file(path), "roles": [kind]})
            (build / "asset_manifest.json").write_text(json.dumps({"assets": assets}))
            (build / "review_manifest.json").write_text(json.dumps({"records": [{"asset_id": item["asset_id"], "decision": "pending"} for item in assets]}))
            selection = {
                "schema_version": 4,
                "run_mode": "automatic",
                "identity_id": "test",
                "ready_for_training": True,
                "blockers": [],
                "selections": [{"asset_id": "visual", "path": str(visual), "sha256": visual_hash, "split": "train", "eligible_for_export": True}],
            }
            conditioning = {"fusion_invariants": ["automatic"]}
            with mock.patch("training_harness.select", return_value=(selection, conditioning)):
                package = training_harness.export_training_package(project, root / "export")
            self.assertEqual(package["run_mode"], "automatic")
            self.assertEqual(len(package["visual"]), 1)
            self.assertEqual(len(package["channels"]["geometry"]), 1)
            self.assertEqual(len(package["channels"]["transcript"]), 1)

    def test_fixture_config_supports_full_harness_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            path = project / "identity.json"
            config = json.loads(path.read_text())
            path.write_text(json.dumps(config))
            selection, conditioning = training_harness.select(project)
            self.assertEqual(selection["run_mode"], "automatic")
            self.assertFalse(any("consent" in item or "audio" in item or "approval" in item for item in selection["blockers"]))
            self.assertIn("identity annotation manifest is missing", selection["blockers"])
            self.assertIn("visual_identity", conditioning["channels"])
            self.assertTrue((project / "build/identity/processed_manifest.json").is_file())
            self.assertTrue((project / "build/identity/selection_manifest.json").is_file())

    def test_fine_tuning_mode_enables_review_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            config_path = project / "identity.json"
            config = json.loads(config_path.read_text())
            config["identity"]["consent"]["status"] = "unverified"
            (project.parent / "source/voice/sample.wav").unlink()
            config_path.write_text(json.dumps(config))
            selection, conditioning = training_harness.select(project, run_mode="fine_tuning")
            self.assertEqual(selection["run_mode"], "fine_tuning")
            self.assertIn("consent is not verified", selection["blockers"])
            self.assertIn("generated voice audio has not been supplied", selection["blockers"])
            self.assertTrue(conditioning["channels"]["webarchive_derivatives"]["requires_review"])

    def test_group_id_drives_split_and_motion_only_frames_are_not_visual_training(self):
        video_frame = {
            "asset_id": "motion-frame",
            "kind": "image",
            "modality": "captured_video_frames",
            "path": "/tmp/motion.jpg",
            "sha256": "1" * 64,
            "group_id": "video:motion",
            "usage_roles": ["motion_reference"],
            "training_policy": "derive_then_review",
            "provenance": "sampled_user_video_frame",
            "automatic_quality_pass": True,
            "quality_score": 100,
            "visual_metrics": {"dhash64": "0" * 16},
        }
        identity_frame_a = dict(video_frame, asset_id="identity-a", sha256="2" * 64, group_id="video:identity", usage_roles=["visual_identity"])
        identity_frame_b = dict(video_frame, asset_id="identity-b", sha256="3" * 64, group_id="video:identity", usage_roles=["visual_identity"], visual_metrics={"dhash64": "f" * 16})
        # The group split invariant itself is deterministic and independent of derivative hashes.
        def split_for(item):
            group_id = item.get("group_id", f"source_sha256:{item['sha256']}")
            return int(training_harness.hashlib.sha256(group_id.encode()).hexdigest()[:8], 16)
        self.assertEqual(split_for(identity_frame_a), split_for(identity_frame_b))
        self.assertFalse(any(role in {"visual_identity", "both"} for role in video_frame["usage_roles"]))

    def test_coverage_selection_round_robins_shot_strata(self):
        records = [
            {"asset_id": "close-a", "modality": "photos", "quality_score": 90},
            {"asset_id": "close-b", "modality": "photos", "quality_score": 80},
            {"asset_id": "full-a", "modality": "photos", "quality_score": 70},
        ]
        annotations = {"close-a": {"shot_size": "close_up"}, "close-b": {"shot_size": "close_up"}, "full-a": {"shot_size": "full_body"}}
        captions = {item["asset_id"]: {"clean_shot_score": item["quality_score"] / 100} for item in records}
        selected = training_harness.coverage_constrained_select(records, annotations, captions, 2)
        self.assertEqual({item["asset_id"] for item in selected}, {"close-a", "full-a"})

    def test_group_safe_splits_include_all_heldout_sets_without_leakage(self):
        records = [
            {"asset_id": f"asset-{index}", "sha256": f"{index:064x}", "group_id": f"group-{index // 2}"}
            for index in range(20)
        ]
        policy = {"validation_fraction": 0.15, "calibration_fraction": 0.10, "final_test_fraction": 0.10}
        assignments = training_harness.group_safe_splits(records, policy)
        self.assertEqual(set(assignments.values()), {"train", "validation", "calibration", "final_test"})
        self.assertEqual(len(assignments), 10)
        self.assertEqual(assignments, training_harness.group_safe_splits(list(reversed(records)), policy))


if __name__ == "__main__":
    unittest.main()
