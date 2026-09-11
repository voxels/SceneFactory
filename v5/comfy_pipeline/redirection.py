"""Refusal-with-redirection loop — the 05:31 lesson as code.

On 2026-09-11 05:31 EDT a web-generation attempt died on `policy_denied` with
no retry and no debug. Standing rule from that moment: a refusal must come
with redirection — help debug rejected content into an acceptable request;
refusal without redirection is a failure.

This module implements the loop for Comfy pipeline generations:

1. Record the refusal (kind, request as sent, signal, attempt number).
2. Debug the content along an adjustment ladder into an acceptable request.
3. Retry, bounded at MAX_DEBUG_ATTEMPTS.
4. Never stall: exhaustion escalates to the user with the full debug log.

Rejected media stays as negative training data with its refusal record
attached — never deleted without his approval.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

MAX_DEBUG_ATTEMPTS = 3

REFUSAL_KINDS = ("policy", "identity_gate", "execution")

# Prompt terms known to degrade identity or invite policy friction, mapped to
# their replacements. Identity comes from the LoRA + reference, not words.
PROMPT_REWRITES = (
    ("invented gymnastics", "held pose"),
    ("oversaturated", "natural color"),
    ("cartoon", "photorealistic"),
    ("watermark", ""),
    ("blurry face", "sharp face"),
)


@dataclass
class RefusalRecord:
    """One refusal or gate failure, with its full context."""

    kind: str  # policy | identity_gate | execution
    request: dict  # the generation request as sent
    signal: str  # what the refusal said (verbatim when available)
    attempt: int = 1
    adjustments: list = field(default_factory=list)

    def __post_init__(self):
        if self.kind not in REFUSAL_KINDS:
            raise ValueError(f"Unknown refusal kind: {self.kind}")


def _debug_prompt(text: str, adjustments: list) -> str:
    out = text
    for bad, good in PROMPT_REWRITES:
        if bad in out:
            out = out.replace(bad, good).strip()
            adjustments.append(f"prompt: '{bad}' -> '{good}'")
    # Collapse accidental double spaces from removals.
    out = " ".join(out.split())
    return out


def _next_adjustment(request: dict, refusal: RefusalRecord) -> tuple[dict, str] | None:
    """One rung of the adjustment ladder. Returns (new_request, note) or None
    when the ladder is exhausted."""
    attempt = refusal.attempt
    new = copy.deepcopy(request)
    notes = refusal.adjustments

    if attempt == 1:
        new["positive_prompt"] = _debug_prompt(
            new.get("positive_prompt", ""), notes
        )
        new["negative_prompt"] = _debug_prompt(
            new.get("negative_prompt", ""), notes
        )
        notes.append("ladder r1: prompt rewrite (flagged terms)")
        return new, notes[-1]
    if attempt == 2:
        # Swap to a face-visible reference still; sunset silhouettes fail identity.
        if new.get("reference_image"):
            new["reference_image"] = new["reference_image"].replace(
                "silhouette", "face_visible"
            )
            notes.append("ladder r2: reference still -> face-visible variant")
        # Lower LoRA strength if the face drifts; the gate failed, so weaken it.
        if "lora_strength" in new:
            new["lora_strength"] = max(0.5, round(new["lora_strength"] - 0.15, 2))
            notes.append(f"ladder r2: lora_strength -> {new['lora_strength']}")
        return new, "; ".join(notes[-2:])
    if attempt == 3:
        # Drop optional conditioning, keep depth-only; shorten the take.
        new["conditioning"] = "depth_only"
        notes.append("ladder r3: conditioning -> depth_only")
        if "denoise" in new:
            new["denoise"] = min(1.0, round(new["denoise"] - 0.1, 2))
            notes.append(f"ladder r3: denoise -> {new['denoise']}")
        if "length_frames" in new:
            new["length_frames"] = max(48, new["length_frames"] // 2)
            notes.append(f"ladder r3: length_frames -> {new['length_frames']}")
        return new, "; ".join(notes[-3:])
    return None


def redirect(refusal: RefusalRecord) -> dict:
    """Apply one redirection step.

    Returns:
      {"action": "retry", "request": {...}, "attempt": n, "adjustments": [...]}
      or
      {"action": "escalate", "debug_log": {...}}

    Escalation is the terminal state: the full debug log plus a recommended
    manual move, handed to him. It is never silence.
    """
    if refusal.attempt > MAX_DEBUG_ATTEMPTS:
        return {
            "action": "escalate",
            "debug_log": {
                "kind": refusal.kind,
                "signal": refusal.signal,
                "attempts": refusal.attempt - 1,
                "adjustments": list(refusal.adjustments),
                "final_request": refusal.request,
                "recommendation": (
                    "Ladder exhausted. Manual review: check the reference still "
                    "for face visibility, consider a new held-pose capture, or "
                    "rebalance the cut plan toward SUPPORTED shots."
                ),
            },
        }
    step = _next_adjustment(refusal.request, refusal)
    if step is None:
        return redirect(
            RefusalRecord(
                kind=refusal.kind,
                request=refusal.request,
                signal=refusal.signal,
                attempt=MAX_DEBUG_ATTEMPTS + 1,
                adjustments=refusal.adjustments,
            )
        )
    new_request, _note = step
    return {
        "action": "retry",
        "request": new_request,
        "attempt": refusal.attempt + 1,
        "adjustments": list(refusal.adjustments),
    }
