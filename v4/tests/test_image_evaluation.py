import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import image_evaluation
import comfy_executor


class ImageEvaluationTests(unittest.TestCase):
    def test_plan_inputs_reject_changed_candidate_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            adapter = project / "adapter.safetensors"
            adapter.parent.mkdir(parents=True)
            adapter.write_bytes(b"new-adapter")
            with self.assertRaisesRegex(image_evaluation.ImageEvaluationError, "candidate adapter changed"):
                image_evaluation._assert_plan_inputs_current(project, {
                    "candidates": [{"adapter_path": str(adapter), "adapter_sha256": "0" * 64}],
                })

    def test_plan_drift_does_not_mix_old_resumable_report_with_current_graph(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            run_root = project / "build/training/image_identity/heldout_runs/current"
            run_root.mkdir(parents=True)
            (run_root / "evaluation_report.json").write_text(json.dumps({
                "status": "running", "plan_sha256": "old-plan",
            }))
            plan = {"plan_sha256": "new-plan"}
            with self.assertRaisesRegex(image_evaluation.ImageEvaluationError, "differs from current plan"):
                image_evaluation._evaluate_impl(project, _plan=plan, _run_root=run_root)

    def test_candidate_summary_reports_runtime_when_execution_records_it(self):
        summary = image_evaluation._candidate_summary([
            {"identity_feature_print_median_distance": 0.4,
             "face_detected": True, "person_mask_detected": True,
             "sha256": "a", "runtime_seconds": 2.0},
            {"identity_feature_print_median_distance": 0.5,
             "face_detected": True, "person_mask_detected": True,
             "sha256": "b", "runtime_seconds": 4.0},
        ])
        self.assertEqual(summary["runtime_seconds_median"], 3.0)

    def test_candidate_summary_uses_true_identity_distance_median(self):
        summary = image_evaluation._candidate_summary([
            {"identity_feature_print_median_distance": 0.1, "face_detected": True,
             "person_mask_detected": True, "sha256": "a"},
            {"identity_feature_print_median_distance": 0.4, "face_detected": True,
             "person_mask_detected": True, "sha256": "b"},
            {"identity_feature_print_median_distance": 0.9, "face_detected": True,
             "person_mask_detected": True, "sha256": "c"},
        ])
        self.assertEqual(summary["identity_feature_print_median_distance"], 0.4)

    def test_real_example_plan_is_fixed_group_safe_and_covers_every_adapter(self):
        project = Path(__file__).parents[1] / "examples/modeling_interview"
        plan = image_evaluation.build_plan(project)
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(len(plan["cases"]), 8)
        self.assertEqual(len({case["case_id"] for case in plan["cases"]}), 8)
        self.assertEqual(len(plan["candidates"]), 4)
        self.assertIn("baseline", {item["experiment"] for item in plan["candidates"]})
        self.assertEqual(sum(len(item["route_names"]) for item in plan["candidates"]), 9)
        baseline = next(item for item in plan["candidates"] if item["experiment"] == "baseline")
        self.assertEqual(baseline["route_names"], ["base", "native_reference", "pulid"])
        self.assertTrue(all(item["adapter_sha256"] for item in plan["candidates"] if item["promotable"]))
        groups = {item["group_id"] for item in plan["heldout"]}
        self.assertEqual(len(groups), len(plan["heldout"]))
        self.assertEqual(plan["contract"]["expected_outputs"], len(plan["cases"]))
        self.assertIn("prompt_alignment", plan["contract"]["unsupported_without_additional_model"])

    def test_promotion_contract_fails_closed_without_real_metrics(self):
        plan = {"contract": {"expected_outputs": 2, "promotion": {
            "minimum_face_detection_rate": 0.8,
            "maximum_identity_feature_print_median_distance": 0.75,
        }}}
        summary = {
            "case_count": 2, "identity_scored_cases": 0,
            "identity_feature_print_median_distance": None,
            "face_detection_rate": 0.0, "all_output_hashes_present": False,
        }
        blockers = image_evaluation._promotion_eligibility(summary, plan)
        self.assertGreaterEqual(len(blockers), 3)
        self.assertIn("one or more outputs has no usable identity feature print", blockers)

    def test_output_fetch_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(image_evaluation.ImageEvaluationError, "unsafe output filename"):
                image_evaluation._fetch_output(
                    "http://127.0.0.1:1",
                    {"filename": "../escape.png", "subfolder": "", "type": "output"},
                    Path(temporary) / "out.png",
                )
            with self.assertRaisesRegex(image_evaluation.ImageEvaluationError, "unsafe output filename"):
                image_evaluation._fetch_output(
                    "http://127.0.0.1:1",
                    {"filename": "safe.png", "subfolder": "../escape", "type": "output"},
                    Path(temporary) / "out.png",
                )

    def test_evaluator_run_lock_rejects_duplicate_matrix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            first = image_evaluation._acquire_run_lock(root)
            try:
                with self.assertRaisesRegex(image_evaluation.ImageEvaluationError, "already running"):
                    image_evaluation._acquire_run_lock(root)
            finally:
                image_evaluation._release_run_lock(first)
            second = image_evaluation._acquire_run_lock(root)
            image_evaluation._release_run_lock(second)

    def test_evaluator_project_lock_spans_plan_hash_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            first = image_evaluation._acquire_project_lock(project)
            try:
                with self.assertRaisesRegex(image_evaluation.ImageEvaluationError, "already running for this project"):
                    image_evaluation._acquire_project_lock(project)
            finally:
                image_evaluation._release_run_lock(first)
            second = image_evaluation._acquire_project_lock(project)
            image_evaluation._release_run_lock(second)

    def test_blocked_report_resumes_completed_cases(self):
        plan = {
            "schema_version": 1,
            "plan_sha256": "b" * 64,
            "identity_id": "test",
            "cases": [{"case_id": "case", "prompt": "p", "negative_prompt": "n", "seed": 1}],
            "candidates": [{"experiment": "baseline", "adapter_sha256": None,
                            "promotable": False, "route_names": ["base", "native_reference"]}],
            "contract": {"expected_outputs": 1, "promotion": {
                "minimum_face_detection_rate": 0.8,
                "maximum_identity_feature_print_median_distance": 0.75,
            }},
        }
        calls = []

        def execute(*args, **kwargs):
            route = args[1]
            calls.append(route)
            if route == "native_reference" and calls.count(route) == 1:
                raise comfy_executor.ComfyExecutionError("simulated backend interruption")
            return {"outputs": [{"filename": "case.png", "subfolder": "", "type": "output"}]}

        def fetch(_server, _output, destination):
            return {"path": str(destination), "sha256": "c" * 64, "bytes": 32}

        def score(_project, _plan, _records, run_root):
            distance = 0.8 if run_root.name == "base" else 0.7
            return [{"case_id": "case", "seed": 1,
                     "identity_feature_print_median_distance": distance,
                     "face_detected": True, "person_mask_detected": True,
                     "sha256": "c" * 64}]

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            with patch.object(image_evaluation, "build_plan", return_value=plan), \
                 patch.object(comfy_executor, "execute", side_effect=execute), \
                 patch.object(image_evaluation, "_fetch_output", side_effect=fetch), \
                 patch.object(image_evaluation, "_score_outputs", side_effect=score):
                with self.assertRaisesRegex(image_evaluation.ImageEvaluationError, "simulated backend interruption"):
                    image_evaluation.evaluate(project)
                report_path = project / "build/training/image_identity/heldout_runs" / ("b" * 16) / "evaluation_report.json"
                first = json.loads(report_path.read_text())
                self.assertEqual(first["status"], "blocked")
                self.assertEqual(len(first["candidates"][0]["routes"][0]["cases"]), 1)
                self.assertEqual(first["candidates"][0]["routes"][1]["active_case"]["case_id"], "case")
                with self.assertRaisesRegex(image_evaluation.ImageEvaluationError, "no candidate improved"):
                    image_evaluation.evaluate(project)
            self.assertEqual(calls, ["base", "native_reference", "native_reference"])
            second = json.loads(report_path.read_text())
            self.assertEqual(second["resume_count"], 1)
            self.assertNotIn("active_case", second["candidates"][0]["routes"][1])


if __name__ == "__main__":
    unittest.main()
