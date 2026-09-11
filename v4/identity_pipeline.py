#!/usr/bin/env python3
"""Build provenance-preserving multimodal identity evidence manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import struct
import subprocess
import wave
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


KIND_SUFFIXES = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"},
    "video": {".mp4", ".mov", ".mkv", ".webm"},
    "webarchive": {".webarchive"},
    "audio": {".wav", ".aiff", ".aif", ".flac", ".m4a", ".mp3", ".ogg"},
    "transcript": {".txt", ".md"},
    "geometry": {".usdz"},
    "document": {".html", ".htm"},
}

VIDEO_USAGE_ROLES = {"visual_identity", "motion_reference", "voice_performance", "both", "exclude"}

MIME_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/tiff": ".tiff",
    "image/heic": ".heic",
    "image/avif": ".avif",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Missing configuration: {path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error}") from None


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_asset_id(modality: str, relative_path: str, digest: str) -> str:
    stem = "".join(character if character.isalnum() else "_" for character in Path(relative_path).stem.lower())
    return f"{modality}__{stem.strip('_')[:48]}__{digest[:12]}"


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema_version") != 4:
        raise ValueError("identity.json schema_version must be 4")
    if config.get("run_mode") not in {"automatic", "fine_tuning"}:
        raise ValueError("identity.json run_mode must be automatic or fine_tuning")
    identity = config.get("identity")
    if not isinstance(identity, dict) or not identity.get("id"):
        raise ValueError("identity.json needs identity.id")
    if identity.get("subject_type") != "person":
        raise ValueError("v4 modeling identity subject_type must be 'person'")
    consent = identity.get("consent", {})
    if consent.get("status") not in {"unverified", "verified", "revoked"}:
        raise ValueError("identity.consent.status must be unverified, verified, or revoked")
    exclusion = config.get("exclusion_policy")
    if not isinstance(exclusion, dict):
        raise ValueError("identity.json needs exclusion_policy")
    terms = exclusion.get("case_insensitive_terms")
    if not isinstance(terms, list) or not terms or not all(isinstance(item, str) and item.strip() for item in terms):
        raise ValueError("exclusion_policy.case_insensitive_terms must contain non-empty strings")
    if not any(item.casefold() == "koleka" for item in terms):
        raise ValueError("exclusion_policy must explicitly exclude Koleka")
    matching = config.get("identity_matching")
    if not isinstance(matching, dict) or not isinstance(matching.get("anchors"), list) or len(matching["anchors"]) < 2:
        raise ValueError("identity_matching needs at least two configured anchors")
    modalities = config.get("modalities")
    if not isinstance(modalities, dict) or not modalities:
        raise ValueError("identity.json needs at least one modality")
    for modality, spec in modalities.items():
        if spec.get("kind") not in KIND_SUFFIXES:
            raise ValueError(f"Unknown kind for modality {modality}: {spec.get('kind')!r}")
        if not isinstance(spec.get("globs"), list) or not spec["globs"]:
            raise ValueError(f"Modality {modality} needs one or more globs")
        if spec.get("kind") == "video":
            defaults = spec.get("video_usage_roles")
            if not isinstance(defaults, list) or not defaults:
                raise ValueError(f"Video modality {modality} needs video_usage_roles")
            unknown_roles = sorted(set(defaults) - VIDEO_USAGE_ROLES)
            if unknown_roles:
                raise ValueError(f"Video modality {modality} has unknown video usage roles: {unknown_roles}")
            for rule in spec.get("video_role_rules", []):
                if not rule.get("glob") or not isinstance(rule.get("roles"), list) or not rule["roles"]:
                    raise ValueError(f"Video modality {modality} has an invalid video_role_rule")
                unknown_roles = sorted(set(rule["roles"]) - VIDEO_USAGE_ROLES)
                if unknown_roles:
                    raise ValueError(f"Video modality {modality} has unknown video usage roles: {unknown_roles}")
    policy = config.get("selection_policy")
    if not isinstance(policy, dict):
        raise ValueError("identity.json needs selection_policy")
    required_policy = {
        "minimum_width", "minimum_height", "minimum_contrast", "minimum_sharpness",
        "brightness_range", "near_duplicate_hamming_distance", "validation_fraction",
        "calibration_fraction", "final_test_fraction", "maximum_visual_training_images",
        "video_frames_per_source", "audio_minimum_duration_seconds",
        "audio_maximum_clipping_fraction", "audio_maximum_silence_fraction",
    }
    missing_policy = sorted(required_policy - set(policy))
    if missing_policy:
        raise ValueError(f"selection_policy is missing: {missing_policy}")
    if not 0 < float(policy["validation_fraction"]) < 0.5:
        raise ValueError("selection_policy.validation_fraction must be between 0 and 0.5")
    held_out = sum(float(policy[name]) for name in ("validation_fraction", "calibration_fraction", "final_test_fraction"))
    if not 0 < held_out < 0.5:
        raise ValueError("selection_policy held-out fractions must sum to less than 0.5")
    brightness = policy["brightness_range"]
    if not isinstance(brightness, list) or len(brightness) != 2 or not 0 <= float(brightness[0]) < float(brightness[1]) <= 255:
        raise ValueError("selection_policy.brightness_range must be an increasing [low, high] pair")
    for characteristic, spec in config.get("characteristics", {}).items():
        authority = spec.get("authority")
        if not isinstance(authority, list) or not authority:
            raise ValueError(f"Characteristic {characteristic} needs authority")
        unknown = [item for item in authority if item not in modalities]
        if unknown:
            raise ValueError(f"Characteristic {characteristic} uses unknown modalities: {unknown}")


def resolve_source_root(project_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    path = path if path.is_absolute() else project_root / path
    path = path.resolve()
    if not path.is_dir():
        raise ValueError(f"Source root does not exist: {path}")
    return path


def image_dimensions(path: Path) -> dict[str, int]:
    """Read common image dimensions without an optional imaging dependency."""
    try:
        data = path.read_bytes()
    except OSError:
        return {}
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return {"width": width, "height": height}
    if data.startswith(b"\xff\xd8"):
        cursor = 2
        while cursor + 9 < len(data):
            if data[cursor] != 0xFF:
                cursor += 1
                continue
            marker = data[cursor + 1]
            cursor += 2
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if cursor + 2 > len(data):
                break
            length = struct.unpack(">H", data[cursor:cursor + 2])[0]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and cursor + 7 <= len(data):
                height, width = struct.unpack(">HH", data[cursor + 3:cursor + 7])
                return {"width": width, "height": height}
            if length < 2:
                break
            cursor += length
    return {}


def inspect_audio(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as stream:
                frames = stream.getnframes()
                rate = stream.getframerate()
                return {
                    "channels": stream.getnchannels(),
                    "sample_rate": rate,
                    "sample_width_bytes": stream.getsampwidth(),
                    "duration_seconds": round(frames / rate, 6) if rate else None,
                }
        except (wave.Error, EOFError):
            pass
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=codec_name,channels,sample_rate,duration", "-of", "json", str(path)],
            check=True, capture_output=True, text=True,
        )
        streams = json.loads(result.stdout).get("streams", [])
        return streams[0] if streams else {"probe_status": "no_audio_stream"}
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return {"probe_status": "unavailable"}


def inspect_video(path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,channels,sample_rate",
             "-of", "json", str(path)],
            check=True, capture_output=True, text=True,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return {"probe_status": "unavailable"}


def inspect_usdz(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            suffixes = Counter(Path(item.filename).suffix.lower() or "<none>" for item in members)
            return {
                "member_count": len(members),
                "uncompressed_bytes": sum(item.file_size for item in members),
                "member_types": dict(sorted(suffixes.items())),
                "usd_layers": [item.filename for item in members if Path(item.filename).suffix.lower() in {".usd", ".usda", ".usdc"}],
                "texture_members": [item.filename for item in members if Path(item.filename).suffix.lower() in KIND_SUFFIXES["image"]],
            }
    except (OSError, zipfile.BadZipFile):
        return {"archive_status": "invalid"}


def web_resources(document: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    main = document.get("WebMainResource")
    if isinstance(main, dict):
        yield main
    for resource in document.get("WebSubresources", []):
        if isinstance(resource, dict):
            yield resource
    for frame in document.get("WebSubframeArchives", []):
        if isinstance(frame, dict):
            yield from web_resources(frame)


def safe_stem(value: str, fallback: str) -> str:
    name = Path(urlparse(value).path).stem if value else fallback
    normalized = "".join(character if character.isalnum() else "_" for character in name.lower()).strip("_")
    return normalized[:48] or fallback


def inspect_webarchive(path: Path, extraction_root: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        with path.open("rb") as stream:
            document = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException):
        return {"archive_status": "invalid"}, []
    resources = list(web_resources(document))
    mime_counts = Counter(str(item.get("WebResourceMIMEType", "unknown")).lower() for item in resources)
    main = document.get("WebMainResource", {})
    summary = {
        "main_url": main.get("WebResourceURL"),
        "resource_count": len(resources),
        "mime_counts": dict(sorted(mime_counts.items())),
        "embedded_image_count": sum(count for mime, count in mime_counts.items() if mime.startswith("image/")),
    }
    extracted = []
    if extraction_root is None:
        return summary, extracted
    seen = set()
    for resource in resources:
        mime = str(resource.get("WebResourceMIMEType", "")).lower()
        data = resource.get("WebResourceData")
        if not mime.startswith("image/") or mime in {"image/x-icon", "image/vnd.microsoft.icon", "image/svg+xml"}:
            continue
        if not isinstance(data, bytes) or not data:
            continue
        digest = sha256_bytes(data)
        if digest in seen:
            continue
        seen.add(digest)
        suffix = MIME_SUFFIXES.get(mime) or Path(urlparse(str(resource.get("WebResourceURL", ""))).path).suffix.lower() or ".bin"
        output = extraction_root / f"{digest}{suffix}"
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists() or sha256_file(output) != digest:
            output.write_bytes(data)
        extracted.append({
            "path": str(output.resolve()),
            "sha256": digest,
            "bytes": len(data),
            "mime_type": mime,
            "source_url": resource.get("WebResourceURL"),
            "review_state": "pending",
            "training_eligible": False,
        })
    summary["extracted_image_count"] = len(extracted)
    return summary, extracted


def inspect_file(kind: str, path: Path, extraction_root: Path | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if kind == "image":
        return image_dimensions(path), []
    if kind == "audio":
        return inspect_audio(path), []
    if kind == "video":
        return inspect_video(path), []
    if kind == "geometry":
        return inspect_usdz(path), []
    if kind == "webarchive":
        return inspect_webarchive(path, extraction_root)
    if kind == "transcript":
        text = path.read_text(encoding="utf-8", errors="replace")
        return {"characters": len(text), "words": len(text.split()), "pause_markers": text.count("[pause:")}, []
    if kind == "document":
        text = path.read_text(encoding="utf-8", errors="replace")
        title = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
        return {
            "characters": len(text),
            "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else None,
            "image_reference_count": len(re.findall(r"<img\b", text, flags=re.IGNORECASE)),
            "absolute_url_count": len(re.findall(r"https?://", text, flags=re.IGNORECASE)),
        }, []
    return {}, []


def discover(source_root: Path, globs: Iterable[str], kind: str) -> list[Path]:
    files = set()
    for pattern in globs:
        files.update(path.resolve() for path in source_root.glob(pattern) if path.is_file())
    allowed = KIND_SUFFIXES[kind]
    return sorted(path for path in files if path.suffix.lower() in allowed)


def roles_for_asset(spec: Mapping[str, Any], relative_path: str) -> list[str]:
    for rule in spec.get("role_rules", []):
        if Path(relative_path).match(str(rule.get("glob", ""))):
            return list(rule.get("roles", []))
    return list(spec.get("roles", []))


def video_usage_roles_for_asset(spec: Mapping[str, Any], relative_path: str) -> list[str]:
    """Resolve semantic video use independently from descriptive identity roles."""
    for override in spec.get("video_source_overrides", []):
        if str(override.get("path", "")).casefold() == relative_path.casefold():
            return list(override.get("roles", []))
    for rule in spec.get("video_role_rules", []):
        if Path(relative_path).match(str(rule.get("glob", ""))):
            return list(rule.get("roles", []))
    return list(spec.get("video_usage_roles", []))


def exclusion_reason(relative_path: str, config: Mapping[str, Any]) -> str | None:
    """Return the configured fail-closed reason for a source path, if excluded."""
    policy = config.get("exclusion_policy", {})
    folded = relative_path.casefold()
    for term in policy.get("case_insensitive_terms", []):
        if str(term).casefold() in folded:
            return f"case_insensitive_term:{term}"
    path = Path(relative_path)
    for pattern in policy.get("globs", []):
        if path.match(str(pattern)) or Path(folded).match(str(pattern).casefold()):
            return f"glob:{pattern}"
    return None


def build(project_root: Path, *, extract_web_media: bool = False, run_mode: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    project_root = project_root.resolve()
    config_path = project_root / "identity.json"
    config = read_json(config_path)
    validate_config(config)
    mode = run_mode or config["run_mode"]
    if mode not in {"automatic", "fine_tuning"}:
        raise ValueError("run_mode must be automatic or fine_tuning")
    source_root = resolve_source_root(project_root, config["source_root"])
    output_root = project_root / "build" / "identity"
    extraction_root = output_root / "extracted" / "webarchive" if extract_web_media else None
    assets = []
    counts: dict[str, int] = {}
    bytes_by_modality: dict[str, int] = {}
    evidence_by_modality: dict[str, list[str]] = {}
    missing_required = []
    candidate_by_hash: dict[str, dict[str, Any]] = {}
    excluded_assets: list[dict[str, Any]] = []

    for modality, spec in config["modalities"].items():
        kind = spec["kind"]
        files = discover(source_root, spec["globs"], kind)
        included_files = []
        for path in files:
            relative = path.relative_to(source_root).as_posix()
            reason = exclusion_reason(relative, config)
            if reason:
                excluded_assets.append({
                    "relative_path": relative,
                    "modality": modality,
                    "kind": kind,
                    "reason": reason,
                })
            else:
                included_files.append(path)
        files = included_files
        counts[modality] = len(files)
        bytes_by_modality[modality] = sum(path.stat().st_size for path in files)
        evidence_by_modality[modality] = []
        if spec.get("required_in_fine_tuning") and not files:
            missing_required.append(modality)
        for path in files:
            digest = sha256_file(path)
            relative = path.relative_to(source_root).as_posix()
            asset_id = stable_asset_id(modality, relative, digest)
            metadata, extracted = inspect_file(kind, path, extraction_root)
            asset = {
                "asset_id": asset_id,
                "modality": modality,
                "kind": kind,
                "path": str(path),
                "relative_path": relative,
                "sha256": digest,
                "group_id": f"source_sha256:{digest}",
                "bytes": path.stat().st_size,
                "roles": roles_for_asset(spec, relative),
                "training_policy": spec["training_policy"],
                "review_state": "pending",
                "provenance": "user_supplied_source",
                "metadata": metadata,
            }
            if kind == "video":
                asset["usage_roles"] = video_usage_roles_for_asset(spec, relative)
            assets.append(asset)
            evidence_by_modality[modality].append(asset_id)
            for candidate in extracted:
                existing = candidate_by_hash.get(candidate["sha256"])
                if existing is not None:
                    existing["derived_from"].append(asset_id)
                    source_url = candidate.get("source_url")
                    if source_url and source_url not in existing["source_urls"]:
                        existing["source_urls"].append(source_url)
                    continue
                candidate_id = stable_asset_id(modality, candidate["path"], candidate["sha256"])
                source_url = candidate.pop("source_url", None)
                candidate.update({
                    "asset_id": candidate_id,
                    "modality": modality,
                    "kind": "image",
                    "derived_from": [asset_id],
                    "group_id": asset["group_id"],
                    "source_urls": [source_url] if source_url else [],
                    "roles": ["additional_view_candidate"],
                    "training_policy": "derive_then_review",
                    "provenance": "webarchive_embedded_derivative",
                })
                candidate_by_hash[candidate["sha256"]] = candidate

    extracted_candidates = sorted(candidate_by_hash.values(), key=lambda item: item["sha256"])
    derived_counts = Counter(item["modality"] for item in extracted_candidates)
    for item in extracted_candidates:
        evidence_by_modality[item["modality"]].append(item["asset_id"])
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        by_hash.setdefault(asset["sha256"], []).append(asset)
    exact_duplicate_groups = [
        {
            "sha256": digest,
            "asset_ids": [item["asset_id"] for item in group],
            "paths": [item["path"] for item in group],
        }
        for digest, group in sorted(by_hash.items()) if len(group) > 1
    ]

    if extraction_root is not None and extraction_root.exists():
        expected = {Path(item["path"]).resolve() for item in extracted_candidates}
        for stale in sorted(extraction_root.rglob("*"), reverse=True):
            if stale.is_file() and stale.resolve() not in expected:
                stale.unlink()
            elif stale.is_dir() and not any(stale.iterdir()):
                stale.rmdir()

    manifest = {
        "schema_version": 4,
        "run_mode": mode,
        "generated_at": now(),
        "identity_id": config["identity"]["id"],
        "source_root": str(source_root),
        "configuration": str(config_path),
        "inventory": {
            "source_asset_count": len(assets),
            "unique_source_hash_count": len(by_hash),
            "exact_duplicate_group_count": len(exact_duplicate_groups),
            "extracted_candidate_count": len(extracted_candidates),
            "counts_by_modality": counts,
            "bytes_by_modality": bytes_by_modality,
            "excluded_source_count": len(excluded_assets),
        },
        "assets": assets,
        "excluded_assets": sorted(excluded_assets, key=lambda item: (item["relative_path"], item["modality"])),
        "exact_duplicate_groups": exact_duplicate_groups,
        "derived_review_candidates": extracted_candidates,
    }

    characteristics = {}
    for name, spec in config["characteristics"].items():
        authorities = []
        for rank, modality in enumerate(spec["authority"], 1):
            authorities.append({
                "rank": rank,
                "modality": modality,
                "source_asset_count": counts.get(modality, 0),
                "derived_candidate_count": derived_counts.get(modality, 0),
                "evidence_count": len(evidence_by_modality.get(modality, [])),
                "asset_ids": evidence_by_modality.get(modality, []),
            })
        characteristics[name] = {
            "stable": spec["stable"],
            "notes": spec.get("notes"),
            "authority": authorities,
            "has_evidence": any(item["evidence_count"] for item in authorities),
        }

    consent_status = config["identity"]["consent"]["status"]
    transcript_count = sum(counts[name] for name, spec in config["modalities"].items() if spec["kind"] == "transcript")
    audio_count = sum(counts[name] for name, spec in config["modalities"].items() if spec["kind"] == "audio")
    blockers = []
    if consent_status != "verified":
        blockers.append(f"consent status is {consent_status}")
    if mode == "fine_tuning":
        blockers.extend(f"missing required modality: {item}" for item in missing_required)
        if audio_count and not transcript_count:
            blockers.append("audio exists without a transcript")
    warnings = []
    if mode == "automatic" and missing_required:
        warnings.append(f"optional-in-automatic modalities not present: {', '.join(missing_required)}")
    if any(spec["kind"] == "webarchive" and counts[name] for name, spec in config["modalities"].items()) and not extract_web_media:
        warnings.append("webarchive media was indexed but not extracted; rebuild with --extract-web-media")
    if extracted_candidates and mode == "fine_tuning":
        warnings.append(f"{len(extracted_candidates)} extracted web images require subject and provenance review")
    if exact_duplicate_groups:
        warnings.append(f"{len(exact_duplicate_groups)} exact source-duplicate groups must stay in one dataset split")

    audio_asset_ids = [item["asset_id"] for item in assets if item["kind"] == "audio"]
    transcript_asset_ids = [item["asset_id"] for item in assets if item["kind"] == "transcript"]

    characteristic_manifest = {
        "schema_version": 4,
        "run_mode": mode,
        "generated_at": manifest["generated_at"],
        "identity": config["identity"],
        "source_root": str(source_root),
        "characteristics": characteristics,
        "fusion_policy": config["fusion_policy"],
        "audio_transcript_alignment": {
            "audio_asset_ids": audio_asset_ids,
            "transcript_asset_ids": transcript_asset_ids,
            "policy": "verify_exact_spoken_text_and_pause_timing_before_voice_use",
            "status": "ready_for_review" if audio_asset_ids and transcript_asset_ids else "incomplete",
        },
        "training_views": {
            "visual_identity": [name for name, spec in config["modalities"].items() if spec["kind"] == "image" and counts[name]],
            "visual_identity_video_asset_ids": [item["asset_id"] for item in assets if item["kind"] == "video" and any(role in {"visual_identity", "both"} for role in item.get("usage_roles", []))],
            "motion_conditioning_asset_ids": [item["asset_id"] for item in assets if item["kind"] == "video" and any(role in {"motion_reference", "both"} for role in item.get("usage_roles", []))],
            "voice_performance_video_asset_ids": [item["asset_id"] for item in assets if item["kind"] == "video" and any(role in {"voice_performance", "both"} for role in item.get("usage_roles", []))],
            "geometry_conditioning": [name for name, spec in config["modalities"].items() if spec["kind"] == "geometry" and counts[name]],
            "voice_conditioning": [name for name, spec in config["modalities"].items() if spec["kind"] == "audio" and counts[name]],
            "webarchive_candidates": len(extracted_candidates),
        },
        "readiness": {
            "ready_for_training": not blockers,
            "blockers": blockers,
            "warnings": warnings,
        },
    }
    write_json(output_root / "asset_manifest.json", manifest)
    write_json(output_root / "identity_characteristics.json", characteristic_manifest)
    return manifest, characteristic_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="inventory and inspect identity evidence")
    build_parser.add_argument("project", type=Path)
    build_parser.add_argument("--extract-web-media", action="store_true")
    arguments = parser.parse_args(argv)
    manifest, characteristics = build(arguments.project, extract_web_media=arguments.extract_web_media)
    print(json.dumps({
        "identity_id": manifest["identity_id"],
        "source_asset_count": manifest["inventory"]["source_asset_count"],
        "extracted_candidate_count": manifest["inventory"]["extracted_candidate_count"],
        "ready_for_training": characteristics["readiness"]["ready_for_training"],
        "blockers": characteristics["readiness"]["blockers"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
