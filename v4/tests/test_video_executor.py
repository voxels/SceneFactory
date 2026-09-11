import json
import tempfile
import unittest
import shutil
import subprocess
import wave
from pathlib import Path
from unittest import mock

import identity_pipeline as identity
import scene_factory_v4
import video_executor
import video_workflows
from test_video_workflows import VideoWorkflowTests


class VideoExecutorTests(unittest.TestCase):
    def test_audio_presence_does_not_enable_missing_identity_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = VideoWorkflowTests()._project(Path(temporary))
            audio = project / "speech.wav"
            audio.write_bytes(b"test-audio")
            with mock.patch.object(video_workflows, "_audio_input", return_value=audio):
                compiled = video_workflows.compile_workflow(project)
            self.assertFalse(compiled["contract"]["execution_allowed"])
            with mock.patch.object(video_executor, "_json_request") as network:
                with self.assertRaisesRegex(RuntimeError, "promoted LTX identity LoRA"):
                    video_executor.validate_execution_contract(project, server_url="http://unused")
                network.assert_not_called()

    def test_mutated_graph_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = VideoWorkflowTests()._project(Path(temporary))
            compiled = video_workflows.compile_workflow(project)
            graph_path = Path(compiled["graph"])
            graph = json.loads(graph_path.read_text())
            graph["4"]["inputs"]["text"] = "changed"
            identity.write_json(graph_path, graph)
            with mock.patch.object(video_executor, "_json_request") as network:
                with self.assertRaisesRegex(RuntimeError, "graph hash changed"):
                    video_executor.validate_execution_contract(project, server_url="http://unused")
                network.assert_not_called()

    def test_generate_video_dispatches_to_executor_without_rebuilding_inputs(self):
        project = Path("/unused/project")
        with mock.patch.object(video_executor, "execute", return_value={"status": "complete"}) as execute:
            scene_factory_v4.run_command("generate-video", project, server_url="http://comfy")
            execute.assert_called_once_with(project, server_url="http://comfy")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires ffmpeg/ffprobe")
    def test_delivery_preserves_original_audio_and_prevents_truncation_and_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            video = project / "render.mp4"
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-f", "lavfi",
                            "-i", "color=c=black:s=64x64:r=10:d=1", "-an", "-c:v", "libx264",
                            str(video)], check=True)
            source = project / "original.wav"
            def make_audio(seconds):
                with wave.open(str(source), "wb") as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(16000)
                    stream.writeframes(b"\x01\x00" * int(16000 * seconds))
                return {"inputs": {"authoritative_audio": {
                    "source": str(source), "source_sha256": identity.sha256_file(source)}}}
            generated = {"path": str(video), "sha256": identity.sha256_file(video)}
            contract = make_audio(0.5)
            result = video_executor.finalize_delivery(project, generated, contract, "test")
            self.assertTrue(result["source_audio_unchanged"])
            self.assertFalse(result["production_ready"])
            self.assertEqual(set(result["stream_types"]), {"audio", "video"})
            with self.assertRaisesRegex(RuntimeError, "destination already exists"):
                video_executor.finalize_delivery(project, generated, contract, "test")
            long_contract = make_audio(2)
            with self.assertRaisesRegex(RuntimeError, "shorter than the performance"):
                video_executor.finalize_delivery(project, generated, long_contract, "too_short")
            self.assertFalse((project / "build/identity/video/deliveries/too_short/performance.mkv").exists())
