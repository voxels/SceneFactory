import json
import plistlib
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

import identity_pipeline


class IdentityPipelineTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        source = root / "source"
        (source / "voice").mkdir(parents=True)
        (source / "web").mkdir()
        (source / "3D").mkdir()
        # Minimal PNG header sufficient for the dependency-free dimension reader.
        (source / "portrait.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (640).to_bytes(4, "big") + (480).to_bytes(4, "big")
        )
        (source / "voice" / "tts_text.txt").write_text("Hello world. [pause:1.0]\n", encoding="utf-8")
        with wave.open(str(source / "voice" / "sample.wav"), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 1600)
        with zipfile.ZipFile(source / "3D" / "head.usdz", "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("head.usda", "#usda 1.0\n")
            archive.writestr("textures/face.jpg", b"fake texture")
        webarchive = {
            "WebMainResource": {
                "WebResourceURL": "https://example.test/person",
                "WebResourceMIMEType": "text/html",
                "WebResourceData": b"<html></html>",
            },
            "WebSubresources": [{
                "WebResourceURL": "https://example.test/reference.png",
                "WebResourceMIMEType": "image/png",
                "WebResourceData": b"web image",
            }],
        }
        with (source / "web" / "source.webarchive").open("wb") as stream:
            plistlib.dump(webarchive, stream, fmt=plistlib.FMT_BINARY)
        project = root / "project"
        project.mkdir()
        config = {
            "schema_version": 4,
            "run_mode": "automatic",
            "identity": {"id": "test", "display_name": "Test", "subject_type": "person", "consent": {"status": "verified", "required_in_fine_tuning": True}},
            "source_root": "../source",
            "exclusion_policy": {"case_insensitive_terms": ["Koleka", "k0l3k4"], "globs": ["**/*koleka*"]},
            "identity_matching": {"anchors": ["portrait.png", "portrait.png"], "maximum_anchor_distance": 0.75, "minimum_face_area_fraction": 0.01, "minimum_multi_face_identity_margin": 0.08},
            "modalities": {
                "photos": {"kind": "image", "globs": ["*.png"], "required_in_fine_tuning": True, "training_policy": "direct_after_review", "roles": ["face_identity"]},
                "voice": {"kind": "audio", "globs": ["voice/*.wav"], "required_in_fine_tuning": True, "training_policy": "performance_reference", "roles": ["voiceprint"]},
                "script": {"kind": "transcript", "globs": ["voice/*.txt"], "required_in_fine_tuning": True, "training_policy": "metadata_only", "roles": ["audio_alignment"]},
                "geometry": {"kind": "geometry", "globs": ["3D/*.usdz"], "required_in_fine_tuning": True, "training_policy": "conditioning_only", "roles": ["head_geometry"]},
                "web": {"kind": "webarchive", "globs": ["web/*.webarchive"], "required_in_fine_tuning": False, "training_policy": "derive_then_review", "roles": ["appearance_history"]},
            },
            "characteristics": {
                "face": {"stable": True, "authority": ["geometry", "photos", "web"]},
                "voice": {"stable": True, "authority": ["voice", "script"]},
            },
            "fusion_policy": {
                "conflict_resolution": "higher_authority_then_mode_policy",
                "cross_modal_alignment": "preserve_separate_conditioning_channels",
                "webarchive_review": "fine_tuning_only",
                "generated_audio_scope": "voice_and_performance_only",
            },
            "selection_policy": {
                "minimum_width": 1,
                "minimum_height": 1,
                "minimum_contrast": 0,
                "minimum_sharpness": 0,
                "brightness_range": [0, 255],
                "near_duplicate_hamming_distance": 0,
                "validation_fraction": 0.2,
                "calibration_fraction": 0.1,
                "final_test_fraction": 0.1,
                "maximum_visual_training_images": 100,
                "video_frames_per_source": 1,
                "audio_minimum_duration_seconds": 0.01,
                "audio_maximum_clipping_fraction": 0.01,
                "audio_maximum_silence_fraction": 1.0
            },
        }
        (project / "identity.json").write_text(json.dumps(config), encoding="utf-8")
        return project

    def test_build_indexes_every_modality_and_extracts_review_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            manifest, characteristics = identity_pipeline.build(project, extract_web_media=True)
            self.assertEqual(manifest["inventory"]["source_asset_count"], 5)
            self.assertEqual(manifest["inventory"]["extracted_candidate_count"], 1)
            self.assertTrue(characteristics["readiness"]["ready_for_training"])
            candidate = manifest["derived_review_candidates"][0]
            self.assertEqual(candidate["review_state"], "pending")
            self.assertFalse(candidate["training_eligible"])
            self.assertEqual(candidate["provenance"], "webarchive_embedded_derivative")
            self.assertEqual(len(candidate["derived_from"]), 1)
            geometry = next(item for item in manifest["assets"] if item["kind"] == "geometry")
            self.assertEqual(geometry["metadata"]["member_types"][".usda"], 1)
            self.assertEqual(geometry["metadata"]["texture_members"], ["textures/face.jpg"])
            audio = next(item for item in manifest["assets"] if item["kind"] == "audio")
            self.assertEqual(audio["metadata"]["sample_rate"], 16000)
            image = next(item for item in manifest["assets"] if item["kind"] == "image")
            self.assertEqual(image["metadata"], {"width": 640, "height": 480})
            self.assertEqual(characteristics["audio_transcript_alignment"]["status"], "ready_for_review")
            self.assertTrue((project / "build/identity/asset_manifest.json").is_file())
            self.assertTrue((project / "build/identity/identity_characteristics.json").is_file())

    def test_missing_audio_and_unverified_consent_block_training(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            config = json.loads((project / "identity.json").read_text())
            config["identity"]["consent"]["status"] = "unverified"
            (project.parent / "source/voice/sample.wav").unlink()
            (project / "identity.json").write_text(json.dumps(config), encoding="utf-8")
            _, characteristics = identity_pipeline.build(project, run_mode="fine_tuning")
            self.assertFalse(characteristics["readiness"]["ready_for_training"])
            self.assertIn("missing required modality: voice", characteristics["readiness"]["blockers"])
            self.assertIn("consent status is unverified", characteristics["readiness"]["blockers"])

    def test_unverified_consent_also_blocks_automatic_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            config = json.loads((project / "identity.json").read_text())
            config["identity"]["consent"]["status"] = "unverified"
            (project / "identity.json").write_text(json.dumps(config), encoding="utf-8")
            _, characteristics = identity_pipeline.build(project)
            self.assertFalse(characteristics["readiness"]["ready_for_training"])
            self.assertIn("consent status is unverified", characteristics["readiness"]["blockers"])

    def test_koleka_paths_are_excluded_case_insensitively(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            source = project.parent / "source"
            (source / "KoLeKa_reference.png").write_bytes((source / "portrait.png").read_bytes())
            manifest, _ = identity_pipeline.build(project)
            self.assertFalse(any("koleka" in item["relative_path"].casefold() for item in manifest["assets"]))
            self.assertEqual(manifest["inventory"]["excluded_source_count"], 1)
            self.assertEqual(manifest["excluded_assets"][0]["relative_path"], "KoLeKa_reference.png")

    def test_unknown_characteristic_authority_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            config = json.loads((project / "identity.json").read_text())
            config["characteristics"]["face"]["authority"] = ["missing"]
            (project / "identity.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown modalities"):
                identity_pipeline.build(project)

    def test_exact_duplicate_sources_are_grouped(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            source = project.parent / "source"
            (source / "duplicate.png").write_bytes((source / "portrait.png").read_bytes())
            manifest, _ = identity_pipeline.build(project)
            self.assertEqual(manifest["inventory"]["exact_duplicate_group_count"], 1)
            self.assertEqual(len(manifest["exact_duplicate_groups"][0]["asset_ids"]), 2)


if __name__ == "__main__":
    unittest.main()
