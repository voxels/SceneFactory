import tempfile
import unittest
import wave
import json
import shutil
import subprocess
from pathlib import Path

import video_audio_pipeline
import test_identity_pipeline


class VideoAudioPipelineTests(unittest.TestCase):
    def test_explicit_video_roles_are_independent_and_motion_cannot_leak(self):
        manifest = {
            "assets": [
                {"asset_id": "visual", "kind": "video", "path": "/visual.mp4", "sha256": "a" * 64, "group_id": "g-visual", "usage_roles": ["visual_identity"]},
                {"asset_id": "motion", "kind": "video", "path": "/motion.mp4", "sha256": "b" * 64, "group_id": "g-motion", "usage_roles": ["motion_reference"]},
                {"asset_id": "both", "kind": "video", "path": "/both.mp4", "sha256": "c" * 64, "group_id": "g-both", "usage_roles": ["both"]},
            ]
        }
        partition = video_audio_pipeline.partition_video_assets(manifest)
        visual_ids = {item["asset_id"] for item in partition["visual_identity"]}
        motion_ids = {item["asset_id"] for item in partition["motion_reference"]}
        self.assertEqual(visual_ids, {"visual", "both"})
        self.assertEqual(motion_ids, {"motion", "both"})
        self.assertNotIn("motion", visual_ids)
        self.assertFalse(next(item for item in partition["motion_reference"] if item["asset_id"] == "motion")["identity_eligible"])

    def test_missing_role_is_blocked_instead_of_inferred(self):
        partition = video_audio_pipeline.partition_video_assets({"assets": [{"asset_id": "unknown", "kind": "video", "path": "/x", "sha256": "d" * 64}]})
        self.assertEqual(partition["visual_identity"], [])
        self.assertEqual(partition["motion_reference"], [])
        self.assertTrue(partition["blockers"])
        self.assertEqual(partition["excluded"][0]["reason"], "missing_explicit_video_usage_role")

    def test_audio_contract_preserves_source_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dialogue.wav"
            with wave.open(str(path), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(b"\x01\x00" * 16000)
            before = video_audio_pipeline.identity.sha256_file(path)
            contract = video_audio_pipeline._audio_stream_contract(path)
            self.assertEqual(contract["sha256"], before)
            self.assertTrue(contract["source_bytes_preserved"])
            self.assertEqual(video_audio_pipeline.verify_audio_unchanged(path, before)["status"], "ready")

    def test_audio_mutation_blocks_mux_postcondition(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dialogue.wav"
            with wave.open(str(path), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(b"\x01\x00" * 16000)
            before = video_audio_pipeline.identity.sha256_file(path)
            path.write_bytes(path.read_bytes() + b"tampered")
            result = video_audio_pipeline.verify_audio_unchanged(path, before)
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["source_audio_unchanged"])

    def test_mux_original_audio_stream_copies_waveform_without_mutation(self):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg is required for mux integration test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "video.mp4"
            audio = root / "dialogue.wav"
            output = root / "final.mkv"
            subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=1",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
            ], check=True)
            with wave.open(str(audio), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(b"\x01\x00" * 8000)
            before = video_audio_pipeline.identity.sha256_file(audio)
            result = video_audio_pipeline.mux_original_audio(video, audio, output, expected_audio_sha256=before)
            self.assertEqual(result["status"], "complete")
            self.assertTrue(result["stream_copy"])
            self.assertEqual(set(result["stream_types"]), {"video", "audio"})
            self.assertEqual(video_audio_pipeline.identity.sha256_file(audio), before)

    def test_transcript_contract_keeps_pause_offsets(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tts.txt"
            path.write_text("Hello [pause:1.25] world", encoding="utf-8")
            record = video_audio_pipeline._parse_transcript(path)
            self.assertEqual(record["word_count"], 2)
            self.assertEqual(record["pause_markers"][0]["seconds"], 1.25)
            self.assertEqual(record["sha256"], video_audio_pipeline.identity.sha256_file(path))

    def test_video_runtime_contract_is_emitted_even_when_training_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            result = video_audio_pipeline.prepare_video_audio(project)
            runtime_path = project / "build/identity/video/video_runtime.json"
            runtime = json.loads(runtime_path.read_text())
            self.assertEqual(runtime["status"], "blocked")
            self.assertEqual(runtime["identity_id"], "test")
            self.assertTrue(runtime["promotion_required"])
            self.assertIn("ingredients_ic_lora", runtime["controls"])
            self.assertEqual(result["runtime_contract"]["audio_alignment_manifest"], str((project / "build/identity/video/audio_alignment_manifest.json").resolve()))


if __name__ == "__main__":
    unittest.main()
