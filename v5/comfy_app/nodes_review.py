"""Review nodes — the cross-media reference fine-tuning surface.

This is the UI the user directed at 16:02: "a ui for folliw up review to
fine tune references across media types maybe just as an app in comfy",
with the automated identity pre-filter screening and his eyes giving final
approval.

Rules:
- Gate bands are shown as DIAGNOSTIC ONLY. The model never approves and
  never overrules him.
- SF_UserAttribution is the write path: approve / reject / write
  attribution. user_confirmed=True forces approval regardless of the gate
  band — USER ATTRIBUTION OVERRULES THE MODEL, no exceptions.
- SF_RefusalRedirect implements the refusal-with-redirection loop
  (DESIGN_SPEC_COMFY_PIPELINE.md section 5): a refusal debugs the request
  into an acceptable one and retries, bounded; exhaustion escalates with
  the full debug log. Silence is not an option.
"""

from __future__ import annotations

import json
import os

from .node_types import (
    SF_CANDIDATE, SF_TAKE, SF_VOICE, SF_REVIEW, SF_REFUSAL,
    gate_band, build_review_record,
)

CATEGORY = "SceneFactory/Review"

MAX_DEBUG_ATTEMPTS = 3

# Adjustment ladder, in order (spec section 5). Each entry: (name, action).
ADJUSTMENT_LADDER = (
    ("rephrase_prompt",
     "Strip or rephrase flagged prompt terms; keep 'same man as reference' phrasing."),
    ("swap_reference",
     "Swap to a face-visible held-pose still; sunset silhouettes fail identity."),
    ("lower_lora",
     "Lower LoRA strength (0.85 -> 0.7) if the face drifts; raise if identity is weak."),
    ("reduce_denoise",
     "Reduce denoise below 1.0 to preserve reference structure."),
    ("drop_conditioning",
     "Drop optional conditioning (pose/canny); retry depth-only."),
    ("split_shot",
     "Split the shot: shorter take, reframe the camera move."),
)


class SF_ReviewCandidateBrowser:
    """Cross-media reference candidate browser.

    Takes a JSON list of candidate records
    [{"id", "media": "image|audio|text", "path", "distance" (optional),
      "note"}] or a path to such a file. Attaches the gate band as a
    diagnostic label. The sidecar web UI renders previews per media type;
    approval happens only in SF_UserAttribution.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "candidates": ("STRING", {"multiline": True, "default": "[]"}),
            },
            "optional": {
                "media_filter": (["any", "image", "audio", "text"],),
            },
        }

    RETURN_TYPES = (SF_CANDIDATE,)
    RETURN_NAMES = ("candidate",)
    FUNCTION = "browse"
    CATEGORY = CATEGORY

    def browse(self, candidates, media_filter="any"):
        raw = candidates.strip()
        if os.path.isfile(raw):
            with open(raw, "r", encoding="utf-8") as fh:
                items = json.load(fh)
        else:
            items = json.loads(raw or "[]")
        if media_filter != "any":
            items = [c for c in items if c.get("media") == media_filter]
        enriched = []
        for c in items:
            c = dict(c)
            d = c.get("distance")
            c["gate_band"] = gate_band(float(d)) if d is not None else "UNMEASURED"
            c["gate_note"] = "diagnostic only — the model never approves"
            enriched.append(c)
        return ({
            "kind": "candidate_browser",
            "media_filter": media_filter,
            "candidates": enriched,
            "count": len(enriched),
        },)


class SF_UserAttribution:
    """THE write path for approvals. OUTPUT_NODE.

    Exactly one of candidate / take / voice_render must be connected.
    decision + issues come from the review UI (his eyes). The gate band is
    accepted as a diagnostic display string only — it cannot change the
    decision.

    user_confirmed=True forces decision=approved with approved_by=user,
    regardless of gate band or issues: USER ATTRIBUTION OVERRULES THE MODEL.

    Writes the review JSON to manifest_dir (Scene Factory owns approvals).
    """

    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "decision": (["approved", "rejected"],),
                "issues": ("STRING", {"multiline": True, "default": ""}),
                "manifest_dir": ("STRING", {"default": ""}),
            },
            "optional": {
                "candidate": (SF_CANDIDATE,),
                "take": (SF_TAKE,),
                "voice_render": (SF_VOICE,),
                "gate_band_display": ("STRING", {"default": ""}),
                "user_confirmed": ("BOOLEAN", {"default": False}),
                "subject_id": ("STRING", {"default": "review"}),
            },
        }

    RETURN_TYPES = (SF_REVIEW,)
    RETURN_NAMES = ("review",)
    FUNCTION = "attribute"
    CATEGORY = CATEGORY

    def attribute(self, decision, issues, manifest_dir, candidate=None,
                  take=None, voice_render=None, gate_band_display="",
                  user_confirmed=False, subject_id="review"):
        subjects = [s for s in (candidate, take, voice_render) if s is not None]
        if len(subjects) != 1:
            raise ValueError(
                "SF_UserAttribution: connect exactly one of candidate / take / voice_render"
            )
        subject = subjects[0]
        issue_list = [i.strip() for i in issues.replace("\n", ",").split(",") if i.strip()]
        if user_confirmed:
            # His attribution overrules the model — and overrules the issues
            # box too: a confirmed attribution is a clean approval.
            record = build_review_record("approved", "user", [])
            record["user_confirmed"] = True
            record["gate_band_at_review"] = gate_band_display or None
            record["note"] = "user attribution overruled the model"
        else:
            record = build_review_record(decision, "user", issue_list)
            record["gate_band_at_review"] = gate_band_display or None
        record["subject_kind"] = subject.get("kind")
        record["subject_id"] = subject_id
        if manifest_dir:
            os.makedirs(manifest_dir, exist_ok=True)
            path = os.path.join(manifest_dir, f"review_{subject_id}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(record, fh, indent=2)
            record["review_path"] = path
        return (record,)


class SF_RefusalRedirect:
    """Refusal-with-redirection loop (spec section 5).

    Input: a take bundle + the refusal (kind / signal / attempt) + the
    request as sent (prompt, reference, lora strength, denoise). Output: the
    adjusted take for retry + the refusal record appended to the take's
    refusal_history.

    Bounded at MAX_DEBUG_ATTEMPTS; on exhaustion it emits an escalation
    record (full debug log + recommended manual move) instead of stalling.
    Rejected media stays as negative training data with its refusal record.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "take": (SF_TAKE,),
                "refusal_kind": (["policy", "identity_gate", "execution"],),
                "refusal_signal": ("STRING", {"multiline": True, "default": ""}),
                "attempt": ("INT", {"default": 1, "min": 1, "max": 99}),
            },
            "optional": {
                "prompt_text": ("STRING", {"multiline": True, "default": ""}),
                "lora_strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.05}),
                "denoise": ("FLOAT", {"default": 0.85, "min": 0.1, "max": 1.0, "step": 0.05}),
            },
        }

    RETURN_TYPES = (SF_TAKE, SF_REFUSAL)
    RETURN_NAMES = ("adjusted_take", "refusal_record")
    FUNCTION = "redirect"
    CATEGORY = CATEGORY

    def redirect(self, take, refusal_kind, refusal_signal, attempt,
                 prompt_text="", lora_strength=0.85, denoise=0.85):
        take = dict(take)
        history = list(take.get("refusal_history") or [])
        step_name, step_action = ADJUSTMENT_LADDER[(attempt - 1) % len(ADJUSTMENT_LADDER)]
        record = {
            "kind": "refusal_record",
            "refusal_kind": refusal_kind,
            "refusal_signal": refusal_signal,
            "attempt": int(attempt),
            "adjustment": step_name,
            "adjustment_action": step_action,
            "request_as_sent": {
                "prompt": prompt_text,
                "lora_strength": float(lora_strength),
                "denoise": float(denoise),
            },
        }
        if attempt > MAX_DEBUG_ATTEMPTS:
            record["escalated"] = True
            record["escalation"] = (
                "Adjustment ladder exhausted after "
                f"{MAX_DEBUG_ATTEMPTS} attempts. Hand the full debug log to "
                "the operator with the recommended next manual move: swap "
                "the reference still and re-run the identity proof (A)."
            )
            take["refusal_history"] = history + [record]
            take["status"] = "escalated_to_operator"
            return (take, record)
        # Apply this rung's adjustment to the take params.
        adjusted = dict(take)
        if step_name == "lower_lora":
            adjusted["lora_strength"] = max(0.5, float(lora_strength) - 0.15)
        if step_name == "reduce_denoise":
            adjusted["denoise"] = max(0.5, float(denoise) - 0.15)
        if step_name == "split_shot":
            adjusted["duration_sec"] = float(take.get("duration_sec", 4.0)) / 2.0
        adjusted["refusal_history"] = history + [record]
        adjusted["status"] = f"retry_attempt_{attempt}_{step_name}"
        record["escalated"] = False
        return (adjusted, record)
