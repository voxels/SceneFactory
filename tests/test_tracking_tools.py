import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


@unittest.skipUnless(shutil.which("swiftc"), "swiftc is required")
class TrackingToolContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.binaries = {}
        for name in ("track_body_pose", "track_planar_object"):
            binary = Path(cls.tempdir.name) / name
            subprocess.run(
                [
                    "swiftc",
                    "-module-cache-path",
                    str(Path(cls.tempdir.name) / "module-cache"),
                    str(TOOLS / f"{name}.swift"),
                    "-framework",
                    "AVFoundation",
                    "-framework",
                    "Vision",
                    "-o",
                    str(binary),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            cls.binaries[name] = binary

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def run_tool(self, name, *args):
        return subprocess.run(
            [str(self.binaries[name]), *args],
            capture_output=True,
            text=True,
        )

    def test_body_pose_help_describes_range_interval_and_output(self):
        result = self.run_tool("track_body_pose", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--start SECONDS", result.stdout)
        self.assertIn("--end SECONDS", result.stdout)
        self.assertIn("--interval SECONDS", result.stdout)
        self.assertIn("Vision's normalized lower-left", result.stdout)

    def test_body_pose_rejects_nonpositive_interval_before_opening_video(self):
        result = self.run_tool("track_body_pose", "missing.mov", "--interval", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--interval must be greater than zero", result.stderr)

    def test_planar_help_documents_required_initial_box(self):
        result = self.run_tool("track_planar_object", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--bbox X,Y,WIDTH,HEIGHT", result.stdout)
        self.assertIn("caller-supplied initial bounding box", result.stdout)

    def test_planar_requires_initial_box(self):
        result = self.run_tool("track_planar_object", "missing.mov")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Missing required --bbox", result.stderr)

    def test_planar_rejects_box_outside_normalized_frame(self):
        result = self.run_tool(
            "track_planar_object", "missing.mov", "--bbox", "0.8,0.2,0.3,0.4"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("fully inside 0...1", result.stderr)


if __name__ == "__main__":
    unittest.main()
