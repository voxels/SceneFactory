#!/usr/bin/env python3
"""Audit whether each declared modality reached a real downstream consumer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import identity_pipeline as identity


def _read(path: Path) -> dict[str, Any] | None:
    return identity.read_json(path) if path.is_file() else None


def _evidence(path: Path, *, status: str, consumer: str, detail: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {"status": status, "consumer": consumer, "path": str(path), "present": path.is_file()}
    if path.is_file():
        record["sha256"] = identity.sha256_file(path)
    if detail:
        record["detail"] = detail
    return record


def _completed_image_training(project_root: Path) -> bool:
    plan = _read(project_root / "build/training/image_identity/training_plan.json")
    if not plan or not plan.get("experiments"):
        return False
    for experiment in plan["experiments"]:
        output = Path(experiment.get("output_dir", ""))
        marker = output / "experiment_complete.json"
        adapter = output / "pytorch_lora_weights.safetensors"
        if not marker.is_file() or not adapter.is_file():
            return False
    return True


def _has_image_execution(project_root: Path, route: str | None = None) -> bool:
    execution_root = project_root / "build/workflows/image_ablation/executions"
    for path in execution_root.glob("*.json"):
        record = _read(path)
        if not record or record.get("status") != "complete":
            continue
        if route and record.get("route") != route:
            continue
        if record.get("downloaded_outputs") and all(item.get("sha256") for item in record["downloaded_outputs"]):
            return True
    return False


def _has_usdz_control_execution(project_root: Path) -> bool:
    execution_root = project_root / "build/workflows/image_ablation/executions"
    for path in execution_root.glob("*.json"):
        record = _read(path)
        if record and record.get("geometry_control_consumed") is True:
            return True
    return False


def build_consumption_report(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    identity.validate_config(config)
    identity_root = project_root / "build/identity"
    image_manifest = _read(identity_root / "processed_manifest.json")
    selection = _read(identity_root / "selection_manifest.json")
    video = _read(identity_root / "video_audio_manifest.json")
    usdz = _read(identity_root / "geometry/usdz_ingestion_manifest.json")
    workflows = _read(project_root / "build/workflows/image_ablation/manifest.json")
    promotion = _read(project_root / "build/training/image_identity/promoted/promotion_manifest.json")
    image_training = _completed_image_training(project_root)
    video_training = _read(project_root / "build/training/video_identity/training_plan.json")
    video_promotion = project_root / "build/training/video_identity/promoted/pytorch_lora_weights.safetensors"
    video_runtime = _read(project_root / "build/identity/video/video_runtime.json")
    stub_manifest_path = project_root / "build/stubs/stub_manifest.json"
    stub_manifest = _read(stub_manifest_path)
    evidence = {
        "photographic_identity": _evidence(
            identity_root / "processed_manifest.json",
            status="consumed" if image_manifest and selection and image_training else "prepared" if image_manifest and selection else "blocked",
            consumer="flux2_klein_subject_lora_dataset",
            detail=(f"selected={len((selection or {}).get('selections', []))}; trainer checkpoints complete" if image_training
                    else f"selected={len((selection or {}).get('selections', []))}; trainer consumption not complete" if selection
                    else "selection manifest missing"),
        ),
        "visual_identity_video": _evidence(
            identity_root / "video/visual_identity_manifest.json",
            status="consumed" if video and (video.get("visual_identity") or {}).get("clip_count", 0) > 0 and video_training and video_training.get("status") in {"complete", "promoted"} and video_promotion.is_file() else "prepared" if video and (video.get("visual_identity") or {}).get("clip_count", 0) > 0 else "blocked",
            consumer="ltx_identity_clip_dataset",
            detail=(f"clips={(video or {}).get('visual_identity', {}).get('clip_count', 0)}; promoted LTX trainer output present" if video_promotion.is_file() and video_training and video_training.get("status") in {"complete", "promoted"}
                    else f"clips={(video or {}).get('visual_identity', {}).get('clip_count', 0)}; clips prepared, LTX trainer consumption pending"),
        ),
        "motion_reference_video": _evidence(
            identity_root / "video/motion_reference_manifest.json",
            status="consumed" if video_runtime and video_runtime.get("status") == "complete" and video_runtime.get("motion_control_consumed") is True else "prepared" if video and (video.get("motion_reference") or {}).get("status") == "ready" else "blocked",
            consumer="ltx_motion_or_union_control",
            detail=(f"tracks={(video or {}).get('motion_reference', {}).get('tracks', []) and len(video['motion_reference']['tracks'])}; control execution verified" if video_runtime and video_runtime.get("motion_control_consumed") is True
                    else f"tracks={(video or {}).get('motion_reference', {}).get('tracks', []) and len(video['motion_reference']['tracks'])}; guide prepared, control execution pending"),
        ),
        "usdz_geometry": _evidence(
            identity_root / "geometry/usdz_ingestion_manifest.json",
            status="consumed" if usdz and all(item.get("derived_controls", {}).get("consumed") for item in usdz.get("records", [])) and _has_usdz_control_execution(project_root) else "prepared" if usdz and all(item.get("derived_controls", {}).get("consumed") for item in usdz.get("records", [])) else "blocked",
            consumer="geometry_control_render_and_structural_ablation",
            detail=(f"controls={(usdz or {}).get('counts', {}).get('controls_bound', 0)}; geometry control execution verified" if _has_usdz_control_execution(project_root)
                    else f"controls={(usdz or {}).get('counts', {}).get('controls_bound', 0)}; renders prepared, structural execution pending"),
        ),
        "voice_performance": _evidence(
            identity_root / "video/audio_alignment_manifest.json",
            status="consumed" if video and (video.get("audio") or {}).get("audio") else "blocked",
            consumer="authoritative_audio_mux_and_viseme_alignment",
            detail=(video or {}).get("audio", {}).get("alignment_status"),
        ),
        "image_runtime": _evidence(
            project_root / "build/workflows/image_ablation/manifest.json",
            status="consumed" if workflows and promotion and _has_image_execution(project_root, promotion.get("route")) else "prepared" if workflows else "blocked",
            consumer="comfyui_connected_image_generation",
            detail=("promoted route has hash-verified execution evidence" if promotion and _has_image_execution(project_root, promotion.get("route"))
                    else "compiled routes prepared; promotion and connected execution evidence required"),
        ),
    }
    blockers = [f"{name}: {item.get('detail', 'missing consumer evidence')}" for name, item in evidence.items() if item["status"] != "consumed"]
    report = {
        "schema_version": 1,
        "identity_id": config["identity"]["id"],
        "status": "complete" if not blockers else "blocked",
        "evidence": evidence,
        "stubs": {
            "path": str(stub_manifest_path),
            "present": stub_manifest is not None,
            "status": (stub_manifest or {}).get("status"),
            "production_ready": (stub_manifest or {}).get("production_ready", False),
            "does_not_count_as_consumed": (stub_manifest or {}).get("does_not_count_as_consumed", True),
        },
        "blockers": blockers,
        "invariant": "a modality is consumed only when a concrete derived artifact is connected to a downstream trainer or executing runtime",
    }
    output = project_root / "build/validation/modality_consumption_report.json"
    identity.write_json(output, report)
    return report
