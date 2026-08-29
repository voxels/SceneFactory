import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from production_tracking import (
    homography_from_unit_square,
    openpose_frames_to_samples,
    retarget_pose_samples,
    smooth_pose_samples,
    write_rotated_hammer_mask,
)


class ProductionTrackingTests(unittest.TestCase):
    def test_openpose_frames_convert_to_normalized_samples_and_root(self):
        points = []
        for index in range(18):
            points.extend([100 + index, 200 + index, 0.9])
        raw = {
            "start_timestamp_seconds": 36.48,
            "fps": 24,
            "frames": [{"canvas_width": 1000, "canvas_height": 500, "people": [{"pose_keypoints_2d": points}]}],
        }
        samples = openpose_frames_to_samples(raw)
        self.assertEqual(samples[0]["timestamp_seconds"], 36.48)
        joints = {joint["name"]: joint for joint in samples[0]["poses"][0]["joints"]}
        self.assertAlmostEqual(joints["nose"]["x"], 0.1)
        self.assertAlmostEqual(joints["nose"]["y"], 0.4)
        self.assertIn("root", joints)

    def test_homography_maps_unit_square_corners(self):
        corners = [[0.2, 0.1], [0.8, 0.12], [0.78, 0.9], [0.18, 0.88]]
        matrix = np.asarray(homography_from_unit_square(corners))
        for source, expected in zip([[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], corners):
            projected = matrix @ np.asarray(source)
            projected = projected[:2] / projected[2]
            np.testing.assert_allclose(projected, expected)

    def test_association_prefers_continuous_performer_and_smooths(self):
        samples = [
            {"timestamp_seconds": 0, "poses": [{"confidence": 1, "joints": [{"name": "root", "x": 0.2, "y": 0.2, "confidence": 1}]}]},
            {"timestamp_seconds": 1, "poses": [
                {"confidence": 1, "joints": [{"name": "root", "x": 0.9, "y": 0.9, "confidence": 1}]},
                {"confidence": 0.8, "joints": [{"name": "root", "x": 0.3, "y": 0.2, "confidence": 1}]},
            ]},
        ]
        result = smooth_pose_samples(samples, alpha=0.5)
        self.assertEqual(result[1]["source_pose_index"], 1)
        self.assertAlmostEqual(result[1]["joints"][0]["x"], 0.25)

    def test_retargeting_is_root_relative_and_proportion_neutral(self):
        result = retarget_pose_samples([{"timestamp_seconds": 0, "joints": [
            {"name": "root", "x": 0.5, "y": 0.4, "confidence": 1},
            {"name": "neck", "x": 0.5, "y": 0.8, "confidence": 1},
        ]}])[0]
        controls = {item["name"]: item for item in result["controls"]}
        self.assertEqual(controls["root"]["x"], 0)
        self.assertAlmostEqual(controls["neck"]["y"], 1)

    def test_proxy_mask_is_real_nonempty_pgm(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.pgm"
            write_rotated_hammer_mask(path, 64, 32, 0.5, 0.5, 45)
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"P5\n64 32\n255\n"))
            self.assertIn(255, data[len(b"P5\n64 32\n255\n"):])

    def test_checked_in_records_are_honest_about_readiness(self):
        project = Path(__file__).resolve().parents[1] / "examples" / "ad2184"
        manifest_path = project / "build/tracking/tracking_manifest.json"
        if not manifest_path.is_file():
            self.skipTest("clean root intentionally contains no generated tracking records")
        manifest = json.loads(manifest_path.read_text())
        self.assertTrue(manifest["production_readiness"]["k_skeleton"])
        self.assertFalse(manifest["production_readiness"]["hammer"])
        self.assertTrue(manifest["production_readiness"]["screen"])
        self.assertTrue(manifest["generation_blocked"])
        screen = json.loads((project / manifest["records"]["screen"]).read_text())
        self.assertEqual(screen["destruction_boundary"]["first_destroyed_timestamp_seconds"], 46.08)


if __name__ == "__main__":
    unittest.main()
