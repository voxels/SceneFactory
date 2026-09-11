"""Manifest / approval nodes — Scene Factory owns these.

ComfyUI executes generated API graphs; manifests and approvals are written
here, never inferred from files on disk.
"""

from __future__ import annotations

import json
import os

from .node_types import (
    SF_TAKE, SF_REVIEW, SF_REFUSAL, SF_MANIFEST,
    INTERFACE_ID, INTERFACE_VERSION,
)

CATEGORY = "SceneFactory/Manifests"

REQUIRED_TAKE_FIELDS = (
    "event", "shot", "start_sec", "duration_sec",
    "lora_version", "gate_verdict",
)

VALID_GATE_VERDICTS = ("HOLDS", "DRIFTS", "NO MATCH", "USER_CONFIRMED")


class SF_TakeManifestWriter:
    """OUTPUT_NODE — writes the take manifest record.

    The take must carry a gate verdict and a review record. Only a clean
    user approval makes the take eligible for assembly; anything else is
    kept as negative training data (never deleted).
    """

    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "take": (SF_TAKE,),
                "review": (SF_REVIEW,),
                "manifest_dir": ("STRING", {"default": ""}),
            },
            "optional": {
                "refusal": (SF_REFUSAL,),
                "source_file": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = (SF_TAKE,)
    RETURN_NAMES = ("manifested_take",)
    FUNCTION = "write"
    CATEGORY = CATEGORY

    def write(self, take, review, manifest_dir, refusal=None, source_file=""):
        from .node_types import is_approved
        take = dict(take)
        missing = [f for f in REQUIRED_TAKE_FIELDS if take.get(f) is None]
        if missing:
            raise ValueError(f"SF_TakeManifestWriter: take missing fields: {missing}")
        if take["gate_verdict"] not in VALID_GATE_VERDICTS:
            raise ValueError(
                f"SF_TakeManifestWriter: invalid gate verdict {take['gate_verdict']!r}"
            )
        take["review"] = review
        take["approved_for_assembly"] = is_approved(review)
        if refusal:
            hist = list(take.get("refusal_history") or [])
            hist.append(refusal)
            take["refusal_history"] = hist
        if source_file:
            take["source_file"] = source_file
        if manifest_dir:
            os.makedirs(manifest_dir, exist_ok=True)
            path = os.path.join(
                manifest_dir, f"take_{take['event']}_shot_{take['shot']}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(take, fh, indent=2)
            take["manifest_path"] = path
        return (take,)


class SF_GraphManifestBuilder:
    """Builds the versioned graph manifest.

    One compiled task -> one ComfyUI API workflow, stamped with the
    interface id (scene_factory.comfyui_api_workflow v1). The graph JSON
    itself is validated for API-format structure before stamping.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workflow_id": (["A", "B", "C"],),
                "api_graph_json": ("STRING", {"multiline": True, "default": "{}"}),
                "graph_version": ("STRING", {"default": "1"}),
            },
        }

    RETURN_TYPES = (SF_MANIFEST,)
    RETURN_NAMES = ("graph_manifest",)
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, workflow_id, api_graph_json, graph_version="1"):
        try:
            graph = json.loads(api_graph_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"SF_GraphManifestBuilder: invalid graph JSON: {exc}")
        node_ids = [k for k in graph if not str(k).startswith("_")]
        for nid in node_ids:
            node = graph[nid]
            if not isinstance(node, dict) or "class_type" not in node:
                raise ValueError(
                    f"SF_GraphManifestBuilder: node {nid} has no class_type")
        class_types = sorted({graph[n]["class_type"] for n in node_ids})
        return ({
            "kind": "graph_manifest",
            "interface_id": INTERFACE_ID,
            "interface_version": INTERFACE_VERSION,
            "workflow": workflow_id,
            "graph_version": str(graph_version),
            "node_count": len(node_ids),
            "class_types": class_types,
        },)
