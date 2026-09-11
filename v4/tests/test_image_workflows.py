import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import image_workflows
import comfy_executor


class ImageWorkflowTests(unittest.TestCase):
    def test_adapter_staging_refreshes_stale_copy_by_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "trained.safetensors"
            target = root / "comfy/scene_factory_v4/trained.safetensors"
            source.write_bytes(b"adapter-v2")
            digest = image_workflows.identity.sha256_file(source)
            first = image_workflows._stage_adapter(source, target, digest)
            self.assertTrue(first["refreshed"])
            source.write_bytes(b"adapter-v3")
            digest = image_workflows.identity.sha256_file(source)
            second = image_workflows._stage_adapter(source, target, digest)
            self.assertTrue(second["refreshed"])
            self.assertEqual(target.read_bytes(), b"adapter-v3")

    def test_links_are_checked_and_missing_links_fail(self):
        image_workflows.validate_api_graph({
            "1": {"class_type": "EmptyLatentImage", "inputs": {"width": 64}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        })
        with self.assertRaisesRegex(ValueError, "missing node"):
            image_workflows.validate_api_graph({
                "1": {"class_type": "SaveImage", "inputs": {"images": ["404", 0]}},
            })

    def test_real_example_compiles_connected_base_reference_and_pulid_routes(self):
        source = Path(__file__).parents[1] / "examples/modeling_interview"
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            (project / "build/identity/reference_bank").mkdir(parents=True)
            (project / "identity.json").write_text((source / "identity.json").read_text())
            bank = source / "build/identity/reference_bank/reference_bank.json"
            (project / "build/identity/reference_bank/reference_bank.json").write_text(bank.read_text())
            report = image_workflows.compile_workflows(project)
            compiled = [item for item in report["routes"] if item["status"] == "compiled"]
            self.assertGreaterEqual(len(compiled), 2)
            for item in compiled:
                graph = json.loads(Path(item["path"]).read_text())
                image_workflows.validate_api_graph(graph)
                # A locally installed adapter or cached node must never leak a
                # Koleka asset into an executable v4 route.
                serialized = json.dumps(graph, sort_keys=True).casefold()
                self.assertNotIn("koleka", serialized)
                self.assertNotIn("k0l3k4", serialized)
            native = json.loads((project / "build/workflows/image_ablation/native_reference.json").read_text())
            self.assertIn("ReferenceLatent", {node["class_type"] for node in native.values()})
            self.assertIn("FluxKontextMultiReferenceLatentMethod", {node["class_type"] for node in native.values()})
            staging = json.loads((project / "build/workflows/image_ablation/staging_manifest.json").read_text())
            self.assertTrue(any(item["derived_from_mask"] for item in staging["records"]))
            self.assertGreaterEqual(sum(node["class_type"] == "LoadImage" for node in native.values()), 2)
            runtime = json.loads((project / "build/runtime/image_runtime.json").read_text())
            self.assertEqual(runtime["status"], "compiled")
            self.assertTrue(runtime["promotion_required"])

    def test_base_route_is_an_exact_adapter_bypass_and_candidate_route_is_not(self):
        source = Path(__file__).parents[1] / "examples/modeling_interview"
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            (project / "build/identity/reference_bank").mkdir(parents=True)
            (project / "identity.json").write_text((source / "identity.json").read_text())
            bank = source / "build/identity/reference_bank/reference_bank.json"
            (project / "build/identity/reference_bank/reference_bank.json").write_text(bank.read_text())
            report = image_workflows.compile_workflows(project)
            routes = {item["name"]: item for item in report["routes"]}
            base = json.loads(Path(routes["base"]["path"]).read_text())
            self.assertEqual(base["7"]["inputs"]["model"], ["1", 0])
            self.assertFalse(any(node["class_type"] == "LoraLoaderModelOnly" for node in base.values()))
            candidate = image_workflows._apply_subject_lora(base, "adapter.safetensors", "candidate")
            self.assertTrue(any(node["class_type"] == "LoraLoaderModelOnly" for node in candidate.values()))

    def test_executor_rejects_unavailable_route_before_queueing(self):
        source = Path(__file__).parents[1] / "examples/modeling_interview"
        with self.assertRaisesRegex(comfy_executor.ComfyExecutionError, "no promoted image identity LoRA"):
            comfy_executor.validate_execution_contract(source, "subject_lora")

    def test_executor_requires_declared_models_to_be_bound_in_graph(self):
        source = Path(__file__).parents[1] / "examples/modeling_interview"
        contract = comfy_executor.validate_execution_contract(source, "base")
        self.assertTrue(set(contract["route"]["required_models"]).issubset(set(contract["bound_models"])))
        self.assertIn("flux-2-klein-4b.safetensors", contract["bound_models"])

    def test_executor_finds_text_through_reference_conditioning_chain(self):
        graph = {
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
            "20": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["4", 0]}},
            "21": {"class_type": "KSampler", "inputs": {"positive": ["20", 0], "negative": ["5", 0]}},
        }
        self.assertEqual(comfy_executor._upstream_text_node(graph, ["20", 0]), "4")
        self.assertEqual(comfy_executor._upstream_text_node(graph, ["5", 0]), "5")

    def test_executor_download_rejects_subfolder_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(comfy_executor.ComfyExecutionError, "unsafe output filename"):
                comfy_executor._download_output(
                    "http://127.0.0.1:1",
                    {"filename": "safe.png", "subfolder": "../escape", "type": "output"},
                    Path(temporary) / "out.png",
                )

    def test_executor_download_rejects_non_image_payload(self):
        response = mock.Mock()
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        response.read.return_value = b"not-an-image-payload"
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(comfy_executor.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(comfy_executor.ComfyExecutionError, "not an image"):
                comfy_executor._download_output(
                    "http://127.0.0.1:1",
                    {"filename": "fake.png", "subfolder": "", "type": "output"},
                    Path(temporary) / "out.png",
                )


if __name__ == "__main__":
    unittest.main()
