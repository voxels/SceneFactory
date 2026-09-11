import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import scene_factory_v4
import test_identity_pipeline
import identity_bundle
import modality_audit


class SceneFactoryV4Tests(unittest.TestCase):
    def test_automatic_stage_cannot_mark_blocked_contract_complete(self):
        with self.assertRaisesRegex(RuntimeError, "example returned blocked"):
            scene_factory_v4._raise_for_blocked_stage("example", {"status": "blocked", "reason": "missing control"})
        scene_factory_v4._raise_for_blocked_stage("example", {"status": "compiled"})

    def test_metal_probe_is_actionable_and_does_not_launch_unreal(self):
        def fake_run(args, **kwargs):
            command = tuple(args)
            if command == ("xcode-select", "-p"):
                return mock.Mock(returncode=0, stdout="/Applications/Xcode-beta.app/Contents/Developer\n", stderr="")
            if command == ("xcrun", "--sdk", "macosx", "--show-sdk-version"):
                return mock.Mock(returncode=0, stdout="27.0\n", stderr="")
            if command == ("xcrun", "--sdk", "macosx", "--show-sdk-path"):
                return mock.Mock(returncode=0, stdout="/sdk/MacOSX27.0.sdk\n", stderr="")
            if command == ("xcrun", "--find", "metal"):
                return mock.Mock(returncode=0, stdout="/missing/metal\n", stderr="")
            raise AssertionError(command)

        with mock.patch.object(scene_factory_v4.subprocess, "run", side_effect=fake_run):
            report = scene_factory_v4.metal_toolchain_contract()
        self.assertEqual(report["status"], "missing_or_unusable")
        self.assertEqual(report["install_command"], "xcodebuild -downloadComponent MetalToolchain")
        self.assertFalse(report["editor_launch_attempted"])
        self.assertIn("-nullrhi", report["safe_commandlet_flags"])

    def test_preflight_is_machine_readable_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            config_path = project / "identity.json"
            config = json.loads(config_path.read_text())
            config["identity"]["consent"]["status"] = "unverified"
            config_path.write_text(json.dumps(config))
            with mock.patch.object(scene_factory_v4, "torch_backend", return_value={"available": False}):
                report = scene_factory_v4.preflight(project)
            self.assertFalse(report["ready_for_complete_run"])
            self.assertIn("consent status is unverified", report["blockers"]["safety"])
            self.assertNotIn("blender", report["blockers"]["dependencies"])
            persisted = json.loads((project / "build/pipeline/preflight.json").read_text())
            self.assertEqual(persisted["identity_id"], "test")

    def test_preflight_marks_missing_audio_deferred_but_not_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            (project.parent / "source/voice/sample.wav").unlink()
            available_backend = {"available": True, "mps": True, "cuda": False}
            with mock.patch.object(scene_factory_v4, "torch_backend", return_value=available_backend), \
                 mock.patch.object(scene_factory_v4, "comfy_api_contract", return_value={"inference_accelerator_available": True}), \
                 mock.patch.object(scene_factory_v4, "metal_toolchain_contract", return_value={"status": "available"}), \
                 mock.patch.object(scene_factory_v4, "git_commit", return_value="test-commit"):
                report = scene_factory_v4.preflight(project)
            self.assertTrue(report["ready_for_ingest"])
            self.assertFalse(report["ready_for_complete_run"])
            self.assertEqual(report["status"], "blocked")
            self.assertIn("supplied TTS audio is missing", report["blockers"]["deferred"])
            self.assertIn("supplied TTS audio is missing", report["blockers"]["safety"])

    def test_generate_image_fails_closed_without_promoted_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            with self.assertRaisesRegex(RuntimeError, "image runtime contract is missing"):
                scene_factory_v4.run_command("generate-image", project)

    def test_generate_image_uses_only_promoted_route_and_forwards_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            runtime = project / "build/runtime/image_runtime.json"
            runtime.parent.mkdir(parents=True, exist_ok=True)
            runtime.write_text(json.dumps({
                "selected_route": "subject_lora_exp1", "promotion_required": True,
                "route_selection": "promoted",
            }))
            expected = {"status": "complete", "route": "subject_lora_exp1"}
            with mock.patch.object(scene_factory_v4.comfy_executor, "execute", return_value=expected) as execute:
                result = scene_factory_v4.run_command(
                    "generate-image", project, route="subject_lora_exp1", server_url="http://comfy",
                    prompt_override="gage in a studio", negative_prompt_override="blur", seed=17,
                    filename_prefix="proof",
                )
            self.assertEqual(result, expected)
            execute.assert_called_once_with(
                project, "subject_lora_exp1", server_url="http://comfy",
                prompt_override="gage in a studio", negative_prompt_override="blur", seed=17,
                filename_prefix="proof",
            )

    def test_cli_propagates_blocked_result_status(self):
        output = io.StringIO()
        with mock.patch.object(scene_factory_v4, "run_command", return_value={"status": "blocked", "reason": "missing input"}), \
             redirect_stdout(output):
            code = scene_factory_v4.main(["prepare-video-audio", "--project", "/tmp/project"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "blocked")

    def test_automatic_run_records_preflight_block_without_placeholder_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            config_path = project / "identity.json"
            config = json.loads(config_path.read_text())
            config["identity"]["consent"]["status"] = "unverified"
            config_path.write_text(json.dumps(config))
            with self.assertRaisesRegex(RuntimeError, "preflight blocked complete run"):
                scene_factory_v4.run_command("run", project)
            report = json.loads((project / "build/pipeline/automatic_run.json").read_text())
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["completed_stages"], [])

    def test_preflight_block_preserves_same_identity_completed_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            ledger_path = project / "build/pipeline/automatic_run.json"
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            ledger_path.write_text(json.dumps({
                "schema_version": 1, "status": "complete", "identity_id": "test",
                "completed_stages": ["ingest"], "stages": {"ingest": {"status": "complete"}},
            }))
            blocked = {
                "identity_id": "test", "ready_for_complete_run": False,
                "blockers": {"safety": ["missing audio"], "dependencies": [], "execution": [], "avatar": []},
            }
            with mock.patch.object(scene_factory_v4, "preflight", return_value=blocked), \
                 self.assertRaisesRegex(RuntimeError, "preflight blocked complete run"):
                scene_factory_v4.run_command("run", project)
            report = json.loads(ledger_path.read_text())
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["completed_stages"], ["ingest"])
            self.assertEqual(report["blockers"]["safety"], ["missing audio"])

    def test_bundle_audio_uses_configured_source_fallback_with_local_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            config = json.loads((project / "identity.json").read_text())
            source_audio = project.parent / "source/voice/sample.wav"
            self.assertEqual(identity_bundle._supplied_audio(project, config), [source_audio.resolve()])
            local_voice = project / "voice"
            local_voice.mkdir()
            local_audio = local_voice / "sample.wav"
            local_audio.write_bytes(b"local-audio")
            self.assertEqual(identity_bundle._supplied_audio(project, config), [local_audio.resolve()])

    def test_bundle_transcript_uses_same_source_fallback_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            config = json.loads((project / "identity.json").read_text())
            source_transcript = project.parent / "source/voice/tts_text.txt"
            self.assertEqual(identity_bundle._supplied_transcripts(project, config), [source_transcript.resolve()])
            local_voice = project / "voice"
            local_voice.mkdir()
            local_transcript = local_voice / "tts_text.txt"
            local_transcript.write_text("local transcript")
            self.assertEqual(identity_bundle._supplied_transcripts(project, config), [local_transcript.resolve()])

    def test_source_fingerprint_ignores_koleka_derived_cache_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            source = project.parent / "source"
            before = scene_factory_v4._source_fingerprint(project)
            cache = source / "derived_cache" / "KoLeKa" / "embedding.bin"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"must-not-enter-v4")
            self.assertEqual(before, scene_factory_v4._source_fingerprint(project))
            (source / "authorized_derivative.bin").write_bytes(b"must-change-fingerprint")
            self.assertNotEqual(before, scene_factory_v4._source_fingerprint(project))

    def test_modality_audit_requires_execution_of_promoted_image_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            execution_root = project / "build/workflows/image_ablation/executions"
            execution_root.mkdir(parents=True)
            (execution_root / "base.json").write_text(json.dumps({
                "status": "complete", "route": "base",
                "downloaded_outputs": [{"sha256": "a" * 64}],
            }))
            self.assertFalse(modality_audit._has_image_execution(project, "promoted_route"))
            (execution_root / "promoted.json").write_text(json.dumps({
                "status": "complete", "route": "promoted_route",
                "downloaded_outputs": [{"sha256": "b" * 64}],
            }))
            self.assertTrue(modality_audit._has_image_execution(project, "promoted_route"))

    def test_automatic_stage_signature_and_output_hashes_invalidate_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            input_path = project / "input.dat"
            output_path = project / "output.dat"
            input_path.write_bytes(b"source-v1")
            output_path.write_bytes(b"output-v1")
            signature = scene_factory_v4._stage_signature(project, "example", "source-fingerprint", [input_path])
            stage = {"signature": signature, "output_hashes": {str(output_path.resolve()): scene_factory_v4.identity.sha256_file(output_path)}}
            self.assertTrue(scene_factory_v4._outputs_match(stage, [output_path]))
            input_path.write_bytes(b"source-v2")
            self.assertNotEqual(signature, scene_factory_v4._stage_signature(project, "example", "source-fingerprint", [input_path]))
            output_path.write_bytes(b"output-v2")
            self.assertFalse(scene_factory_v4._outputs_match(stage, [output_path]))

    def test_automatic_run_completes_and_resumes_by_stage(self):
        """The automatic command must run every real stage once, then skip intact stages."""
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            build = project / "build"

            def emit(relative, payload=None):
                path = project / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload or {"status": "stubbed-test-output"}))
                return {"path": str(path)}

            ready = {
                "identity_id": "test", "ready_for_complete_run": True,
                "ready_for_ingest": True,
                "blockers": {"safety": [], "dependencies": [], "execution": [], "avatar": []},
            }
            def build_identity(_project, **_kwargs):
                emit("build/identity/asset_manifest.json")
                return ({}, {})

            def process_annotations(_project): return emit("build/identity/annotations/annotations.json")
            def process_motion(_project): return emit("build/identity/motion/motion_manifest.json")
            def process_video(_project):
                emit("build/identity/video/visual_identity_manifest.json")
                return emit("build/identity/video_audio_manifest.json")
            def process_captions(_project): return emit("build/identity/captions/captions.json")
            def process_selection(_project):
                emit("build/identity/selection_manifest.json")
                return ({}, {})
            def process_reference_bank(_project):
                emit("build/identity/reference_bank/reference_bank.json")
                return {}

            patches = {
                "preflight": mock.Mock(return_value=ready),
                "identity.build": mock.Mock(side_effect=build_identity),
                "usdz_controls.render": mock.Mock(side_effect=lambda p: emit("build/identity/geometry/geometry_control_manifest.json")),
                "usdz_ingestion.ingest": mock.Mock(side_effect=lambda p: emit("build/identity/geometry/usdz_ingestion_manifest.json")),
                "identity_annotations.annotate": mock.Mock(side_effect=process_annotations),
                "motion_tracking.track": mock.Mock(side_effect=process_motion),
                "video_audio_pipeline.prepare_video_audio": mock.Mock(side_effect=process_video),
                "identity_captions.generate_pinned": mock.Mock(side_effect=process_captions),
                "training.select": mock.Mock(side_effect=process_selection),
                "reference_bank.build": mock.Mock(side_effect=process_reference_bank),
                "image_training.train": mock.Mock(side_effect=lambda p: emit("build/training/image_identity/training_plan.json")),
                "image_workflows.compile_workflows": mock.Mock(side_effect=lambda p: emit("build/workflows/image_ablation/manifest.json")),
                "image_evaluation.evaluate": mock.Mock(side_effect=lambda p, **kwargs: emit("build/training/image_identity/heldout_evaluation_plan.json")),
                "video_audio_pipeline.train_video_identity": mock.Mock(side_effect=lambda p: emit("build/training/video_identity/training_plan.json")),
                "modality_audit.build_consumption_report": mock.Mock(side_effect=lambda p: emit("build/validation/modality_consumption_report.json")),
                "identity_bundle.build_bundle": mock.Mock(side_effect=lambda p, out: emit("build/identity_bundle/bundle.json")),
            }
            with mock.patch.object(scene_factory_v4, "preflight", patches["preflight"]), \
                 mock.patch.object(scene_factory_v4.identity, "build", patches["identity.build"]), \
                 mock.patch.object(scene_factory_v4.usdz_controls, "render", patches["usdz_controls.render"]), \
                 mock.patch.object(scene_factory_v4.usdz_ingestion, "ingest", patches["usdz_ingestion.ingest"]), \
                 mock.patch.object(scene_factory_v4.identity_annotations, "annotate", patches["identity_annotations.annotate"]), \
                 mock.patch.object(scene_factory_v4.motion_tracking, "track", patches["motion_tracking.track"]), \
                 mock.patch.object(scene_factory_v4.video_audio_pipeline, "prepare_video_audio", patches["video_audio_pipeline.prepare_video_audio"]), \
                 mock.patch.object(scene_factory_v4.identity_captions, "generate_pinned", patches["identity_captions.generate_pinned"]), \
                 mock.patch.object(scene_factory_v4.training, "select", patches["training.select"]), \
                 mock.patch.object(scene_factory_v4.reference_bank, "build", patches["reference_bank.build"]), \
                 mock.patch.object(scene_factory_v4.image_training, "train", patches["image_training.train"]), \
                 mock.patch.object(scene_factory_v4.image_workflows, "compile_workflows", patches["image_workflows.compile_workflows"]), \
                 mock.patch.object(scene_factory_v4.image_evaluation, "evaluate", patches["image_evaluation.evaluate"]), \
                 mock.patch.object(scene_factory_v4.video_audio_pipeline, "train_video_identity", patches["video_audio_pipeline.train_video_identity"]), \
                 mock.patch.object(scene_factory_v4.modality_audit, "build_consumption_report", patches["modality_audit.build_consumption_report"]), \
                 mock.patch.object(scene_factory_v4.identity_bundle, "build_bundle", patches["identity_bundle.build_bundle"]):
                first = scene_factory_v4.run_command("run", project)
                self.assertEqual(first["status"], "complete")
                self.assertEqual(len(first["completed_stages"]), 10)
                second = scene_factory_v4.run_command("run", project)
                self.assertEqual(second["status"], "complete")
                self.assertEqual(len(second["completed_stages"]), 10)
                self.assertTrue(all(stage["status"] == "skipped" for stage in second["stages"].values()), second["stages"])
                self.assertEqual(patches["identity.build"].call_count, 1)
                self.assertEqual(patches["image_training.train"].call_count, 1)
                self.assertEqual(patches["identity_bundle.build_bundle"].call_count, 1)

    def test_identity_bundle_refuses_without_real_promoted_video_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            with self.assertRaisesRegex(RuntimeError, "promoted image identity LoRA"):
                scene_factory_v4.run_command("package-identity-bundle", project, adapter_path=str(Path(temporary) / "bundle"))

    def test_identity_bundle_success_path_is_self_contained(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            build = project / "build"
            (build / "training/image_identity/promoted").mkdir(parents=True)
            (build / "training/video_identity/promoted").mkdir(parents=True)
            (build / "identity/reference_bank").mkdir(parents=True)
            (build / "identity/geometry").mkdir(parents=True)
            (build / "identity/motion").mkdir(parents=True)
            (build / "identity/video").mkdir(parents=True)
            (build / "avatar/gage_portrait").mkdir(parents=True)
            (build / "avatar/gage_portrait/gage_talking_head.usdz").write_bytes(b"mesh-usdz")
            (build / "avatar/gage_portrait/avatar_manifest.json").write_text(json.dumps({"status": "valid"}))
            (build / "test-package-current/geometry").mkdir(parents=True)
            (build / "test-package-current/geometry/gage_portrait.usdz").write_bytes(b"source-usdz")
            (build / "validation").mkdir(parents=True)
            (build / "pipeline").mkdir(parents=True)
            (build / "runtime").mkdir(parents=True)
            (build / "training/image_identity/heldout_runs/run").mkdir(parents=True)
            (build / "training/image_identity/promoted/pytorch_lora_weights.safetensors").write_bytes(b"image-adapter")
            (build / "training/video_identity/promoted/pytorch_lora_weights.safetensors").write_bytes(b"video-adapter")
            for relative in (
                "identity/reference_bank/reference_bank.json", "identity/selection_manifest.json",
                "identity/geometry/usdz_ingestion_manifest.json", "identity/motion/skeleton_manifest.json",
                "identity/video_audio_manifest.json", "pipeline/preflight.json",
                "runtime/image_runtime.json", "identity/video/video_runtime.json",
                "validation/modality_consumption_report.json",
            ):
                (build / relative).write_text(json.dumps({"status": "complete"}))
            (build / "runtime/image_runtime.json").write_text(json.dumps({
                "status": "compiled", "manifest": str((build / "workflows/image_ablation/manifest.json").resolve())
            }))
            (build / "identity/video/video_runtime.json").write_text(json.dumps({
                "status": "blocked", "audio_alignment_manifest": str((build / "identity/video/audio_alignment_manifest.json").resolve()),
                "visual_identity_manifest": str((build / "identity/video/visual_identity_manifest.json").resolve())
            }))
            (build / "identity/video/visual_identity_manifest.json").write_text(json.dumps({"status": "complete"}))
            (build / "identity/video/audio_alignment_manifest.json").write_text(json.dumps({"alignment_status": "ready"}))
            destination = Path(temporary) / "identity_bundle"
            bundle = identity_bundle.build_bundle(project, destination)
            self.assertEqual(bundle["status"], "complete")
            for relative in (
                "bundle.json", "models/image_identity_lora.safetensors", "models/video_identity_lora.safetensors",
                "voice/sample.wav", "voice/tts_text.txt", "voice/alignment.json",
                "runtime/image_runtime.json", "runtime/video_runtime.json",
                "avatar/gage_portrait/gage_talking_head.usdz", "avatar/gage_portrait/avatar_manifest.json",
                "geometry/usdz/gage_portrait.usdz",
            ):
                self.assertTrue((destination / relative).is_file(), relative)
            image_runtime = json.loads((destination / "runtime/image_runtime.json").read_text())
            video_runtime = json.loads((destination / "runtime/video_runtime.json").read_text())
            self.assertEqual(image_runtime["path_root"], "bundle_root")
            self.assertEqual(image_runtime["manifest"], "workflows/image_ablation/manifest.json")
            self.assertEqual(video_runtime["audio_alignment_manifest"], "voice/alignment.json")
            self.assertNotIn(str(project), json.dumps({"image": image_runtime, "video": video_runtime}))
            self.assertTrue(all("koleka" not in key.casefold() for key in bundle["files"]))

    def test_validate_emits_modality_consumption_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            report = scene_factory_v4.run_command("validate", project)
            self.assertEqual(report["status"], "blocked")
            self.assertTrue((project / "build/validation/modality_consumption_report.json").is_file())

    def test_real_example_reports_prepared_channels_without_downstream_overclaim(self):
        project = Path(__file__).parents[1] / "examples/modeling_interview"
        report = scene_factory_v4.run_command("validate", project)
        self.assertEqual(report["evidence"]["photographic_identity"]["status"], "consumed")
        self.assertEqual(report["evidence"]["visual_identity_video"]["status"], "prepared")
        self.assertEqual(report["evidence"]["motion_reference_video"]["status"], "prepared")
        self.assertEqual(report["evidence"]["usdz_geometry"]["status"], "prepared")
        self.assertIn("consumption pending", report["evidence"]["visual_identity_video"]["detail"])


if __name__ == "__main__":
    unittest.main()
