import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scene_factory


def reconstruction_config():
    return {
        "enabled": True,
        "reference_id": "apple_1984_motion",
        "audio_policy": "strip_and_ignore",
        "approval_authority": "user_only",
        "master": {
            "fidelity": "reference_faithful",
            "cut_precision": "approximate",
            "duration_multiplier": 1.0,
            "invariants": ["narrative boundaries", "story beat order", "relative rhythm"],
        },
        "alternates": {
            "enabled": True,
            "selection": "automatic",
            "scope": "existing_narrative",
            "purpose": "creative_pov_coverage",
            "duration_multiplier": 2.0,
        },
        "layers": {
            "convenience_occluders": "allowed_if_invisible",
        },
        "screen_insert": {
            "mode": "tracked_chroma_green_plane",
            "color": "#00FF00",
            "shatter_with_screen": True,
        },
    }


class ReferenceReconstructionTests(unittest.TestCase):
    def test_coverage_compiles_one_master_plus_three_times_total(self):
        context = {
            "total_duration": 10.0,
            "project": {"reference_reconstruction": reconstruction_config()},
            "scenes": [{
                "id": "scene_02",
                "environment_id": "pursuit_corridor",
                "shots": [{
                    "id": "shot_02",
                    "duration_seconds": 10,
                    "cast": ["k0l3k4", "enforcers"],
                    "props": ["hammer"],
                    "formations": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                }],
            }],
        }

        result = scene_factory.compile_reference_coverage(context, Path("/tmp/output"))

        self.assertEqual(result["summary"]["master_tasks"], 1)
        self.assertEqual(result["summary"]["alternate_tasks"], 3)
        self.assertEqual(result["summary"]["master_seconds"], 10.0)
        self.assertEqual(result["summary"]["alternate_seconds"], 20.0)
        self.assertEqual(result["summary"]["total_seconds"], 30.0)
        self.assertEqual(result["summary"]["coverage_multiplier"], 3.0)
        self.assertTrue(all(item["audio_policy"] == "strip_and_ignore" for item in result["tasks"]))

    def test_k_enforcers_and_held_hammer_have_separate_ownership(self):
        scene = {"id": "scene_02", "environment_id": "pursuit_corridor"}
        shot = {"id": "shot_02", "cast": ["k0l3k4", "enforcers"], "props": ["hammer"]}

        layers = scene_factory.render_layers_for_shot(scene, shot, reconstruction_config())
        by_id = {item["id"]: item for item in layers}

        self.assertIn("k0l3k4_foreground", by_id)
        self.assertIn("enforcers_group", by_id)
        self.assertFalse(by_id["k0l3k4_foreground"]["includes_held_hammer"])
        self.assertIn("held_hammer", by_id)
        self.assertEqual(by_id["held_hammer"]["interaction_owner"], "k0l3k4")
        self.assertEqual(
            by_id["k0l3k4_foreground"]["conditioning_scope"]["include_subjects"],
            ["k0l3k4"],
        )
        self.assertIn(
            "enforcers",
            by_id["k0l3k4_foreground"]["conditioning_scope"]["exclude_subjects"],
        )
        self.assertEqual(
            by_id["enforcers_group"]["conditioning_scope"]["include_subjects"],
            ["enforcers"],
        )
        self.assertIsNone(
            by_id["enforcers_group"]["conditioning_scope"]["identity_lora"]
        )
        self.assertEqual(by_id["enforcers_group"]["must_render_separately_from"], ["k0l3k4"])
        self.assertNotIn("released_hammer", by_id)

    def test_hammer_transfers_to_prop_layer_at_release(self):
        scene = {"id": "scene_05", "environment_id": "ideology_hall"}
        shot = {"id": "shot_05", "cast": ["k0l3k4", "dystopian_masses"], "props": ["hammer"]}

        layers = scene_factory.render_layers_for_shot(scene, shot, reconstruction_config())
        by_id = {item["id"]: item for item in layers}

        self.assertFalse(by_id["k0l3k4_foreground"]["includes_held_hammer"])
        self.assertEqual(by_id["held_hammer"]["ownership_state"], "held_by_k0l3k4")
        self.assertEqual(by_id["released_hammer"]["activation"], "at_release")
        self.assertEqual(by_id["released_hammer"]["ownership_transfer_from"], "k0l3k4")
        self.assertEqual(by_id["released_hammer"]["ownership_state"], "released")
        self.assertEqual(
            by_id["released_hammer"]["conditioning_scope"]["geometry_lock"],
            [
                "one straight handle", "one crosswise hammer head",
                "bare grip end", "no duplicate head",
            ],
        )

    def test_green_insert_ends_at_screen_impact(self):
        scene = {"id": "scene_06", "environment_id": "ideology_hall"}
        shot = {"id": "shot_06", "cast": ["dystopian_masses"], "props": ["hammer"]}

        layers = scene_factory.render_layers_for_shot(scene, shot, reconstruction_config())
        insert = next(item for item in layers if item["id"] == "tracked_green_insert")

        self.assertEqual(insert["lifetime"], "until_screen_impact")
        self.assertTrue(insert["shatter_with_screen"])
        self.assertFalse(insert["generated_content"])

    def test_post_manifest_is_visual_only_and_explicit_about_planned_layers(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary)
            (project_root / "project.json").write_text("{}\n", encoding="utf-8")
            coverage = {
                "summary": {"master_seconds": 10, "alternate_seconds": 20, "total_seconds": 30},
                "tasks": [{
                    "id": "coverage__scene_02__shot_02__master",
                    "coverage_type": "master",
                    "required": True,
                    "narrative_order": 1,
                    "scene_id": "scene_02",
                    "shot_id": "shot_02",
                    "target_duration_seconds": 10,
                    "output_root": str(project_root / "outputs" / "shot_02"),
                    "layers": [{"id": "k0l3k4_foreground", "z_order": 30, "matte_required": True}],
                }],
            }
            generation = {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "project": {"id": "test"},
                "source_scripts": [],
                "reference_coverage": coverage,
            }

            output, result = scene_factory.compile_post_production_manifest(project_root, generation)

            self.assertTrue(output.is_file())
            self.assertEqual(result["audio_policy"], "strip_and_ignore")
            self.assertEqual(result["audio_artifacts"], [])
            layer = result["shots"][0]["layers"][0]
            self.assertEqual(layer["state"], "invalidated")
            self.assertTrue(layer["media_path"].endswith("k0l3k4_foreground.mov"))
            self.assertTrue(layer["matte_path"].endswith("k0l3k4_foreground__matte.mov"))
            self.assertEqual(result["shots"][0]["approval"]["required_actor"], "user")


if __name__ == "__main__":
    unittest.main()
