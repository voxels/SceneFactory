import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import reference_contracts


def task(task_id="vision_contract__shot_01__start", status="pending"):
    return {
        "id": task_id, "status": status, "shot_id": "shot_01", "sample": "start",
        "timestamp_seconds": 1.25, "frame_path": "build/reference/frames/frame.png",
        "frame_sha256": "abc123", "resource_tags": ["camera", "environment", "workers", "screen"],
        "contract_types": ["camera", "lighting", "blocking", "environment_design", "workers_design", "workers_group_motion", "screen_state"],
        "source_authority": "reference_video", "identity_exclusions": [],
    }


class ReferenceContractTests(unittest.TestCase):
    def make_root(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        frame = root / "build/reference/frames/frame.png"
        frame.parent.mkdir(parents=True)
        frame.write_bytes(b"png")
        reference_contracts.write_json(root / "build/reference/reference_manifest.json", {
            "vision_contract_tasks": [task()], "shot_ranges": [],
        })
        return temporary, root

    def test_execution_writes_field_level_provenance_and_classifies_claims(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        claims = [{"claim_id": "shot_01.action", "shot_id": "shot_01", "field": "action", "value": "workers march"}]

        def infer(_path, _prompt, schema):
            types = schema["properties"]["contracts"]["required"]
            return {
                "contracts": {name: {"visible_summary": f"observed {name}"} for name in types},
                "claim_findings": [{"claim_id": "shot_01.action", "status": "supported", "reason": "march visible"}],
            }

        result = reference_contracts.execute_tasks(
            root, infer, claims=claims, model_provenance={"model": "test-vision"}
        )
        self.assertEqual(result["completed"], 1)
        contract = reference_contracts.read_json(root / "build/reference/contracts/camera.json")
        observation = contract["fields"]["visible_summary"][0]
        self.assertEqual(observation["provenance"]["frame_sha256"], "abc123")
        self.assertEqual(observation["provenance"]["timestamp_seconds"], 1.25)
        saved_task = reference_contracts.read_json(root / "build/reference/reference_manifest.json")["vision_contract_tasks"][0]
        self.assertEqual(saved_task["status"], "complete")

    def test_contradiction_with_cited_evidence_blocks_generation(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        manifest_path = root / "build/reference/reference_manifest.json"
        manifest = reference_contracts.read_json(manifest_path)
        result_path = root / "build/reference/task_results/result.json"
        reference_contracts.write_json(result_path, {
            "contracts": {name: {"visible_summary": name} for name in task()["contract_types"]},
            "claim_findings": [{
                "claim_id": "shot_01.action", "status": "contradicted", "reason": "workers stand still",
                "evidence": {"task_id": task()["id"], "frame_sha256": "abc123", "timestamp_seconds": 1.25},
            }],
        })
        manifest["vision_contract_tasks"][0].update({
            "status": "complete", "result_path": str(result_path.relative_to(root)),
        })
        reference_contracts.write_json(manifest_path, manifest)
        reference_contracts.aggregate_contracts(root)
        project = {"props": []}
        scenes = [{"id": "scene_01", "shots": [{"id": "shot_01", "action": "workers march"}]}]
        report = reference_contracts.audit_disagreements(root, project, scenes)
        self.assertFalse(report["generation_gate"]["allowed"])
        self.assertEqual(len(report["unresolved_contradictions"]), 1)
        with self.assertRaisesRegex(ValueError, "contradictions"):
            reference_contracts.enforce_generation_gate(root)

    def test_incomplete_contract_types_block_generation(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        reference_contracts.aggregate_contracts(root)
        report = reference_contracts.audit_disagreements(root, {}, [])
        self.assertFalse(report["generation_gate"]["allowed"])
        self.assertIn("incomplete", " ".join(report["generation_gate"]["reasons"]))

    def test_runtime_invalidation_propagates_to_all_descendants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = reference_contracts.refresh_invalidation_state(root, [
                {"id": "source", "fingerprint": "a", "dependencies": []},
                {"id": "contract", "fingerprint": "b", "dependencies": ["source"]},
                {"id": "track", "fingerprint": "c", "dependencies": ["contract"]},
                {"id": "layer", "fingerprint": "d", "dependencies": ["track"]},
                {"id": "artifact", "fingerprint": "e", "dependencies": ["layer"]},
            ])
            self.assertEqual(set(first["invalidated"]), {"source", "contract", "track", "layer", "artifact"})
            unchanged = reference_contracts.refresh_invalidation_state(root, [
                {"id": "source", "fingerprint": "a", "dependencies": []},
                {"id": "contract", "fingerprint": "b", "dependencies": ["source"]},
                {"id": "track", "fingerprint": "c", "dependencies": ["contract"]},
                {"id": "layer", "fingerprint": "d", "dependencies": ["track"]},
                {"id": "artifact", "fingerprint": "e", "dependencies": ["layer"]},
            ])
            self.assertEqual(unchanged["invalidated"], [])
            changed = reference_contracts.refresh_invalidation_state(root, [
                {"id": "source", "fingerprint": "new", "dependencies": []},
                {"id": "contract", "fingerprint": "b", "dependencies": ["source"]},
                {"id": "track", "fingerprint": "c", "dependencies": ["contract"]},
                {"id": "layer", "fingerprint": "d", "dependencies": ["track"]},
                {"id": "artifact", "fingerprint": "e", "dependencies": ["layer"]},
            ])
            self.assertEqual(set(changed["invalidated"]), {"source", "contract", "track", "layer", "artifact"})

    def test_generation_gate_rejects_stale_contract_audit(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        manifest_path = root / "build/reference/reference_manifest.json"
        manifest = reference_contracts.read_json(manifest_path)
        result_path = root / "build/reference/task_results/result.json"
        reference_contracts.write_json(result_path, {
            "contracts": {name: {"visible_summary": name} for name in task()["contract_types"]},
            "claim_findings": [],
        })
        manifest["vision_contract_tasks"][0].update({"status": "complete", "result_path": str(result_path.relative_to(root))})
        reference_contracts.write_json(manifest_path, manifest)
        reference_contracts.aggregate_contracts(root)
        # This fixture lacks several production-required types, so use a comparator only to
        # establish and then exercise the freshness check before the allowed-state check.
        report = reference_contracts.audit_disagreements(root, {}, [])
        report["generation_gate"] = {"allowed": True, "reasons": []}
        reference_contracts.write_json(root / "build/reference/disagreement_report.json", report)
        contract = root / "build/reference/contracts/camera.json"
        contract.write_text(contract.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale"):
            reference_contracts.enforce_generation_gate(root)


if __name__ == "__main__":
    unittest.main()
