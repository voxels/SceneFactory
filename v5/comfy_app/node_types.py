"""Shared custom types, gate constants, and defensive sibling imports.

Custom ComfyUI types here are in-process Python dicts with a "kind" field.
They are NOT tensors and do NOT serialize inside API-format graphs; when a
graph is exported, bundles travel as JSON sidecars (see README).

Interface assumptions for the spec crew (sibling comfy_pipeline package):
- A1: HOLDS_MAX / DRIFTS_MAX duplicate sibling identity_gate.py (canonical).
- A2: take/review record shapes mirror sibling manifests.py.
- A3: the refusal-record shape is defined here (sibling redirection.py does
  not exist yet) per DESIGN_SPEC_COMFY_PIPELINE.md section 5.
- A4: the SF_VOICE profile bundle shape is defined here; the spec crew
  should adopt it for any voice conditioning in graphs.
"""

from __future__ import annotations

# ComfyUI custom socket types (arbitrary type strings; dicts in-process).
SF_IDENTITY = "SF_IDENTITY"
SF_ENV = "SF_ENV"
SF_TAKE = "SF_TAKE"
SF_VOICE = "SF_VOICE"
SF_CANDIDATE = "SF_CANDIDATE"
SF_REVIEW = "SF_REVIEW"
SF_MANIFEST = "SF_MANIFEST"
SF_EDL = "SF_EDL"
SF_REFUSAL = "SF_REFUSAL"

# Gate bands — canonical source is sibling comfy_pipeline/identity_gate.py.
HOLDS_MAX = 0.45
DRIFTS_MAX = 0.65

INTERFACE_ID = "scene_factory.comfyui_api_workflow"
INTERFACE_VERSION = "v1"

# --- Defensive sibling imports -------------------------------------------
# Prefer the sibling package when it exists; fall back to local pure-Python
# implementations so this pack loads standalone on the Mac.

try:  # sibling canonical gate
    from comfy_pipeline.identity_gate import (  # type: ignore
        gate_band as _sibling_gate_band,
        prefilter as _sibling_prefilter,
    )
    _HAS_SIBLING_GATE = True
except Exception:
    _HAS_SIBLING_GATE = False
    _sibling_gate_band = None
    _sibling_prefilter = None


def gate_band(distance: float) -> str:
    """HOLDS / DRIFTS / NO MATCH for a cosine distance. Diagnostic only."""
    if _HAS_SIBLING_GATE:
        return _sibling_gate_band(distance)
    if distance < HOLDS_MAX:
        return "HOLDS"
    if distance < DRIFTS_MAX:
        return "DRIFTS"
    return "NO MATCH"


def is_approved(review: dict | None) -> bool:
    """True only for a user approval with zero issues.

    A file on disk is not an approval. Only the operator may approve
    identity or production media (docs/22).
    """
    return bool(
        review
        and review.get("decision") == "approved"
        and review.get("approved_by") == "user"
        and not review.get("issues")
    )


def build_review_record(decision: str, approved_by: str, issues: list) -> dict:
    """The review record — the only authority that can mark approved."""
    if decision not in ("approved", "rejected"):
        raise ValueError(f"decision must be approved/rejected, got {decision!r}")
    return {
        "decision": decision,
        "approved_by": approved_by,
        "issues": list(issues),
    }
