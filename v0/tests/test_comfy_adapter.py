import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import comfy_adapter


class ComfyAdapterTests(unittest.TestCase):
    def test_flux_graph_routes_model_through_identity_lora(self):
        graph = comfy_adapter.text_image_graph(
            "k0l3k4 portrait", "extra people", "test/output", 2184,
            lora_name=comfy_adapter.K0L3K4_LORA, lora_strength=0.85
        )
        self.assertEqual(graph["14"]["class_type"], "LoraLoaderModelOnly")
        self.assertEqual(graph["14"]["inputs"]["model"], ["1", 0])
        self.assertEqual(graph["14"]["inputs"]["strength_model"], 0.85)
        self.assertEqual(graph["8"]["inputs"]["model"], ["14", 0])

    def test_flux_graph_can_omit_identity_lora(self):
        graph = comfy_adapter.text_image_graph(
            "empty environment", "people", "test/output", 2184
        )
        self.assertNotIn("14", graph)
        self.assertEqual(graph["8"]["inputs"]["model"], ["1", 0])

    def test_ltx_graph_uses_ltx_tuned_encoder_and_core_conditioning(self):
        task = {
            "scene_id": "scene_01",
            "shot_id": "shot_01",
            "formation_id": "formation_01",
            "direction": {"character_action": "walk forward"},
        }
        candidate = comfy_adapter.CANDIDATE_VARIANTS[0]
        graph = comfy_adapter.native_ltx_api_graph(
            task, 5, candidate, "test/ltx/output"
        )
        self.assertEqual(
            graph["2"]["inputs"],
            {
                "clip_name": comfy_adapter.LTX_TEXT_ENCODER,
                "type": "ltxv",
                "device": "default",
            },
        )
        self.assertIn("int8-convrot", graph["2"]["inputs"]["clip_name"])
        self.assertEqual(graph["9"]["class_type"], "LTXVConditioning")
        self.assertEqual(graph["20"]["inputs"]["temporal_size"], 128)
        self.assertEqual(graph["20"]["inputs"]["temporal_overlap"], 32)
        self.assertNotIn("audio", graph["22"]["inputs"])
        self.assertEqual(graph["23"]["inputs"]["codec"], "auto")
        self.assertNotEqual(
            graph["2"]["inputs"]["clip_name"], comfy_adapter.FLUX_TEXT_ENCODER
        )

    def test_ltx_ui_workflow_replaces_bf16_encoder_reference(self):
        workflow = {
            "nodes": [],
            "definitions": {
                "widgets_values": [
                    "gemma4-12b-with-proj-ltx-2.5-bf16.safetensors"
                ]
            },
        }
        task = {
            "scene_id": "scene_01",
            "shot_id": "shot_01",
            "formation_id": "formation_01",
            "direction": {"character_action": "walk forward"},
        }

        comfy_adapter.configure_ltx_ui_workflow(
            workflow, task, 5, comfy_adapter.CANDIDATE_VARIANTS[0]
        )

        self.assertEqual(
            workflow["definitions"]["widgets_values"],
            [comfy_adapter.LTX_TEXT_ENCODER],
        )

    def test_ltx_model_links_reuse_desktop_weights_without_copying(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            external = root / "external"
            shared = root / "shared"
            external.mkdir()
            for name in {
                **comfy_adapter.LTX_MODELS,
                **comfy_adapter.LTX_OPTIONAL_MODELS,
            }.values():
                (external / name).write_bytes(b"model")

            first = comfy_adapter.link_ltx_models(shared, external)
            second = comfy_adapter.link_ltx_models(shared, external)

            self.assertTrue(all(item["linked"] for item in first))
            self.assertTrue(all(item["linked"] for item in second))
            for item in first:
                destination = Path(item["destination"])
                self.assertTrue(destination.is_symlink())
                self.assertEqual(destination.resolve(), Path(item["source"]).resolve())


if __name__ == "__main__":
    unittest.main()
