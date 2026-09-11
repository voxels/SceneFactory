"""Workflow graph builders/validators against the archived ComfyUI workflows.

The archived workflows (API format) live at
~/workspace/your_files/cezar-comfy-workflows/. This module loads them,
validates node wiring, and instantiates the event-take template (C) per
event from the shot manifest. His Mac queues and executes the result.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

# Node sets each archived workflow must contain (class_type values).
WORKFLOW_SPECS = {
    "A": {
        "file": "workflow_A_identity_proof.json",
        "required_nodes": {
            "LTXVLoader", "LoadImage", "LoraLoader", "CLIPTextEncode",
            "LTXVImgToVideo", "LTXVScheduler", "SamplerCustom", "VAEDecode",
            "SaveImage",
        },
        "min_nodes": 9,
    },
    "B": {
        "file": "workflow_B_env_reference.json",
        "required_nodes": {
            "LoadPlySplat", "CameraTrajectoryNode", "RenderSplat",
            "DepthEstimatorNode", "SaveImage",
        },
        "min_nodes": 5,
    },
    "C": {
        "file": "workflow_C_event_take_template.json",
        "required_nodes": {
            "LTXVLoader", "LoadImage", "LoraLoader", "CLIPTextEncode",
            "LTXVImgToVideo", "LTXVScheduler", "SamplerCustom", "VAEDecode",
            "SaveImage", "LTXVConditioning",
        },
        "min_nodes": 10,
    },
}

# Tokens the C template expects to be substituted per event. The leftover
# check also catches template drift: any EVENT_*/SHOT_* token pattern that
# survives substitution is a silent mis-generation.
C_TEMPLATE_TOKENS = ("EVENT_TOKEN", "EVENT_FOLDER", "EVENT_PROMPT", "SHOT_FRAMES")
_TOKEN_RE = re.compile(r"\b(EVENT_[A-Z_]{2,}|SHOT_[A-Z_]{2,})\b")


def load_workflow(path: str | Path) -> dict:
    """Parse a ComfyUI API-format workflow JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        graph = json.load(fh)
    if not isinstance(graph, dict) or not graph:
        raise ValueError(f"Not a valid API workflow: {path}")
    return graph


def _iter_links(value):
    """Yield (node_id, slot) link references found anywhere in a value."""
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
        node_id, slot = value
        if node_id.isdigit() and isinstance(slot, int):
            yield node_id, slot
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_links(v)
    elif isinstance(value, list):
        for v in value:
            yield from _iter_links(v)


def _is_node_id(key: str) -> bool:
    """ComfyUI API-format node ids are numeric strings. Top-level metadata
    keys (gate, trajectory_note, _meta) are not nodes."""
    return key.isdigit()


def validate_api_graph(graph: dict, *, workflow_id: str) -> dict:
    """Validate one archived workflow's node set and internal wiring.

    Returns a summary dict. Raises ValueError on any structural problem.
    """
    spec = WORKFLOW_SPECS[workflow_id]
    node_ids = {k for k in graph if _is_node_id(k)}
    if len(node_ids) < spec["min_nodes"]:
        raise ValueError(
            f"Workflow {workflow_id}: only {len(node_ids)} nodes, "
            f"expected at least {spec['min_nodes']}"
        )
    class_types = set()
    for nid in node_ids:
        node = graph[nid]
        if not isinstance(node, dict) or "class_type" not in node:
            raise ValueError(f"Workflow {workflow_id}: node {nid} has no class_type")
        class_types.add(node["class_type"])
        if not isinstance(node.get("inputs"), dict):
            raise ValueError(f"Workflow {workflow_id}: node {nid} has no inputs dict")
    missing = spec["required_nodes"] - class_types
    if missing:
        raise ValueError(
            f"Workflow {workflow_id}: missing required nodes: {sorted(missing)}"
        )
    # Every ["node_id", slot] link must point at an existing node.
    for nid in node_ids:
        for target, slot in _iter_links(graph[nid].get("inputs", {})):
            if target not in node_ids:
                raise ValueError(
                    f"Workflow {workflow_id}: node {nid} links to unknown node {target}"
                )
    return {
        "workflow": workflow_id,
        "nodes": len(node_ids),
        "class_types": sorted(class_types),
        "valid": True,
    }


def _substitute_tokens(obj, mapping: dict) -> object:
    if isinstance(obj, str):
        for token, value in mapping.items():
            obj = obj.replace(token, str(value))
        return obj
    if isinstance(obj, dict):
        return {k: _substitute_tokens(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_tokens(v, mapping) for v in obj]
    return obj


def instantiate_event_take(
    template: dict,
    *,
    event_token: str,
    event_folder: str,
    event_prompt: str,
    shot_frames: int,
    noise_seed: int,
) -> dict:
    """Instantiate the C template for one event take.

    Substitutes EVENT_TOKEN / EVENT_FOLDER / EVENT_PROMPT / SHOT_FRAMES and
    sets the per-take noise seed. Raises ValueError if any template token
    survives substitution (an un-substituted token reaching ComfyUI is a
    silent mis-generation).
    """
    graph = _substitute_tokens(
        copy.deepcopy(template),
        {
            "EVENT_TOKEN": event_token,
            "EVENT_FOLDER": event_folder,
            "EVENT_PROMPT": event_prompt,
            "SHOT_FRAMES": shot_frames,
        },
    )
    # Per-take noise seed: node 8 (SamplerCustom) input noise_seed.
    graph["8"]["inputs"]["noise_seed"] = noise_seed
    leftover = _find_tokens(graph)
    if leftover:
        raise ValueError(
            f"Unsubstituted template tokens remain: {sorted(leftover)}"
        )
    return graph


def _find_tokens(obj) -> set:
    found = set()
    if isinstance(obj, str):
        found.update(_TOKEN_RE.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            found |= _find_tokens(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _find_tokens(v)
    return found


def frames_for_duration(duration_sec: float, fps: int = 24) -> int:
    """Snap a shot duration to an LTX-friendly frame count (multiple of 8)."""
    raw = max(8, int(round(duration_sec * fps)))
    return raw - (raw % 8) or 8
