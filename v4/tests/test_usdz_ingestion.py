import json
import tempfile
import unittest
from pathlib import Path

import usdz_ingestion


class USDZIngestionTests(unittest.TestCase):
    def test_member_hashes_and_missing_rig_signals_are_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source" / "3D"
            source.mkdir(parents=True)
            import zipfile
            with zipfile.ZipFile(source / "head.usdz", "w") as archive:
                archive.writestr("head.usda", "def Mesh \"head\" { uniform token[] primvars:st = [] }\n")
                archive.writestr("textures/skin.jpg", b"texture")
            # Use the production project's valid config and redirect its source root.
            production = Path(__file__).parents[1] / "examples/modeling_interview/identity.json"
            config = json.loads(production.read_text())
            config["source_root"] = "../source"
            config["modalities"] = {"geometry": {"kind": "geometry", "globs": ["3D/*.usdz"], "required_in_fine_tuning": False, "training_policy": "conditioning_only", "roles": ["head_geometry"]}}
            config["characteristics"] = {"face": {"stable": True, "authority": ["geometry"]}}
            project = root / "project"
            project.mkdir()
            (project / "identity.json").write_text(json.dumps(config))
            report = usdz_ingestion.ingest(project)
            self.assertEqual(report["counts"]["sources"], 1)
            record = report["records"][0]
            self.assertTrue(record["members"][0]["sha256"])
            self.assertIn("skeleton", record["limitations"])
            self.assertIn("blend_shapes", record["limitations"])
            self.assertFalse(record["derived_controls"]["consumed"])


if __name__ == "__main__":
    unittest.main()
