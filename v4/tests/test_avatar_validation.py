import unittest
from pathlib import Path

import avatar_validation


class AvatarValidationTests(unittest.TestCase):
    def test_produced_avatar_bundle_is_structurally_valid(self):
        root = Path(__file__).parents[1] / "examples/modeling_interview/build/avatar/gage_portrait"
        if not (root / "avatar_manifest.json").is_file():
            self.skipTest("production avatar has not been exported yet")
        report = avatar_validation.validate(root)
        self.assertEqual(report["status"], "valid")
        self.assertGreater(report["vertex_count"], 0)
        self.assertEqual(report["voice_viseme_timing"], "pending_supplied_tts_audio")

    def test_produced_usdz_contains_semantic_rig_features(self):
        root = Path(__file__).parents[1] / "examples/modeling_interview/build/avatar/gage_portrait"
        mesh = root / "gage_talking_head.usdz"
        if not mesh.is_file():
            self.skipTest("production avatar has not been exported yet")
        usd = avatar_validation._usd_text(mesh)
        for token in ("Skeleton", "BlendShape", "jawOpen", "viseme_", "normal", "texCoord", "material"):
            self.assertIn(token, usd)


if __name__ == "__main__":
    unittest.main()
