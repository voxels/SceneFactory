"""Unit tests for comfy_pipeline — metadata layer only, no ComfyUI/GPU."""

import json
import os
import unittest
from pathlib import Path

from comfy_pipeline import graphs, manifests, identity_gate, redirection, edl

ROOT = Path(__file__).resolve().parents[2]

WORKFLOWS_DIR = Path(
    os.environ.get("CEZAR_WORKFLOWS_DIR", ROOT / "fixtures" / "workflows")
)
FACE_ID_V3 = Path(
    os.environ.get("CEZAR_FACE_ID_V3", ROOT / "fixtures" / "face_id")
)


def _load(name):
    return graphs.load_workflow(WORKFLOWS_DIR / name)


class GraphValidationTests(unittest.TestCase):
    def test_workflow_a_validates(self):
        g = _load("workflow_A_identity_proof.json")
        summary = graphs.validate_api_graph(g, workflow_id="A")
        self.assertTrue(summary["valid"])
        self.assertGreaterEqual(summary["nodes"], 9)

    def test_workflow_b_validates(self):
        g = _load("workflow_B_env_reference.json")
        summary = graphs.validate_api_graph(g, workflow_id="B")
        self.assertTrue(summary["valid"])

    def test_workflow_c_validates(self):
        g = _load("workflow_C_event_take_template.json")
        summary = graphs.validate_api_graph(g, workflow_id="C")
        self.assertTrue(summary["valid"])
        self.assertIn("LTXVConditioning", summary["class_types"])

    def test_dangling_link_rejected(self):
        g = _load("workflow_A_identity_proof.json")
        g["10"]["inputs"]["images"] = ["999", 0]  # point at a nonexistent node
        with self.assertRaises(ValueError):
            graphs.validate_api_graph(g, workflow_id="A")

    def test_event_take_instantiation_substitutes_all_tokens(self):
        template = _load("workflow_C_event_take_template.json")
        take = graphs.instantiate_event_take(
            template,
            event_token="event_04",
            event_folder="event_04_run_point",
            event_prompt="man running up the beach pointing",
            shot_frames=72,
            noise_seed=42,
        )
        dumped = json.dumps(take)
        for tok in graphs.C_TEMPLATE_TOKENS:
            self.assertNotIn(tok, dumped)
        self.assertIn("event_04", dumped)
        self.assertEqual(take["8"]["inputs"]["noise_seed"], 42)

    def test_unsubstituted_token_raises(self):
        template = _load("workflow_C_event_take_template.json")
        template["4"]["inputs"]["text"] = "EVENT_MYSTERY stays"
        with self.assertRaises(ValueError):
            graphs.instantiate_event_take(
                template,
                event_token="event_01",
                event_folder="event_01_handstand_env1",
                event_prompt="handstand",
                shot_frames=72,
                noise_seed=1,
            )

    def test_frames_for_duration_snaps_to_eight(self):
        self.assertEqual(graphs.frames_for_duration(3.0), 72)
        self.assertEqual(graphs.frames_for_duration(2.5) % 8, 0)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        with open(WORKFLOWS_DIR / "manifest_shots.json") as fh:
            self.manifest = json.load(fh)

    def test_real_manifest_validates_138_shots(self):
        summary = manifests.validate_shot_manifest(self.manifest)
        self.assertEqual(summary["total_shots"], 138)
        self.assertEqual(
            summary["supported"] + summary["novel"], 138
        )

    def test_duplicate_shot_rejected(self):
        bad = json.loads(json.dumps(self.manifest))
        dup = dict(bad["events"]["event_01"]["shots"][0])
        bad["events"]["event_02"]["shots"].append(dup)
        with self.assertRaises(ValueError):
            manifests.validate_shot_manifest(bad)

    def test_review_approval_rules(self):
        ok = manifests.build_review_record(
            decision="approved", approved_by="user", issues=[]
        )
        self.assertTrue(manifests.is_approved(ok))
        # Non-user approver is not an approval.
        self.assertFalse(
            manifests.is_approved(
                manifests.build_review_record(
                    decision="approved", approved_by="model", issues=[]
                )
            )
        )
        # Issues block approval.
        self.assertFalse(
            manifests.is_approved(
                manifests.build_review_record(
                    decision="approved", approved_by="user", issues=["face drift"]
                )
            )
        )
        # A file on disk is not an approval.
        self.assertFalse(manifests.is_approved(None))

    def test_take_record_requires_valid_verdict(self):
        with self.assertRaises(ValueError):
            manifests.build_take_record(
                event="event_01", shot=3, start_sec=12.0, duration_sec=3.0,
                camera_sample_range=(0, 71), lora_version="cezar-v1",
                gate_verdict="MAYBE",
            )


class IdentityGateTests(unittest.TestCase):
    def setUp(self):
        self.impression = identity_gate.load_impression(
            FACE_ID_V3 / "cezar_id_impression.npy",
            FACE_ID_V3 / "cezar_id_impression.json",
        )

    def test_impression_loads_with_provenance(self):
        self.assertEqual(self.impression["manifest"]["n_inliers"], 18)
        self.assertEqual(self.impression["manifest"]["method"][:12], "trimmed mean")

    def test_self_distance_holds(self):
        d = identity_gate.cosine_distance(
            self.impression["embedding"], self.impression["embedding"]
        )
        self.assertLess(d, 0.01)
        self.assertEqual(identity_gate.gate_band(d), "HOLDS")

    def test_gate_bands(self):
        self.assertEqual(identity_gate.gate_band(0.0), "HOLDS")
        self.assertEqual(identity_gate.gate_band(0.449), "HOLDS")
        self.assertEqual(identity_gate.gate_band(0.45), "DRIFTS")
        self.assertEqual(identity_gate.gate_band(0.649), "DRIFTS")
        self.assertEqual(identity_gate.gate_band(0.65), "NO MATCH")

    def test_prefilter_routes_and_user_overrules(self):
        import numpy as np

        anchor = self.impression["embedding"]
        far = anchor + np.random.RandomState(0).randn(*anchor.shape) * 5.0
        verdicts = identity_gate.prefilter(
            self.impression,
            [
                {"id": "self", "embedding": anchor, "user_confirmed": False},
                {"id": "far", "embedding": far, "user_confirmed": False},
                # His attribution overrules the model, no exceptions.
                {"id": "declared", "embedding": far, "user_confirmed": True},
            ],
        )
        by_id = {v["id"]: v for v in verdicts}
        self.assertEqual(by_id["self"]["route"], "proceeds_to_eye_gate")
        self.assertEqual(by_id["far"]["band"], "NO MATCH")
        self.assertEqual(by_id["far"]["route"], "rejected_before_review")
        self.assertEqual(by_id["declared"]["band"], "USER_CONFIRMED")


class RedirectionTests(unittest.TestCase):
    def _refusal(self, **kw):
        base = {
            "kind": "policy",
            "request": {
                "positive_prompt": "man holding handstand, invented gymnastics",
                "negative_prompt": "cartoon, watermark",
                "reference_image": "silhouette_still.png",
                "lora_strength": 0.85,
                "denoise": 0.85,
                "length_frames": 96,
            },
            "signal": "policy_denied / HTTP 403",
        }
        base.update(kw)
        return redirection.RefusalRecord(**base)

    def test_first_refusal_retries_with_prompt_rewrite(self):
        out = redirection.redirect(self._refusal(attempt=1))
        self.assertEqual(out["action"], "retry")
        self.assertNotIn("invented gymnastics", out["request"]["positive_prompt"])
        self.assertNotIn("cartoon", out["request"]["negative_prompt"])

    def test_second_refusal_adjusts_reference_and_lora(self):
        out = redirection.redirect(self._refusal(attempt=2))
        self.assertEqual(out["action"], "retry")
        self.assertIn("face_visible", out["request"]["reference_image"])
        self.assertLess(out["request"]["lora_strength"], 0.85)

    def test_third_refusal_drops_conditioning(self):
        out = redirection.redirect(self._refusal(attempt=3))
        self.assertEqual(out["action"], "retry")
        self.assertEqual(out["request"]["conditioning"], "depth_only")

    def test_exhaustion_escalates_with_debug_log_never_silence(self):
        out = redirection.redirect(self._refusal(attempt=4))
        self.assertEqual(out["action"], "escalate")
        log = out["debug_log"]
        self.assertIn("recommendation", log)
        self.assertGreaterEqual(log["attempts"], 3)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            redirection.RefusalRecord(kind="mystery", request={}, signal="x")

    def test_identity_gate_refusal_also_redirects(self):
        out = redirection.redirect(self._refusal(kind="identity_gate", attempt=1))
        self.assertEqual(out["action"], "retry")


class EdlTests(unittest.TestCase):
    def setUp(self):
        with open(WORKFLOWS_DIR / "manifest_shots.json") as fh:
            self.manifest = json.load(fh)

    def _approved_take(self, shot_idx, event):
        take = manifests.build_take_record(
            event=event, shot=shot_idx, start_sec=0.0, duration_sec=3.0,
            camera_sample_range=(0, 71), lora_version="cezar-v1",
            gate_verdict="HOLDS",
        )
        take["review"] = manifests.build_review_record(
            decision="approved", approved_by="user", issues=[]
        )
        return take

    def test_missing_takes_block_with_names(self):
        result = edl.build_edl(self.manifest, [])
        self.assertTrue(result["assembly_blocked"])
        self.assertEqual(len(result["blocked"]), 138)
        self.assertIn("shot", result["blocked"][0])
        self.assertIn("reason", result["blocked"][0])

    def test_unapproved_take_blocks(self):
        take = manifests.build_take_record(
            event="event_01", shot=3, start_sec=12.0, duration_sec=3.0,
            camera_sample_range=(0, 71), lora_version="cezar-v1",
            gate_verdict="DRIFTS",
        )
        result = edl.build_edl(self.manifest, [take])
        self.assertTrue(result["assembly_blocked"])
        entry = next(b for b in result["blocked"] if b["shot"] == 3)
        self.assertIn("not user-approved", entry["reason"])

    def test_approved_takes_produce_ordered_cuts(self):
        shots = self.manifest["events"]["event_01"]["shots"][:2]
        takes = [self._approved_take(s["shot"], s["event"]) for s in shots]
        result = edl.build_edl(self.manifest, takes)
        self.assertEqual(len(result["cuts"]), 2)
        self.assertEqual(
            [c["shot"] for c in result["cuts"]],
            sorted(c["shot"] for c in result["cuts"]),
        )
        self.assertEqual(result["cuts"][0]["scale"], "768x1344")


if __name__ == "__main__":
    unittest.main(verbosity=2)
