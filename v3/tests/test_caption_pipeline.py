import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pipeline


def caption_value(identity_tags=None, subjects=None):
    return {
        "description": "A visible subject in a close portrait.",
        "subjects": subjects if subjects is not None else [{"identity": "woman", "expression": "smiling"}],
        "composition": {"framing": "close-up", "view": "frontal", "camera_angle": "eye-level"},
        "lighting": ["soft light"],
        "environment": ["plain background"],
        "visible_text": [],
        "quality": {"sharpness": "good", "occlusion": "minimal", "training_usable": True, "risks": []},
        "identity_tags": identity_tags if identity_tags is not None else ["woman"],
        "attribute_tags": ["smiling"],
        "apparent_life_stage": "adult",
        "visible_traits": {
            "face_visibility": "full", "hair_color": "dark", "hair_texture": "wavy",
            "hair_style": "loose", "expression": "smiling", "makeup": "unspecified",
            "body_visibility": "head and shoulders", "wardrobe": ["plain top"], "pose": "front"
        },
        "training_caption": "woman smiling"
    }


def caption_task(result_path):
    return {
        "asset_id": "k0l3k4__test",
        "source_path": "/tmp/source.jpeg",
        "source_sha256": "abc123",
        "concept_id": "k0l3k4_identity",
        "required_identity_tags": ["k0l3k4"],
        "class_token": "woman",
        "caption_order": [
            "k0l3k4", "woman", "source_real",
            "view", "framing", "visible expression", "visible occlusion"
        ],
        "status": "pending",
        "result_path": str(result_path)
    }


class CaptionPipelineTests(unittest.TestCase):
    def test_fenced_json_parses_as_top_level_caption(self):
        content = "```json\n" + json.dumps(caption_value()) + "\n```"
        result = pipeline._parse_caption_json(content, "asset")
        self.assertEqual(result["description"], "A visible subject in a close portrait.")

    def test_truncated_outer_json_does_not_return_nested_subject(self):
        content = '{"description":"group","subjects":[{"identity":"woman"}]'
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            pipeline._parse_caption_json(content, "asset")

    def test_policy_enforces_order_and_multi_person_isolation(self):
        task = caption_task("/tmp/result.json")
        value = caption_value(subjects=[{"identity": "woman"}, {"identity": "child"}])
        result = pipeline.apply_caption_policies(task, value)
        self.assertTrue(result["training_caption"].startswith("k0l3k4, woman, source_real"))
        self.assertFalse(result["quality"]["training_usable"])
        self.assertIn("isolate the target subject", " ".join(result["quality"]["risks"]))

    def test_policy_promotes_single_subject_fields(self):
        task = caption_task("/tmp/result.json")
        value = caption_value()
        value.pop("identity_tags")
        value.pop("attribute_tags")
        value.pop("apparent_life_stage")
        value.pop("visible_traits")
        value["subjects"] = [{
            "identity_tags": ["woman"], "attribute_tags": ["wavy hair"],
            "apparent_life_stage": "adult",
            "visible_traits": {
                "face_visibility": "full", "hair_color": "dark", "hair_texture": "wavy",
                "hair_style": "loose", "expression": "smiling", "makeup": "none",
                "body_visibility": "head", "wardrobe": "plain top", "pose": "front"
            }
        }]
        result = pipeline.apply_caption_policies(task, value)
        self.assertEqual(result["identity_tags"], ["woman", "k0l3k4"])
        self.assertEqual(result["attribute_tags"], ["wavy hair"])
        self.assertEqual(result["apparent_life_stage"], "adult")
        self.assertEqual(result["visible_traits"]["wardrobe"], ["plain top"])

    def test_policy_flags_declared_class_mismatch(self):
        task = caption_task("/tmp/result.json")
        result = pipeline.apply_caption_policies(
            task, caption_value(identity_tags=["child"], subjects=[{"identity": "child"}])
        )
        self.assertFalse(result["quality"]["training_usable"])
        self.assertIn("declared class woman", " ".join(result["quality"]["risks"]))

    def test_policy_accepts_class_from_subject_identity(self):
        task = caption_task("/tmp/result.json")
        value = caption_value(identity_tags=[])
        value["subjects"] = [{"identity": "woman"}]
        result = pipeline.apply_caption_policies(task, value)
        self.assertTrue(result["quality"]["training_usable"])
        self.assertNotIn("declared class woman", " ".join(result["quality"]["risks"]))

    def test_policy_blocks_exact_age_caption(self):
        task = caption_task("/tmp/result.json")
        value = caption_value()
        value["training_caption"] = "k0l3k4, woman, mid-20s portrait"
        result = pipeline.apply_caption_policies(task, value)
        self.assertFalse(result["quality"]["training_usable"])
        self.assertIn("exact or narrow age", " ".join(result["quality"]["risks"]))

    def test_isolation_approval_requires_all_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report_path = root / "build" / "isolation" / "k0l3k4" / "isolation_report.json"
            pipeline.core.write_json(report_path, {
                "records": [{
                    "source_sha256": "abc123", "selected_face_id": "face_01",
                    "selected_person_instance": 1, "mask_path": str(root / "mask.png"),
                    "isolated_path": str(root / "isolated.png"),
                    "overlay_path": str(root / "overlay.png")
                }]
            })
            with self.assertRaisesRegex(ValueError, "artifact does not exist"):
                pipeline.review_isolation(root, "abc123", "approved")
            for name in ("mask.png", "isolated.png", "overlay.png"):
                (root / name).write_bytes(b"test")
            result = pipeline.review_isolation(root, "abc123", "approved")
            self.assertEqual(result["review_state"], "approved")

    def test_saved_raw_response_recovers_without_model_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result_path = root / "build" / "captions" / "results" / "k0l3k4__test.json"
            task = caption_task(result_path)
            task_file = {"tasks": [task], "counts": {"total": 1, "pending": 1, "complete": 0}}
            pipeline.core.write_json(root / "build" / "caption_tasks.json", task_file)
            raw_path = root / "build" / "captions" / "raw" / "k0l3k4__test.txt"
            raw_path.parent.mkdir(parents=True)
            raw_path.write_text(json.dumps(caption_value()) + "\n")
            completed, failures = pipeline.run_captions(
                root, {"provider": "huggingface", "model_path": "/not/loaded"}
            )
            self.assertEqual(completed, 1)
            self.assertEqual(failures, [])
            self.assertTrue(result_path.exists())

    def test_multi_person_caption_needs_approved_isolated_caption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result_path = root / "build" / "captions" / "results" / "k0l3k4__test.json"
            task = caption_task(result_path)
            source_result = pipeline._caption_result(
                task,
                json.dumps(caption_value(subjects=[{"identity": "woman"}, {"identity": "child"}])),
                "test-model"
            )
            pipeline.core.write_json(result_path, source_result)
            isolation_root = root / "build" / "isolation" / "k0l3k4"
            pipeline.core.write_json(isolation_root / "isolation_report.json", {
                "records": [{"source_sha256": "abc123", "review_state": "approved"}]
            })
            with self.assertRaisesRegex(ValueError, "approved caption of the isolated derivative"):
                pipeline.review_caption(root, "k0l3k4__test", "approved", "train")
            isolated_task = {**task, "asset_id": "k0l3k4__test__isolated", "source_sha256": "def456"}
            isolated_result = pipeline._caption_result(
                isolated_task, json.dumps(caption_value()), "test-model"
            )
            isolated_result["review_state"] = "approved"
            pipeline.core.write_json(
                isolation_root / "captions" / "results" / "k0l3k4__test__isolated.json",
                isolated_result
            )
            reviewed = pipeline.review_caption(root, "k0l3k4__test", "approved", "train")
            self.assertEqual(reviewed["review_state"], "approved")

    def test_rejected_isolation_counts_as_reviewed_stage_work(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result_path = root / "build" / "captions" / "results" / "k0l3k4__test.json"
            task = caption_task(result_path)
            source_result = pipeline._caption_result(
                task,
                json.dumps(caption_value(subjects=[{"identity": "woman"}, {"identity": "child"}])),
                "test-model"
            )
            source_result["review_state"] = "rejected"
            pipeline.core.write_json(result_path, source_result)
            pipeline.core.write_json(root / "build" / "isolation" / "k0l3k4" / "isolation_report.json", {
                "records": [{"source_sha256": "abc123", "review_state": "rejected"}]
            })
            state = pipeline.refresh_state(
                root,
                context={"project": {"project": {"id": "test"}}},
                catalog={"assets": [{"asset_id": "test"}]},
                captions={"tasks": [{"status": "complete"}]}
            )
            isolation_stage = next(item for item in state["stages"] if item["id"] == "identity_isolation")
            self.assertEqual(isolation_stage["status"], "complete")
            self.assertEqual(isolation_stage["blockers"], [])

    def test_balance_excludes_rejected_isolated_caption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            contract_path = root / "characters" / "k0l3k4.character.json"
            pipeline.core.write_json(contract_path, {
                "character_id": "k0l3k4",
                "identity_concept": "k0l3k4_identity",
                "balance_targets": {"minimum_train_images": 1, "minimum_validation_images": 1}
            })
            result_path = root / "build" / "captions" / "results" / "k0l3k4__test.json"
            task = caption_task(result_path)
            source_result = pipeline._caption_result(
                task,
                json.dumps(caption_value(subjects=[{"identity": "woman"}, {"identity": "child"}])),
                "test-model"
            )
            source_result["concept_id"] = "k0l3k4_identity"
            pipeline.core.write_json(result_path, source_result)
            isolation_root = root / "build" / "isolation" / "k0l3k4"
            pipeline.core.write_json(isolation_root / "isolation_report.json", {
                "records": [{"source_sha256": "abc123", "review_state": "approved"}]
            })
            isolated_result = pipeline._caption_result(task, json.dumps(caption_value()), "test-model")
            isolated_result["review_state"] = "rejected"
            pipeline.core.write_json(
                isolation_root / "captions" / "results" / "k0l3k4__test__isolated.json",
                isolated_result
            )
            report, _, _ = pipeline.build_character_balance_report(root)
            self.assertEqual(report["counts"]["approved_isolated_eligible"], 0)


if __name__ == "__main__":
    unittest.main()
