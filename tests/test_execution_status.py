import json
import tempfile
import unittest
from pathlib import Path

import execution_status


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def make_project(root: Path, *, namespace="Ad2184_v3"):
    write_json(root / "project.json", {
        "project": {"id": "ad2184_v3_identity_fidelity"},
        "path_defaults": {"OUTPUT_ROOT": "${PROJECT_ROOT}/outputs"},
    })
    job_id = "video__scene_04__shot_04__frontal_run__candidate_01__5s__portrait"
    write_json(root / "build" / "comfyui" / "full_visual_graph_manifest.json", {
        "videos": [{
            "id": job_id,
            "candidate": {"number": 1},
            "execution_phase": "motion_proofs",
            "output_prefix": f"{namespace}/generated/clips/scene_04/shot_04/frontal_run/candidate_01/5s",
            "duration_seconds": 5,
        }]
    })
    return job_id


class ExecutionStatusTests(unittest.TestCase):
    def test_report_stage_statuses_match_execution_schema_enum(self):
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "schemas/execution.schema.json").read_text()
        )
        allowed = set(
            schema["properties"]["stages"]["items"]["properties"]["status"]["enum"]
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            make_project(root)
            statuses = {item["status"] for item in execution_status.collect_status(root)["stages"]}
            self.assertLessEqual(statuses, allowed)

    def test_complete_log_with_missing_file_is_output_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job_id = make_project(root)
            write_json(root / "build" / "execution" / "comfy_state.json", {
                "jobs": {job_id: {"status": "complete", "outputs": [str(root / "missing.mp4")]}}
            })
            report = execution_status.collect_status(root)
            job = report["jobs"][0]
            self.assertEqual(job["state"], "output_missing")
            self.assertNotEqual(job["state"], "approved")
            clips = next(item for item in report["stages"] if item["id"] == "scripted_clips")
            self.assertNotEqual(clips["status"], "complete")

    def test_existing_file_without_review_is_output_present(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job_id = make_project(root)
            clip = root / "clip.mp4"
            clip.write_bytes(b"video")
            write_json(root / "build" / "execution" / "comfy_state.json", {
                "jobs": {job_id: {"status": "complete", "outputs": [str(clip)]}}
            })
            job = execution_status.collect_status(root)["jobs"][0]
            self.assertEqual(job["state"], "output_present")
            self.assertTrue(job["outputs"][0]["exists"])
            self.assertEqual(job["outputs"][0]["sha256"], execution_status.sha256_file(clip))

    def test_user_approval_with_empty_issues_is_approved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job_id = make_project(root)
            clip = root / "clip.mp4"
            clip.write_bytes(b"video")
            write_json(root / "build" / "execution" / "comfy_state.json", {
                "jobs": {job_id: {"status": "complete", "outputs": [str(clip)]}}
            })
            write_json(root / "build" / "review" / "motion_proof_reviews.json", {
                "approvals": [{
                    "video_task_id": "video__scene_04__shot_04__frontal_run",
                    "candidate": 1,
                    "decision": "approved",
                    "approved_by": "user",
                    "issues": [],
                    "extend": True,
                }]
            })
            report = execution_status.collect_status(root)
            self.assertEqual(report["jobs"][0]["state"], "approved")
            clips = next(item for item in report["stages"] if item["id"] == "scripted_clips")
            self.assertEqual(clips["status"], "complete")

    def test_approval_without_user_is_not_approved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job_id = make_project(root)
            clip = root / "clip.mp4"
            clip.write_bytes(b"video")
            write_json(root / "build" / "execution" / "comfy_state.json", {
                "jobs": {job_id: {"status": "complete", "outputs": [str(clip)]}}
            })
            write_json(root / "build" / "review" / "motion_proof_reviews.json", {
                "approvals": [{
                    "video_task_id": "video__scene_04__shot_04__frontal_run",
                    "candidate": 1,
                    "decision": "approved",
                    "issues": [],
                }]
            })
            self.assertEqual(execution_status.collect_status(root)["jobs"][0]["state"], "output_present")

    def test_does_not_create_or_modify_job_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            make_project(root)
            log_path = root / "build" / "execution" / "comfy_state.json"
            self.assertFalse(log_path.exists())
            execution_status.collect_status(root)
            self.assertFalse(log_path.exists())
            write_json(log_path, {"jobs": {}})
            before = log_path.read_text(encoding="utf-8")
            execution_status.collect_status(root)
            self.assertEqual(log_path.read_text(encoding="utf-8"), before)

    def test_plan_without_graph_is_reported_not_compiled(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "project.json", {"project": {"id": "test"}})
            write_json(root / "build" / "storyboard_plan.json", {
                "tasks": [{"id": "storyboard__scene_01__shot_01__wide"}]
            })
            report = execution_status.collect_status(root)
            job = next(item for item in report["jobs"] if item["id"].startswith("storyboard__"))
            self.assertEqual(job["state"], "not_compiled")
            stage = next(item for item in report["stages"] if item["id"] == "storyboards")
            self.assertEqual(stage["status"], "blocked")

    def test_foreign_namespace_live_job_does_not_mark_project_in_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            make_project(root, namespace="Ad2184_v3")
            live = {
                "running_prompt_ids": ["foreign"],
                "pending_prompt_ids": [],
                "running_prefixes": [
                    "Ad2184_v2/generated/clips/scene_04/shot_04/face_guards/candidate_01/5s"
                ],
                "pending_prefixes": [],
            }
            report = execution_status.collect_status(root, live=live)
            self.assertEqual(report["comfy_output_namespace"], "Ad2184_v3")
            self.assertEqual(report["jobs"][0]["state"], "graph_ready")
            clips = next(item for item in report["stages"] if item["id"] == "scripted_clips")
            self.assertNotEqual(clips["status"], "active")
            self.assertEqual(report["counts"]["running"], 0)

    def test_running_job_log_marks_stage_in_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job_id = make_project(root)
            write_json(root / "build" / "execution" / "comfy_state.json", {
                "jobs": {job_id: {"status": "running", "prompt_id": "abc"}}
            })
            report = execution_status.collect_status(root)
            self.assertEqual(report["jobs"][0]["state"], "running")
            clips = next(item for item in report["stages"] if item["id"] == "scripted_clips")
            self.assertEqual(clips["status"], "active")

    def test_storyboard_stage_completes_when_one_candidate_is_approved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "project.json", {
                "project": {"id": "ad2184_v3_identity_fidelity"},
                "path_defaults": {"OUTPUT_ROOT": "${PROJECT_ROOT}/outputs"},
            })
            frame = root / "board.png"
            frame.write_bytes(b"png")
            first = "storyboard__scene_02__shot_02__frontal_chase__candidate_01"
            second = "storyboard__scene_02__shot_02__frontal_chase__candidate_02"
            write_json(root / "build" / "comfyui" / "full_visual_graph_manifest.json", {
                "storyboards": [
                    {
                        "id": first,
                        "candidate": {"number": 1},
                        "execution_phase": "storyboard_candidates",
                        "output_prefix": "Ad2184_v3/generated/storyboards/scene_02/shot_02/frontal_chase/candidate_01",
                    },
                    {
                        "id": second,
                        "candidate": {"number": 2},
                        "execution_phase": "storyboard_candidates",
                        "output_prefix": "Ad2184_v3/generated/storyboards/scene_02/shot_02/frontal_chase/candidate_02",
                    },
                ]
            })
            write_json(root / "build" / "execution" / "comfy_state.json", {
                "jobs": {first: {"status": "complete", "outputs": [str(frame)]}}
            })
            write_json(root / "build" / "review" / "storyboard_selections.json", {
                "selections": [{
                    "storyboard_task_id": "storyboard__scene_02__shot_02__frontal_chase",
                    "candidate": 1,
                    "decision": "approved",
                    "approved_by": "user",
                    "issues": [],
                }]
            })
            report = execution_status.collect_status(root)
            states = {item["id"]: item["state"] for item in report["jobs"]}
            self.assertEqual(states[first], "approved")
            self.assertEqual(states[second], "graph_ready")
            boards = next(item for item in report["stages"] if item["id"] == "storyboards")
            self.assertEqual(boards["status"], "complete")
            self.assertEqual(boards["required"], 1)
            self.assertEqual(boards["approved"], 1)

    def test_same_namespace_live_prefix_marks_running(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job_id = make_project(root, namespace="Ad2184_v3")
            prefix = "Ad2184_v3/generated/clips/scene_04/shot_04/frontal_run/candidate_01/5s"
            report = execution_status.collect_status(root, live={
                "running_prompt_ids": [],
                "pending_prompt_ids": [],
                "running_prefixes": [prefix],
                "pending_prefixes": [],
            })
            self.assertEqual(report["jobs"][0]["id"], job_id)
            self.assertEqual(report["jobs"][0]["state"], "running")
            clips = next(item for item in report["stages"] if item["id"] == "scripted_clips")
            self.assertEqual(clips["status"], "active")

    def test_output_present_stage_needs_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job_id = make_project(root)
            clip = root / "clip.mp4"
            clip.write_bytes(b"video")
            write_json(root / "build" / "execution" / "comfy_state.json", {
                "jobs": {job_id: {"status": "complete", "outputs": [str(clip)]}}
            })
            clips = next(
                item for item in execution_status.collect_status(root)["stages"]
                if item["id"] == "scripted_clips"
            )
            self.assertEqual(clips["status"], "needs_approval")

    def test_rough_cut_file_is_output_present_not_approved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            make_project(root)
            write_json(root / "build" / "generation_manifest.json", {
                "assembly": [{"order": 1, "scene_id": "scene_04", "shot_id": "shot_04", "formation_id": "frontal_run"}]
            })
            cut = root / "build" / "rough_cut" / "candidate_01_5s.mp4"
            cut.parent.mkdir(parents=True)
            cut.write_bytes(b"cut")
            report = execution_status.collect_status(root)
            assembly = next(item for item in report["jobs"] if item["stage"] == "final_assembly")
            self.assertEqual(assembly["state"], "output_present")
            stage = next(item for item in report["stages"] if item["id"] == "final_assembly")
            self.assertNotEqual(stage["status"], "complete")

    def test_episode_artifact_review_can_approve_rough_cut(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            make_project(root)
            write_json(root / "build" / "generation_manifest.json", {
                "assembly": [{"order": 1, "scene_id": "scene_04", "shot_id": "shot_04"}]
            })
            cut = root / "build" / "rough_cut" / "candidate_01_5s.mp4"
            cut.parent.mkdir(parents=True)
            cut.write_bytes(b"cut")
            write_json(root / "reviews" / "episode_artifact_review.json", {
                "artifact_id": "rough_cut__candidate_01_5s",
                "decision": "approved",
                "approved_by": "user",
                "issues": [],
            })
            report = execution_status.collect_status(root)
            assembly = next(item for item in report["jobs"] if item["stage"] == "final_assembly")
            self.assertEqual(assembly["state"], "approved")
            stage = next(item for item in report["stages"] if item["id"] == "final_assembly")
            self.assertEqual(stage["status"], "complete")

    def test_live_overlay_from_queue_reads_prefix_and_prompt_id(self):
        overlay = execution_status.live_overlay_from_queue({
            "queue_running": [[0, "prompt-1", {
                "24": {"class_type": "SaveVideo", "inputs": {
                    "filename_prefix": "Ad2184_v2/generated/clips/scene_05/shot_05/windup_orbit/candidate_01/5s"
                }}
            }]],
            "queue_pending": [],
        })
        self.assertEqual(overlay["running_prompt_ids"], ["prompt-1"])
        self.assertEqual(
            overlay["running_prefixes"],
            ["Ad2184_v2/generated/clips/scene_05/shot_05/windup_orbit/candidate_01/5s"],
        )


if __name__ == "__main__":
    unittest.main()
