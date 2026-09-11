import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import lora_validation
from scene_factory import command_new, read_json


class LoraValidationTests(unittest.TestCase):
    def test_builds_fixed_grid_and_preserves_promotion_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "episode"
            command_new(SimpleNamespace(destination=root, id="test", title="Test"))
            manifest, manifest_path, promotion_path = lora_validation.build(root, "lead_identity")
            self.assertEqual(len(manifest["jobs"]), 4 * 5 * 3)
            self.assertEqual(manifest["fixed_seeds"], [2184, 2185, 2186])
            self.assertTrue(all(Path(item["workflow"]).is_file() for item in manifest["jobs"]))
            self.assertTrue(manifest_path.is_file())
            promotion = read_json(promotion_path)
            self.assertEqual(promotion["decision"], "pending")
            promotion["notes"] = "keep"
            promotion_path.write_text(__import__("json").dumps(promotion) + "\n")
            lora_validation.build(root, "lead_identity")
            self.assertEqual(read_json(promotion_path)["notes"], "keep")


if __name__ == "__main__":
    unittest.main()
