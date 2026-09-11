"""Stable boundary between compiled Scene Factory tasks and execution runners."""

from __future__ import annotations

from pathlib import Path


INTERFACE_ID = "scene_factory.comfyui_api_workflow"
INTERFACE_VERSION = 1
REQUIRED_FIELDS = ("id", "execution_phase", "workflow", "output_prefix")


def validate_job(record: dict, *, require_workflow_file: bool = False) -> dict:
    """Validate one compiled-task → ComfyUI API-workflow adapter record."""
    if not isinstance(record, dict):
        raise ValueError("Execution adapter job must be an object")
    missing = [field for field in REQUIRED_FIELDS if not record.get(field)]
    if missing:
        raise ValueError(f"Execution adapter job is missing: {', '.join(missing)}")
    adapter = record.get("adapter") or {}
    interface = adapter.get("interface", INTERFACE_ID)
    version = adapter.get("version", INTERFACE_VERSION)
    if interface != INTERFACE_ID or version != INTERFACE_VERSION:
        raise ValueError(
            f"Unsupported execution adapter for {record['id']}: {interface} v{version}"
        )
    if require_workflow_file and not Path(record["workflow"]).is_file():
        raise ValueError(f"Execution workflow does not exist for {record['id']}: {record['workflow']}")
    return record


def validate_manifest(manifest: dict, *, require_workflow_files: bool = False) -> list[dict]:
    jobs = [
        *manifest.get("character_sheets", []),
        *manifest.get("storyboards", []),
        *manifest.get("videos", []),
    ]
    seen = set()
    for record in jobs:
        validate_job(record, require_workflow_file=require_workflow_files)
        if record["id"] in seen:
            raise ValueError(f"Duplicate execution adapter job id: {record['id']}")
        seen.add(record["id"])
    return jobs
