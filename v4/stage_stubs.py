#!/usr/bin/env python3
"""Emit explicit non-production contracts for unavailable downstream stages.

Stubs make the handoff boundaries executable and reviewable while preserving the
invariant that a prepared modality is not reported as consumed until a real
trainer or runtime writes verified output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import identity_pipeline as identity


def _file_ref(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path.resolve()), "present": path.is_file()}
    if path.is_file():
        record["sha256"] = identity.sha256_file(path)
    return record


def emit(project_root: Path) -> dict[str, Any]:
    """Write deterministic stubs for currently blocked production handoffs."""
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    identity.validate_config(config)
    build = project_root / "build"
    stubs = project_root / "build/stubs"
    stubs.mkdir(parents=True, exist_ok=True)

    entries = [
        {
            "id": "ltx_identity_training",
            "status": "blocked_stub",
            "production_ready": False,
            "reason": "official LTX 2.5 trainer is not installed",
            "consumer": "ltx_identity_clip_dataset",
            "inputs": {
                "visual_identity_manifest": _file_ref(build / "identity/video/visual_identity_manifest.json"),
                "training_plan": _file_ref(build / "training/video_identity/training_plan.json"),
            },
            "expected_outputs": [
                "build/training/video_identity/promoted/pytorch_lora_weights.safetensors",
                "build/training/video_identity/promoted/promotion_manifest.json",
            ],
            "resume_command": "./v4/scene-factory-v4 train-video-identity --project v4/examples/modeling_interview",
        },
        {
            "id": "motion_control_execution",
            "status": "blocked_stub",
            "production_ready": False,
            "reason": "LTX motion/Union control execution has not run",
            "consumer": "ltx_motion_or_union_control",
            "inputs": {
                "motion_reference_manifest": _file_ref(build / "identity/video/motion_reference_manifest.json"),
                "skeleton_manifest": _file_ref(build / "identity/motion/skeleton_manifest.json"),
            },
            "expected_outputs": [
                "build/identity/video/video_runtime.json (status=complete, motion_control_consumed=true)",
                "build/identity/video/generated/*.mp4",
            ],
            "resume_command": "./v4/scene-factory-v4 generate-video --project v4/examples/modeling_interview",
        },
        {
            "id": "usdz_structural_control_execution",
            "status": "blocked_stub",
            "production_ready": False,
            "reason": "compatible depth/normal/silhouette/pose control route has not executed",
            "consumer": "geometry_control_render_and_structural_ablation",
            "inputs": {
                "usdz_manifest": _file_ref(build / "identity/geometry/usdz_ingestion_manifest.json"),
                "control_manifest": _file_ref(build / "identity/geometry/geometry_control_manifest.json"),
            },
            "expected_outputs": [
                "build/workflows/image_ablation/executions/*geometry_control*.json",
                "geometry_control_consumed=true",
            ],
            "resume_command": "./v4/scene-factory-v4 benchmark-image-controls --project v4/examples/modeling_interview",
        },
        {
            "id": "tts_audio_alignment",
            "status": "blocked_stub",
            "production_ready": False,
            "reason": "authoritative waveform for voice/tts_text.txt is missing",
            "consumer": "authoritative_audio_mux_and_viseme_alignment",
            "inputs": {
                "transcript": _file_ref(build / "test-package-current/transcript/voice_script__tts_text__8ced8a23e2e4.txt"),
                "audio_drop_location": str((project_root / "voice").resolve()),
            },
            "expected_outputs": [
                "build/identity/video/audio_alignment_manifest.json (alignment_status=complete)",
                "build/identity/video/generated/final_with_audio.mp4",
            ],
            "resume_command": "./v4/scene-factory-v4 prepare-video-audio --project v4/examples/modeling_interview",
        },
        {
            "id": "unreal_metal_runtime",
            "status": "blocked_stub",
            "production_ready": False,
            "reason": "Xcode Metal Toolchain is missing or unusable on macOS 27",
            "consumer": "unreal_avatar_runtime",
            "inputs": {
                "uproject": _file_ref(project_root / "SceneFactoryV4.uproject"),
                "avatar_manifest": _file_ref(build / "avatar/gage_portrait/avatar_manifest.json"),
            },
            "expected_outputs": [
                "UE commandlet/render proof with Metal backend",
                "final USDZ + Gaussian splat runtime validation",
            ],
            "resume_command": "xcodebuild -downloadComponent MetalToolchain",
        },
    ]
    # These graphs describe the exact downstream wiring without pretending that
    # unavailable nodes/checkpoints have executed. They are intentionally kept
    # outside the production workflow manifest so they cannot be queued by the
    # normal image/video executors.
    graphs = {
        "ltx25_video_identity_stub.json": {
            "schema_version": 1,
            "graph_type": "comfyui_api_contract",
            "status": "blocked_stub",
            "production_ready": False,
            "queue_submission_allowed": False,
            "required_nodes": [
                {"id": "model", "class_type": "LTX25ModelLoader", "path": "/Users/voxels/Library/Application Support/LTXDesktop/models/ltx-2.5/ltx-2.5-22b-distilled-transformer-bf16.safetensors", "present": True},
                {"id": "text_encoder", "class_type": "Gemma4LTXEncoder", "path": "/Users/voxels/ComfyUI-Shared/models/text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "present": True},
                {"id": "identity_lora", "class_type": "LTXVLoRALoader", "path": "build/training/video_identity/promoted/pytorch_lora_weights.safetensors", "present": False},
                {"id": "visual_reference", "class_type": "LoadVideoFrames", "path": "build/identity/video/visual_identity_manifest.json", "present": True},
                {"id": "motion_control", "class_type": "LTXMotionControl", "path": "build/identity/video/motion_reference_manifest.json", "present": True},
                {"id": "union_control", "class_type": "LTXUnionControl", "path": "build/identity/geometry/usdz_ingestion_manifest.json", "present": True},
                {"id": "audio", "class_type": "LoadAudio", "path": "voice/tts_text.wav", "present": False},
                {"id": "sampler", "class_type": "LTX25Sampler"},
                {"id": "output", "class_type": "SaveVideo", "path": "build/identity/video/generated/final_with_audio.mp4"},
            ],
            "connections": [
                ["model", "sampler", "model"],
                ["text_encoder", "sampler", "conditioning"],
                ["identity_lora", "sampler", "identity_adapter"],
                ["visual_reference", "sampler", "reference_frames"],
                ["motion_control", "sampler", "motion_control"],
                ["union_control", "sampler", "structural_control"],
                ["audio", "sampler", "audio"],
                ["sampler", "output", "video"],
            ],
            "blockers": [
                "official LTX 2.5 trainer/promotion is unavailable",
                "LTX ComfyUI video node package is unavailable",
                "authoritative TTS waveform is unavailable",
            ],
            "invariant": "this graph is a wiring contract only; it must not be submitted or counted as consumed",
        },
        "usdz_structural_control_stub.json": {
            "schema_version": 1,
            "graph_type": "comfyui_api_contract",
            "status": "blocked_stub",
            "production_ready": False,
            "queue_submission_allowed": False,
            "required_nodes": [
                {"id": "base_model", "class_type": "UNETLoader", "path": "local FLUX.2 Klein base installation"},
                {"id": "rgb", "class_type": "LoadImageBatch", "role": "rgb", "path": "build/identity/geometry"},
                {"id": "depth", "class_type": "LoadImageBatch", "role": "depth", "path": "build/identity/geometry"},
                {"id": "normal", "class_type": "LoadImageBatch", "role": "normal", "path": "build/identity/geometry"},
                {"id": "silhouette", "class_type": "LoadImageBatch", "role": "silhouette", "path": "build/identity/geometry"},
                {"id": "pose", "class_type": "LoadImageBatch", "role": "pose", "path": "build/identity/geometry"},
                {"id": "controlnet", "class_type": "Flux2ControlNetUnion", "path": "JLC-Flux2-ControlNet (not installed)", "present": False},
                {"id": "output", "class_type": "SaveImage", "path": "build/workflows/image_ablation/executions/geometry_control"},
            ],
            "connections": [
                ["rgb", "base_model", "reference"],
                ["depth", "controlnet", "depth"],
                ["normal", "controlnet", "normal"],
                ["silhouette", "controlnet", "silhouette"],
                ["pose", "controlnet", "pose"],
                ["controlnet", "base_model", "conditioning"],
                ["base_model", "output", "images"],
            ],
            "blockers": [
                "compatible FLUX.2 ControlNet Union checkpoint is unavailable",
                "JLC-Flux2-ControlNet node is unavailable",
            ],
            "invariant": "rendered USDZ controls remain prepared, not consumed, until this graph executes with a compatible control route",
        },
    }
    manifest = {
        "schema_version": 1,
        "identity_id": config["identity"]["id"],
        "status": "stubbed",
        "production_ready": False,
        "does_not_count_as_consumed": True,
        "invariant": "stubs never satisfy modality consumption, promotion, packaging, or final-run completion",
        "entries": entries,
    }
    identity.write_json(stubs / "stub_manifest.json", manifest)
    for entry in entries:
        identity.write_json(stubs / f"{entry['id']}.json", entry)
    workflow_root = project_root / "build/workflows/stubs"
    workflow_root.mkdir(parents=True, exist_ok=True)
    for filename, graph in graphs.items():
        identity.write_json(workflow_root / filename, graph)
    manifest["workflow_stubs"] = [str((workflow_root / filename).resolve()) for filename in sorted(graphs)]
    identity.write_json(stubs / "stub_manifest.json", manifest)
    return manifest
