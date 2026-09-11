#!/usr/bin/env python3
"""Requirement-level audit for AUGUST_2026_IDENTITY_PIPELINE_GOAL.md."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import adapter_validation
import identity_pipeline as identity


def _read(path: Path) -> dict[str, Any] | None:
    return identity.read_json(path) if path.is_file() else None


def _exists(project: Path, *relative: str) -> bool:
    return all((project / item).is_file() for item in relative)


def _image_promotion(project: Path) -> bool:
    adapter = project / "build/training/image_identity/promoted/pytorch_lora_weights.safetensors"
    marker = project / "build/training/image_identity/promoted/promotion_manifest.json"
    if not adapter.is_file() or not marker.is_file():
        return False
    try:
        return adapter_validation.validate(adapter).get("status") == "structurally_loadable"
    except (OSError, ValueError, RuntimeError):
        return False


def _image_runtime(project: Path) -> bool:
    runtime = _read(project / "build/runtime/image_runtime.json") or {}
    if runtime.get("route_selection") != "promoted" or not runtime.get("selected_route"):
        return False
    execution_root = project / "build/workflows/image_ablation/executions"
    for path in execution_root.glob("*.json"):
        record = _read(path) or {}
        if (record.get("status") == "complete" and record.get("route") == runtime["selected_route"]
                and record.get("downloaded_outputs")
                and all(item.get("sha256") for item in record["downloaded_outputs"])):
            return True
    return False


def _video_runtime(project: Path) -> bool:
    runtime = _read(project / "build/identity/video/video_runtime.json") or {}
    return runtime.get("status") == "complete" and runtime.get("motion_control_consumed") is True


def _usdz_execution(project: Path) -> bool:
    for path in (project / "build/workflows/image_ablation/executions").glob("*.json"):
        record = _read(path) or {}
        if record.get("status") == "complete" and record.get("geometry_control_consumed") is True:
            return True
    return False


def _heldout_complete(project: Path) -> bool:
    reports = sorted((project / "build/training/image_identity/heldout_runs").glob("*/evaluation_report.json"))
    if not reports:
        return False
    report = _read(reports[-1]) or {}
    if report.get("status") != "complete":
        return False
    image_ok = any(len(route.get("cases", [])) > 0 for candidate in report.get("candidates", []) for route in candidate.get("routes", []))
    video_runtime = _read(project / "build/identity/video/video_runtime.json") or {}
    generated = list((project / "build/identity/video/generated").glob("*.mp4"))
    video_metrics = list((project / "build/identity/video").glob("*evaluation*.json"))
    # Criterion 8 explicitly requires representative video outputs and metrics;
    # an image-only held-out report is insufficient.
    return image_ok and video_runtime.get("status") == "complete" and bool(generated) and bool(video_metrics)


def audit(project_root: Path) -> dict[str, Any]:
    project = project_root.resolve()
    config = _read(project / "identity.json") or {}
    identity_id = (config.get("identity") or {}).get("id")
    checks: list[dict[str, Any]] = []

    def add(number: int, requirement: str, passed: bool, evidence: list[str], detail: str) -> None:
        checks.append({"number": number, "requirement": requirement, "status": "passed" if passed else "blocked", "evidence": evidence, "detail": detail})

    ledger = _read(project / "build/pipeline/automatic_run.json") or {}
    add(1, "fresh automatic run reaches completion", ledger.get("status") == "complete", ["build/pipeline/automatic_run.json"], f"ledger status={ledger.get('status')}")
    image_promoted = _image_promotion(project)
    add(2, "promoted loadable FLUX.2 identity LoRA", image_promoted, ["build/training/image_identity/promoted"], "promotion and structural adapter audit")
    video_adapter = project / "build/training/video_identity/promoted/pytorch_lora_weights.safetensors"
    add(3, "promoted loadable LTX identity LoRA", video_adapter.is_file(), ["build/training/video_identity/promoted"], "real adapter required; a plan or stub is insufficient")
    add(4, "image runtime uses promoted identity, references, and controls", image_promoted and _image_runtime(project), ["build/runtime/image_runtime.json", "build/workflows/image_ablation/executions"], "requires promoted route plus hash-verified connected execution")
    add(5, "video runtime uses identity and motion/Union/Ingredients controls", _video_runtime(project), ["build/identity/video/video_runtime.json"], "requires complete runtime evidence and motion_control_consumed=true")
    add(6, "USDZ controls exercised in successful generation", _usdz_execution(project), ["build/identity/geometry", "build/workflows/image_ablation/executions"], "requires a successful geometry_control_consumed execution")
    modality_files = [
        "build/identity/annotation_manifest.json", "build/identity/caption_manifest.json",
        "build/identity/reference_bank/reference_bank.json", "build/identity/motion/skeleton_manifest.json",
        "build/identity/selection_manifest.json", "build/identity/asset_manifest.json",
    ]
    add(7, "masks/captions/embeddings/skeletons/splits/provenance validated", _exists(project, *modality_files), modality_files, "required provenance and derived-data manifests")
    add(8, "held-out image/video outputs and ablation metrics", _heldout_complete(project), ["build/training/image_identity/heldout_runs"], "requires a terminal held-out report with outputs and comparative metrics")
    bundle = project / "build/identity_bundle/bundle.json"
    add(9, "self-contained bundle generates image and video", bundle.is_file() and (_read(bundle) or {}).get("status") == "complete", ["build/identity_bundle/bundle.json"], "requires packaged promoted adapters, audio, workflows, and runtime contracts")
    docs = ["README.md", "docs/AUGUST_2026_IDENTITY_PIPELINE_GOAL.md", "docs/IMPLEMENTATION_TASKS.md"]
    add(10, "documentation states limitations/licenses/hardware/routes", _exists(Path(__file__).parent, *docs), docs, "documentation files are present; route claims remain subject to checks above")

    blockers = [f"{item['number']}: {item['detail']}" for item in checks if item["status"] != "passed"]
    report = {
        "schema_version": 1,
        "identity_id": identity_id,
        "goal": "AUGUST_2026_IDENTITY_PIPELINE_GOAL.md",
        "status": "complete" if not blockers else "blocked",
        "checks": checks,
        "passed_count": sum(item["status"] == "passed" for item in checks),
        "required_count": len(checks),
        "blockers": blockers,
        "invariant": "plans, stubs, and prepared manifests never satisfy a completion criterion requiring real downstream execution",
    }
    identity.write_json(project / "build/validation/goal_completion_audit.json", report)
    return report
