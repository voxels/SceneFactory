import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from scene_factory import command_new, command_pipeline_status, read_json
import pipeline


class NewProjectTemplateTests(unittest.TestCase):
    def test_new_project_includes_series_forms_and_updates_episode_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "episode"
            command_new(SimpleNamespace(destination=destination, id="S01E02 Test", title="Episode Two"))
            self.assertTrue((destination / "SERIES_EPISODE_WORKSHEET.md").exists())
            self.assertTrue((destination / "RUNTIME_DEPENDENCIES.md").exists())
            self.assertTrue((destination / "runtime.env.sh").exists())
            self.assertTrue((destination / "reviews/asset_swap_manifest.json").exists())
            self.assertTrue((destination / "reviews/episode_artifact_review.json").exists())
            self.assertEqual(read_json(destination / "series_context.json")["episode_id"], "s01e02_test")
            self.assertEqual(read_json(destination / "project.json")["project"]["title"], "Episode Two")
            project = read_json(destination / "project.json")
            self.assertEqual(project["models"]["captioner"]["model"], "Qwen3.8-27B")
            self.assertEqual(
                project["path_defaults"]["QWEN_VISION_MODEL_PATH"],
                project["path_defaults"]["QWEN_VISION_PROCESSOR_PATH"],
            )

    def test_prepare_creates_empty_execution_review_ledgers_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "episode"
            command_new(SimpleNamespace(destination=destination, id="test", title="Test"))
            pipeline.prepare(destination)
            storyboard_path = destination / "build/review/storyboard_selections.json"
            proof_path = destination / "build/review/motion_proof_reviews.json"
            self.assertEqual(read_json(storyboard_path)["selections"], [])
            self.assertEqual(read_json(proof_path)["approvals"], [])
            storyboard_path.write_text('{"schema_version": 1, "selections": [{"keep": true}]}\n')
            pipeline.prepare(destination)
            self.assertEqual(read_json(storyboard_path)["selections"], [{"keep": True}])

    def test_pipeline_status_does_not_rewrite_pipeline_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "episode"
            command_new(SimpleNamespace(destination=destination, id="test", title="Test"))
            pipeline.prepare(destination)
            state_path = destination / "build/pipeline_state.json"
            before = state_path.read_bytes()
            with redirect_stdout(StringIO()):
                command_pipeline_status(SimpleNamespace(project=destination))
            self.assertEqual(state_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
