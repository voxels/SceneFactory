"""Workflow nodes A -> B -> C -> D.

Covers the archived workflows in ~/workspace/your_files/cezar-comfy-workflows/:
- A: workflow_A_identity_proof.json (identity proof, user-eye gate)
- B: workflow_B_env_reference.json (splat/trajectory/depth conditioning)
- C: workflow_C_event_take_template.json (per-event takes, token substitution)
- D: assemble_reel.sh (assembly handoff; EDL built here, ffmpeg runs on Mac)

No video is generated here. Nodes validate inputs, build parameter bundles,
and hand validated graphs/manifests to the Mac for execution.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .node_types import (
    SF_IDENTITY, SF_ENV, SF_TAKE, SF_EDL, SF_REFUSAL,
    HOLDS_MAX, DRIFTS_MAX, gate_band,
)

CATEGORY = "SceneFactory/Workflow"


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _frames_for_duration(duration_sec: float, fps: int = 24) -> int:
    raw = max(8, int(round(duration_sec * fps)))
    snapped = raw - (raw % 8)
    return snapped or 8


class SF_IdentityReferenceIntake:
    """A — reference still + v3 identity impression intake.

    Bundles the face-visible held-pose still with the impression contract
    (impression .npy + manifest .json). The embedding itself is compared on
    the metadata layer; the image tensor passes through to the Mac graph.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "impression_npy": ("STRING", {"default": ""}),
                "impression_json": ("STRING", {"default": ""}),
            },
            "optional": {
                "lora_name": ("STRING", {"default": "cezar-identity-lora.safetensors"}),
                "lora_strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.05}),
            },
        }

    RETURN_TYPES = (SF_IDENTITY,)
    RETURN_NAMES = ("identity_ref",)
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, image, impression_npy, impression_json,
              lora_name="cezar-identity-lora.safetensors", lora_strength=0.85):
        for label, p in (("impression_npy", impression_npy), ("impression_json", impression_json)):
            if not p or not os.path.isfile(p):
                raise ValueError(f"SF_IdentityReferenceIntake: {label} not found: {p!r}")
        manifest = _read_json(impression_json)
        return ({
            "kind": "identity_ref",
            "image": image,  # tensor passthrough; Mac graph consumes it
            "impression_npy": impression_npy,
            "impression_json": impression_json,
            "impression_inliers": manifest.get("n_inliers"),
            "lora_name": lora_name,
            "lora_strength": float(lora_strength),
            "holds_max": HOLDS_MAX,
            "drifts_max": DRIFTS_MAX,
        },)


class SF_IdentityGatePrefilter:
    """A — automated identity pre-filter over candidate frames.

    DIAGNOSTIC ONLY: NO MATCH candidates are rejected before they reach his
    eyes; DRIFTS are flagged for his attention; HOLDS proceed. It can NEVER
    approve — only a user review record approves. USER_CONFIRMED ids bypass
    the model entirely (user attribution overrules the model).

    candidate_distances: JSON list of {"id": str, "distance": float} or a path
    to such a JSON file. Distances are computed on the metadata layer against
    the v3 impression; this node routes them.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "identity_ref": (SF_IDENTITY,),
                "candidate_distances": ("STRING", {"multiline": True, "default": "[]"}),
            },
            "optional": {
                "user_confirmed_ids": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", SF_IDENTITY)
    RETURN_NAMES = ("verdicts_json", "annotated_ref")
    FUNCTION = "prefilter"
    CATEGORY = CATEGORY

    def prefilter(self, identity_ref, candidate_distances, user_confirmed_ids=""):
        raw = candidate_distances.strip()
        if os.path.isfile(raw):
            candidates = _read_json(raw)
        else:
            candidates = json.loads(raw or "[]")
        confirmed = {s.strip() for s in (user_confirmed_ids or "").split(",") if s.strip()}
        verdicts = []
        for cand in candidates:
            cid = cand.get("id", "?")
            if cid in confirmed:
                verdicts.append({"id": cid, "band": "USER_CONFIRMED",
                                 "distance": None, "route": "proceeds_to_eye_gate"})
                continue
            d = float(cand["distance"])
            band = gate_band(d)
            route = {"HOLDS": "proceeds_to_eye_gate",
                     "DRIFTS": "flagged_for_attention",
                     "NO MATCH": "rejected_before_review"}[band]
            verdicts.append({"id": cid, "band": band, "distance": d, "route": route})
        annotated = dict(identity_ref)
        annotated["prefilter_verdicts"] = verdicts
        return (json.dumps(verdicts, indent=2), annotated)


class SF_EnvironmentReference:
    """B — environment conditioning bundle (splat + trajectory).

    Validates the separated environment PLY and the camera trajectory JSON
    (from convert_trajectory.py). RenderSplat/DepthEstimatorNode run on the
    Mac; this node is the validated input contract for them.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ply_path": ("STRING", {"default": ""}),
                "trajectory_path": ("STRING", {"default": ""}),
            },
            "optional": {
                "width": ("INT", {"default": 768, "min": 64, "max": 4096}),
                "height": ("INT", {"default": 1344, "min": 64, "max": 4096}),
            },
        }

    RETURN_TYPES = (SF_ENV,)
    RETURN_NAMES = ("env_ref",)
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, ply_path, trajectory_path, width=768, height=1344):
        if not ply_path or not os.path.isfile(ply_path):
            raise ValueError(f"SF_EnvironmentReference: ply not found: {ply_path!r}")
        if not trajectory_path or not os.path.isfile(trajectory_path):
            raise ValueError(f"SF_EnvironmentReference: trajectory not found: {trajectory_path!r}")
        traj = _read_json(trajectory_path)
        frames = traj.get("frames") if isinstance(traj, dict) else None
        if not isinstance(frames, list) or not frames:
            raise ValueError("SF_EnvironmentReference: trajectory JSON has no 'frames' list")
        return ({
            "kind": "env_ref",
            "ply_path": ply_path,
            "trajectory_path": trajectory_path,
            "trajectory_frames": len(frames),
            "width": int(width),
            "height": int(height),
            "label": "PREVIZ",
        },)


class SF_EventTakeParams:
    """C — per-event take parameters from the shot manifest.

    Reads manifest_shots.json, resolves the shot (event, index), snaps the
    duration to an LTX-friendly frame count, and emits the EVENT_* token
    mapping plus per-take values. The sibling graph builder substitutes them
    into workflow_C_event_take_template.json; the Mac queues the result.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "env_ref": (SF_ENV,),
                "event_token": ("STRING", {"default": "event_01"}),
                "shot_index": ("INT", {"default": 0, "min": 0, "max": 10000}),
                "shot_manifest": ("STRING", {"default": ""}),
                "noise_seed": ("INT", {"default": 1, "min": 0, "max": 2**31 - 1}),
            },
            "optional": {
                "lora_version": ("STRING", {"default": "cezar-identity-lora.safetensors"}),
            },
        }

    RETURN_TYPES = (SF_TAKE,)
    RETURN_NAMES = ("take",)
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, env_ref, event_token, shot_index, shot_manifest,
              noise_seed, lora_version="cezar-identity-lora.safetensors"):
        if not shot_manifest or not os.path.isfile(shot_manifest):
            raise ValueError(f"SF_EventTakeParams: shot manifest not found: {shot_manifest!r}")
        manifest = _read_json(shot_manifest)
        events = manifest.get("events", {})
        if event_token not in events:
            raise ValueError(f"SF_EventTakeParams: unknown event {event_token!r}")
        shots = events[event_token].get("shots", [])
        shot = next((s for s in shots if s.get("shot") == shot_index), None)
        if shot is None:
            raise ValueError(
                f"SF_EventTakeParams: shot {shot_index} not in {event_token} "
                f"({len(shots)} shots)"
            )
        duration = float(shot["duration_sec"])
        return ({
            "kind": "take",
            "event": event_token,
            "shot": int(shot_index),
            "start_sec": float(shot["start_sec"]),
            "duration_sec": duration,
            "shot_frames": _frames_for_duration(duration),
            "camera_sample_range": shot.get("camera_sample_range"),
            "support": shot.get("support"),
            "risk": shot.get("risk"),
            "pov": shot.get("pov"),
            "noise_seed": int(noise_seed),
            "lora_version": lora_version,
            "skeleton_take": None,  # null until skeleton takes land
            "env_ref": {k: v for k, v in env_ref.items() if k != "kind"},
            "token_mapping": {
                "EVENT_TOKEN": event_token,
                "EVENT_FOLDER": f"teaser_kit/events/{event_token}/",
                "EVENT_PROMPT": events[event_token].get("prompt", ""),
                "SHOT_FRAMES": _frames_for_duration(duration),
            },
            "gate_verdict": None,   # filled by the pre-filter / review path
            "refusal_history": [],
            "review": None,         # filled only by SF_UserAttribution
        },)


class SF_AssemblyHandoff:
    """D — assembly EDL from accepted takes + shot manifest.

    A missing take for any shot is a hard, named failure — never a silent
    skip. Only takes whose review record is a clean user approval are
    eligible. The Mac runs assemble_reel.sh against this EDL.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "take_manifests": ("STRING", {"multiline": True, "default": "[]"}),
                "shot_manifest": ("STRING", {"default": ""}),
                "soundtrack_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = (SF_EDL, "STRING")
    RETURN_NAMES = ("edl", "edl_json")
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, take_manifests, shot_manifest, soundtrack_path):
        from .node_types import is_approved
        raw = take_manifests.strip()
        takes = _read_json(raw) if os.path.isfile(raw) else json.loads(raw or "[]")
        manifest = _read_json(shot_manifest)
        accepted = {}
        for t in takes:
            if is_approved(t.get("review")):
                accepted[(t.get("event"), t.get("shot"))] = t
        cuts = []
        missing = []
        for event_id, event in manifest.get("events", {}).items():
            for shot in event.get("shots", []):
                key = (event_id, shot.get("shot"))
                take = accepted.get(key)
                if take is None:
                    missing.append(f"{event_id}/shot_{shot.get('shot')}")
                    continue
                cuts.append({
                    "event": event_id,
                    "shot": shot.get("shot"),
                    "start_sec": shot.get("start_sec"),
                    "duration_sec": shot.get("duration_sec"),
                    "source_take": take.get("source_file"),
                    "lora_version": take.get("lora_version"),
                })
        if missing:
            raise ValueError(
                "SF_AssemblyHandoff: assembly BLOCKED — missing accepted takes for: "
                + ", ".join(missing)
            )
        edl = {
            "kind": "edl",
            "track": manifest.get("track"),
            "track_sec": manifest.get("track_sec"),
            "soundtrack_path": soundtrack_path,
            "output_scale": [768, 1344],
            "color_treatment": "none",
            "cuts": cuts,
        }
        return (edl, json.dumps(edl, indent=2))
