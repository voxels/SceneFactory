#!/usr/bin/env python3
"""Audit Diffusers/PEFT LoRA artifacts before they enter an identity route."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safetensors import safe_open

import identity_pipeline as identity


def validate(path: Path, *, expected_rank: int | None = None) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file() or path.suffix != ".safetensors":
        raise ValueError(f"LoRA adapter is missing or not a safetensors file: {path}")
    pairs: dict[str, set[str]] = {}
    shapes: dict[str, list[int]] = {}
    with safe_open(str(path), framework="pt", device="cpu") as handle:
        keys = list(handle.keys())
        metadata = handle.metadata() or {}
        for key in keys:
            if not key.endswith((".lora_A.weight", ".lora_B.weight")):
                continue
            suffix = ".lora_A.weight" if key.endswith(".lora_A.weight") else ".lora_B.weight"
            module = key[:-len(suffix)]
            pairs.setdefault(module, set()).add(suffix[1:-7])
            shapes[key] = list(handle.get_tensor(key).shape)
    if not pairs:
        raise ValueError(f"LoRA adapter has no PEFT lora_A/lora_B tensors: {path}")
    incomplete = sorted(module for module, values in pairs.items() if values != {"lora_A", "lora_B"})
    if incomplete:
        raise ValueError(f"LoRA adapter has incomplete tensor pairs: {incomplete[:8]}")
    ranks = set()
    bad_shapes = []
    for module in sorted(pairs):
        a = shapes[f"{module}.lora_A.weight"]
        b = shapes[f"{module}.lora_B.weight"]
        if len(a) != 2 or len(b) != 2 or a[0] != b[1]:
            bad_shapes.append({"module": module, "a": a, "b": b})
        else:
            ranks.add(a[0])
    if bad_shapes:
        raise ValueError(f"LoRA adapter has incompatible tensor shapes: {bad_shapes[:4]}")
    if expected_rank is not None and ranks != {expected_rank}:
        raise ValueError(f"LoRA ranks {sorted(ranks)} do not match expected rank {expected_rank}")
    metadata_text = metadata.get("lora_adapter_metadata", "")
    adapter_metadata: dict[str, Any] = {}
    if metadata_text:
        try:
            adapter_metadata = json.loads(metadata_text)
        except json.JSONDecodeError as error:
            raise ValueError(f"LoRA metadata is not JSON: {path}") from error
    declared_rank = adapter_metadata.get("transformer.r")
    if declared_rank is not None and ranks != {int(declared_rank)}:
        raise ValueError(f"LoRA tensor rank {sorted(ranks)} disagrees with metadata rank {declared_rank}")
    result = {
        "schema_version": 1,
        "status": "structurally_loadable",
        "path": str(path),
        "sha256": identity.sha256_file(path),
        "bytes": path.stat().st_size,
        "tensor_count": len(keys),
        "paired_module_count": len(pairs),
        "ranks": sorted(ranks),
        "declared_rank": declared_rank,
        "format": metadata.get("format", "unknown"),
        "scope": "tensor-schema-and-metadata-only; full base-model load is a separate runtime check",
    }
    identity.write_json(path.parent / f"{path.stem}_validation.json", result)
    return result


def validate_checkpoint_tree(root: Path, *, expected_rank: int | None = None) -> dict[str, Any]:
    root = root.resolve()
    adapters = sorted(root.glob("**/*.safetensors"))
    if not adapters:
        raise ValueError(f"no safetensors adapters found under {root}")
    return {"root": str(root), "status": "complete", "adapters": [validate(item, expected_rank=expected_rank) for item in adapters]}
