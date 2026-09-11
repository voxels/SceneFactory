import json
import shutil
import tempfile
import unittest
from pathlib import Path

import render_pipeline


class RenderPipelineTests(unittest.TestCase):
    def official_template_stub(self):
        return {
            "nodes": [
                {"type": "PrimitiveStringMultiline", "title": "Prompt (positive)", "widgets_values": [""]},
                {"type": "PrimitiveStringMultiline", "title": "Prompt (negative)", "widgets_values": [""]},
                {"type": "LoadImage", "widgets_values": ["", "image"]},
                {"type": "PrimitiveFloat", "title": "fps (frames per second)", "widgets_values": [24]},
                {"type": "PrimitiveFloat", "title": "duration in seconds (determines frames #)", "widgets_values": [5]},
                {"type": "LTXVSparseTrackEditor", "widgets_values": ["", "", 121, ""]},
                {"type": "SaveVideo", "title": "Save tracks preview", "widgets_values": ["tracks", "auto", "auto"]},
                {"type": "SaveVideo", "widgets_values": ["output", "auto", "auto"]},
            ],
            "definitions": {"encoder": "gemma4-12b-with-proj-ltx-2.5-bf16.safetensors"},
        }

    def test_motion_workflow_requires_one_point_per_legal_frame(self):
        tracks = [[{"x": frame, "y": frame + 1} for frame in range(73)]]
        workflow, metadata = render_pipeline.configure_motion_track_workflow(
            self.official_template_stub(),
            prompt="K runs",
            negative="identity drift",
            input_image="k.png",
            tracks=tracks,
            output_prefix="proof/k",
            duration_seconds=3,
            fps=24,
        )
        self.assertEqual(metadata["frame_count"], 73)
        editor = next(node for node in workflow["nodes"] if node["type"] == "LTXVSparseTrackEditor")
        self.assertEqual(len(json.loads(editor["widgets_values"][1])[0]), 73)
        self.assertEqual(
            workflow["definitions"]["encoder"], render_pipeline.LTX_TEXT_ENCODER
        )

    def test_motion_workflow_rejects_short_track(self):
        with self.assertRaisesRegex(ValueError, "exactly 73"):
            render_pipeline.configure_motion_track_workflow(
                self.official_template_stub(),
                prompt="K runs",
                negative="",
                input_image="k.png",
                tracks=[[{"x": 1, "y": 2}]],
                output_prefix="proof/k",
                duration_seconds=3,
            )

    def test_visual_only_motion_api_has_control_and_no_audio_nodes(self):
        tracks = [[{"x": frame, "y": frame + 1} for frame in range(73)]]
        graph, metadata = render_pipeline.visual_only_motion_api_graph(
            prompt="K runs",
            negative="identity drift",
            input_image="k.png",
            tracks=tracks,
            output_prefix="proof/k",
        )
        class_types = {node["class_type"] for node in graph.values()}
        self.assertIn("LTXICLoRALoaderModelOnly", class_types)
        self.assertIn("LTXAddVideoICLoRAGuide", class_types)
        self.assertIn("LTXVDrawTracks", class_types)
        self.assertIn("LTXVCropGuides", class_types)
        self.assertFalse(any("Audio" in name or "AVLatent" in name for name in class_types))
        self.assertEqual(metadata["audio_nodes"], [])
        self.assertEqual(graph["15"]["inputs"]["model"], ["4", 0])

    def test_audit_reports_incomplete_extension_and_missing_motion_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            comfy = root / "ComfyUI"
            models = root / "models"
            (comfy / "custom_nodes" / "ComfyUI-LTXVideo").mkdir(parents=True)
            (models / "diffusion_models").mkdir(parents=True)
            (models / "vae").mkdir()
            (models / "text_encoders").mkdir()
            (models / "loras").mkdir()
            report = render_pipeline.audit_ltx_install(comfy, models)
            self.assertFalse(report["ready"])
            self.assertIn("official_extension_incomplete", report["blockers"])
            self.assertIn("required_models_missing", report["blockers"])

    def test_conditioning_scope_isolates_k_from_enforcers(self):
        layer = {
            "kind": "subject",
            "owner": "k0l3k4",
            "conditioning_scope": {
                "include_subjects": ["k0l3k4"],
                "exclude_subjects": ["enforcers"],
                "include_props": [],
                "exclude_props": ["hammer"],
                "identity_lora": "k0l3k4",
                "forbidden_attributes": ["helmet", "visor", "riot armor"],
            },
        }
        self.assertEqual(render_pipeline.validate_conditioning_scope(layer), [])
        layer["conditioning_scope"]["include_subjects"].append("enforcers")
        self.assertTrue(render_pipeline.validate_conditioning_scope(layer))

    def test_hammer_scope_requires_independent_single_head_geometry(self):
        layer = {
            "kind": "prop",
            "owner": "hammer",
            "conditioning_scope": {
                "include_subjects": [],
                "exclude_subjects": ["k0l3k4"],
                "include_props": ["hammer"],
                "exclude_props": [],
                "identity_lora": None,
                "geometry_lock": [
                    "one straight handle", "one crosswise hammer head",
                    "bare grip end", "no duplicate head",
                ],
            },
        }
        self.assertEqual(render_pipeline.validate_conditioning_scope(layer), [])
        layer["conditioning_scope"]["geometry_lock"].remove("no duplicate head")
        self.assertTrue(render_pipeline.validate_conditioning_scope(layer))

    def test_pose_conversion_rejects_an_interval_crossing_a_shot_cut(self):
        record = {"samples": [
            {"timestamp_seconds": 9.9, "root": {"x": 0.5, "y": 0.5}, "joints": []},
            {"timestamp_seconds": 10.1, "root": {"x": 0.5, "y": 0.5}, "joints": []},
        ]}
        with self.assertRaisesRegex(ValueError, "crosses shot_01 bounds"):
            render_pipeline.pose_record_to_motion_tracks(
                record,
                start_index=0,
                frame_count=2,
                width=576,
                height=960,
                anchors={"root": (0.5, 0.5)},
                shot_id="shot_01",
                source_start_seconds=0.0,
                source_end_seconds=10.0,
            )

    def test_complete_dry_run_materializes_every_job_without_touching_production(self):
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue_path = root / "queue.json"
            production_root = root / "production"
            queue_path.write_text(json.dumps({"jobs": [
                {
                    "id": "plate", "stage": "render_layer", "required": True,
                    "output": str(production_root / "plate.mov"),
                    "matte_output": None, "missing": [], "state": "ready",
                },
                {
                    "id": "k", "stage": "render_layer", "required": True,
                    "output": str(production_root / "k.mov"),
                    "matte_output": str(production_root / "k_matte.mov"),
                    "missing": ["k_start.png"], "state": "blocked",
                },
                {
                    "id": "composite", "stage": "composite", "required": True,
                    "output": str(production_root / "composite.mp4"),
                    "matte_output": None, "missing": ["approval:pending"],
                    "state": "blocked",
                },
                {
                    "id": "occluder", "stage": "optional_occluder", "required": False,
                    "output": str(production_root / "occluder.mov"),
                    "missing": [], "state": "deferred_unless_review_requires_occluder",
                },
            ]}), encoding="utf-8")
            result, report = render_pipeline.materialize_dry_run(
                queue_path, root / "dry_run", approved_by="user"
            )
            self.assertTrue(result["ready"])
            self.assertEqual(result["summary"]["completed_jobs"], 4)
            self.assertEqual(result["summary"]["artifacts"], 6)
            self.assertEqual(result["summary"]["deliverables"], 1)
            self.assertTrue(report.is_file())
            self.assertFalse(production_root.exists())
            self.assertTrue(all(Path(job["output"]).is_file() for job in result["jobs"]))
            self.assertTrue(all(job["state"] == "dry_run_complete" for job in result["jobs"]))
            self.assertEqual(result["jobs"][1]["production_missing"], ["k_start.png"])

    def test_dry_run_cannot_fabricate_non_user_approval(self):
        with self.assertRaisesRegex(ValueError, "attributed to user"):
            render_pipeline.materialize_dry_run(
                Path("queue.json"), Path("dry_run"), approved_by="agent"
            )


if __name__ == "__main__":
    unittest.main()
