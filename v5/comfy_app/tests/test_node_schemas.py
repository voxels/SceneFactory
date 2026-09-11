"""Mock harness: validate every node's ComfyUI interface without ComfyUI.

No torch, no numpy, no GPU. Each node module is pure Python at import time
(lazy imports inside methods only). The harness:
  1. imports the pack's __init__ (fails loudly if mappings are broken),
  2. instantiates every registered node class,
  3. validates INPUT_TYPES / RETURN_TYPES / RETURN_NAMES / FUNCTION /
     CATEGORY schema consistency,
  4. asserts OUTPUT_NODE only on side-effect nodes,
  5. runs pure-Python unit checks: gate bands, pre-filter routing,
     user-attribution override, refusal ladder bounds, EDL missing-take
     failure, WAV validation on a synthetic file, voice graph structure.

Run: python3 tests/test_node_schemas.py
Exit 0 = all green.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import wave

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PACK))  # import as v5.comfy_app
sys.path.insert(0, PACK)

failures = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def main():
    import comfy_app
    from comfy_app import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

    check("mappings non-empty", bool(NODE_CLASS_MAPPINGS))
    check("display names cover mappings",
          set(NODE_DISPLAY_NAME_MAPPINGS) == set(NODE_CLASS_MAPPINGS))
    check("web dir exists", os.path.isdir(os.path.join(PACK, "web", "js")))
    check("review js present",
          os.path.isfile(os.path.join(PACK, "web", "js", "scenefactory_review.js")))

    side_effect_nodes = {"SF_UserAttribution", "SF_TakeManifestWriter"}

    for key, cls in NODE_CLASS_MAPPINGS.items():
        inst = cls()  # must construct with no args
        types = cls.INPUT_TYPES()
        check(f"{key}: INPUT_TYPES has required",
              isinstance(types, dict) and "required" in types)
        rt, rn = cls.RETURN_TYPES, cls.RETURN_NAMES
        check(f"{key}: RETURN_TYPES/RETURN_NAMES same length",
              isinstance(rt, tuple) and isinstance(rn, tuple) and len(rt) == len(rn),
              f"{rt} vs {rn}")
        check(f"{key}: FUNCTION exists", hasattr(inst, cls.FUNCTION))
        check(f"{key}: CATEGORY set",
              isinstance(cls.CATEGORY, str) and cls.CATEGORY.startswith("SceneFactory/"))
        is_output = bool(getattr(cls, "OUTPUT_NODE", False))
        check(f"{key}: OUTPUT_NODE only on side-effect nodes",
              is_output == (key in side_effect_nodes), f"OUTPUT_NODE={is_output}")

    # --- pure-Python unit checks -----------------------------------------
    from comfy_app.node_types import gate_band, is_approved, build_review_record

    check("gate HOLDS", gate_band(0.3) == "HOLDS")
    check("gate DRIFTS", gate_band(0.5) == "DRIFTS")
    check("gate NO MATCH", gate_band(0.8) == "NO MATCH")
    check("gate boundary 0.45", gate_band(0.45) == "DRIFTS")
    check("gate boundary 0.65", gate_band(0.65) == "NO MATCH")
    check("is_approved clean", is_approved(
        {"decision": "approved", "approved_by": "user", "issues": []}))
    check("is_approved rejects issues", not is_approved(
        {"decision": "approved", "approved_by": "user", "issues": ["x"]}))
    check("is_approved rejects non-user", not is_approved(
        {"decision": "approved", "approved_by": "model", "issues": []}))
    try:
        build_review_record("maybe", "user", [])
        check("review record rejects bad decision", False)
    except ValueError:
        check("review record rejects bad decision", True)

    # Pre-filter routing incl. user-confirmed override.
    from comfy_app.nodes_workflow import SF_IdentityGatePrefilter
    with tempfile.TemporaryDirectory() as td:
        npy = os.path.join(td, "imp.npy")
        js = os.path.join(td, "imp.json")
        open(npy, "wb").write(b"\x93NUMPY")
        json.dump({"n_inliers": 18}, open(js, "w"))
        from comfy_app.nodes_workflow import SF_IdentityReferenceIntake
        (ref,) = SF_IdentityReferenceIntake().build(
            image=None, impression_npy=npy, impression_json=js)
        check("intake keeps impression contract",
              ref["impression_inliers"] == 18 and ref["holds_max"] == 0.45)
        cands = json.dumps([
            {"id": "a", "distance": 0.3},
            {"id": "b", "distance": 0.5},
            {"id": "c", "distance": 0.9},
            {"id": "d", "distance": 0.9},
        ])
        verdicts_json, annotated = SF_IdentityGatePrefilter().prefilter(
            ref, cands, user_confirmed_ids="d")
        v = {x["id"]: x for x in json.loads(verdicts_json)}
        check("prefilter HOLDS routes to eye gate",
              v["a"]["band"] == "HOLDS" and v["a"]["route"] == "proceeds_to_eye_gate")
        check("prefilter DRIFTS flagged",
              v["b"]["band"] == "DRIFTS" and v["b"]["route"] == "flagged_for_attention")
        check("prefilter NO MATCH rejected before review",
              v["c"]["band"] == "NO MATCH" and v["c"]["route"] == "rejected_before_review")
        check("user attribution overrules model",
              v["d"]["band"] == "USER_CONFIRMED" and v["d"]["distance"] is None)

    # User attribution write path incl. forced approval.
    from comfy_app.nodes_review import SF_UserAttribution
    with tempfile.TemporaryDirectory() as td:
        (rec,) = SF_UserAttribution().attribute(
            "rejected", "blurry", td,
            candidate={"kind": "candidate_browser", "count": 1},
            gate_band_display="NO MATCH", user_confirmed=True,
            subject_id="t1")
        check("user_confirmed forces approval",
              rec["decision"] == "approved" and rec["approved_by"] == "user"
              and rec["issues"] == [] and rec["user_confirmed"] is True)
        check("review JSON written",
              os.path.isfile(os.path.join(td, "review_t1.json")))
        (rec2,) = SF_UserAttribution().attribute(
            "rejected", "blurry", td,
            candidate={"kind": "candidate_browser"}, subject_id="t2")
        check("plain rejection keeps issues",
              rec2["decision"] == "rejected" and rec2["issues"] == ["blurry"])
        try:
            SF_UserAttribution().attribute(
                "approved", "", td,
                candidate={"kind": "x"}, take={"kind": "y"})
            check("attribution requires exactly one subject", False)
        except ValueError:
            check("attribution requires exactly one subject", True)

    # Refusal ladder: bounded, then escalates — never stalls.
    from comfy_app.nodes_review import SF_RefusalRedirect, MAX_DEBUG_ATTEMPTS
    take0 = {"kind": "take", "event": "event_01", "shot": 3,
             "duration_sec": 4.0, "refusal_history": []}
    (t1, r1) = SF_RefusalRedirect().redirect(
        take0, "policy", "403", 1, lora_strength=0.85, denoise=0.85)
    check("refusal attempt 1 adjusts", r1["escalated"] is False
          and len(t1["refusal_history"]) == 1)
    (t4, r4) = SF_RefusalRedirect().redirect(
        take0, "identity_gate", "NO MATCH", MAX_DEBUG_ATTEMPTS + 1)
    check("refusal ladder exhausts into escalation",
          r4["escalated"] is True and t4["status"] == "escalated_to_operator")
    check("refusal history preserved", len(t4["refusal_history"]) == 1)

    # EDL: missing take is a hard named failure.
    from comfy_app.nodes_workflow import SF_AssemblyHandoff
    manifest = {"track": "t", "track_sec": 424.0, "events": {
        "event_01": {"shots": [{"shot": 0, "start_sec": 0.0, "duration_sec": 4.0}]}}}
    with tempfile.TemporaryDirectory() as td:
        mp = os.path.join(td, "shots.json")
        json.dump(manifest, open(mp, "w"))
        try:
            SF_AssemblyHandoff().build("[]", mp, "/tmp/sound.m4a")
            check("EDL names missing takes", False)
        except ValueError as exc:
            check("EDL names missing takes", "event_01/shot_0" in str(exc))
        good_take = json.dumps([{
            "event": "event_01", "shot": 0, "source_file": "take0.mp4",
            "lora_version": "cezar.safetensors",
            "review": {"decision": "approved", "approved_by": "user", "issues": []}}])
        edl, edl_json = SF_AssemblyHandoff().build(good_take, mp, "/tmp/sound.m4a")
        check("EDL builds on clean approvals",
              len(edl["cuts"]) == 1 and edl["color_treatment"] == "none")

    # Voice: WAV validation on a synthetic 10 s mono file.
    from comfy_app.nodes_voice import SF_VoiceReferenceProfile, VOICE_PROFILES
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "ref.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x00\x00" * 22050 * 10)
        (prof,) = SF_VoiceReferenceProfile().build(
            "max_data", wav, "exact transcript here")
        check("voice profile validates 10 s mono",
              prof["validation"]["valid"] is True)
        check("voice profile settings not mixed",
              VOICE_PROFILES["max_data"]["temperature"] == 0.72
              and VOICE_PROFILES["short_clean"]["temperature"] == 0.78)
        (graph_json, record) = __import__(
            "comfy_app.nodes_voice", fromlist=["SF_VoiceParagraphRender"]
        ).SF_VoiceParagraphRender().build(prof, "Hello world.", 1, "vp", seed=43)
        g = json.loads(graph_json)
        check("voice graph has TTS node chain",
              g["4"]["class_type"] == "Qwen3TTSEngineNode"
              and g["5"]["inputs"]["seed"] == 43)

    # Take manifest writer: rejects bad verdicts, keeps negatives.
    from comfy_app.nodes_manifest import SF_TakeManifestWriter
    with tempfile.TemporaryDirectory() as td:
        take = {"kind": "take", "event": "event_02", "shot": 5,
                "start_sec": 10.0, "duration_sec": 4.0,
                "lora_version": "cezar.safetensors", "gate_verdict": "DRIFTS"}
        review = {"decision": "rejected", "approved_by": "user", "issues": ["drift"]}
        (mt,) = SF_TakeManifestWriter().write(take, review, td)
        check("rejected take kept as negative data",
              mt["approved_for_assembly"] is False
              and os.path.isfile(os.path.join(td, "take_event_02_shot_5.json")))
        bad = dict(take, gate_verdict="MAYBE")
        try:
            SF_TakeManifestWriter().write(bad, review, td)
            check("manifest writer rejects bad verdict", False)
        except ValueError:
            check("manifest writer rejects bad verdict", True)

    print()
    if failures:
        print(f"{len(failures)} FAILURES: {failures}")
        sys.exit(1)
    print("ALL GREEN")


if __name__ == "__main__":
    main()
