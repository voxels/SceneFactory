import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scene_factory import command_new, read_json


class NewProjectTemplateTests(unittest.TestCase):
    def test_new_project_includes_series_forms_and_updates_episode_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "episode"
            command_new(SimpleNamespace(destination=destination, id="S01E02 Test", title="Episode Two"))
            self.assertTrue((destination / "SERIES_EPISODE_WORKSHEET.md").exists())
            self.assertTrue((destination / "reviews/asset_swap_manifest.json").exists())
            self.assertTrue((destination / "reviews/episode_artifact_review.json").exists())
            self.assertEqual(read_json(destination / "series_context.json")["episode_id"], "s01e02_test")
            self.assertEqual(read_json(destination / "project.json")["project"]["title"], "Episode Two")


if __name__ == "__main__":
    unittest.main()
