import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import comfy_adapter
import prompt_plan


class ComfyAdapterTests(unittest.TestCase):
    def test_pulid_reference_requires_user_approval_and_existing_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "face.png"
            source.write_bytes(b"face")
            project = {"characters": [{
                "id": "k0l3k4",
                "pulid_reference": {
                    "source": "face.png", "decision": "approved",
                    "approved_by": "user", "issues": [],
                },
            }]}
            result = comfy_adapter.approved_pulid_reference(root, project)
            self.assertEqual(Path(result["source"]), source.resolve())
            self.assertTrue(result["staged_input"].startswith("scene_factory_v3_identity/"))
            project["characters"][0]["pulid_reference"]["approved_by"] = "agent"
            with self.assertRaisesRegex(ValueError, "user-approved"):
                comfy_adapter.approved_pulid_reference(root, project)

    def test_prompt_plan_contract_uses_exact_project_issue_codes(self):
        codes = ["BINDING_HELMET_ON_K", "PROP_DUPLICATED", "FACE_OCCLUDED_OR_MERGED"]
        contract = prompt_plan.build_contract({"required": ["keep attributes bound"], "issue_codes": codes})
        prompt_plan.validate_contract(contract)
        self.assertEqual(
            contract["response_schema"]["properties"]["issue_codes"]["items"]["enum"],
            codes,
        )
        with self.assertRaisesRegex(ValueError, "unknown issue codes"):
            prompt_plan.validate_response(contract, {
                "positive_prompt": "one subject",
                "negative_prompt": "duplicates",
                "issue_codes": ["INVENTED_CODE"],
            })

    def test_production_scope_removes_enforcers_props_and_mask_transfer_from_k(self):
        task = {
            "prompt_contract": {
                "subjects": [
                    {"id": "k0l3k4", "identity_tag": "k0l3k4", "must_have": ["unobstructed visible face"], "must_not_have": ["helmet", "gas mask"]},
                    {"id": "enforcers", "identity_tag": "enforcer_anchor", "must_have": ["opaque visor helmet", "riot armor"]},
                ],
                "props": [{"id": "hammer", "description": "one sledgehammer"}],
                "blocking": {}, "negative": [],
            },
            "direction": {
                "subject_locks": [{"id": "k0l3k4"}, {"id": "enforcers"}],
                "prop_locks": [{"id": "hammer"}],
            },
        }
        scoped, policy = comfy_adapter.production_scoped_task(task)
        positive = comfy_adapter.storyboard_prompt(scoped).lower()
        negative = comfy_adapter.storyboard_negative(scoped).lower()
        self.assertEqual([item["id"] for item in scoped["prompt_contract"]["subjects"]], ["k0l3k4"])
        self.assertEqual(scoped["prompt_contract"]["props"], [])
        self.assertNotIn("opaque visor", positive)
        self.assertNotIn("sledgehammer", positive)
        self.assertIn("mask on k0l3k4", negative)
        self.assertEqual(scoped["direction"]["prop_locks"], [])
        self.assertEqual(policy["identity_lora"], "k0l3k4")
        self.assertEqual(comfy_adapter.INPUT_NAMESPACE, "scene_factory_v3_generated")

    def test_storyboard_prompt_binds_attributes_to_subjects_and_props(self):
        task = {
            "prompt_contract": {
                "subjects": [
                    {
                        "id": "k0l3k4",
                        "identity_tag": "k0l3k4",
                        "required_attributes": ["white athletic tank top"],
                        "must_have": ["unobstructed visible face"],
                        "must_not_have": ["helmet", "riot armor"],
                        "anatomy": ["exactly two arms"],
                    },
                    {
                        "id": "enforcers",
                        "identity_tag": "enforcer_anchor",
                        "required_attributes": ["opaque visor helmets"],
                        "must_have": ["riot armor"],
                    },
                ],
                "props": [
                    {
                        "id": "hammer",
                        "description": "one industrial throwing sledgehammer",
                        "geometry": ["one handle", "one steel head at the striking end"],
                        "forbidden": ["hammer head at both ends"],
                    }
                ],
                "blocking": {
                    "subject_positions": ["enforcers remain behind k0l3k4"],
                    "anatomy": ["both arms connect to the shoulders"],
                    "prop_state": ["the grip end is bare"],
                },
                "environment_attributes": ["industrial corridor"],
                "action": "k0l3k4 runs while enforcers pursue her",
                "framing": "medium",
                "camera": "frontal tracking",
                "subject_priority": "face and hammer",
                "negative": ["identity drift"],
                "global_constraints": {"required": ["attributes stay bound"]},
            }
        }

        positive = comfy_adapter.storyboard_prompt(task)
        negative = comfy_adapter.storyboard_negative(task)

        self.assertIn("SUBJECT k0l3k4 ONLY", positive)
        self.assertIn("SUBJECT enforcers ONLY", positive)
        self.assertIn("PROP hammer ONLY", positive)
        self.assertIn("exactly two arms", positive)
        self.assertIn("the grip end is bare", positive)
        self.assertNotIn("must not have helmet", positive)
        self.assertIn("helmet on SUBJECT k0l3k4", negative)
        self.assertIn("hammer head at both ends for PROP hammer", negative)

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

    def test_pulid_flux2_graph_uses_upstream_nodes_and_strength(self):
        graph = comfy_adapter.pulid_image_graph(
            "k0l3k4 portrait", "helmet", "test/output", 2184, "approved_face.png"
        )
        self.assertEqual(graph["5"]["class_type"], "PuLIDModelLoader")
        self.assertEqual(graph["5"]["inputs"]["pulid_file"], "pulid_flux2_klein_v2.safetensors")
        self.assertEqual(graph["6"]["class_type"], "PuLIDEVACLIPLoader")
        self.assertEqual(graph["7"]["inputs"]["provider"], "CPU")
        self.assertEqual(graph["8"]["class_type"], "ApplyPuLIDFlux2")
        self.assertEqual(graph["8"]["inputs"]["strength"], 1.4)
        self.assertEqual(graph["13"]["inputs"]["model"], ["8", 0])
        self.assertEqual(graph["4"]["inputs"]["image"], "approved_face.png")

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
        self.assertEqual(graph["1"]["inputs"]["weight_dtype"], "fp8_e4m3fn")
        self.assertEqual(graph["10"]["inputs"]["length"], 121)
        self.assertEqual(graph["15"]["inputs"]["cfg"], 3.25)
        self.assertEqual(graph["17"]["class_type"], "LTXVScheduler")
        self.assertEqual(graph["17"]["inputs"]["steps"], 24)
        class_types = {node["class_type"] for node in graph.values()}
        self.assertNotIn("LTXVEmptyLatentAudio", class_types)
        self.assertNotIn("LTXVConcatAVLatent", class_types)
        self.assertNotIn("LTXVSeparateAVLatent", class_types)
        self.assertEqual(graph["18"]["inputs"]["latent_image"], ["11", 0])
        self.assertEqual(graph["20"]["inputs"]["samples"], ["18", 0])
        self.assertEqual(graph["20"]["inputs"]["temporal_size"], 128)
        self.assertEqual(graph["20"]["inputs"]["temporal_overlap"], 32)
        self.assertNotIn("audio", graph["22"]["inputs"])
        self.assertEqual(graph["23"]["inputs"]["codec"], "auto")
        self.assertNotEqual(
            graph["2"]["inputs"]["clip_name"], comfy_adapter.FLUX_TEXT_ENCODER
        )

    def test_ltx_motion_proof_uses_mod8_plus1_frame_target(self):
        task = {
            "scene_id": "scene_01", "shot_id": "shot_01", "formation_id": "wide",
            "direction": {"character_action": "walk forward"},
        }
        graph = comfy_adapter.native_ltx_api_graph(
            task, 3, comfy_adapter.CANDIDATE_VARIANTS[0], "test/ltx/proof"
        )
        self.assertEqual(graph["10"]["inputs"]["length"], 73)

    def test_ltx_model_requirements_are_video_only(self):
        self.assertEqual(
            set(comfy_adapter.LTX_MODELS), {"diffusion_model", "video_vae"}
        )

    def test_approval_requires_user_actor_and_empty_issues(self):
        clean = {
            "decision": "approved",
            "approved_by": "user",
            "issues": [],
        }
        self.assertTrue(comfy_adapter.user_approved_without_issues(clean))

        for invalid in (
            {**clean, "approved_by": "agent"},
            {key: value for key, value in clean.items() if key != "approved_by"},
            {**clean, "issues": ["identity drift"]},
            {key: value for key, value in clean.items() if key != "issues"},
            {**clean, "decision": "rejected"},
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(
                    comfy_adapter.user_approved_without_issues(invalid)
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
