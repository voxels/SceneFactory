#!/usr/bin/env python3
"""Provenance-preserving bridge between the Voice handoff and Scene Factory.

The Voice package is not a replacement for the example's source tree.  This
module creates an additive, role-separated index: source bytes stay where they
were created, while each record carries its origin, creation time, purpose,
and whether it may be consumed by a production stage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import identity_pipeline as identity


AUDIO_EXTENSIONS = {".wav", ".aiff", ".aif", ".flac", ".m4a", ".mp3", ".ogg"}
TRANSCRIPT_EXTENSIONS = {".txt", ".srt", ".vtt"}


def resolve_voice_root(project_root: Path, config: Mapping[str, Any]) -> Path | None:
    """Resolve the configured canonical Voice package without mutating it."""
    configured = config.get("voice_root")
    if configured:
        path = Path(str(configured)).expanduser()
        path = path if path.is_absolute() else project_root / path
        return path.resolve()
    # Backward-compatible fallback for test projects and older drop-ins.
    local = project_root / "voice"
    if local.is_dir():
        return local.resolve()
    source = identity.resolve_source_root(project_root, config["source_root"]) / "voice"
    return source.resolve() if source.is_dir() else None


def _created_at(path: Path) -> str | None:
    try:
        stat = path.stat()
        timestamp = getattr(stat, "st_birthtime", stat.st_mtime)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _classify(relative: Path) -> tuple[str, str, bool, str]:
    top = relative.parts[0] if relative.parts else ""
    if top == "inputs":
        return "reference_input", "clean reference or requested target script", True, "pending"
    if top == "reference_profiles":
        return "reference_profile", "speaker identity/prosody reference", True, "pending"
    if top == "output":
        return "final_output", "approved assembled TTS master destination", False, "not_present_or_not_approved"
    if top == "examples":
        return "comparison_only", "listening comparison; never training input", False, "comparison_only"
    if top == "renders":
        return "generated_render", "generated paragraph awaiting human review", False, "pending_review"
    if top == "archive":
        return "archived_material", "historical material; excluded from current run", False, "archived"
    if top == "workflows":
        return "workflow_definition", "Voice rendering workflow", False, "definition_only"
    if top == "scripts":
        return "operator_tooling", "Voice staging/rendering tooling", False, "tooling_only"
    return "unclassified", "unclassified Voice package file", False, "blocked_unclassified"


def _record(path: Path, root: Path) -> dict[str, Any]:
    relative = path.relative_to(root)
    purpose, description, consumable, approval = _classify(relative)
    return {
        "path": str(path.resolve()),
        "relative_path": relative.as_posix(),
        "sha256": identity.sha256_file(path),
        "bytes": path.stat().st_size,
        "created_at": _created_at(path),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "origin": "Voice_package",
        "purpose": purpose,
        "purpose_description": description,
        "consumable_by_scene_factory": consumable,
        "approval_state": approval,
    }


def build_voice_manifest(project_root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Write an additive Voice manifest and return its contract.

    Only ``inputs`` and ``reference_profiles`` are eligible reference channels.
    Existing examples/renders/archive are recorded, never silently promoted.
    The final master is a destination contract, not a substitute for a missing
    waveform.
    """
    project_root = project_root.resolve()
    root = resolve_voice_root(project_root, config)
    records: list[dict[str, Any]] = []
    if root and root.is_dir():
        records = [_record(path, root) for path in sorted(root.rglob("*")) if path.is_file() and path.name != "MANIFEST.sha256"]

    transcripts = [item for item in records if Path(item["relative_path"]).suffix.lower() in TRANSCRIPT_EXTENSIONS]
    audio = [item for item in records if Path(item["relative_path"]).suffix.lower() in AUDIO_EXTENSIONS]
    target_script = next((item for item in transcripts if item["relative_path"] == "inputs/tts_script.txt"), None)
    if target_script is None:
        target_script = next((item for item in transcripts if item["relative_path"] == "tts_text.txt"), None)
    reference_audio = [item for item in audio if item["purpose"] in {"reference_input", "reference_profile"}]
    final_master = root / "output" / "gage_final_master.flac" if root else None
    performance = next((item for item in audio if item["relative_path"] == "output/gage_final_master.flac"), None)
    blockers: list[str] = []
    if root is None or not root.is_dir():
        blockers.append("canonical Voice root is missing")
    if target_script is None:
        blockers.append("Voice target script is missing (expected inputs/tts_script.txt)")
    if performance is None:
        blockers.append("approved final performance waveform is missing (expected output/gage_final_master.flac)")

    manifest = {
        "schema_version": 1,
        "status": "ready_for_render" if not blockers else "blocked",
        "project": str(project_root),
        "voice_root": str(root) if root else None,
        "merge_policy": "additive_provenance_preserving; no source replacement or implicit promotion",
        "records": records,
        "channels": {
            "target_transcript": target_script,
            "reference_audio": reference_audio,
            "performance_audio": [performance] if performance else [],
            "comparison_only": [item for item in records if item["purpose"] == "comparison_only"],
            "generated_pending_review": [item for item in records if item["purpose"] == "generated_render"],
        },
        "final_destination": {
            "path": str(final_master) if final_master else None,
            "required_filename": "gage_final_master.flac",
            "must_be_created_only_after_six_paragraph_review": True,
        },
        "blockers": blockers,
        "invariants": [
            "source bytes remain immutable and retain their original paths",
            "reference audio is never mistaken for the requested final performance",
            "examples, renders, archive, workflows, and scripts are not training inputs",
            "finishing remains possible after merge because output is an explicit destination contract",
        ],
    }
    identity.write_json(project_root / "build/identity/voice/voice_input_manifest.json", manifest)
    return manifest

