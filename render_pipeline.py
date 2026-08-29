#!/usr/bin/env python3
"""Strict reconstruction render preflight, workflow compilation, and compositing.

This module deliberately separates three claims:

* ``planned``: a render job has complete declarative metadata;
* ``ready``: every required local input, model, and Comfy node is present;
* ``proved``: an output exists and has passed machine inspection.

It never silently falls back from motion-track IC-LoRA to text-only I2V.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


OFFICIAL_LTX_REPOSITORY = "https://github.com/Lightricks/ComfyUI-LTXVideo"
OFFICIAL_MOTION_MODEL_REPOSITORY = (
    "https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control"
)
OFFICIAL_MOTION_WORKFLOW = "example_workflows/2.5/LTX-2.5_ICLoRA_Motion_Track_Distilled.json"
MOTION_MODEL = "ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors"
LTX_DIFFUSION_MODEL = "ltx-2.5-22b-distilled-transformer-bf16.safetensors"
LTX_VIDEO_VAE = "ltx-2.5-video-vae-bf16.safetensors"
LTX_TEXT_ENCODER = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
REQUIRED_EXTENSION_FILES = (
    "__init__.py",
    "nodes_registry.py",
    "iclora.py",
    "sparse_tracks.py",
    OFFICIAL_MOTION_WORKFLOW,
)
REQUIRED_MOTION_NODE_TYPES = (
    "LTXICLoRALoaderModelOnly",
    "LTXAddVideoICLoRAGuide",
    "LTXVDrawTracks",
    "LTXVSparseTrackEditor",
    "LTXVCropGuides",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_value(directory: Path, *arguments: str) -> str | None:
    if not (directory / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def audit_ltx_install(
    comfy_root: Path,
    models_root: Path,
    server_url: str = "http://127.0.0.1:8188",
    runtime_python: Path | None = None,
    object_info_path: Path | None = None,
) -> dict:
    """Inspect, but never mutate, the local LTX motion-control installation."""
    comfy_root = Path(comfy_root)
    models_root = Path(models_root)
    extension = comfy_root / "custom_nodes" / "ComfyUI-LTXVideo"
    file_checks = [
        {"path": str(extension / relative), "present": (extension / relative).is_file()}
        for relative in REQUIRED_EXTENSION_FILES
    ]
    model_locations = {
        "motion_ic_lora": models_root / "loras" / MOTION_MODEL,
        "diffusion_model": models_root / "diffusion_models" / LTX_DIFFUSION_MODEL,
        "video_vae": models_root / "vae" / LTX_VIDEO_VAE,
        "text_encoder": models_root / "text_encoders" / LTX_TEXT_ENCODER,
    }
    model_checks = []
    for role, path in model_locations.items():
        present = path.is_file()
        model_checks.append({
            "role": role,
            "path": str(path),
            "present": present,
            "size_bytes": path.stat().st_size if present else None,
            "sha256": sha256(path) if present and role == "motion_ic_lora" else None,
        })
    status = git_value(extension, "status", "--porcelain")
    runtime_candidates = (
        Path(runtime_python) if runtime_python else comfy_root / ".venv" / "bin" / "python",
        comfy_root / ".venv" / "bin" / "python",
        comfy_root.parent / "standalone-env" / "bin" / "python",
    )
    runtime_python = next((path for path in runtime_candidates if path.is_file()), runtime_candidates[0])
    kornia_version = None
    if runtime_python.is_file():
        result = subprocess.run(
            [
                str(runtime_python), "-c",
                "import importlib.metadata; print(importlib.metadata.version('kornia'))",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        kornia_version = result.stdout.strip() if result.returncode == 0 else None
    live_nodes = None
    live_error = None
    try:
        if object_info_path:
            object_info = read_json(Path(object_info_path))
        else:
            with urllib.request.urlopen(f"{server_url.rstrip('/')}/object_info", timeout=3) as response:
                object_info = json.loads(response.read().decode("utf-8"))
        live_nodes = {name: name in object_info for name in REQUIRED_MOTION_NODE_TYPES}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        live_error = str(error)
    missing_files = [item["path"] for item in file_checks if not item["present"]]
    missing_models = [item["path"] for item in model_checks if not item["present"]]
    blockers = []
    if missing_files:
        blockers.append("official_extension_incomplete")
    if status:
        blockers.append("official_extension_worktree_not_clean")
    if missing_models:
        blockers.append("required_models_missing")
    if kornia_version == "0.8.3" and not (live_nodes and all(live_nodes.values())):
        blockers.append("kornia_0_8_3_incompatible_with_extension_issue_494")
    if live_nodes is None:
        blockers.append("live_node_registration_unverified")
    elif not all(live_nodes.values()):
        blockers.append("required_motion_nodes_not_registered")
    return {
        "schema_version": 1,
        "generated_at": now(),
        "official_sources": {
            "extension": OFFICIAL_LTX_REPOSITORY,
            "motion_model": OFFICIAL_MOTION_MODEL_REPOSITORY,
        },
        "comfy": {
            "root": str(comfy_root),
            "commit": git_value(comfy_root, "rev-parse", "HEAD"),
        },
        "extension": {
            "root": str(extension),
            "commit": git_value(extension, "rev-parse", "HEAD"),
            "clean": not bool(status),
            "status_porcelain": status.splitlines() if status else [],
            "files": file_checks,
            "required_node_types": list(REQUIRED_MOTION_NODE_TYPES),
        },
        "models": model_checks,
        "runtime": {
            "python": str(runtime_python) if runtime_python.is_file() else None,
            "kornia_version": kornia_version,
            "required_kornia_version": "0.8.2",
            "upstream_issue": "https://github.com/Lightricks/ComfyUI-LTXVideo/issues/494",
        },
        "live_node_registration": {
            "server_url": server_url,
            "object_info_path": str(object_info_path) if object_info_path else None,
            "nodes": live_nodes,
            "error": live_error,
        },
        "ready": not blockers,
        "blockers": blockers,
    }


def validated_tracks(value, expected_frames: int) -> str:
    """Validate full-frame pixel trajectories accepted by LTXVDrawTracks."""
    tracks = json.loads(value) if isinstance(value, str) else value
    if not isinstance(tracks, list) or not tracks:
        raise ValueError("motion tracks must contain at least one trajectory")
    for track_index, track in enumerate(tracks):
        if not isinstance(track, list) or len(track) != expected_frames:
            raise ValueError(
                f"track {track_index} must have exactly {expected_frames} frame points"
            )
        for frame_index, point in enumerate(track):
            if set(point) != {"x", "y"}:
                raise ValueError(
                    f"track {track_index} frame {frame_index} must contain only x and y"
                )
            if not all(isinstance(point[key], (int, float)) for key in ("x", "y")):
                raise ValueError("track coordinates must be numeric pixel values")
    return json.dumps(tracks, separators=(",", ":"))


def pose_record_to_motion_tracks(record: dict, *, start_index: int, frame_count: int,
                                 width: int, height: int,
                                 anchors: dict[str, tuple[float, float]],
                                 motion_scale: float = 0.8,
                                 shot_id: str | None = None,
                                 source_start_seconds: float | None = None,
                                 source_end_seconds: float | None = None):
    """Retarget observed pose motion to image anchors with documented interpolation."""
    samples = record.get("samples", [])[start_index:start_index + frame_count]
    if len(samples) != frame_count:
        raise ValueError("requested pose interval exceeds available samples")
    timestamps = [sample.get("timestamp_seconds") for sample in samples]
    if shot_id is not None:
        if source_start_seconds is None or source_end_seconds is None:
            raise ValueError("shot-bounded pose conversion requires source bounds")
        if any(not isinstance(value, (int, float)) for value in timestamps):
            raise ValueError("shot-bounded pose samples require timestamps")
        if min(timestamps) < source_start_seconds or max(timestamps) > source_end_seconds:
            raise ValueError(
                f"pose interval crosses {shot_id} bounds "
                f"{source_start_seconds:.6f}-{source_end_seconds:.6f}"
            )

    def observed(sample, name):
        joints = {item["name"]: item for item in sample.get("joints", [])}
        if name == "root":
            root = sample.get("root")
            return (root["x"], root["y"]) if root else None
        if name == "upper_torso":
            points = [joints.get("left_shoulder"), joints.get("right_shoulder")]
            points = [item for item in points if item]
            return ((sum(p["x"] for p in points) / len(points),
                     sum(p["y"] for p in points) / len(points)) if points else None)
        point = joints.get(name)
        return (point["x"], point["y"]) if point else None

    tracks, provenance = [], {}
    for name, anchor in anchors.items():
        values = [observed(sample, name) for sample in samples]
        real = [index for index, value in enumerate(values) if value is not None]
        if not real:
            raise ValueError(f"pose interval has no observations for {name}")
        filled = list(values)
        for index in range(real[0]):
            filled[index] = values[real[0]]
        for index in range(real[-1] + 1, frame_count):
            filled[index] = values[real[-1]]
        for left, right in zip(real, real[1:]):
            for index in range(left + 1, right):
                ratio = (index - left) / (right - left)
                filled[index] = tuple(
                    values[left][axis] + ratio * (values[right][axis] - values[left][axis])
                    for axis in (0, 1)
                )
        origin = filled[0]
        tracks.append([{
            "x": round(max(0, min(width - 1, anchor[0] * width +
                                   (x - origin[0]) * width * motion_scale)), 3),
            "y": round(max(0, min(height - 1, anchor[1] * height +
                                   (y - origin[1]) * height * motion_scale)), 3),
        } for x, y in filled])
        provenance[name] = {
            "anchor_normalized": {"x": anchor[0], "y": anchor[1]},
            "observed_frames": len(real),
            "filled_frames": frame_count - len(real),
            "fill_policy": "linear_between_observations_nearest_at_edges",
        }
    return tracks, {
        "shot_id": shot_id,
        "cut_boundary_policy": "single_shot_no_cross_cut" if shot_id else None,
        "authoritative_source_bounds_seconds": (
            [source_start_seconds, source_end_seconds] if shot_id else None
        ),
        "source_pose_indices": [start_index, start_index + frame_count - 1],
        "source_timestamps_seconds": [samples[0].get("timestamp_seconds"),
                                      samples[-1].get("timestamp_seconds")],
        "frame_count": frame_count,
        "canvas": {"width": width, "height": height},
        "motion_scale": motion_scale,
        "tracks": provenance,
    }


def replace_strings(value, replacements: dict[str, str]):
    if isinstance(value, dict):
        return {key: replace_strings(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_strings(item, replacements) for item in value]
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
    return value


def configure_motion_track_workflow(
    template: dict,
    *,
    prompt: str,
    negative: str,
    input_image: str,
    tracks,
    output_prefix: str,
    duration_seconds: float = 3.0,
    fps: int = 24,
) -> tuple[dict, dict]:
    """Configure the official UI workflow without reimplementing its subgraphs."""
    workflow = copy.deepcopy(template)
    # The official workflow computes the legal 1 + 8n length from these widgets.
    expected_frames = 1 + 8 * round((duration_seconds * fps - 1) / 8)
    tracks_json = validated_tracks(tracks, expected_frames)
    replacements = {
        "gemma4-12b-with-proj-ltx-2.5-bf16.safetensors": LTX_TEXT_ENCODER,
    }
    workflow = replace_strings(workflow, replacements)
    found = set()
    for node in workflow.get("nodes", []):
        node_type = node.get("type")
        title = node.get("title", "")
        if node_type == "PrimitiveStringMultiline" and title == "Prompt (positive)":
            node["widgets_values"] = [prompt]
            found.add("prompt")
        elif node_type == "PrimitiveStringMultiline" and title == "Prompt (negative)":
            node["widgets_values"] = [negative]
            found.add("negative")
        elif node_type == "LoadImage":
            node["widgets_values"] = [input_image, "image"]
            found.add("input_image")
        elif node_type == "PrimitiveFloat" and title.startswith("fps"):
            node["widgets_values"] = [fps]
            found.add("fps")
        elif node_type == "PrimitiveFloat" and title.startswith("duration in seconds"):
            node["widgets_values"] = [duration_seconds]
            found.add("duration")
        elif node_type == "LTXVSparseTrackEditor":
            values = list(node.get("widgets_values", []))
            while len(values) < 4:
                values.append("")
            values[0] = tracks_json
            values[1] = tracks_json
            values[2] = expected_frames
            node["widgets_values"] = values
            found.add("tracks")
        elif node_type == "SaveVideo" and title == "Save tracks preview":
            node["widgets_values"] = [f"{output_prefix}__tracks", "auto", "auto"]
            found.add("tracks_output")
        elif node_type == "SaveVideo" and title != "Save tracks preview":
            node["widgets_values"] = [output_prefix, "auto", "auto"]
            found.add("video_output")
    required = {
        "prompt", "negative", "input_image", "fps", "duration", "tracks",
        "tracks_output", "video_output",
    }
    missing = sorted(required - found)
    if missing:
        raise ValueError(f"official motion workflow template is incompatible; missing {missing}")
    metadata = {
        "control": "motion_track_ic_lora",
        "motion_model": MOTION_MODEL,
        "reference_downscale_factor": 2,
        "fps": fps,
        "requested_duration_seconds": duration_seconds,
        "frame_count": expected_frames,
        "input_image": input_image,
        "output_prefix": output_prefix,
        "audio_policy": "strip_and_ignore",
        "official_template": OFFICIAL_MOTION_WORKFLOW,
    }
    return workflow, metadata


def visual_only_motion_api_graph(
    *,
    prompt: str,
    negative: str,
    input_image: str,
    tracks,
    output_prefix: str,
    duration_seconds: float = 3.0,
    fps: int = 24,
    width: int = 544,
    height: int = 960,
    seed: int = 32184,
) -> tuple[dict, dict]:
    """Build an API graph equivalent to official motion control, without audio.

    The official UI template concatenates an audio latent. This graph follows
    its video branch and the current official custom-node schemas, omitting the
    audio VAE, latent, decoder, and muxing path entirely.
    """
    frames = 1 + 8 * round((duration_seconds * fps - 1) / 8)
    tracks_json = validated_tracks(tracks, frames)
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": LTX_DIFFUSION_MODEL, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": LTX_TEXT_ENCODER, "type": "ltxv", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": LTX_VIDEO_VAE}},
        "4": {"class_type": "LTXICLoRALoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": MOTION_MODEL, "strength_model": 1.0}},
        "5": {"class_type": "LoadImage", "inputs": {"image": input_image}},
        "6": {"class_type": "LTXVPreprocess", "inputs": {"image": ["5", 0], "img_compression": 18}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative}},
        "9": {"class_type": "LTXVConditioning", "inputs": {"positive": ["7", 0], "negative": ["8", 0], "frame_rate": float(fps)}},
        "10": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": width, "height": height, "length": frames, "batch_size": 1}},
        "11": {"class_type": "LTXVImgToVideoInplace", "inputs": {"vae": ["3", 0], "image": ["6", 0], "latent": ["10", 0], "strength": 0.7, "bypass": False}},
        "12": {"class_type": "LTXVDrawTracks", "inputs": {"tracks": tracks_json, "width": width, "height": height}},
        "13": {"class_type": "LTXAddVideoICLoRAGuide", "inputs": {
            "positive": ["9", 0], "negative": ["9", 1], "vae": ["3", 0],
            "latent": ["11", 0], "image": ["12", 0], "frame_idx": 0,
            "strength": 1.0, "latent_downscale_factor": ["4", 1], "crop": "disabled",
            "use_tiled_encode": False, "tile_size": 256, "tile_overlap": 64,
        }},
        "14": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "15": {"class_type": "CFGGuider", "inputs": {"model": ["4", 0], "positive": ["13", 0], "negative": ["13", 1], "cfg": 1.0}},
        "16": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}},
        "17": {"class_type": "ManualSigmas", "inputs": {"sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}},
        "18": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["14", 0], "guider": ["15", 0], "sampler": ["16", 0], "sigmas": ["17", 0], "latent_image": ["13", 2]}},
        "19": {"class_type": "LTXVCropGuides", "inputs": {"positive": ["13", 0], "negative": ["13", 1], "latent": ["18", 0]}},
        "20": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["19", 2], "vae": ["3", 0], "tile_size": 512, "overlap": 64, "temporal_size": 128, "temporal_overlap": 32}},
        "21": {"class_type": "CreateVideo", "inputs": {"images": ["20", 0], "fps": float(fps), "bit_depth": 8}},
        "22": {"class_type": "SaveVideo", "inputs": {"video": ["21", 0], "filename_prefix": output_prefix, "format": "mp4", "codec": "auto"}},
        "23": {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "fps": float(fps), "bit_depth": 8}},
        "24": {"class_type": "SaveVideo", "inputs": {"video": ["23", 0], "filename_prefix": f"{output_prefix}__tracks", "format": "mp4", "codec": "auto"}},
    }
    metadata = {
        "control": "motion_track_ic_lora",
        "motion_model": MOTION_MODEL,
        "reference_downscale_factor": 2,
        "fps": fps,
        "requested_duration_seconds": duration_seconds,
        "frame_count": frames,
        "width": width,
        "height": height,
        "seed": seed,
        "audio_policy": "strip_and_ignore",
        "audio_nodes": [],
        "format": "comfy_api",
    }
    return graph, metadata


def ffprobe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def inspect_visual_output(path: Path, require_alpha: bool = False) -> dict:
    probe = ffprobe(path)
    video = [item for item in probe.get("streams", []) if item.get("codec_type") == "video"]
    audio = [item for item in probe.get("streams", []) if item.get("codec_type") == "audio"]
    pixel_formats = [item.get("pix_fmt", "") for item in video]
    has_alpha = any(
        value.startswith(("argb", "abgr", "rgba", "bgra", "yuva", "gbrap"))
        for value in pixel_formats
    )
    errors = []
    if not video:
        errors.append("no_video_stream")
    if audio:
        errors.append("audio_stream_present")
    if require_alpha and not has_alpha:
        errors.append("alpha_channel_absent")
    return {
        "path": str(path),
        "exists": path.is_file(),
        "sha256": sha256(path) if path.is_file() else None,
        "video_streams": len(video),
        "audio_streams": len(audio),
        "pixel_formats": pixel_formats,
        "has_alpha": has_alpha,
        "passed": not errors,
        "errors": errors,
    }


def composite_visual_layers(
    plate: Path, layers: list[Path], output: Path, proof_scope: str = "production"
) -> dict:
    """Overlay ordered RGBA/alpha video layers over a plate, emitting no audio."""
    if not layers:
        raise ValueError("at least one foreground layer is required")
    for path in [plate, *layers]:
        if not Path(path).is_file():
            raise FileNotFoundError(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y", "-i", str(plate)]
    for layer in layers:
        command.extend(["-i", str(layer)])
    filters = []
    previous = "[0:v]"
    for index in range(1, len(layers) + 1):
        destination = f"[v{index}]"
        filters.append(
            f"{previous}[{index}:v]overlay=eof_action=pass:shortest=0:format=auto{destination}"
        )
        previous = destination
    command.extend([
        "-filter_complex", ";".join(filters),
        "-map", previous,
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:])
    report = inspect_visual_output(output)
    report.update({
        "kind": "layered_visual_composite",
        "proof_scope": proof_scope,
        "production_artifact": proof_scope == "production",
        "plate": str(plate),
        "layers": [str(path) for path in layers],
        "ffmpeg_command": command,
    })
    return report


def validate_conditioning_scope(layer: dict) -> list[str]:
    """Reject layer jobs whose subject or prop conditioning can leak."""
    scope = layer.get("conditioning_scope")
    if not isinstance(scope, dict):
        return ["missing conditioning_scope"]
    include_subjects = set(scope.get("include_subjects", []))
    exclude_subjects = set(scope.get("exclude_subjects", []))
    include_props = set(scope.get("include_props", []))
    exclude_props = set(scope.get("exclude_props", []))
    errors = []
    if include_subjects & exclude_subjects:
        errors.append("subject appears in both include and exclude conditioning")
    if include_props & exclude_props:
        errors.append("prop appears in both include and exclude conditioning")
    if layer.get("owner") == "k0l3k4":
        if include_subjects != {"k0l3k4"} or "enforcers" not in exclude_subjects:
            errors.append("K layer must include only k0l3k4 and exclude enforcers")
        forbidden = set(scope.get("forbidden_attributes", []))
        if not {"helmet", "visor", "riot armor"}.issubset(forbidden):
            errors.append("K layer must forbid helmet, visor, and riot armor")
        if scope.get("identity_lora") != "k0l3k4":
            errors.append("K layer must use only the k0l3k4 identity LoRA")
    if layer.get("owner") == "enforcers":
        if include_subjects != {"enforcers"} or "k0l3k4" not in exclude_subjects:
            errors.append("enforcer layer must include only enforcers and exclude k0l3k4")
        if scope.get("identity_lora") is not None:
            errors.append("enforcer layer must not use K identity conditioning")
    if layer.get("kind") == "prop" and layer.get("owner") == "hammer":
        if include_props != {"hammer"} or include_subjects:
            errors.append("hammer layer must include only hammer prop conditioning")
        required_geometry = {
            "one straight handle", "one crosswise hammer head",
            "bare grip end", "no duplicate head",
        }
        if not required_geometry.issubset(set(scope.get("geometry_lock", []))):
            errors.append("hammer layer is missing the locked single-head geometry contract")
    return errors


def validate_shot_bounded_track(path: Path, *, shot: dict, track_type: str) -> list[str]:
    """Validate control provenance and prohibit production tracks spanning cuts."""
    if not path.is_file():
        return [str(path)]
    try:
        record = read_json(path)
    except (OSError, json.JSONDecodeError) as error:
        return [f"invalid:{track_type}:unreadable:{error}"]
    errors = []
    if record.get("track_type") != track_type:
        errors.append(f"track_type must be {track_type}")
    if record.get("shot_id") != shot["shot_id"]:
        errors.append(f"shot_id must be {shot['shot_id']}")
    if record.get("cut_boundary_policy") != "single_shot_no_cross_cut":
        errors.append("cut_boundary_policy must be single_shot_no_cross_cut")
    if record.get("operational_for_generation") is not True:
        errors.append("operational_for_generation must be true")
    source_range = shot.get("source_range") or {}
    start = source_range.get("source_start_seconds")
    end = source_range.get("source_end_seconds")
    timestamps = [
        sample.get("timestamp_seconds") for sample in record.get("samples", [])
        if isinstance(sample.get("timestamp_seconds"), (int, float))
    ]
    if not timestamps:
        errors.append("track has no timestamped samples")
    elif start is None or end is None:
        errors.append("shot has no authoritative source bounds")
    elif min(timestamps) < start or max(timestamps) > end:
        errors.append(f"samples cross shot bounds {start:.6f}-{end:.6f}")
    return [f"invalid:{track_type}:{error}" for error in errors]


def compile_reconstruction_queue(project_root: Path, ltx_audit: dict) -> dict:
    """Compile a dependency-explicit render queue from the post manifest.

    The queue is intentionally blocked by absent production inputs. A missing K
    track can therefore never degrade to unconstrained I2V by accident.
    """
    project_root = Path(project_root).resolve()
    post_path = project_root / "build" / "post_production_manifest.json"
    post = read_json(post_path)
    contracts = project_root / "build" / "reference" / "contracts" / "index.json"
    jobs = []
    for shot in post.get("shots", []):
        task_id = shot["task_id"]
        staged_root = project_root / "build" / "render_inputs" / task_id
        shot_jobs = []
        for layer in sorted(shot.get("layers", []), key=lambda item: item["z_order"]):
            if layer["kind"] == "optional_occluder":
                shot_jobs.append({
                    "id": f"{task_id}__{layer['id']}",
                    "stage": "optional_occluder",
                    "state": "deferred_unless_review_requires_occluder",
                    "output": layer["media_path"],
                    "required": False,
                })
                continue
            inputs = [contracts]
            control = "reference_video_guidance"
            validation_errors = [
                f"invalid:conditioning_scope:{error}"
                for error in validate_conditioning_scope(layer)
            ]
            if layer["id"] == "k0l3k4_foreground":
                pose_path = Path(shot["k_skeleton_track"])
                inputs.extend([
                    pose_path,
                    staged_root / "k_start.png",
                    Path(next(
                        item["path"] for item in ltx_audit["models"]
                        if item["role"] == "motion_ic_lora"
                    )),
                ])
                validation_errors.extend(validate_shot_bounded_track(
                    pose_path, shot=shot, track_type="k_skeleton"
                ))
                control = "official_ltx_motion_track_ic_lora"
            if layer["id"] in {"held_hammer", "released_hammer"}:
                hammer_path = Path(shot["hammer_track"])
                inputs.append(hammer_path)
                validation_errors.extend(validate_shot_bounded_track(
                    hammer_path, shot=shot, track_type="hammer_rigid_body"
                ))
                control = (
                    "rigid_body_grip_track" if layer["id"] == "held_hammer"
                    else "rigid_body_release_track"
                )
            if layer["id"] == "tracked_green_insert":
                inputs.append(Path(shot["screen_corner_track"]))
                control = "four_corner_homography"
            missing = [str(path) for path in inputs if not path.is_file()]
            missing.extend(validation_errors)
            if control == "official_ltx_motion_track_ic_lora" and not ltx_audit["ready"]:
                missing.extend(f"ltx:{blocker}" for blocker in ltx_audit["blockers"])
            job = {
                "id": f"{task_id}__{layer['id']}",
                "stage": "render_layer" if layer["id"] != "tracked_green_insert" else "build_insert",
                "control": control,
                "conditioning_scope": layer.get("conditioning_scope"),
                "required": True,
                "inputs": [str(path) for path in inputs],
                "missing": sorted(set(missing)),
                "output": layer["media_path"],
                "matte_output": layer.get("matte_path"),
                "state": "ready" if not missing else "blocked",
            }
            shot_jobs.append(job)
        composite_inputs = [
            Path(item["output"])
            for item in shot_jobs
            if item.get("required") and item["stage"] in {"render_layer", "build_insert"}
        ]
        matte_inputs = [
            Path(item["matte_output"])
            for item in shot_jobs
            if item.get("required") and item.get("matte_output")
        ]
        missing_composite = [
            str(path) for path in [*composite_inputs, *matte_inputs] if not path.is_file()
        ]
        approval = shot.get("approval", {})
        if approval.get("state") != "approved":
            missing_composite.append(f"approval:{approval.get('state', 'missing')}")
        shot_jobs.append({
            "id": f"{task_id}__composite",
            "stage": "composite",
            "required": True,
            "inputs": [str(path) for path in [*composite_inputs, *matte_inputs]],
            "missing": sorted(set(missing_composite)),
            "output": str(Path(shot["layers"][0]["media_path"]).parents[1] / "composite.mp4"),
            "audio_policy": "strip_and_ignore",
            "state": "ready" if not missing_composite else "blocked",
        })
        jobs.extend(shot_jobs)
    required_jobs = [item for item in jobs if item.get("required")]
    ready_jobs = [item for item in required_jobs if item["state"] == "ready"]
    return {
        "schema_version": 1,
        "generated_at": now(),
        "project": project_root.name,
        "source_manifest": str(post_path),
        "execution_policy": {
            "no_text_only_fallback_for_k": True,
            "subject_conditioning": "strict_owner_only",
            "k_identity_lora_scope": "k_only",
            "pose_tracks": "single_shot_no_cross_cut",
            "hammer": "independent_rigid_body_layer_with_grip_and_release_states",
            "audio": "strip_and_ignore",
            "foreground_requires_alpha_or_matte": True,
            "approval_authority": "user",
        },
        "ltx_motion_preflight": ltx_audit,
        "summary": {
            "jobs": len(jobs),
            "required_jobs": len(required_jobs),
            "ready_jobs": len(ready_jobs),
            "blocked_jobs": len(required_jobs) - len(ready_jobs),
        },
        "ready": len(required_jobs) == len(ready_jobs),
        "jobs": jobs,
    }


def _make_dry_run_templates(root: Path) -> dict[str, Path]:
    """Create tiny visual-only media templates for execution proofs."""
    root.mkdir(parents=True, exist_ok=True)
    templates = {
        "opaque_mov": root / "opaque.mov",
        "alpha_mov": root / "alpha.mov",
        "matte_mov": root / "matte.mov",
        "composite_mp4": root / "composite.mp4",
    }
    commands = {
        "opaque_mov": [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=#243447:s=160x288:d=0.25:r=8",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(templates["opaque_mov"]),
        ],
        "alpha_mov": [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=#00cc88@0.55:s=160x288:d=0.25:r=8",
            "-vf", "format=argb", "-an", "-c:v", "qtrle",
            str(templates["alpha_mov"]),
        ],
        "matte_mov": [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=white:s=160x288:d=0.25:r=8",
            "-vf", "format=gray", "-an", "-c:v", "ffv1",
            str(templates["matte_mov"]),
        ],
        "composite_mp4": [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=#101820:s=160x288:d=0.25:r=8",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(templates["composite_mp4"]),
        ],
    }
    for key, command in commands.items():
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"failed to build dry-run {key}: {result.stderr[-2000:]}")
    return templates


def _concat_dry_run_visuals(inputs: list[Path], output: Path) -> Path:
    if not inputs:
        raise ValueError("dry-run assembly requires at least one input")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y"]
    for path in inputs:
        command.extend(["-i", str(path)])
    streams = "".join(f"[{index}:v]" for index in range(len(inputs)))
    command.extend([
        "-filter_complex", f"{streams}concat=n={len(inputs)}:v=1:a=0[outv]",
        "-map", "[outv]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output),
    ])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"failed to assemble dry-run reel: {result.stderr[-2000:]}")
    return output


def materialize_dry_run(
    queue_path: Path, output_root: Path, *, approved_by: str
) -> tuple[dict, Path]:
    """Complete every queue job with synthetic, non-production media."""
    if approved_by != "user":
        raise ValueError("dry-run approval must be explicitly attributed to user")
    queue_path = Path(queue_path).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    queue = read_json(queue_path)
    templates = _make_dry_run_templates(output_root / "_templates")
    completed = []
    verification = []
    for job in queue.get("jobs", []):
        stage = job["stage"]
        extension = ".mp4" if stage == "composite" else ".mov"
        artifact = output_root / "assets" / stage / f"{job['id']}{extension}"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        if stage == "composite":
            template = templates["composite_mp4"]
        elif stage == "optional_occluder" or job.get("matte_output"):
            template = templates["alpha_mov"]
        else:
            template = templates["opaque_mov"]
        shutil.copy2(template, artifact)
        matte = None
        if job.get("matte_output"):
            matte = output_root / "assets" / stage / f"{job['id']}__matte.mov"
            shutil.copy2(templates["matte_mov"], matte)
        report = inspect_visual_output(
            artifact,
            require_alpha=stage == "optional_occluder" or bool(job.get("matte_output")),
        )
        verification.append(report)
        completed.append({
            **job,
            "production_output": job.get("output"),
            "production_matte_output": job.get("matte_output"),
            "output": str(artifact),
            "matte_output": str(matte) if matte else None,
            "production_missing": job.get("missing", []),
            "missing": [],
            "state": "dry_run_complete",
            "production_artifact": False,
            "synthetic_inputs": True,
            "user_approval_assumed_for_dry_run": True,
        })
    failed = [item for item in verification if not item["passed"]]
    deliverables = []
    master_composites = [
        Path(item["output"]) for item in completed
        if item["stage"] == "composite" and "__master__composite" in item["id"]
    ]
    all_composites = [
        Path(item["output"]) for item in completed if item["stage"] == "composite"
    ]
    if master_composites:
        sequences_root = output_root / "sequences"
        for item in completed:
            if item["stage"] != "composite" or "__master__composite" not in item["id"]:
                continue
            parts = item["id"].split("__")
            scene_id = parts[1]
            sequence = sequences_root / f"{scene_id}.mp4"
            sequence.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["output"], sequence)
            deliverables.append({"kind": "scene_sequence", "scene_id": scene_id, "path": str(sequence)})
        master = _concat_dry_run_visuals(
            master_composites, output_root / "master" / "ad2184_dry_run_master.mp4"
        )
        deliverables.append({"kind": "dry_run_master", "path": str(master)})
    if all_composites:
        reel = _concat_dry_run_visuals(
            all_composites, output_root / "master" / "ad2184_all_coverage_reel.mp4"
        )
        deliverables.append({"kind": "all_coverage_reel", "path": str(reel)})
    deliverable_verification = [
        inspect_visual_output(Path(item["path"])) for item in deliverables
    ]
    failed.extend(item for item in deliverable_verification if not item["passed"])
    result = {
        "schema_version": 1,
        "generated_at": now(),
        "mode": "complete_synthetic_dry_run",
        "production_artifact": False,
        "source_queue": str(queue_path),
        "output_root": str(output_root),
        "approval": {
            "decision": "approved_for_dry_run_only",
            "approved_by": approved_by,
            "issues": [],
        },
        "policy": {
            "production_outputs_untouched": True,
            "missing_inputs_synthetically_overridden": True,
            "audio": "absent",
            "all_optional_jobs_materialized": True,
        },
        "summary": {
            "jobs": len(completed),
            "completed_jobs": len(completed) - len(failed),
            "failed_jobs": len(failed),
            "artifacts": (
                len(completed)
                + sum(bool(item.get("matte_output")) for item in completed)
                + len(deliverables)
            ),
            "deliverables": len(deliverables),
        },
        "ready": not failed and len(completed) == len(queue.get("jobs", [])),
        "verification": [*verification, *deliverable_verification],
        "deliverables": deliverables,
        "jobs": completed,
    }
    report_path = output_root / "dry_run_queue.json"
    write_json(report_path, result)
    return result, report_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit-ltx")
    audit.add_argument("--comfy-root", type=Path, required=True)
    audit.add_argument("--models-root", type=Path, required=True)
    audit.add_argument("--output", type=Path)
    audit.add_argument("--server-url", default="http://127.0.0.1:8188")
    audit.add_argument("--runtime-python", type=Path)
    audit.add_argument("--object-info", type=Path)
    compile_motion = subparsers.add_parser("compile-motion-workflow")
    compile_motion.add_argument("template", type=Path)
    compile_motion.add_argument("tracks", type=Path)
    compile_motion.add_argument("output", type=Path)
    compile_motion.add_argument("--metadata", type=Path)
    compile_motion.add_argument("--prompt", required=True)
    compile_motion.add_argument("--negative", default="identity drift, anatomy drift, flicker")
    compile_motion.add_argument("--input-image", required=True)
    compile_motion.add_argument("--output-prefix", required=True)
    compile_motion.add_argument("--duration", type=float, default=3.0)
    compile_motion.add_argument("--fps", type=int, default=24)
    compile_api = subparsers.add_parser("compile-motion-api")
    compile_api.add_argument("tracks", type=Path)
    compile_api.add_argument("output", type=Path)
    compile_api.add_argument("--metadata", type=Path)
    compile_api.add_argument("--prompt", required=True)
    compile_api.add_argument("--negative", default="identity drift, anatomy drift, flicker")
    compile_api.add_argument("--input-image", required=True)
    compile_api.add_argument("--output-prefix", required=True)
    compile_api.add_argument("--duration", type=float, default=3.0)
    compile_api.add_argument("--fps", type=int, default=24)
    compile_api.add_argument("--width", type=int, default=544)
    compile_api.add_argument("--height", type=int, default=960)
    compile_api.add_argument("--seed", type=int, default=32184)
    make_track = subparsers.add_parser("make-linear-track")
    make_track.add_argument("output", type=Path)
    make_track.add_argument("--frames", type=int, required=True)
    make_track.add_argument("--start-x", type=float, required=True)
    make_track.add_argument("--start-y", type=float, required=True)
    make_track.add_argument("--end-x", type=float, required=True)
    make_track.add_argument("--end-y", type=float, required=True)
    pose_track = subparsers.add_parser("pose-to-motion-tracks")
    pose_track.add_argument("pose_record", type=Path)
    pose_track.add_argument("output", type=Path)
    pose_track.add_argument("--provenance", type=Path, required=True)
    pose_track.add_argument("--start-index", type=int, required=True)
    pose_track.add_argument("--frames", type=int, required=True)
    pose_track.add_argument("--width", type=int, default=544)
    pose_track.add_argument("--height", type=int, default=960)
    pose_track.add_argument("--motion-scale", type=float, default=0.8)
    pose_track.add_argument("--shot-id", required=True)
    pose_track.add_argument("--source-start", type=float, required=True)
    pose_track.add_argument("--source-end", type=float, required=True)
    plan = subparsers.add_parser("plan-project")
    plan.add_argument("project", type=Path)
    plan.add_argument("--comfy-root", type=Path, required=True)
    plan.add_argument("--models-root", type=Path, required=True)
    plan.add_argument("--output", type=Path)
    plan.add_argument("--server-url", default="http://127.0.0.1:8188")
    plan.add_argument("--runtime-python", type=Path)
    plan.add_argument("--object-info", type=Path)
    inspect = subparsers.add_parser("inspect-output")
    inspect.add_argument("media", type=Path)
    inspect.add_argument("--require-alpha", action="store_true")
    compose = subparsers.add_parser("composite")
    compose.add_argument("plate", type=Path)
    compose.add_argument("output", type=Path)
    compose.add_argument("layers", type=Path, nargs="+")
    compose.add_argument("--report", type=Path)
    compose.add_argument(
        "--proof-scope", choices=("production", "synthetic_technical"), default="production"
    )
    dry_run = subparsers.add_parser("dry-run-project")
    dry_run.add_argument("queue", type=Path)
    dry_run.add_argument("--output-root", type=Path, required=True)
    dry_run.add_argument("--approved-by", choices=("user",), required=True)
    arguments = parser.parse_args()
    if arguments.command == "audit-ltx":
        report = audit_ltx_install(
            arguments.comfy_root, arguments.models_root, arguments.server_url,
            arguments.runtime_python, arguments.object_info,
        )
        if arguments.output:
            write_json(arguments.output, report)
        print(json.dumps(report, indent=2))
        return 0 if report["ready"] else 2
    if arguments.command == "compile-motion-workflow":
        workflow, metadata = configure_motion_track_workflow(
            read_json(arguments.template),
            prompt=arguments.prompt,
            negative=arguments.negative,
            input_image=arguments.input_image,
            tracks=read_json(arguments.tracks),
            output_prefix=arguments.output_prefix,
            duration_seconds=arguments.duration,
            fps=arguments.fps,
        )
        write_json(arguments.output, workflow)
        metadata.update({
            "workflow": str(arguments.output),
            "tracks": str(arguments.tracks),
            "status": "compiled_not_executed",
        })
        if arguments.metadata:
            write_json(arguments.metadata, metadata)
        print(json.dumps(metadata, indent=2))
        return 0
    if arguments.command == "compile-motion-api":
        graph, metadata = visual_only_motion_api_graph(
            prompt=arguments.prompt,
            negative=arguments.negative,
            input_image=arguments.input_image,
            tracks=read_json(arguments.tracks),
            output_prefix=arguments.output_prefix,
            duration_seconds=arguments.duration,
            fps=arguments.fps,
            width=arguments.width,
            height=arguments.height,
            seed=arguments.seed,
        )
        write_json(arguments.output, graph)
        metadata.update({"workflow": str(arguments.output), "tracks": str(arguments.tracks), "status": "compiled_not_executed"})
        if arguments.metadata:
            write_json(arguments.metadata, metadata)
        print(json.dumps(metadata, indent=2))
        return 0
    if arguments.command == "make-linear-track":
        if arguments.frames < 2:
            raise ValueError("frames must be at least 2")
        track = []
        for frame in range(arguments.frames):
            fraction = frame / (arguments.frames - 1)
            track.append({
                "x": arguments.start_x + (arguments.end_x - arguments.start_x) * fraction,
                "y": arguments.start_y + (arguments.end_y - arguments.start_y) * fraction,
            })
        write_json(arguments.output, [track])
        print(json.dumps({
            "output": str(arguments.output),
            "tracks": 1,
            "frames": arguments.frames,
            "status": "synthetic_test_track_not_production_tracking",
        }, indent=2))
        return 0
    if arguments.command == "pose-to-motion-tracks":
        tracks, provenance = pose_record_to_motion_tracks(
            read_json(arguments.pose_record),
            start_index=arguments.start_index,
            frame_count=arguments.frames,
            width=arguments.width,
            height=arguments.height,
            anchors={
                "root": (0.50, 0.56),
                "upper_torso": (0.50, 0.34),
                "left_wrist": (0.61, 0.31),
                "right_wrist": (0.42, 0.43),
            },
            motion_scale=arguments.motion_scale,
            shot_id=arguments.shot_id,
            source_start_seconds=arguments.source_start,
            source_end_seconds=arguments.source_end,
        )
        write_json(arguments.output, tracks)
        provenance.update({
            "generated_at": now(),
            "source": str(arguments.pose_record),
            "output": str(arguments.output),
            "status": "derived_from_observed_pose",
        })
        write_json(arguments.provenance, provenance)
        print(json.dumps(provenance, indent=2))
        return 0
    if arguments.command == "plan-project":
        audit_report = audit_ltx_install(
            arguments.comfy_root, arguments.models_root, arguments.server_url,
            arguments.runtime_python, arguments.object_info,
        )
        report = compile_reconstruction_queue(arguments.project, audit_report)
        output = arguments.output or arguments.project / "build" / "reconstruction_render_queue.json"
        write_json(output, report)
        print(json.dumps({**report["summary"], "ready": report["ready"], "output": str(output)}, indent=2))
        return 0 if report["ready"] else 2
    if arguments.command == "inspect-output":
        report = inspect_visual_output(arguments.media, arguments.require_alpha)
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 2
    if arguments.command == "dry-run-project":
        result, report_path = materialize_dry_run(
            arguments.queue, arguments.output_root, approved_by=arguments.approved_by
        )
        print(json.dumps({
            **result["summary"], "ready": result["ready"],
            "report": str(report_path),
        }, indent=2))
        return 0 if result["ready"] else 2
    report = composite_visual_layers(
        arguments.plate, arguments.layers, arguments.output, arguments.proof_scope
    )
    if arguments.report:
        write_json(arguments.report, report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
