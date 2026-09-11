"""Voice nodes — voice capture as a first-class input.

Wired per the Voice/ pipeline (AGENTS.md / PLAN.md): Qwen3-TTS 12Hz 1.7B
Base, zero-shot clone, six independently-rendered paragraphs, human
listening approval per paragraph. Voice sits alongside identity and
environment as a conditioning input to the A->B->C->D workflow — not an
afterthought.

Node graph mirror: LoadAudio -> CharacterVoicesNode -> Qwen3TTSEngineNode
-> UnifiedTTSTextNode -> SaveAudio (see Voice/workflows/base.api.json).

Standing Voice rules enforced here:
- Reference audio is validated (mono PCM, 6-15 s); raw sources are never
  overwritten in place.
- Transcripts must be exact — no invented words.
- Zero-shot inference only; no fine-tuning path is exposed.
"""

from __future__ import annotations

import json
import os
import wave

from .node_types import SF_VOICE

CATEGORY = "SceneFactory/Voice"

# Profile defaults from Voice/AGENTS.md + PLAN.md (do not silently mix).
VOICE_PROFILES = {
    "max_data": {
        "temperature": 0.72,
        "max_chars_per_chunk": 180,
        "chunk_combination_method": "silence_padding",
        "silence_between_chunks_ms": 140,
        "notes": "favors identity; may inherit inconsistent mic acoustics",
    },
    "short_clean": {
        "temperature": 0.78,
        "max_chars_per_chunk": 400,
        "chunk_combination_method": "crossfade",
        "silence_between_chunks_ms": 140,
        "notes": "favors capture clarity; judged less similar in production",
    },
}

TTS_ENGINE_DEFAULTS = {
    "model_variant": "TTS - Base 1.7B (Voice Clone)",
    "device": "auto",
    "language": "English",
    "top_k": 50,
    "top_p": 0.95,
    "repetition_penalty": 1.05,
    "max_new_tokens": 2048,
    "dtype": "float32",
    "attn_implementation": "sdpa",
    "x_vector_only_mode": False,
    "runtime_mode": "Shared Runtime",
}


def _validate_reference_wav(path: str) -> dict:
    """Validate the reference WAV per the Voice preflight rules.

    Returns {"valid": bool, "issues": [...], "seconds": float, ...}.
    Pure stdlib (wave header only) — no decode, no numpy.
    """
    issues = []
    info = {"path": path}
    try:
        with wave.open(path, "rb") as w:
            info["channels"] = w.getnchannels()
            info["sampwidth"] = w.getsampwidth()
            info["framerate"] = w.getframerate()
            info["frames"] = w.getnframes()
            info["seconds"] = round(w.getnframes() / w.getframerate(), 2)
    except Exception as exc:
        return {"valid": False, "issues": [f"unreadable WAV: {exc}"], **info}
    if info["channels"] != 1:
        issues.append(f"must be mono, got {info['channels']} channels")
    if not (6.0 <= info["seconds"] <= 15.0):
        issues.append(
            f"reference should be 6-15 s, got {info['seconds']} s "
            "(several clean 5-15 s utterances beat one noisy composite)"
        )
    if os.path.getsize(path) == 0:
        issues.append("file is empty")
    info["issues"] = issues
    info["valid"] = not issues
    return info


class SF_VoiceReferenceProfile:
    """Voice reference-profile intake + validation.

    Takes a profile name (max_data / short_clean), a reference WAV path,
    and the EXACT transcript. Emits a validated voice-profile bundle that
    paragraph renders consume. Rejected references stay documented; nothing
    is overwritten in place.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "profile": (list(VOICE_PROFILES),),
                "reference_audio": ("STRING", {"default": ""}),
                "reference_transcript": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = (SF_VOICE,)
    RETURN_NAMES = ("voice_profile",)
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, profile, reference_audio, reference_transcript):
        if profile not in VOICE_PROFILES:
            raise ValueError(f"SF_VoiceReferenceProfile: unknown profile {profile!r}")
        if not reference_audio or not os.path.isfile(reference_audio):
            raise ValueError(
                f"SF_VoiceReferenceProfile: reference audio not found: {reference_audio!r}"
            )
        if not reference_transcript.strip():
            raise ValueError(
                "SF_VoiceReferenceProfile: transcript must be exact — "
                "mark uncertain words, never invent them"
            )
        check = _validate_reference_wav(reference_audio)
        return ({
            "kind": "voice_profile",
            "profile": profile,
            "profile_settings": dict(VOICE_PROFILES[profile]),
            "reference_audio": reference_audio,
            "reference_transcript": reference_transcript.strip(),
            "validation": check,
            "engine": dict(TTS_ENGINE_DEFAULTS),
        },)


class SF_VoiceParagraphRender:
    """One paragraph TTS render — graph builder.

    Builds the ComfyUI API workflow JSON for a single paragraph using the
    Qwen3-TTS zero-shot graph (mirrors Voice/workflows/paragraph_XX.api.json).
    The Mac queues and executes it; this node validates the request and
    emits the graph + a render record for the listening gate.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "voice_profile": (SF_VOICE,),
                "paragraph_text": ("STRING", {"multiline": True, "default": ""}),
                "paragraph_index": ("INT", {"default": 1, "min": 1, "max": 99}),
                "output_prefix": ("STRING", {"default": "voice_paragraph"}),
            },
            "optional": {
                "seed": ("INT", {"default": 43, "min": 0, "max": 2**31 - 1}),
                "temperature": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 2.0, "step": 0.01}),
                "max_chars_per_chunk": ("INT", {"default": -1, "min": -1, "max": 2000}),
            },
        }

    RETURN_TYPES = ("STRING", SF_VOICE)
    RETURN_NAMES = ("api_graph_json", "render_record")
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, voice_profile, paragraph_text, paragraph_index,
              output_prefix, seed=43, temperature=-1.0, max_chars_per_chunk=-1):
        text = paragraph_text.strip()
        if not text:
            raise ValueError("SF_VoiceParagraphRender: paragraph text is empty")
        settings = dict(voice_profile["profile_settings"])
        if temperature >= 0:
            settings["temperature"] = float(temperature)
        if max_chars_per_chunk > 0:
            settings["max_chars_per_chunk"] = int(max_chars_per_chunk)
        engine = dict(voice_profile["engine"])
        engine["temperature"] = settings["temperature"]
        ref_audio = voice_profile["reference_audio"]
        graph = {
            "2": {"class_type": "LoadAudio",
                  "inputs": {"audio": ref_audio}},
            "3": {"class_type": "CharacterVoicesNode",
                  "inputs": {
                      "voice_name": "none",
                      "reference_text": voice_profile["reference_transcript"],
                      "trim_start": 0.0, "trim_end": 0.0, "customized": False,
                      "opt_audio_input": ["2", 0]}},
            "4": {"class_type": "Qwen3TTSEngineNode",
                  "inputs": {
                      "model_variant": engine["model_variant"],
                      "device": engine["device"],
                      "voice_preset": "None (Zero-shot / Custom)",
                      "language": engine["language"],
                      "top_k": engine["top_k"], "top_p": engine["top_p"],
                      "temperature": engine["temperature"],
                      "repetition_penalty": engine["repetition_penalty"],
                      "max_new_tokens": engine["max_new_tokens"],
                      "dtype": engine["dtype"],
                      "attn_implementation": engine["attn_implementation"],
                      "x_vector_only_mode": engine["x_vector_only_mode"],
                      "runtime_mode": engine["runtime_mode"]}},
            "5": {"class_type": "UnifiedTTSTextNode",
                  "inputs": {
                      "TTS_engine": ["4", 0],
                      "text": text,
                      "narrator_voice": "none",
                      "seed": int(seed),
                      "opt_narrator": ["3", 0],
                      "enable_chunking": True,
                      "max_chars_per_chunk": settings["max_chars_per_chunk"],
                      "chunk_combination_method": settings["chunk_combination_method"],
                      "silence_between_chunks_ms": settings["silence_between_chunks_ms"],
                      "enable_audio_cache": False,
                      "batch_size": 0}},
            "7": {"class_type": "SaveAudio",
                  "inputs": {"audio": ["5", 0],
                             "filename_prefix": f"{output_prefix}_p{paragraph_index:02d}"}},
            "_meta": {
                "title": f"Voice paragraph {paragraph_index} (zero-shot Qwen3-TTS)",
                "profile": voice_profile["profile"],
                "note": "Inference only — no fine-tuning. Change one variable "
                        "at a time when a paragraph is weak.",
            },
        }
        record = {
            "kind": "voice_render",
            "paragraph_index": int(paragraph_index),
            "profile": voice_profile["profile"],
            "seed": int(seed),
            "temperature": settings["temperature"],
            "max_chars_per_chunk": settings["max_chars_per_chunk"],
            "output_prefix": f"{output_prefix}_p{paragraph_index:02d}",
            "text_chars": len(text),
            "audio_path": None,  # filled after the Mac executes the graph
            "review": None,       # filled only by SF_UserAttribution
        }
        return (json.dumps(graph, indent=2), record)


class SF_VoiceListeningGate:
    """Technical validation before the listening gate.

    Checks the rendered paragraph file exists, is non-empty, and has a
    readable WAV header. Technical validation is NOT human approval — the
    bundle goes to SF_UserAttribution for the listening decision.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "render_record": (SF_VOICE,),
                "audio_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = (SF_VOICE,)
    RETURN_NAMES = ("gated_render",)
    FUNCTION = "check"
    CATEGORY = CATEGORY

    def check(self, render_record, audio_path):
        issues = []
        if not audio_path or not os.path.isfile(audio_path):
            issues.append(f"audio not found: {audio_path!r}")
        elif os.path.getsize(audio_path) == 0:
            issues.append("audio file is empty")
        else:
            try:
                with wave.open(audio_path, "rb") as w:
                    if w.getnchannels() != 1:
                        issues.append("expected mono render")
            except Exception as exc:
                issues.append(f"unreadable audio: {exc}")
        gated = dict(render_record)
        gated["audio_path"] = audio_path
        gated["technical_check"] = {"passed": not issues, "issues": issues}
        return (gated,)
