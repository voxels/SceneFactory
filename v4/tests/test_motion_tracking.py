import unittest

import motion_tracking


class MotionTrackingTests(unittest.TestCase):
    def test_nearest_centroid_association_preserves_track_ids(self):
        frames = [
            {"body_poses": [{"joints": [{"name": "root", "x": 0.2, "y": 0.3, "confidence": 1.0}]}]},
            {"body_poses": [{"joints": [{"name": "root", "x": 0.22, "y": 0.31, "confidence": 1.0}]}]},
        ]
        motion_tracking._assign_tracks(frames, 0.25, 0.2)
        self.assertEqual(frames[0]["body_poses"][0]["track_id"], frames[1]["body_poses"][0]["track_id"])

    def test_distant_detection_starts_new_track(self):
        frames = [
            {"body_poses": [{"joints": [{"name": "root", "x": 0.1, "y": 0.1, "confidence": 1.0}]}]},
            {"body_poses": [{"joints": [{"name": "root", "x": 0.9, "y": 0.9, "confidence": 1.0}]}]},
        ]
        motion_tracking._assign_tracks(frames, 0.25, 0.2)
        self.assertNotEqual(frames[0]["body_poses"][0]["track_id"], frames[1]["body_poses"][0]["track_id"])


if __name__ == "__main__":
    unittest.main()
