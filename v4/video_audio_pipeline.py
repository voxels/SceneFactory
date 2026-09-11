#!/usr/bin/env python3
"""Prepare the role-separated LTX video and authoritative audio inputs.

This module intentionally stops before training or generation when the official
LTX trainer, matching text encoder, or supplied waveform is unavailable.  The
manifests it writes are executable contracts rather than claims that a model
has consumed a modality.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any, Mapping

import identity_pipeline as identity
import voice_flow


LTX_MODEL_ROOT = Path("/Users/voxels/Library/Application Support/LTXDesktop/models/ltx-2.5")
COMFY_ROOT = Path("/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI")
_VIDEO_ROLES = {"visual_identity", "motion_reference", "voice_performance", "both", "exclude"}
_CUT_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
_PAUSE_RE = re.compile(r"\[pause\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*\]", re.IGNORECASE)


def _write(path: Path, value: Any) -> None:
    identity.write_json(path, value)


def _video_roles(asset: Mapping[str, Any]) -> set[str]:
    roles = asset.get("usage_roles") or asset.get("video_usage_roles") or []
    return {str(role) for role in roles if str(role) in _VIDEO_ROLES}


def partition_video_assets(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Partition videos into independent identity and motion channels.

    A video is never inferred to be identity material merely because it has a
    face or because its descriptive ``roles`` mention movement.  ``both`` is
    represented in both channels but retains two independent eligibility flags.
    """
    visual: list[dict[str, Any]] = []
    motion: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    blockers: list[str] = []
    for asset in manifest.get("assets", []):
        if asset.get("kind") != "video":
            continue
        roles = _video_roles(asset)
        if not roles:
            excluded.append({"asset_id": asset.get("asset_id"), "reason": "missing_explicit_video_usage_role"})
            blockers.append(f"video {asset.get('asset_id')} has no explicit usage role")
            continue
        if "exclude" in roles:
            excluded.append({"asset_id": asset.get("asset_id"), "reason": "explicit_exclude_role"})
            continue
        record = {
            "asset_id": asset["asset_id"],
            "path": asset["path"],
            "sha256": asset["sha256"],
            "group_id": asset.get("group_id", f"source_sha256:{asset['sha256']}"),
            "usage_roles": sorted(roles),
            "source_modality": asset.get("modality"),
            "identity_eligible": bool(roles & {"visual_identity", "both"}),
            "motion_eligible": bool(roles & {"motion_reference", "both"}),
        }
        if record["identity_eligible"]:
            visual.append({**record, "dataset_role": "visual_identity"})
        if record["motion_eligible"]:
            motion.append({**record, "dataset_role": "motion_reference"})
    return {
        "schema_version": 4,
        "visual_identity": visual,
        "motion_reference": motion,
        "excluded": excluded,
        "invariants": [
            "motion_reference records never enter the visual identity clip dataset",
            "visual_identity records never become motion guides without an explicit both role",
            "both records are independently eligible in each channel",
            "every derivative retains the source group_id and source sha256",
        ],
        "blockers": blockers,
    }


def _probe_video(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"status": "blocked", "reason": "ffprobe_not_found"}
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            check=True, capture_output=True, text=True,
        )
        value = json.loads(result.stdout)
        stream = next((item for item in value.get("streams", []) if item.get("codec_type") == "video"), {})
        duration = float((value.get("format") or {}).get("duration") or stream.get("duration") or 0)
        return {
            "status": "complete",
            "duration_seconds": duration,
            "width": stream.get("width"),
            "height": stream.get("height"),
            "fps": stream.get("r_frame_rate") or stream.get("avg_frame_rate"),
            "codec": stream.get("codec_name"),
        }
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as error:
        return {"status": "blocked", "reason": f"ffprobe_failed:{type(error).__name__}"}


def _scene_boundaries(path: Path, duration: float, *, threshold: float, min_seconds: float, max_seconds: float) -> list[tuple[float, float]]:
    """Return deterministic scene-ish segments with bounded duration.

    FFmpeg's scene detector supplies candidate cuts; min/max duration guards keep
    one long shot from becoming an unbounded LTX training clip.  On a detector
    error we fail closed instead of silently treating the whole file as one clip.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("LTX video preparation requires ffmpeg for scene splitting")
    if duration <= 0:
        return []
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "info", "-nostdin", "-i", str(path),
             "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"scene splitting failed for {path}: {type(error).__name__}") from error
    cuts = sorted({float(value) for value in _CUT_RE.findall(result.stderr) if min_seconds < float(value) < duration - min_seconds})
    boundaries = [0.0]
    for cut in cuts:
        if cut - boundaries[-1] >= min_seconds:
            boundaries.append(cut)
    if duration - boundaries[-1] < min_seconds and len(boundaries) > 1:
        boundaries.pop()
    boundaries.append(duration)
    segments: list[tuple[float, float]] = []
    for start, end in zip(boundaries, boundaries[1:]):
        while end - start > max_seconds:
            segments.append((start, start + max_seconds))
            start += max_seconds
        if end - start >= min_seconds:
            segments.append((start, end))
    return segments


def _extract_visual_clips(
    source: Mapping[str, Any], destination: Path, *, threshold: float, min_seconds: float,
    max_seconds: float, fps: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create role-specific frame and short-clip derivatives for visual identity."""
    source_path = Path(source["path"])
    probe = _probe_video(source_path)
    if probe.get("status") != "complete":
        return ({"asset_id": source["asset_id"], "status": "blocked", "reason": probe.get("reason")}, [])
    segments = _scene_boundaries(source_path, float(probe["duration_seconds"]), threshold=threshold, min_seconds=min_seconds, max_seconds=max_seconds)
    records: list[dict[str, Any]] = []
    source_report = {"asset_id": source["asset_id"], "status": "complete", "probe": probe, "segments": []}
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    for segment_index, (start, end) in enumerate(segments):
        segment_id = f"{source['asset_id']}__scene_{segment_index:04d}"
        clip_path = destination / "clips" / f"{segment_id}.mp4"
        frame_dir = destination / "frames" / segment_id
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        frame_dir.mkdir(parents=True, exist_ok=True)
        duration = end - start
        # Re-encode clips so segment bounds are exact and deterministic; audio is
        # deliberately omitted from training clips and remains a separate input.
        if not clip_path.is_file():
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{start:.6f}",
                 "-i", str(source_path), "-t", f"{duration:.6f}", "-an", "-vf", f"fps={fps:g}",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", str(clip_path)],
                check=True,
            )
        # Save the image-frame view as well; it is used for masks/annotations and
        # for LTX validation references, but never for motion-only sources.
        if not list(frame_dir.glob("frame_*.jpg")):
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{start:.6f}",
                 "-i", str(source_path), "-t", f"{duration:.6f}", "-an", "-vf", f"fps={fps:g}",
                 "-q:v", "2", str(frame_dir / "frame_%06d.jpg")], check=True,
            )
        frame_records = []
        for frame_index, frame_path in enumerate(sorted(frame_dir.glob("frame_*.jpg"))):
            timestamp = start + frame_index / fps
            frame_records.append({
                "asset_id": f"visual_identity_frame__{segment_id}__{frame_index:06d}",
                "path": str(frame_path.resolve()), "sha256": identity.sha256_file(frame_path),
                "source_asset_id": source["asset_id"], "source_sha256": source["sha256"],
                "group_id": source["group_id"], "segment_id": segment_id,
                "frame_index": frame_index, "timestamp_seconds": round(timestamp, 6),
                "dataset_role": "visual_identity", "identity_eligible": True,
                "motion_eligible": False,
            })
        clip_record = {
            "asset_id": f"ltx_identity_clip__{segment_id}",
            "path": str(clip_path.resolve()), "sha256": identity.sha256_file(clip_path),
            "source_asset_id": source["asset_id"], "source_sha256": source["sha256"],
            "group_id": source["group_id"], "segment_id": segment_id,
            "start_seconds": round(start, 6), "end_seconds": round(end, 6),
            "fps": fps, "dataset_role": "visual_identity", "identity_eligible": True,
            "motion_eligible": False, "frames": frame_records,
        }
        records.append(clip_record)
        source_report["segments"].append({"segment_id": segment_id, "start_seconds": start, "end_seconds": end, "clip_asset_id": clip_record["asset_id"], "frame_count": len(frame_records)})
    return source_report, records


def _motion_manifest(project_root: Path, partition: Mapping[str, Any]) -> dict[str, Any]:
    path = project_root / "build/identity/motion/skeleton_manifest.json"
    if not path.is_file():
        return {"status": "blocked", "reason": "skeleton_manifest_missing", "sources": partition["motion_reference"]}
    skeleton = identity.read_json(path)
    allowed = {item["asset_id"] for item in partition["motion_reference"]}
    sources = [item for item in skeleton.get("sources", []) if item.get("asset_id") in allowed]
    frames = [item for item in skeleton.get("frames", []) if item.get("source_asset_id") in allowed]
    tracks = [item for item in skeleton.get("tracks", []) if item.get("track_id", "").split(":", 1)[0] in allowed]
    # This check is intentionally strict: a motion guide without pose data is
    # not a usable LTX Motion/Union control input.
    if sources and not frames:
        return {"status": "blocked", "reason": "motion_sources_have_no_extracted_frames", "sources": sources}
    return {
        "status": "ready", "source_manifest": str(path), "source_manifest_sha256": identity.sha256_file(path),
        "sources": sources, "frames": frames, "tracks": tracks,
        "dataset_role": "motion_reference", "identity_training_eligible": False,
    }


def _parse_transcript(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    pauses = [{"seconds": float(value), "offset": match.start()} for match in _PAUSE_RE.finditer(text) for value in [match.group(1)]]
    clean = _PAUSE_RE.sub(" ", text)
    words = re.findall(r"\b[\w'’-]+\b", clean, flags=re.UNICODE)
    return {"path": str(path.resolve()), "sha256": identity.sha256_file(path), "characters": len(text), "word_count": len(words), "pause_markers": pauses}


def _audio_stream_contract(path: Path) -> dict[str, Any]:
    """Describe supplied audio without rewriting it; hash remains source authority."""
    record: dict[str, Any] = {"path": str(path.resolve()), "sha256": identity.sha256_file(path), "bytes": path.stat().st_size, "source_bytes_preserved": True}
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        record.update({"status": "present_unprobed", "probe_blocker": "ffprobe_not_found"})
        return record
    try:
        result = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "audio"), None)
        if stream is None:
            record.update({"status": "blocked", "reason": "no_audio_stream"})
        else:
            record.update({"status": "ready", "codec": stream.get("codec_name"), "sample_rate": stream.get("sample_rate"), "channels": stream.get("channels"), "duration_seconds": float((data.get("format") or {}).get("duration") or stream.get("duration") or 0)})
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as error:
        record.update({"status": "present_unprobed", "probe_blocker": f"ffprobe_failed:{type(error).__name__}"})
    return record


def _ltx_runtime_contract() -> dict[str, Any]:
    trainer_env = os.environ.get("SCENE_FACTORY_LTX_TRAINER_ROOT")
    candidates = [Path(trainer_env)] if trainer_env else []
    candidates.extend([Path("/Users/voxels/LTX-2"), Path("/Users/voxels/ltx-2"), Path("/Users/voxels/ComfyUI-Installs/LTX-2")])
    scripts = ("train_lora.py", "train_video_lora.py", "scripts/train.py", "training/train.py")
    trainer_root = next((item for item in candidates if item.is_dir() and any((item / script).is_file() for script in scripts)), None)
    models = {}
    for name, filename in {
        "transformer": "ltx-2.5-22b-distilled-transformer-bf16.safetensors",
        "video_vae": "ltx-2.5-video-vae-bf16.safetensors",
        "audio_vae": "ltx-2.5-audio-vae-bf16.safetensors",
    }.items():
        path = LTX_MODEL_ROOT / filename
        models[name] = {"path": str(path), "present": path.is_file(), "bytes": path.stat().st_size if path.is_file() else None}
    encoder_roots = [LTX_MODEL_ROOT, Path("/Users/voxels/ComfyUI-Shared/models/text_encoders")]
    encoder_candidates = []
    for root in encoder_roots:
        if not root.is_dir():
            continue
        encoder_candidates.extend(item for item in sorted(root.glob("*gemma*"))
                                  if item.is_file() or any(child.is_file() for child in item.rglob("*")))
        encoder_candidates.extend(item for item in sorted(root.glob("*text*encoder*"))
                                  if item.is_file() or any(child.is_file() for child in item.rglob("*")))
    encoder_candidates = sorted({item.resolve() for item in encoder_candidates})
    native_nodes = {
        "video": COMFY_ROOT / "comfy_extras/nodes_lt.py",
        "audio": COMFY_ROOT / "comfy_extras/nodes_lt_audio.py",
        "motion_lora": COMFY_ROOT / "custom_nodes/comfyui-ltxvideolora",
    }
    native_inference_ready = (
        all(item["present"] for item in models.values())
        and all(path.is_file() or path.is_dir() for path in native_nodes.values())
    )
    return {
        "model_root": str(LTX_MODEL_ROOT), "models": models,
        "matching_gemma_encoder": {"present": bool(encoder_candidates), "candidates": [str(item) for item in encoder_candidates]},
        "trainer": {"present": trainer_root is not None, "root": str(trainer_root) if trainer_root else None, "scripts": [str(trainer_root / script) for script in scripts if trainer_root and (trainer_root / script).is_file()]},
        "native_comfyui": {
            "nodes": {name: {"path": str(path), "present": path.is_file() or path.is_dir()} for name, path in native_nodes.items()},
            "inference_ready": native_inference_ready,
            "workflow_compiler": "video_workflows.compile_workflow",
        },
        "inference_weights_present": all(item["present"] for item in models.values()),
        "training_ready": bool(trainer_root and encoder_candidates and all(item["present"] for item in models.values())),
    }


def prepare_video_audio(project_root: Path) -> dict[str, Any]:
    """Materialize role-separated LTX inputs and an audio/lipsync contract."""
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    manifest, _ = identity.build(project_root, extract_web_media=False, run_mode=config["run_mode"])
    voice_input = voice_flow.build_voice_manifest(project_root, config)
    partition = partition_video_assets(manifest)
    output_root = project_root / "build/identity/video"
    output_root.mkdir(parents=True, exist_ok=True)
    _write(output_root / "video_roles_manifest.json", partition)
    policy = config.get("video_processing", {})
    threshold = float(policy.get("scene_cut_threshold", 0.35))
    min_seconds = float(policy.get("minimum_segment_seconds", 2.0))
    max_seconds = float(policy.get("maximum_segment_seconds", 8.0))
    fps = float(policy.get("identity_frame_fps", 2.0))
    identity_sources = []
    clips: list[dict[str, Any]] = []
    blockers = list(partition["blockers"])
    for source in partition["visual_identity"]:
        try:
            report, records = _extract_visual_clips(source, output_root, threshold=threshold, min_seconds=min_seconds, max_seconds=max_seconds, fps=fps)
        except RuntimeError as error:
            report, records = ({"asset_id": source["asset_id"], "status": "blocked", "reason": str(error)}, [])
        identity_sources.append(report)
        clips.extend(records)
        if report.get("status") != "complete":
            blockers.append(f"visual identity source {source['asset_id']}: {report.get('reason', 'processing_failed')}")
    visual_manifest = {
        "schema_version": 4, "dataset_role": "visual_identity", "sources": identity_sources, "clips": clips,
        "clip_count": len(clips), "frame_count": sum(len(item.get("frames", [])) for item in clips),
        "motion_source_asset_ids": [item["asset_id"] for item in partition["motion_reference"]],
        "invariant": "motion-only sources and derivatives are absent from clips and frames",
    }
    _write(output_root / "visual_identity_manifest.json", visual_manifest)
    motion = _motion_manifest(project_root, partition)
    _write(output_root / "motion_reference_manifest.json", motion)
    if motion.get("status") != "ready" and partition["motion_reference"]:
        blockers.append(f"motion guide: {motion.get('reason', 'unavailable')}")

    transcripts = [item for item in manifest.get("assets", []) if item.get("kind") == "transcript"]
    audio_assets = [item for item in manifest.get("assets", []) if item.get("kind") == "audio"]
    # Support the v4 example's own voice/ drop-in directory as well as the
    # configured v3 source root.  This keeps the supplied waveform local to the
    # example when the operator places it there, without copying or mutating it.
    local_voice = project_root / "voice"
    if local_voice.is_dir():
        audio_extensions = {".wav", ".aiff", ".aif", ".flac", ".m4a", ".mp3", ".ogg"}
        known_audio = {str(Path(item.get("path", "")).resolve()) for item in audio_assets}
        for path in sorted(local_voice.iterdir()):
            if path.is_file() and path.suffix.lower() in audio_extensions and str(path.resolve()) not in known_audio:
                audio_assets.append({"asset_id": f"project_voice__{path.stem}", "path": str(path.resolve()), "sha256": identity.sha256_file(path)})
        local_transcript = local_voice / "tts_text.txt"
        if local_transcript.is_file() and not any(Path(item.get("path", "")).resolve() == local_transcript.resolve() for item in transcripts):
            transcripts.append({"asset_id": "project_voice_script__tts_text", "path": str(local_transcript.resolve())})
    # The canonical Voice package is additive and role-separated.  Its target
    # script is authoritative; reference recordings are not substituted for a
    # missing final performance waveform.
    if voice_input.get("channels", {}).get("target_transcript"):
        target = voice_input["channels"]["target_transcript"]
        transcripts = [{"asset_id": "voice_package_target_script", "path": target["path"], "sha256": target["sha256"]}]
    performance_audio = voice_input.get("channels", {}).get("performance_audio", [])
    if performance_audio:
        audio_assets = [{"asset_id": "voice_package_final_performance", "path": item["path"], "sha256": item["sha256"]} for item in performance_audio]
    audio_records = [_audio_stream_contract(Path(item["path"])) for item in audio_assets]
    transcript_records = [_parse_transcript(Path(item["path"])) for item in transcripts if Path(item["path"]).is_file()]
    if not audio_records:
        blockers.append("supplied TTS audio is missing from Voice/output/gage_final_master.flac")
        alignment_status = "blocked_missing_audio"
    elif not transcript_records:
        blockers.append("voice transcript is missing")
        alignment_status = "blocked_missing_transcript"
    else:
        # A forced aligner is required for actual timestamps.  Estimated timing
        # would be unsafe for lipsync and is therefore never reported as ready.
        alignment_status = "blocked_aligner_not_configured"
        blockers.append("phoneme/viseme aligner is not configured; refusing estimated lipsync")
    audio_manifest = {
        "schema_version": 4, "audio": audio_records, "transcripts": transcript_records,
        "voice_input_manifest": str((project_root / "build/identity/voice/voice_input_manifest.json").resolve()),
        "voice_reference_audio": voice_input.get("channels", {}).get("reference_audio", []),
        "source_audio_byte_preservation": "required", "alignment_status": alignment_status,
        "waveform_mutation_allowed": False,
        "mux_contract": {"audio_codec": "stream_copy", "must_match_source_sha256": True, "must_use_original_audio_stream": True},
    }
    _write(output_root / "audio_alignment_manifest.json", audio_manifest)
    runtime = _ltx_runtime_contract()
    if not runtime["trainer"]["present"]:
        blockers.append("official LTX 2.5 trainer repository is unavailable")
    if not runtime["matching_gemma_encoder"]["present"]:
        blockers.append("matching LTX-tuned Gemma encoder is unavailable")
    if not runtime["inference_weights_present"]:
        blockers.append("one or more required LTX 2.5 inference weights are unavailable")
    training_status = "ready_for_trainer" if clips and runtime["training_ready"] and not blockers else "blocked"
    training_plan = {
        "schema_version": 4, "status": training_status, "dataset_role": "visual_identity",
        "dataset_manifest": str((output_root / "visual_identity_manifest.json").resolve()),
        "motion_manifest": str((output_root / "motion_reference_manifest.json").resolve()),
        "runtime": runtime, "blockers": blockers,
        "required_consumers": ["ltx_identity_lora_trainer", "ltx_i2v_identity_keyframe", "ltx_ingredients_ic_lora", "ltx_union_or_motion_control"],
        "resume_policy": "content_addressed_source_and_model_signature",
    }
    training_root = project_root / "build/training/video_identity"
    _write(training_root / "training_plan.json", training_plan)
    runtime_contract = {
        "schema_version": 1,
        "status": "compiled" if training_status == "ready_for_trainer" else "blocked",
        "identity_id": manifest["identity_id"],
        "dataset_role": "visual_identity",
        "training_plan": str((training_root / "training_plan.json").resolve()),
        "visual_identity_manifest": str((output_root / "visual_identity_manifest.json").resolve()),
        "motion_reference_manifest": str((output_root / "motion_reference_manifest.json").resolve()),
        "audio_alignment_manifest": str((output_root / "audio_alignment_manifest.json").resolve()),
        "ltx_runtime": runtime,
        "controls": ["ingredients_ic_lora", "union_control", "motion_control", "person_spatiotemporal_mask"],
        "invocation": "scene-factory-v4 generate-video --project <project>",
        "promotion_required": True,
        "blockers": blockers,
    }
    # Compile the native ComfyUI LTX graph whenever the role-separated inputs
    # are available.  This is a real executable graph contract; it does not
    # promote an adapter or bypass the audio/training gates above.
    try:
        from video_workflows import compile_workflow
        compiled = compile_workflow(project_root)
        runtime_contract["workflow_graph"] = compiled["contract"]["graph"]
        runtime_contract["workflow_graph_sha256"] = compiled["contract"]["graph_sha256"]
        runtime_contract["workflow_compilation_status"] = "complete"
    except (OSError, ValueError, RuntimeError) as error:
        runtime_contract["workflow_compilation_status"] = "blocked"
        runtime_contract["workflow_compilation_blocker"] = str(error)
    _write(output_root / "video_runtime.json", runtime_contract)
    result = {
        "schema_version": 4, "status": training_status, "video_roles": partition,
        "voice_input": voice_input,
        "visual_identity": visual_manifest, "motion_reference": motion, "audio": audio_manifest,
        "ltx_runtime": runtime, "training_plan": training_plan, "runtime_contract": runtime_contract,
    }
    _write(project_root / "build/identity/video_audio_manifest.json", result)
    return result


def train_video_identity(project_root: Path) -> dict[str, Any]:
    result = prepare_video_audio(project_root)
    if result["status"] != "ready_for_trainer":
        blockers = result["training_plan"].get("blockers", [])
        raise RuntimeError("LTX video identity training blocked: " + "; ".join(blockers))
    # The exact upstream CLI is intentionally not guessed.  Once a pinned
    # trainer is installed, its verified command must be added to the runtime
    # contract before any checkpoint can be called promoted.
    raise RuntimeError("LTX trainer discovery succeeded but command contract is not pinned; refusing an unverified training invocation")


def verify_audio_unchanged(source_audio: Path, before_sha256: str) -> dict[str, Any]:
    """Fail-closed postcondition used by mux/integration tests."""
    if not source_audio.is_file():
        return {"status": "blocked", "reason": "source_audio_missing"}
    current = identity.sha256_file(source_audio)
    return {"status": "ready" if current == before_sha256 else "blocked", "before_sha256": before_sha256, "after_sha256": current, "source_audio_unchanged": current == before_sha256}


def mux_original_audio(video: Path, source_audio: Path, destination: Path,
                       *, expected_audio_sha256: str | None = None) -> dict[str, Any]:
    """Mux the authoritative waveform with a generated video using stream copy."""
    video = video.resolve()
    source_audio = source_audio.resolve()
    destination = destination.resolve()
    if not video.is_file():
        raise RuntimeError(f"generated video is missing: {video}")
    if not source_audio.is_file():
        raise RuntimeError(f"supplied TTS audio is missing: {source_audio}")
    if destination.exists():
        raise RuntimeError(f"mux destination already exists; choose a new delivery path: {destination}")
    before = identity.sha256_file(source_audio)
    if expected_audio_sha256 and before != expected_audio_sha256:
        raise RuntimeError(f"supplied TTS audio hash changed: {source_audio}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("audio mux requires ffmpeg")
    video_probe = _probe_video(video)
    audio_probe = _audio_stream_contract(source_audio)
    if video_probe.get("status") != "complete" or audio_probe.get("status") != "ready":
        raise RuntimeError("audio mux requires successfully probed video and audio")
    if not video_probe.get("width") or not video_probe.get("height"):
        raise RuntimeError("audio mux source has no video stream")
    if video_probe.get("duration_seconds", 0) + 0.1 < audio_probe.get("duration_seconds", 0):
        raise RuntimeError("generated video is shorter than the performance; complete the video timeline before mux")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
        "-i", str(video), "-i", str(source_audio),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
        str(destination),
    ], check=True)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("audio mux produced no output")
    after = identity.sha256_file(source_audio)
    if after != before:
        raise RuntimeError("audio mux mutated the supplied waveform")
    ffprobe = shutil.which("ffprobe")
    streams = []
    if ffprobe:
        result = subprocess.run([
            ffprobe, "-v", "error", "-print_format", "json", "-show_streams", str(destination)
        ], check=True, capture_output=True, text=True)
        streams = json.loads(result.stdout).get("streams", [])
    stream_types = [item.get("codec_type") for item in streams]
    if ffprobe and not {"video", "audio"}.issubset(stream_types):
        raise RuntimeError(f"muxed output is missing video/audio streams: {stream_types}")
    return {
        "status": "complete", "path": str(destination), "sha256": identity.sha256_file(destination),
        "source_audio": str(source_audio), "source_audio_sha256": before,
        "source_audio_unchanged": after == before, "stream_copy": True,
        "stream_types": stream_types,
    }
