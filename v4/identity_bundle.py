#!/usr/bin/env python3
"""Build the self-contained v4 identity bundle after real A/B promotion."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import identity_pipeline as identity
import voice_flow


class BundleError(RuntimeError):
    """The bundle contract is incomplete or a source changed during packaging."""


_AUDIO_EXTENSIONS = {".wav", ".aiff", ".aif", ".flac", ".m4a", ".mp3", ".ogg"}
_TRANSCRIPT_EXTENSIONS = {".txt", ".srt", ".vtt"}


def _supplied_audio(project_root: Path, config: dict[str, Any]) -> list[Path]:
    """Resolve performance audio without mistaking reference audio for delivery."""
    canonical = voice_flow.resolve_voice_root(project_root, config)
    if config.get("voice_root") and canonical:
        final = canonical / "output" / "gage_final_master.flac"
        if final.is_file():
            return [final.resolve()]
        return []
    source_root = identity.resolve_source_root(project_root, config["source_root"])
    by_name: dict[str, Path] = {}
    # A project-local drop-in wins over the configured source-root fallback when
    # both contain the same filename; never merge ambiguous duplicate inputs.
    for voice_root in (project_root / "voice", source_root / "voice"):
        if not voice_root.is_dir():
            continue
        for path in sorted(voice_root.iterdir()):
            lowered = str(path).casefold()
            if (not path.is_file() or path.suffix.lower() not in _AUDIO_EXTENSIONS
                    or "koleka" in lowered or "k0l3k4" in lowered):
                continue
            by_name.setdefault(path.name, path.resolve())
    return [by_name[name] for name in sorted(by_name)]


def _supplied_transcripts(project_root: Path, config: dict[str, Any]) -> list[Path]:
    """Resolve authoritative dialogue text/captions using the same fallback policy."""
    canonical = voice_flow.resolve_voice_root(project_root, config)
    if config.get("voice_root") and canonical:
        target = canonical / "inputs" / "tts_script.txt"
        if target.is_file():
            return [target.resolve()]
        return []
    source_root = identity.resolve_source_root(project_root, config["source_root"])
    by_name: dict[str, Path] = {}
    for voice_root in (project_root / "voice", source_root / "voice"):
        if not voice_root.is_dir():
            continue
        for path in sorted(voice_root.iterdir()):
            lowered = str(path).casefold()
            if (not path.is_file() or path.suffix.lower() not in _TRANSCRIPT_EXTENSIONS
                    or "koleka" in lowered or "k0l3k4" in lowered):
                continue
            by_name.setdefault(path.name, path.resolve())
    return [by_name[name] for name in sorted(by_name)]


def _copy_verified(source: Path, destination: Path, expected: str | None = None) -> dict[str, Any]:
    if not source.is_file():
        raise BundleError(f"bundle source is missing: {source}")
    digest = identity.sha256_file(source)
    if expected and digest != expected:
        raise BundleError(f"bundle source hash changed: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and identity.sha256_file(destination) != digest:
        raise BundleError(f"bundle destination collision: {destination}")
    if not destination.exists():
        shutil.copy2(source, destination)
    return {"path": str(destination), "sha256": digest, "bytes": destination.stat().st_size}


def _copy_tree(source: Path, destination: Path) -> list[dict[str, Any]]:
    if not source.is_dir():
        return []
    records = []
    for item in sorted(path for path in source.rglob("*") if path.is_file()):
        if "koleka" in str(item).lower() or "k0l3k4" in str(item).lower():
            raise BundleError(f"Koleka-derived path cannot enter identity bundle: {item}")
        records.append(_copy_verified(item, destination / item.relative_to(source)))
    return records


def _bundle_path(value: str, project_root: Path) -> str:
    """Map project-local runtime paths to their declared bundle locations."""
    root = str(project_root.resolve()).rstrip("/") + "/"
    if not value.startswith(root):
        return value
    relative = Path(value[len(root):])
    parts = relative.parts
    if parts[:2] == ("build", "workflows"):
        return str(Path("workflows", *parts[2:]))
    if parts[:3] == ("build", "identity", "video"):
        if parts[-1] == "audio_alignment_manifest.json":
            return "voice/alignment.json"
        return str(Path("provenance", "video", *parts[3:]))
    if parts[:2] == ("build", "training"):
        return str(Path("provenance", *parts[2:]))
    return str(Path("provenance", relative.name))


def _rewrite_runtime(value: Any, project_root: Path) -> Any:
    if isinstance(value, str):
        return _bundle_path(value, project_root)
    if isinstance(value, list):
        return [_rewrite_runtime(item, project_root) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_runtime(item, project_root) for key, item in value.items()}
    return value


def _copy_runtime_contract(source: Path, destination: Path, project_root: Path) -> dict[str, Any]:
    """Copy a runtime contract while removing project-tree path coupling."""
    if not source.is_file():
        raise BundleError(f"bundle runtime contract is missing: {source}")
    value = _rewrite_runtime(identity.read_json(source), project_root)
    value["path_root"] = "bundle_root"
    value["external_project_paths_allowed"] = False
    destination.parent.mkdir(parents=True, exist_ok=True)
    identity.write_json(destination, value)
    return {"path": str(destination), "sha256": identity.sha256_file(destination), "bytes": destination.stat().st_size}


def build_bundle(project_root: Path, destination: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    destination = destination.resolve()
    config = identity.read_json(project_root / "identity.json")
    identity.validate_config(config)
    promotion = project_root / "build/training/image_identity/promoted/pytorch_lora_weights.safetensors"
    video_promotion = project_root / "build/training/video_identity/promoted/pytorch_lora_weights.safetensors"
    if not promotion.is_file():
        raise BundleError("promoted image identity LoRA is missing; complete held-out promotion first")
    if not video_promotion.is_file():
        raise BundleError("promoted video identity LoRA is missing; complete LTX promotion first")
    audio = _supplied_audio(project_root, config)
    if not audio:
        raise BundleError("supplied TTS waveform is missing from v4/voice and the configured source-root voice fallback")
    source_root = identity.resolve_source_root(project_root, config["source_root"])
    for item in source_root.rglob("*"):
        if "koleka" in str(item).lower() or "k0l3k4" in str(item).lower():
            raise BundleError(f"Koleka path detected during bundle audit: {item}")

    records = {
        "models/image_identity_lora.safetensors": _copy_verified(promotion, destination / "models/image_identity_lora.safetensors"),
        "models/video_identity_lora.safetensors": _copy_verified(video_promotion, destination / "models/video_identity_lora.safetensors"),
    }
    for item in audio:
        records[f"voice/{item.name}"] = _copy_verified(item, destination / "voice" / item.name)
    for item in _supplied_transcripts(project_root, config):
        records[f"voice/{item.name}"] = _copy_verified(item, destination / "voice" / item.name)
    alignment = project_root / "build/identity/video/audio_alignment_manifest.json"
    if alignment.is_file():
        records["voice/alignment.json"] = _copy_verified(alignment, destination / "voice/alignment.json")
    evaluation_reports = sorted((project_root / "build/training/image_identity/heldout_runs").glob("*/evaluation_report.json"))
    manifest_files = [
        project_root / "identity.json",
        project_root / "build/identity/reference_bank/reference_bank.json",
        project_root / "build/identity/selection_manifest.json",
        project_root / "build/identity/geometry/usdz_ingestion_manifest.json",
        project_root / "build/identity/motion/skeleton_manifest.json",
        project_root / "build/identity/video_audio_manifest.json",
        project_root / "build/pipeline/preflight.json",
    ] + evaluation_reports[-1:]
    for item in manifest_files:
        if item.is_file():
            records[str(item.relative_to(project_root))] = _copy_verified(item, destination / "provenance" / item.name)
    runtime_files = [
        (project_root / "build/runtime/image_runtime.json", destination / "runtime/image_runtime.json"),
        (project_root / "build/identity/video/video_runtime.json", destination / "runtime/video_runtime.json"),
    ]
    for source, target in runtime_files:
        if source.is_file():
            records[str(target.relative_to(destination))] = _copy_runtime_contract(source, target, project_root)
    for source, target in [
        (project_root / "build/avatar", destination / "avatar"),
        (project_root / "build/test-package-current/geometry", destination / "geometry/usdz"),
        (project_root / "build/workflows", destination / "workflows"),
        (project_root / "build/identity/geometry", destination / "geometry/renders"),
        (project_root / "build/identity/motion", destination / "motion"),
        (project_root / "build/identity/video", destination / "provenance/video"),
    ]:
        tree_records = _copy_tree(source, target)
        for item in tree_records:
            records[str(Path(item["path"]).relative_to(destination))] = item
    bundle = {
        "schema_version": 4,
        "identity_id": config["identity"]["id"],
        "status": "complete",
        "source_policy": "Koleka excluded; all packaged files hash-verified",
        "files": records,
    }
    identity.write_json(destination / "bundle.json", bundle)
    return bundle
