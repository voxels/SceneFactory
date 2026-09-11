"""Automated identity pre-filter wired to the v3 impression contract.

Contract (from the face_id work):
- impression .npy: trimmed-mean SFace embedding of 18 user-confirmed faces
- impression .json: method, n_inliers, inliers, outliers, dist_to_centroid
- gate bands: HOLDS d < 0.45, DRIFTS d < 0.65, NO MATCH d >= 0.65

The pre-filter is DIAGNOSTIC: it may reject (NO MATCH takes never reach his
eyes), it may flag (DRIFTS get his attention), it can NEVER approve. Only a
user review record marks a take approved. USER ATTRIBUTION OVERRULES THE
MODEL — a `user_confirmed` face is accepted regardless of distance.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HOLDS_MAX = 0.45
DRIFTS_MAX = 0.65


def load_impression(npy_path: str | Path, json_path: str | Path) -> dict:
    """Load the v3 impression contract (embedding + provenance manifest)."""
    import numpy as np

    embedding = np.load(str(npy_path))
    with open(json_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    if embedding.ndim != 1:
        raise ValueError(f"Impression embedding must be 1-D, got {embedding.shape}")
    if manifest.get("n_inliers", 0) < 1:
        raise ValueError("Impression manifest has no inliers")
    return {"embedding": embedding, "manifest": manifest}


def cosine_distance(a, b) -> float:
    """Cosine distance between two embedding vectors (0 = identical)."""
    try:
        import numpy as np

        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0:
            return 1.0
        return float(1.0 - np.dot(a, b) / denom)
    except ImportError:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0.0 or nb == 0.0:
            return 1.0
        return 1.0 - dot / (na * nb)


def gate_band(distance: float) -> str:
    """Map a cosine distance to a gate band."""
    if distance < HOLDS_MAX:
        return "HOLDS"
    if distance < DRIFTS_MAX:
        return "DRIFTS"
    return "NO MATCH"


def prefilter(
    impression: dict,
    candidates: list[dict],
) -> list[dict]:
    """Run the automated pre-filter over candidate face embeddings.

    Each candidate: {"id": str, "embedding": vector, "user_confirmed": bool}.
    Returns per-candidate verdicts: HOLDS / DRIFTS / NO MATCH, or
    USER_CONFIRMED when his attribution overrules the model.

    Verdicts route takes: NO MATCH -> rejected before his eyes; DRIFTS ->
    flagged for his attention; HOLDS -> proceeds to the user-eye gate.
    """
    anchor = impression["embedding"]
    verdicts = []
    for cand in candidates:
        cid = cand.get("id", "?")
        if cand.get("user_confirmed"):
            verdicts.append(
                {"id": cid, "band": "USER_CONFIRMED", "distance": None,
                 "route": "proceeds_to_eye_gate"}
            )
            continue
        d = cosine_distance(anchor, cand["embedding"])
        band = gate_band(d)
        route = {
            "HOLDS": "proceeds_to_eye_gate",
            "DRIFTS": "flagged_for_attention",
            "NO MATCH": "rejected_before_review",
        }[band]
        verdicts.append({"id": cid, "band": band, "distance": d, "route": route})
    return verdicts
