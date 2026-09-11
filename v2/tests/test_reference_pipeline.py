import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import reference_pipeline


def project(reference_path="reference.mp4"):
    return {
        "reference_reconstruction": {
            "enabled": True,
            "reference_id": "master",
            "audio_policy": "strip_and_ignore",
        },
        "motion_references": [{"id": "master", "path": reference_path}],
    }


def scenes():
    return [
        {
            "id": "scene_01", "title": "Tunnel monitors", "environment_id": "tunnel",
            "shots": [{
                "id": "shot_01", "duration_seconds": 1, "cast": ["dystopian_masses"],
                "action": "Workers watch a CRT screen.",
            }],
        },
        {
            "id": "scene_02", "title": "Throw", "environment_id": "hall",
            "shots": [{
                "id": "shot_02", "duration_seconds": 3,
                "cast": ["k0l3k4", "enforcers"], "props": ["hammer"],
                "action": "The performer throws the hammer at the screen.",
            }],
        },
    ]


def probe_data():
    return {
        "format": {"duration": "40.0", "format_name": "mov,mp4", "bit_rate": "8000"},
        "streams": [
            {
                "index": 0, "codec_type": "video", "codec_name": "h264",
                "width": 1920, "height": 1080, "avg_frame_rate": "24000/1001",
            },
            {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2},
        ],
    }


class ReferencePipelineTests(unittest.TestCase):
    def test_maps_shots_proportionally_and_in_order(self):
        ranges = reference_pipeline.map_shots_to_reference(scenes(), 40.0)
        self.assertEqual([(item["source_start_seconds"], item["source_end_seconds"]) for item in ranges], [(0.0, 10.0), (10.0, 40.0)])
        self.assertEqual(ranges[0]["resource_tags"], ["camera", "environment", "screen", "workers"])
        self.assertEqual(ranges[1]["resource_tags"], ["camera", "enforcers", "environment", "hammer", "k_performer", "screen"])

    def test_samples_are_deterministic_and_boundary_safe(self):
        self.assertEqual(reference_pipeline.sample_timestamps(10, 20), [
            {"sample": "start", "timestamp_seconds": 11.0},
            {"sample": "action", "timestamp_seconds": 15.0},
            {"sample": "end", "timestamp_seconds": 19.0},
        ])

    def test_normalizes_video_and_audio_stream_inventory(self):
        result = reference_pipeline.normalize_probe(probe_data())
        self.assertEqual(result["duration_seconds"], 40.0)
        self.assertEqual((result["width"], result["height"]), (1920, 1080))
        self.assertEqual(result["frame_rate"], 23.976024)
        self.assertEqual(result["stream_counts"], {"video": 1, "audio": 1, "other": 0})

    def test_ingest_writes_hashed_frames_manifest_and_resource_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "reference.mp4"
            source.write_bytes(b"reference video")
            extracted = []

            def extractor(source_path, timestamp, output_path):
                self.assertEqual(source_path, source.resolve())
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(f"png at {timestamp:.6f}".encode())
                extracted.append((timestamp, output_path))

            manifest = reference_pipeline.ingest_reference(
                root, project(), scenes(), probe_data=probe_data(), frame_extractor=extractor
            )
            self.assertEqual(len(extracted), 6)
            self.assertEqual(manifest["source"]["sha256"], reference_pipeline.sha256_file(source))
            self.assertEqual(manifest["audio"], {"source_stream_count": 1, "ignored": True, "artifacts_emitted": False})
            self.assertTrue(all(sample["sha256"] for item in manifest["shot_ranges"] for sample in item["samples"]))
            hammer_task = next(task for task in manifest["vision_contract_tasks"] if task["shot_id"] == "shot_02")
            self.assertIn("hammer_geometry", hammer_task["contract_types"])
            self.assertIn("reference_performer.face", hammer_task["identity_exclusions"])
            saved = json.loads((root / "build/reference/reference_manifest.json").read_text())
            self.assertEqual(saved, manifest)
            self.assertFalse(any(path.suffix.lower() in {".aac", ".wav", ".mp3"} for path in root.rglob("*")))

    def test_ingest_can_emit_task_stubs_without_extracting_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "reference.mp4").write_bytes(b"video")
            manifest = reference_pipeline.ingest_reference(
                root, project(), scenes(), probe_data=probe_data(), extract_frames=False
            )
            self.assertEqual(len(manifest["vision_contract_tasks"]), 6)
            self.assertTrue(all(task["frame_path"] is None for task in manifest["vision_contract_tasks"]))
            self.assertFalse((root / "build/reference/frames").exists())

    def test_ingest_rejects_non_visual_only_audio_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "reference.mp4").write_bytes(b"video")
            configured = project()
            configured["reference_reconstruction"]["audio_policy"] = "copy"
            with self.assertRaisesRegex(ValueError, "strip_and_ignore"):
                reference_pipeline.ingest_reference(
                    root, configured, scenes(), probe_data=probe_data(), extract_frames=False
                )

    def test_ffmpeg_command_maps_only_video_and_disables_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output = root / "source.mp4", root / "frame.png"
            source.write_bytes(b"video")
            commands = []

            def runner(command, **kwargs):
                commands.append((command, kwargs))
                output.write_bytes(b"png")

            reference_pipeline.extract_png_frame(source, 1.25, output, runner)
            command = commands[0][0]
            self.assertEqual(command[command.index("-map") + 1], "0:v:0")
            self.assertIn("-an", command)

    def test_probe_uses_ffprobe_json(self):
        commands = []

        class Result:
            stdout = json.dumps(probe_data())

        def runner(command, **kwargs):
            commands.append((command, kwargs))
            return Result()

        result = reference_pipeline.probe_reference(Path("video.mp4"), runner)
        self.assertEqual(result["format"]["duration"], "40.0")
        self.assertEqual(commands[0][0][0], "ffprobe")
        self.assertIn("-show_streams", commands[0][0])

    def test_resolve_reference_uses_content_root_and_variables(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            content = root / "external"
            content.mkdir()
            source = content / "clips" / "master.mp4"
            source.parent.mkdir()
            source.write_bytes(b"video")
            reference_id, resolved = reference_pipeline.resolve_reference(
                root, project("${CLIP_DIR}/master.mp4"), content_root=content,
                path_variables={"CLIP_DIR": "clips"},
            )
            self.assertEqual(reference_id, "master")
            self.assertEqual(resolved, source.resolve())


if __name__ == "__main__":
    unittest.main()
