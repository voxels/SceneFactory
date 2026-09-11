import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rough_cut


class RoughCutTests(unittest.TestCase):
    def test_selects_completed_candidate_in_timeline_order(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            build = root / "build"
            build.mkdir()
            clip = root / "clip.mp4"
            clip.write_bytes(b"video")
            (build / "generation_manifest.json").write_text(json.dumps({
                "assembly": [{
                    "order": 1, "scene_id": "scene_01", "shot_id": "shot_01",
                    "formation_id": "wide", "trim_duration_seconds": 2.0
                }]
            }))
            state = build / "execution" / "comfy_state.json"
            state.parent.mkdir()
            state.write_text(json.dumps({"jobs": {
                "video__scene_01__shot_01__wide__candidate_01__5s__portrait": {
                    "status": "complete", "outputs": [str(clip)]
                }
            }}))
            selected, missing = rough_cut.select_clips(root, candidate=1, duration=5)
            self.assertEqual([item["formation_id"] for item in selected], ["wide"])
            self.assertEqual(missing, [])

    def test_reports_missing_job(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            build = root / "build"
            (build / "execution").mkdir(parents=True)
            (build / "generation_manifest.json").write_text(json.dumps({
                "assembly": [{
                    "order": 1, "scene_id": "scene_01", "shot_id": "shot_01",
                    "formation_id": "wide", "trim_duration_seconds": 2.0
                }]
            }))
            (build / "execution" / "comfy_state.json").write_text(json.dumps({"jobs": {}}))
            selected, missing = rough_cut.select_clips(root)
            self.assertEqual(selected, [])
            self.assertEqual(missing[0]["status"], "not_started")


if __name__ == "__main__":
    unittest.main()
