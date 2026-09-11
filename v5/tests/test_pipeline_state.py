"""v5 regression tests: pipeline_state.json is intake-stages-only.

Per v3/docs/19_EXECUTION_STATUS.md (carried into v5): generation status is
derived on read by execution_status.py from the authority order
(user review > plans/graph manifest > runner job log > named output files >
live queue overlay). refresh_state must never hardcode generation stages as
blocked, and status queries must be read-only.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pipeline


class TestPipelineState(unittest.TestCase):
    def test_refresh_state_reports_intake_stages_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = pipeline.refresh_state(
                root,
                context={"project": {"project": {"id": "test"}}},
                catalog={"assets": []},
                captions={"tasks": []},
            )
            stage_ids = [item["id"] for item in state["stages"]]
            self.assertEqual(
                stage_ids,
                [
                    "source_ingestion",
                    "structured_captioning",
                    "identity_isolation",
                    "caption_review",
                    "concept_datasets",
                    "concept_training",
                ],
            )
            for generation_stage in (
                "character_sheets",
                "storyboards",
                "scripted_clips",
                "extended_sequences",
                "final_assembly",
            ):
                self.assertNotIn(generation_stage, stage_ids)

    def test_refresh_state_persist_false_does_not_write(self):
        # pipeline-status must be read-only: no pipeline_state.json write.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = pipeline.refresh_state(
                root,
                context={"project": {"project": {"id": "test"}}},
                catalog={"assets": []},
                captions={"tasks": []},
                persist=False,
            )
            self.assertTrue(state["stages"])
            self.assertFalse((root / "build" / "pipeline_state.json").exists())


if __name__ == "__main__":
    unittest.main()
