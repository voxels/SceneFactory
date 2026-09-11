#!/usr/bin/env python3
"""Deterministic ingestion of a configured reconstruction reference video.

This module deliberately has no dependency on the Scene Factory CLI.  Its small
functions can be used by the compiler, a one-off migration, or unit tests.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


CommandRunner = Callable[..., Any]
FrameExtractor = Callable[[Path, float, Path], Any]
SAMPLE_POSITIONS = (("start", 0.1), ("action", 0.5), ("end", 0.9))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expand_path(value: str, variables: Mapping[str, Any]) -> str:
    pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")
    result = value
    for _ in range(10):
        expanded = pattern.sub(lambda match: str(variables.get(match.group(1), match.group(0))), result)
        if expanded == result:
            break
        result = expanded
    unresolved = pattern.findall(result)
    if unresolved:
        raise ValueError(f"Unresolved reference path variable: {unresolved[0]}")
    return result


def resolve_reference(
    project_root: Path,
    project: Mapping[str, Any],
    *,
    content_root: Path | None = None,
    path_variables: Mapping[str, Any] | None = None,
) -> tuple[str, Path]:
    """Return the configured reconstruction reference ID and absolute path."""
    reconstruction = project.get("reference_reconstruction", {})
    reference_id = reconstruction.get("reference_id")
    if not reconstruction.get("enabled"):
        raise ValueError("Reference reconstruction is not enabled")
    if not reference_id:
        raise ValueError("reference_reconstruction.reference_id is required")
    matches = [item for item in project.get("motion_references", []) if item.get("id") == reference_id]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one configured reference {reference_id!r}; found {len(matches)}")
    raw_path = matches[0].get("path")
    if not raw_path:
        raise ValueError(f"Configured reference {reference_id!r} has no path")
    variables = {"PROJECT_ROOT": str(project_root.resolve()), **(path_variables or {})}
    root = (content_root or project_root).resolve()
    path = Path(_expand_path(str(raw_path), variables)).expanduser()
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not path.is_file():
        raise ValueError(f"Reference video does not exist: {path}")
    return str(reference_id), path


def probe_reference(path: Path, command_runner: CommandRunner = subprocess.run) -> dict[str, Any]:
    """Run ffprobe and return its decoded JSON document."""
    command = [
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path),
    ]
    try:
        result = command_runner(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"Unable to probe reference video {path}: {error}") from error
    try:
        return json.loads(result.stdout)
    except (AttributeError, json.JSONDecodeError) as error:
        raise ValueError(f"ffprobe returned invalid JSON for {path}") from error


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _frame_rate(value: Any) -> float | None:
    if value in (None, "", "0/0"):
        return None
    text = str(value)
    try:
        numerator, denominator = text.split("/", 1)
        result = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        result = _number(value)
    return round(result, 6) if result is not None else None


def normalize_probe(probe: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce ffprobe output to stable production-relevant stream metadata."""
    streams = []
    allowed = (
        "index", "codec_type", "codec_name", "profile", "width", "height",
        "pix_fmt", "r_frame_rate", "avg_frame_rate", "channels", "channel_layout",
        "sample_rate", "duration",
    )
    for source in sorted(probe.get("streams", []), key=lambda item: int(item.get("index", 0))):
        streams.append({key: source[key] for key in allowed if key in source})
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("Configured reference contains no video stream")
    duration = _number(probe.get("format", {}).get("duration"))
    if not duration:
        durations = [_number(item.get("duration")) for item in streams]
        duration = max((item for item in durations if item), default=None)
    if not duration:
        raise ValueError("Configured reference has no positive duration")
    format_source = probe.get("format", {})
    return {
        "duration_seconds": round(duration, 6),
        "width": video.get("width"),
        "height": video.get("height"),
        "frame_rate": _frame_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "format": {
            key: format_source[key]
            for key in ("format_name", "format_long_name", "bit_rate")
            if key in format_source
        },
        "streams": streams,
        "stream_counts": {
            "video": sum(item.get("codec_type") == "video" for item in streams),
            "audio": sum(item.get("codec_type") == "audio" for item in streams),
            "other": sum(item.get("codec_type") not in {"video", "audio"} for item in streams),
        },
    }


def ordered_shots(scenes: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for scene in scenes:
        for shot in scene.get("shots", []):
            duration = _number(shot.get("duration_seconds"))
            if not duration:
                raise ValueError(f"Shot {shot.get('id')!r} must have a positive duration")
            result.append({"scene": scene, "shot": shot, "duration": duration})
    if not result:
        raise ValueError("Cannot map a reference without script shots")
    return result


def map_shots_to_reference(
    scenes: Iterable[Mapping[str, Any]], source_duration: float
) -> list[dict[str, Any]]:
    """Map script shots in order, preserving their proportional durations."""
    if source_duration <= 0:
        raise ValueError("Reference duration must be positive")
    shots = ordered_shots(scenes)
    script_duration = sum(item["duration"] for item in shots)
    cursor = 0.0
    result = []
    for index, item in enumerate(shots):
        end = source_duration if index == len(shots) - 1 else cursor + source_duration * item["duration"] / script_duration
        scene, shot = item["scene"], item["shot"]
        result.append({
            "order": index + 1,
            "scene_id": scene.get("id"),
            "shot_id": shot.get("id"),
            "script_duration_seconds": round(item["duration"], 6),
            "source_start_seconds": round(cursor, 6),
            "source_end_seconds": round(end, 6),
            "resource_tags": resource_tags(scene, shot),
        })
        cursor = end
    return result


def resource_tags(scene: Mapping[str, Any], shot: Mapping[str, Any]) -> list[str]:
    """Conservatively tag resources declared or textually visible in a shot."""
    explicit = shot.get("reference_resource_tags")
    if explicit is not None:
        return sorted({str(item) for item in explicit})
    tags = {"camera", "environment"}
    cast = set(shot.get("cast", []))
    if "k0l3k4" in cast:
        tags.add("k_performer")
    if "dystopian_masses" in cast:
        tags.add("workers")
    if "enforcers" in cast:
        tags.add("enforcers")
    if "hammer" in shot.get("props", []):
        tags.add("hammer")
    text = " ".join(
        str(value)
        for value in (
            shot.get("action", ""), *shot.get("continuity", []),
            scene.get("title", ""), *scene.get("continuity", []),
        )
    ).lower()
    if any(word in text for word in ("screen", "crt", "monitor", "graphic", "speaker")):
        tags.add("screen")
    if "occluder" in text:
        tags.add("occluders")
    return sorted(tags)


def sample_timestamps(start: float, end: float) -> list[dict[str, Any]]:
    """Choose boundary-safe, deterministic start/action/end evidence samples."""
    if end <= start:
        raise ValueError("Shot source range must have positive duration")
    span = end - start
    return [
        {"sample": label, "timestamp_seconds": round(start + span * position, 6)}
        for label, position in SAMPLE_POSITIONS
    ]


def extract_png_frame(
    source_path: Path,
    timestamp: float,
    output_path: Path,
    command_runner: CommandRunner = subprocess.run,
) -> Path:
    """Extract one video-only PNG. No audio stream is mapped or emitted."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-ss", f"{timestamp:.6f}", "-i", str(source_path), "-map", "0:v:0",
        "-frames:v", "1", "-an", str(output_path),
    ]
    try:
        command_runner(command, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"Unable to extract reference frame at {timestamp:.6f}s: {error}") from error
    if not output_path.is_file():
        raise ValueError(f"ffmpeg did not create reference frame: {output_path}")
    return output_path


def _task_contracts(tags: Sequence[str]) -> list[str]:
    contracts = {"camera", "lighting", "blocking"}
    mapping = {
        "k_performer": {"wardrobe", "pose", "movement"},
        "workers": {"workers_design", "workers_group_motion"},
        "enforcers": {"enforcers_design", "enforcers_group_motion"},
        "hammer": {"hammer_geometry", "hammer_state"},
        "environment": {"environment_design"},
        "screen": {"screen_state"},
        "occluders": {"occluder_state"},
    }
    for tag in tags:
        contracts.update(mapping.get(tag, set()))
    return sorted(contracts)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def ingest_reference(
    project_root: Path,
    project: Mapping[str, Any],
    scenes: Iterable[Mapping[str, Any]],
    *,
    content_root: Path | None = None,
    path_variables: Mapping[str, Any] | None = None,
    probe_data: Mapping[str, Any] | None = None,
    extract_frames: bool = True,
    command_runner: CommandRunner = subprocess.run,
    frame_extractor: FrameExtractor | None = None,
) -> dict[str, Any]:
    """Ingest a reference and write ``build/reference/reference_manifest.json``.

    Pass ``probe_data`` and/or ``frame_extractor`` to test or embed this function
    without invoking external processes.
    """
    project_root = project_root.resolve()
    reconstruction = project.get("reference_reconstruction", {})
    audio_policy = reconstruction.get("audio_policy")
    if audio_policy != "strip_and_ignore":
        raise ValueError("reference_reconstruction.audio_policy must be 'strip_and_ignore'")
    reference_id, source_path = resolve_reference(
        project_root, project, content_root=content_root, path_variables=path_variables
    )
    info = normalize_probe(probe_data if probe_data is not None else probe_reference(source_path, command_runner))
    ranges = map_shots_to_reference(scenes, info["duration_seconds"])
    reference_root = project_root / "build" / "reference"
    frames_root = reference_root / "frames"
    tasks = []
    for shot_range in ranges:
        samples = []
        for sample in sample_timestamps(
            shot_range["source_start_seconds"], shot_range["source_end_seconds"]
        ):
            frame_name = f"{shot_range['order']:03d}_{shot_range['shot_id']}__{sample['sample']}.png"
            frame_path = frames_root / frame_name
            frame_record = {**sample, "resource_tags": shot_range["resource_tags"]}
            if extract_frames:
                extractor = frame_extractor or (
                    lambda source, timestamp, output: extract_png_frame(
                        source, timestamp, output, command_runner
                    )
                )
                extractor(source_path, sample["timestamp_seconds"], frame_path)
                if not frame_path.is_file():
                    raise ValueError(f"Frame extractor did not create {frame_path}")
                frame_record.update({
                    "frame_path": _relative(frame_path, project_root),
                    "sha256": sha256_file(frame_path),
                })
            else:
                frame_record.update({"frame_path": None, "sha256": None})
            task_id = f"vision_contract__{shot_range['shot_id']}__{sample['sample']}"
            frame_record["vision_contract_task_id"] = task_id
            tasks.append({
                "id": task_id,
                "status": "pending",
                "shot_id": shot_range["shot_id"],
                "sample": sample["sample"],
                "timestamp_seconds": sample["timestamp_seconds"],
                "frame_path": frame_record["frame_path"],
                "frame_sha256": frame_record["sha256"],
                "resource_tags": shot_range["resource_tags"],
                "contract_types": _task_contracts(shot_range["resource_tags"]),
                "source_authority": "reference_video",
                "identity_exclusions": ["reference_performer.face", "reference_performer.body_identity", "reference_performer.hair"],
            })
            samples.append(frame_record)
        shot_range["samples"] = samples
    manifest = {
        "schema_version": 1,
        "reference_id": reference_id,
        "source": {
            "path": str(source_path),
            "sha256": sha256_file(source_path),
            "size_bytes": source_path.stat().st_size,
            **info,
        },
        "audio_policy": audio_policy,
        "audio": {
            "source_stream_count": info["stream_counts"]["audio"],
            "ignored": True,
            "artifacts_emitted": False,
        },
        "shot_ranges": ranges,
        "vision_contract_tasks": tasks,
    }
    reference_root.mkdir(parents=True, exist_ok=True)
    manifest_path = reference_root / "reference_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
