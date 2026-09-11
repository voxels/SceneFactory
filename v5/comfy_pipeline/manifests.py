"""Manifest schemas and records for the Comfy pipeline.

Scene Factory owns manifests and approvals; ComfyUI executes generated API
graphs. These are the manifest shapes both sides share:

- shot manifest (from manifest_shots.json): the 138-shot cut plan
- take manifest: one record per accepted take
- review record: the ONLY thing that can mark a take approved
  (decision, approved_by: user, issues: []) — per docs/22.
"""

from __future__ import annotations

REQUIRED_MANIFEST_FIELDS = ("track", "track_sec", "format", "total_shots", "events")

REQUIRED_SHOT_FIELDS = (
    "shot", "start_sec", "duration_sec", "event", "support", "risk",
)

REQUIRED_TAKE_FIELDS = (
    "event", "shot", "start_sec", "duration_sec", "camera_sample_range",
    "lora_version", "skeleton_take", "gate_verdict", "review",
)

VALID_GATE_VERDICTS = ("HOLDS", "DRIFTS", "NO MATCH", "USER_CONFIRMED")


def validate_shot_manifest(manifest: dict) -> dict:
    """Validate the archived shot manifest structure.

    Returns a summary (event counts, shot counts, supported/novel split).
    Raises ValueError on structural problems.
    """
    if not isinstance(manifest, dict):
        raise ValueError("Shot manifest must be an object")
    missing = [f for f in REQUIRED_MANIFEST_FIELDS if f not in manifest]
    if missing:
        raise ValueError(f"Shot manifest missing: {', '.join(missing)}")
    events = manifest["events"]
    if not isinstance(events, dict) or not events:
        raise ValueError("Shot manifest has no events")
    total = 0
    supported = 0
    novel = 0
    seen_shots = set()
    per_event = {}
    for event_id, event in events.items():
        shots = event.get("shots")
        if not isinstance(shots, list) or not shots:
            raise ValueError(f"Event {event_id} has no shots")
        counts = {"shots": 0, "supported": 0, "novel": 0}
        for shot in shots:
            missing_s = [f for f in REQUIRED_SHOT_FIELDS if f not in shot]
            if missing_s:
                raise ValueError(
                    f"Event {event_id} shot missing: {', '.join(missing_s)}"
                )
            if shot["shot"] in seen_shots:
                raise ValueError(f"Duplicate shot index: {shot['shot']}")
            seen_shots.add(shot["shot"])
            counts["shots"] += 1
            total += 1
            if shot.get("support") == "SUPPORTED":
                counts["supported"] += 1
                supported += 1
            else:
                counts["novel"] += 1
                novel += 1
        per_event[event_id] = counts
    if total != manifest["total_shots"]:
        raise ValueError(
            f"Shot count mismatch: {total} shots vs total_shots={manifest['total_shots']}"
        )
    return {
        "track": manifest["track"],
        "track_sec": manifest["track_sec"],
        "total_shots": total,
        "supported": supported,
        "novel": novel,
        "events": per_event,
    }


def build_take_record(
    *,
    event: str,
    shot: int,
    start_sec: float,
    duration_sec: float,
    camera_sample_range: tuple[int, int],
    lora_version: str,
    gate_verdict: str,
    skeleton_take: str | None = None,
    refusal_history: list | None = None,
) -> dict:
    """Build one take manifest record.

    Rejected media is negative training data: a take that failed keeps its
    record (with the refusal history) instead of being deleted.
    """
    if gate_verdict not in VALID_GATE_VERDICTS:
        raise ValueError(f"Invalid gate verdict: {gate_verdict}")
    return {
        "event": event,
        "shot": shot,
        "start_sec": start_sec,
        "duration_sec": duration_sec,
        "camera_sample_range": list(camera_sample_range),
        "lora_version": lora_version,
        "skeleton_take": skeleton_take,  # null until skeleton takes land
        "gate_verdict": gate_verdict,
        "refusal_history": refusal_history or [],
        "review": None,  # filled by build_review_record on user decision
    }


def build_review_record(*, decision: str, approved_by: str, issues: list) -> dict:
    """Build the review record — the only authority that can mark approved.

    Per docs/22: a file on disk is not an approval. Only the operator may
    approve identity or production media.
    """
    if decision not in ("approved", "rejected"):
        raise ValueError(f"Review decision must be approved/rejected, got {decision}")
    return {
        "decision": decision,
        "approved_by": approved_by,
        "issues": list(issues),
    }


def is_approved(review: dict | None) -> bool:
    """True only for a user approval with zero issues."""
    return bool(
        review
        and review.get("decision") == "approved"
        and review.get("approved_by") == "user"
        and not review.get("issues")
    )
