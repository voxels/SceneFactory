import unittest

import usdz_controls


class USDZControlTests(unittest.TestCase):
    def test_renderer_script_is_present_and_pinned_by_orchestrator(self):
        self.assertTrue(usdz_controls.RENDER_SCRIPT.is_file())
        source = usdz_controls.RENDER_SCRIPT.read_text()
        for required in ("depth_metric", "depth_normalized", "normals", "silhouette", "camera_location"):
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
