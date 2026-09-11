import json
import tempfile
import unittest
from pathlib import Path

import test_identity_pipeline
import video_workflows


class VideoWorkflowTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        project = test_identity_pipeline.IdentityPipelineTests().make_project(root)
        visual = project / "build/identity/video/visual_identity_manifest.json"
        motion = project / "build/identity/video/motion_reference_manifest.json"
        visual.parent.mkdir(parents=True, exist_ok=True)
        frame = visual.parent / "frame.jpg"
        frame.write_bytes(b"identity-frame")
        source = visual.parent / "motion.mp4"
        source.write_bytes(b"motion-video")
        visual.write_text(json.dumps({"clips": [{"frames": [{"path": str(frame)}]}]}), encoding="utf-8")
        motion.write_text(json.dumps({"sources": [{"path": str(source)}]}), encoding="utf-8")
        return project

    def test_compiler_binds_identity_and_motion_as_separate_guides(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = video_workflows.compile_workflow(self._project(Path(temporary)))
            self.assertEqual(result["status"], "compiled")
            contract = result["contract"]
            graph = json.loads(Path(contract["graph"]).read_text())
            self.assertEqual(graph["10"]["class_type"], "LTXVAddGuide")
            self.assertEqual(graph["12"]["class_type"], "LTXVAddGuide")
            self.assertEqual(graph["10"]["inputs"]["image"], ["8", 0])
            self.assertEqual(graph["12"]["inputs"]["image"], ["11", 0])
            self.assertTrue(contract["controls"]["identity_keyframe"])
            self.assertTrue(contract["controls"]["motion_reference"])
            self.assertTrue(contract["controls"]["motion_lora"])
            self.assertFalse(contract["execution_allowed"])
            self.assertIn("authoritative TTS audio is missing", contract["execution_blockers"])

    def test_compiler_rejects_invalid_ltx_frame_length(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                video_workflows.compile_workflow(self._project(Path(temporary)), length=50)


if __name__ == "__main__":
    unittest.main()
