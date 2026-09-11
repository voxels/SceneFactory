import json
import tempfile
import unittest
from pathlib import Path

import stage_stubs
import test_identity_pipeline
import goal_audit


class StageStubTests(unittest.TestCase):
    def test_emit_is_explicitly_non_production_and_hashes_existing_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            result = stage_stubs.emit(project)
            self.assertEqual(result["status"], "stubbed")
            self.assertFalse(result["production_ready"])
            self.assertTrue(result["does_not_count_as_consumed"])
            self.assertEqual(len(result["entries"]), 5)
            self.assertEqual(len(result["workflow_stubs"]), 2)
            persisted = json.loads((project / "build/stubs/stub_manifest.json").read_text())
            self.assertEqual(persisted["invariant"], result["invariant"])
            for entry in result["entries"]:
                self.assertTrue((project / "build/stubs" / f"{entry['id']}.json").is_file())
                self.assertFalse(entry["production_ready"])
            for path in result["workflow_stubs"]:
                graph = json.loads(Path(path).read_text())
                self.assertEqual(graph["status"], "blocked_stub")
                self.assertFalse(graph["queue_submission_allowed"])

    def test_goal_audit_is_requirement_level_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = test_identity_pipeline.IdentityPipelineTests().make_project(Path(temporary))
            report = goal_audit.audit(project)
            self.assertEqual(report["required_count"], 10)
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["passed_count"], 1)
            self.assertTrue((project / "build/validation/goal_completion_audit.json").is_file())
