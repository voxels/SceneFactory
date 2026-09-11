import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


NODE_PATH = Path(__file__).resolve().parents[1] / "comfy_nodes" / "scene_factory_pose_io" / "__init__.py"


class PoseIONodeTests(unittest.TestCase):
    def _module(self):
        spec = importlib.util.spec_from_file_location("scene_factory_pose_io", NODE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_pose_writer_rejects_paths_outside_workspace(self):
        node = self._module().SceneFactorySavePoseKeypoints()
        with self.assertRaises(ValueError):
            node.save([], "/tmp/not-allowed.json")

    def test_pose_writer_persists_openpose_frames(self):
        node = self._module().SceneFactorySavePoseKeypoints()
        with tempfile.TemporaryDirectory(dir="/Users/voxels/SceneFactory") as temporary:
            output = Path(temporary) / "pose.json"
            node.save([{"canvas_width": 10, "canvas_height": 20, "people": []}], str(output))
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["fps"], 24.0)
            self.assertEqual(len(payload["frames"]), 1)

    def test_mask_writer_persists_timestamped_sequence(self):
        module = self._module()
        node = module.SceneFactorySaveMaskSequence()
        with tempfile.TemporaryDirectory(dir="/Users/voxels/SceneFactory") as temporary:
            node.save(module.np.ones((2, 4, 5), dtype=module.np.float32), temporary, 43.72, 25)
            manifest = json.loads((Path(temporary) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["frames"]), 2)
            self.assertAlmostEqual(manifest["frames"][1]["timestamp_seconds"], 43.76)
            self.assertTrue(Path(manifest["frames"][0]["path"]).read_bytes().startswith(b"P5\n5 4\n255\n"))

    def test_proxy_mask_loader_emits_padded_per_frame_boxes(self):
        module = self._module()
        node = module.SceneFactoryLoadMaskBoundingBoxes()
        with tempfile.TemporaryDirectory(dir="/Users/voxels/SceneFactory") as temporary:
            root = Path(temporary)
            mask = root / "mask.pgm"
            pixels = bytearray(100)
            for y in range(3, 6):
                for x in range(2, 5):
                    pixels[y * 10 + x] = 255
            mask.write_bytes(b"P5\n10 10\n255\n" + bytes(pixels))
            record = root / "record.json"
            record.write_text(json.dumps({"samples": [{"mask_path": "mask.pgm"}]}), encoding="utf-8")
            boxes = node.load(str(record), str(root), 100, 100, 2)[0]
            self.assertEqual(boxes, [[{"x": 18, "y": 28, "width": 34, "height": 34}]])


if __name__ == "__main__":
    unittest.main()
