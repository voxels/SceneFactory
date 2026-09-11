#!/usr/bin/env python3
"""Compile the native ComfyUI LTX 2.5 identity/motion graph.

This compiler is deliberately separate from video generation.  It creates a
hashable, executable API graph when the local native LTX nodes and weights are
available, while keeping training, supplied-audio, and promotion gates honest.
The graph uses the visual-identity keyframe and motion-reference video as
independent guides; motion-only material never becomes an identity keyframe.
"""

from __future__ import annotations

import copy
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import identity_pipeline as identity
from image_workflows import validate_api_graph


COMFY_ROOT = Path("/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI")
SHARED_MODELS = Path("/Users/voxels/ComfyUI-Shared/models")
LTX_TRANSFORMER = "ltx-2.5-22b-distilled-transformer-bf16.safetensors"
LTX_VIDEO_VAE = "ltx-2.5-video-vae-bf16.safetensors"
LTX_AUDIO_VAE = "ltx-2.5-audio-vae-bf16.safetensors"
LTX_TEXT_ENCODER = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
LTX_CLIP_CHECKPOINT = "sdpose_wholebody_fp16.safetensors"
MOTION_LORA = "ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors"
REQUIRED_NODES = (
    "UNETLoader", "VAELoaderKJ", "LTXAVTextEncoderLoader", "CLIPTextEncode",
    "LTXVConditioning", "LoadImage", "LTXVPreprocess",
    "EmptyLTXVLatentVideo", "LTXVAddGuide", "VHS_LoadVideoFFmpegPath",
    "LTX2LoraLoaderAdvanced", "ModelSamplingLTXV", "LTXVScheduler",
    "LTXVDualCFGGuider", "RandomNoise", "KSamplerSelect",
    "SamplerCustomAdvanced", "DecodeAndSaveVideo",
)


def _node(class_type: str, **inputs: Any) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def _link(node_id: str, output: int = 0) -> list[Any]:
    return [str(node_id), output]


def _first_visual_frame(project_root: Path) -> Path:
    path = project_root / "build/identity/video/visual_identity_manifest.json"
    if not path.is_file():
        raise ValueError("visual identity manifest is missing; run prepare-video-audio first")
    data = identity.read_json(path)
    for clip in data.get("clips", []):
        for frame in clip.get("frames", []):
            candidate = Path(frame.get("path", ""))
            if candidate.is_file():
                return candidate.resolve()
    raise ValueError("visual identity manifest has no usable keyframe")


def _first_motion_video(project_root: Path) -> Path:
    path = project_root / "build/identity/video/motion_reference_manifest.json"
    if not path.is_file():
        raise ValueError("motion reference manifest is missing; run prepare-video-audio first")
    data = identity.read_json(path)
    for source in data.get("sources", []):
        candidate = Path(source.get("path", ""))
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError("motion reference manifest has no usable source video")


def _stage_input(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = identity.sha256_file(source)
    if destination.is_file() and identity.sha256_file(destination) != digest:
        raise ValueError(f"video workflow input collision: {destination}")
    if not destination.exists():
        shutil.copy2(source, destination)
    return {"source": str(source), "source_sha256": digest, "staged": str(destination),
            "staged_sha256": identity.sha256_file(destination),
            "staged_filename": destination.name}


def _audio_input(project_root: Path) -> Path | None:
    manifest = project_root / "build/identity/video/audio_alignment_manifest.json"
    if not manifest.is_file():
        return None
    data = identity.read_json(manifest)
    for item in data.get("audio", []):
        candidate = Path(item.get("path", ""))
        if candidate.is_file() and item.get("status") == "ready":
            return candidate.resolve()
    return None


def _local_node_contract() -> dict[str, Any]:
    native_files = {
        "UNETLoader": COMFY_ROOT / "nodes.py",
        "VAELoaderKJ": COMFY_ROOT / "custom_nodes/comfyui-kjnodes",
        "LTXAVTextEncoderLoader": COMFY_ROOT / "comfy_extras/nodes_lt_audio.py",
        "LTXVLoRA": COMFY_ROOT / "custom_nodes/comfyui-ltxvideolora",
    }
    # Most native LTX classes ship in nodes_lt.py; the custom conditioning node
    # is optional because the standard LTXVConditioning node is equivalent.
    native_files.update({name: COMFY_ROOT / "comfy_extras/nodes_lt.py" for name in REQUIRED_NODES
                         if name not in native_files})
    present = {name: path.exists() for name, path in native_files.items()}
    return {"required_nodes": list(REQUIRED_NODES), "local_files": present,
            "native_ltx_nodes_present": all(present.get(name, False) for name in REQUIRED_NODES),
            "motion_lora_node_present": present.get("LTXVLoRA", False)}


def _probe_nodes(server_url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(server_url.rstrip("/") + "/object_info", timeout=5) as response:
            value = json.loads(response.read().decode())
        names = set(value) if isinstance(value, dict) else set()
        return {"status": "available", "url": server_url.rstrip("/"),
                "available_nodes": sorted(names),
                "missing_nodes": [name for name in REQUIRED_NODES if name not in names]}
    except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as error:
        return {"status": "unreachable", "url": server_url.rstrip("/"),
                "reason": f"{type(error).__name__}: {error}"}


def compile_workflow(project_root: Path, *, width: int = 768, height: int = 512,
                     length: int = 49, frame_rate: float = 24.0,
                     server_url: str | None = None) -> dict[str, Any]:
    """Compile a hashable native LTX graph and its input/model contract."""
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    identity.validate_config(config)
    if length < 9 or (length - 1) % 8:
        raise ValueError("LTX video length must be 8*n+1 and at least 9 frames")
    visual = _first_visual_frame(project_root)
    motion = _first_motion_video(project_root)
    input_root = project_root / "build/workflows/video_runtime/input"
    staged_visual = _stage_input(visual, input_root / ("identity_keyframe" + visual.suffix))
    staged_motion = _stage_input(motion, input_root / ("motion_reference" + motion.suffix))
    trigger = config["identity"].get("trigger_token", f"{config['identity']['id']}_identity")
    prompt = f"{trigger}, natural talking-head portrait, accurate facial identity, stable camera, realistic skin"
    negative = "extra people, identity drift, distorted face, duplicate limbs, text, watermark, flicker"

    graph: dict[str, dict[str, Any]] = {
        "1": _node("UNETLoader", unet_name=LTX_TRANSFORMER, weight_dtype="default"),
        "2": _node("VAELoaderKJ", vae_name=LTX_VIDEO_VAE, device="main_device", weight_dtype="bf16"),
        "3": _node("LTXAVTextEncoderLoader", text_encoder=LTX_TEXT_ENCODER,
                   ckpt_name=LTX_CLIP_CHECKPOINT, device="default"),
        "4": _node("CLIPTextEncode", clip=_link("3"), text=prompt),
        "5": _node("CLIPTextEncode", clip=_link("3"), text=negative),
        "6": _node("LTXVConditioning", positive=_link("4"), negative=_link("5"), frame_rate=frame_rate),
        "7": _node("LoadImage", image=staged_visual["staged_filename"]),
        "8": _node("LTXVPreprocess", image=_link("7"), img_compression=35),
        "9": _node("EmptyLTXVLatentVideo", width=width, height=height, length=length, batch_size=1),
        # Identity is seeded first; motion is a separate guide and cannot alter
        # the visual-identity dataset or its source-role manifest.
        "10": _node("LTXVAddGuide", positive=_link("6", 0), negative=_link("6", 1), vae=_link("2"),
                    latent=_link("9"), image=_link("8"), frame_idx=0, strength=1.0),
        "11": _node("VHS_LoadVideoFFmpegPath", video=staged_motion["staged"], force_rate=frame_rate,
                    custom_width=width, custom_height=height, frame_load_cap=length, start_time=0.0,
                    format="LTXV", vae=_link("2")),
        "12": _node("LTXVAddGuide", positive=_link("10", 0), negative=_link("10", 1), vae=_link("2"),
                    latent=_link("10", 2), image=_link("11", 0), frame_idx=0, strength=0.35),
        "13": _node("LTX2LoraLoaderAdvanced", lora_name=MOTION_LORA, model=_link("1"),
                    strength_model=1.0, video=1.0, video_to_audio=0.8, audio=0.8, audio_to_video=0.8, other=1.0),
        "14": _node("ModelSamplingLTXV", model=_link("13"), max_shift=2.05, base_shift=0.95),
        "15": _node("LTXVScheduler", steps=20, max_shift=2.05, base_shift=0.95, stretch=True, terminal=0.1),
        "16": _node("LTXVDualCFGGuider", model=_link("14"), positive=_link("12", 0), negative=_link("12", 1),
                    video_cfg=3.0, audio_cfg=3.0),
        "17": _node("RandomNoise", noise_seed=260801),
        "18": _node("KSamplerSelect", sampler_name="euler"),
        "19": _node("SamplerCustomAdvanced", noise=_link("17"), guider=_link("16"), sampler=_link("18"),
                    sigmas=_link("15"), latent_image=_link("12", 2)),
        "20": _node("DecodeAndSaveVideo", video_latent=_link("19", 0), fps=frame_rate,
                    filename_prefix="scene_factory_v4_video/identity_motion", format="mp4", codec="h264",
                    video_vae=_link("2"), tiling="disabled"),
    }
    audio = _audio_input(project_root)
    audio_staging = None
    if audio:
        audio_staging = _stage_input(audio, input_root / ("authoritative_audio" + audio.suffix))
        graph["21"] = _node("LoadAudio", audio=audio_staging["staged_filename"])
        graph["22"] = _node("VAELoaderKJ", vae_name=LTX_AUDIO_VAE, device="main_device", weight_dtype="bf16")
        graph["23"] = _node("LTXVAudioVAEEncode", audio=_link("21"), audio_vae=_link("22"))
        graph["20"]["inputs"]["audio_latent"] = _link("23")
    validate_api_graph(graph)
    out_dir = project_root / "build/workflows/video_runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    graph_path = out_dir / "ltx25_identity_motion.json"
    identity.write_json(graph_path, graph)
    contract = {
        "schema_version": 1, "status": "compiled", "identity_id": config["identity"]["id"],
        "graph": str(graph_path), "graph_sha256": identity.sha256_file(graph_path),
        "required_nodes": list(REQUIRED_NODES),
        "required_models": [LTX_TRANSFORMER, LTX_VIDEO_VAE, LTX_TEXT_ENCODER, LTX_CLIP_CHECKPOINT, MOTION_LORA],
        "inputs": {"visual_identity_keyframe": staged_visual, "motion_reference_video": staged_motion,
                   "authoritative_audio": audio_staging},
        "controls": {"identity_keyframe": True, "motion_reference": True, "motion_lora": True,
                     "ingredients_ic_lora": False, "union_control": False,
                     "structural_control_reason": "no compatible local FLUX/LTX Union checkpoint"},
        "audio": {"bound": bool(audio_staging), "source_bytes_preserved": bool(audio_staging),
                   "alignment_required": True},
        "training": {"identity_lora_bound": False, "reason": "no promoted LTX identity LoRA"},
        "node_contract": _local_node_contract(),
        "server_contract": _probe_nodes(server_url) if server_url else None,
        "execution_allowed": False,
        "execution_blockers": ([] if audio_staging else ["authoritative TTS audio is missing"])
        + ["promoted LTX identity LoRA is missing"],
        "invariant": "visual identity and motion guides remain separate; this graph does not promote adapters",
    }
    identity.write_json(out_dir / "video_runtime_contract.json", contract)
    return {"status": "compiled", "graph": str(graph_path), "contract": contract}
