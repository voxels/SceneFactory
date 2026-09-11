#!/usr/bin/env python3
"""Compile and validate executable ComfyUI API graphs for image identity ablations.

The compiler deliberately emits only graphs whose required local model/node
contracts are present. A missing adapter or control checkpoint produces an
explicit blocked route in the manifest instead of a fake success workflow.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import copy
from pathlib import Path
from typing import Any

import identity_pipeline as identity


COMFY_MODELS = Path("/Users/voxels/ComfyUI-Shared/models")
DIFFUSION_MODEL = "flux-2-klein-4b.safetensors"
TEXT_ENCODER = "qwen_3_4b.safetensors"
VAE = "flux2-vae.safetensors"
PULID_MODEL = Path("/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI/models/pulid/pulid_flux2_klein_v2.safetensors")
PULID_NODE = Path("/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI/custom_nodes/ComfyUI-PuLID-Flux2")
MAX_REFERENCE_DIM = 1024


def _node(class_type: str, **inputs: Any) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def _link(node_id: str, output: int = 0) -> list[Any]:
    return [str(node_id), output]


def validate_api_graph(graph: dict[str, Any]) -> None:
    """Validate Comfy API prompt shape and all link references."""
    if not graph:
        raise ValueError("workflow graph is empty")
    for node_id, node in graph.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            raise ValueError("workflow node ids and records must be strings/objects")
        if not isinstance(node.get("class_type"), str) or not isinstance(node.get("inputs"), dict):
            raise ValueError(f"invalid API node {node_id}")
    for node_id, node in graph.items():
        for name, value in node["inputs"].items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                if value[0] not in graph:
                    raise ValueError(f"{node_id}.{name} links to missing node {value[0]}")
                if not isinstance(value[1], int) or value[1] < 0:
                    raise ValueError(f"{node_id}.{name} has invalid output index")


def _common_graph(prompt: str, negative: str, *, width: int, height: int) -> dict[str, Any]:
    graph = {
        "1": _node("UNETLoader", unet_name=DIFFUSION_MODEL, weight_dtype="default"),
        "2": _node("CLIPLoader", clip_name=TEXT_ENCODER, type="flux2"),
        "3": _node("VAELoader", vae_name=VAE),
        # CLIPTextEncodeFlux hard-codes the legacy t5xxl token namespace and
        # crashes with the Qwen3 Flux.2 Klein encoder. The generic encoder asks
        # the loaded CLIP object for its native qwen3_4b namespace.
        "4": _node("CLIPTextEncode", clip=_link("2"), text=prompt),
        "5": _node("CLIPTextEncode", clip=_link("2"), text=negative),
        "6": _node("EmptyFlux2LatentImage", width=width, height=height, batch_size=1),
        "7": _node(
            "KSampler", model=_link("1"), seed=260801, steps=20, cfg=1.0,
            sampler_name="euler", scheduler="normal", positive=_link("4"),
            negative=_link("5"), latent_image=_link("6"), denoise=1.0,
        ),
        "8": _node("VAEDecode", samples=_link("7"), vae=_link("3")),
        "9": _node("SaveImage", images=_link("8"), filename_prefix="scene_factory_v4_identity"),
    }
    validate_api_graph(graph)
    return graph


def _reference_graph(prompt: str, negative: str, references: list[Any], *, width: int, height: int) -> dict[str, Any]:
    graph = _common_graph(prompt, negative, width=width, height=height)
    previous = "4"
    next_id = 10
    for reference in references:
        # Feed both the original appearance view and its mask-derived alpha
        # cutout when available. This makes the selected annotation a real
        # inference input instead of metadata that never reaches a node.
        if isinstance(reference, str):
            values = [reference]
        elif reference.get("category") == "canonical_frontal" and reference.get("masked_staged_filename"):
            # Keep the six-category context within MPSGraph limits while making
            # the highest-authority face reference explicitly mask-derived.
            values = [reference["masked_staged_filename"]]
        else:
            values = [reference["staged_filename"]]
        for value in (item for item in values if item):
            load_id, encode_id, ref_id = str(next_id), str(next_id + 1), str(next_id + 2)
            graph[load_id] = _node("LoadImage", image=value)
            graph[encode_id] = _node("VAEEncode", pixels=_link(load_id), vae=_link("3"))
            graph[ref_id] = _node("ReferenceLatent", conditioning=_link(previous), latent=_link(encode_id))
            previous = ref_id
            next_id += 3
    # Explicitly select the FLUX.2 reference-token strategy. Relying on a model
    # default would make the same graph behave differently across Comfy versions.
    method_id = str(next_id)
    graph[method_id] = _node("FluxKontextMultiReferenceLatentMethod", conditioning=_link(previous), reference_latents_method="index_timestep_zero")
    graph["7"]["inputs"]["positive"] = _link(method_id)
    validate_api_graph(graph)
    return graph


def _pulid_graph(prompt: str, negative: str, reference: str, *, width: int, height: int) -> dict[str, Any]:
    graph = _common_graph(prompt, negative, width=width, height=height)
    graph["10"] = _node("LoadImage", image=reference)
    graph["11"] = _node("PuLIDInsightFaceLoader", provider="CPU")
    graph["12"] = _node("PuLIDEVACLIPLoader")
    graph["13"] = _node("PuLIDModelLoader", pulid_file=PULID_MODEL.name)
    graph["14"] = _node(
        "ApplyPuLIDFlux2", model=_link("1"), pulid_model=_link("13"), strength=0.8,
        eva_clip=_link("12"), face_analysis=_link("11"), image=_link("10"),
        face_index=0, debug_mode=False,
    )
    graph["7"]["inputs"]["model"] = _link("14")
    validate_api_graph(graph)
    return graph


def _apply_subject_lora(graph: dict[str, Any], lora_name: str, prefix: str) -> dict[str, Any]:
    graph = copy.deepcopy(graph)
    loader_id = str(max(int(item) for item in graph) + 1)
    graph[loader_id] = _node("LoraLoaderModelOnly", model=_link("1"),
                             lora_name=lora_name, strength_model=1.0)
    graph["7"]["inputs"]["model"] = _link(loader_id)
    graph["9"]["inputs"]["filename_prefix"] = prefix
    validate_api_graph(graph)
    return graph


def _references(project_root: Path) -> list[dict[str, Any]]:
    path = project_root / "build/identity/reference_bank/reference_bank.json"
    if not path.is_file():
        raise ValueError("reference bank is missing; run process-identity first")
    data = identity.read_json(path)
    records = sorted(data.get("records", []), key=lambda item: item["category"])
    if not records:
        raise ValueError("reference bank contains no records")
    result = []
    for record in records:
        original = record.get("original", {})
        source = Path(original.get("path", ""))
        if not source.is_file():
            raise ValueError(f"reference source is missing: {source}")
        # LoadImage resolves a staged basename from ComfyUI input/. The staging
        # manifest is part of the contract; generation must copy+hash before queueing.
        staged = f"sfv4_ref_{record['category']}_{record['asset_id'][:12]}{source.suffix.lower()}"
        alpha = record.get("alpha_cutout") or {}
        alpha_path = Path(alpha.get("path", "")) if alpha else None
        masked = f"sfv4_ref_{record['category']}_{record['asset_id'][:12]}_masked.png" if alpha_path and alpha_path.is_file() else None
        result.append({
            "category": record["category"], "asset_id": record["asset_id"],
            "source": str(source), "source_sha256": record["original"]["sha256"],
            "staged_filename": staged,
            "masked_source": str(alpha_path) if alpha_path else None,
            "masked_source_sha256": alpha.get("sha256") if alpha else None,
            "masked_staged_filename": masked,
        })
    return result


def _stage_reference_assets(refs: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    """Copy/hash every graph input so LoadImage names resolve deterministically."""
    staging = out_dir / "input"
    staging.mkdir(parents=True, exist_ok=True)
    records = []
    for ref in refs:
        entries = [(ref["source"], ref["source_sha256"], ref["staged_filename"], False)]
        if ref.get("masked_source") and ref.get("masked_staged_filename"):
            entries.append((ref["masked_source"], ref["masked_source_sha256"], ref["masked_staged_filename"], True))
        for source_text, expected, name, derived_from_mask in entries:
            source = Path(source_text)
            if not source.is_file():
                raise ValueError(f"reference staging source is missing: {source}")
            actual = identity.sha256_file(source)
            if expected and actual != expected:
                raise ValueError(f"reference staging hash mismatch: {source}")
            destination = staging / name
            dimensions = None
            try:
                probe = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(source)],
                                       capture_output=True, text=True, check=True)
                values = [int(line.split(":", 1)[1].strip()) for line in probe.stdout.splitlines()
                          if ":" in line and line.split(":", 1)[0].strip() in {"pixelWidth", "pixelHeight"}]
                dimensions = (values[0], values[1]) if len(values) == 2 else None
            except (OSError, subprocess.CalledProcessError, ValueError):
                pass
            resized = bool(dimensions and max(dimensions) > MAX_REFERENCE_DIM)
            if resized:
                temporary = destination.with_name(destination.name + ".resizing")
                if temporary.exists():
                    temporary.unlink()
                result = subprocess.run(
                    ["sips", "--resampleHeightWidthMax", str(MAX_REFERENCE_DIM),
                     "--out", str(temporary), str(source)],
                    capture_output=True, text=True, check=False,
                )
                if result.returncode != 0 or not temporary.is_file():
                    raise ValueError(f"failed to resize reference for MPS-safe VAE input: {source}: {result.stderr[-400:]}")
                os.replace(temporary, destination)
            elif destination.is_file() and identity.sha256_file(destination) != actual:
                raise ValueError(f"reference staging collision: {destination}")
            elif not destination.exists():
                shutil.copy2(source, destination)
            records.append({"source": str(source), "source_sha256": actual,
                            "staged": str(destination), "staged_filename": name,
                            "staged_sha256": identity.sha256_file(destination),
                            "source_dimensions": dimensions, "max_reference_dimension": MAX_REFERENCE_DIM,
                            "resized_for_mps": resized, "derived_from_mask": derived_from_mask})
    manifest = {"schema_version": 1, "status": "staged", "records": records,
                "invariants": ["all graph LoadImage inputs are hashed", "mask-derived alpha cutouts are explicit inputs"]}
    identity.write_json(out_dir / "staging_manifest.json", manifest)
    return manifest


def _stage_adapter(source: Path, target: Path, expected_sha256: str) -> dict[str, Any]:
    """Atomically refresh a local ComfyUI LoRA staging copy by content hash."""
    if not source.is_file():
        raise ValueError(f"adapter staging source is missing: {source}")
    actual = identity.sha256_file(source)
    if actual != expected_sha256:
        raise ValueError(f"adapter staging source hash mismatch: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and identity.sha256_file(target) == actual:
        return {"source": str(source), "target": str(target), "sha256": actual, "refreshed": False}
    temporary = target.with_name(target.name + ".staging")
    if temporary.exists():
        temporary.unlink()
    shutil.copy2(source, temporary)
    if identity.sha256_file(temporary) != actual:
        temporary.unlink()
        raise ValueError(f"adapter staging copy hash mismatch: {target}")
    os.replace(temporary, target)
    return {"source": str(source), "target": str(target), "sha256": actual, "refreshed": True}


def compile_workflows(project_root: Path, *, width: int = 1024, height: int = 1024) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    identity.validate_config(config)
    refs = _references(project_root)
    trigger = config["identity"]["trigger_token"]
    prompt = f"editorial photograph of {trigger}, natural skin, accurate anatomy"
    negative = "extra people, distorted face, duplicate limbs, text, watermark"
    out_dir = project_root / "build/workflows/image_ablation"
    out_dir.mkdir(parents=True, exist_ok=True)
    staging = _stage_reference_assets(refs, out_dir)
    routes: list[dict[str, Any]] = []
    candidate_blockers: list[str] = []

    def emit(name: str, graph: dict[str, Any], *, required_nodes: list[str], required_models: list[str], **extra: Any) -> None:
        path = out_dir / f"{name}.json"
        identity.write_json(path, graph)
        record = {"name": name, "status": "compiled", "path": str(path),
                  "required_nodes": required_nodes, "required_models": required_models,
                  "node_count": len(graph), "graph_sha256": identity.sha256_file(path)}
        record.update(extra)
        routes.append(record)

    emit("base", _common_graph(prompt, negative, width=width, height=height), required_nodes=[],
         required_models=[DIFFUSION_MODEL, TEXT_ENCODER, VAE])
    emit("native_reference", _reference_graph(prompt, negative, refs, width=width, height=height),
         required_nodes=[], required_models=[DIFFUSION_MODEL, TEXT_ENCODER, VAE])

    if PULID_NODE.is_dir() and PULID_MODEL.is_file():
        emit("pulid", _pulid_graph(prompt, negative, refs[0].get("masked_staged_filename") or refs[0]["staged_filename"], width=width, height=height),
             required_nodes=["ComfyUI-PuLID-Flux2"], required_models=[DIFFUSION_MODEL, TEXT_ENCODER, VAE, PULID_MODEL.name])
    else:
        routes.append({"name": "pulid", "status": "blocked", "reason": "PuLID node or checkpoint is missing"})

    # Every completed candidate gets its own fixed-seed route. Promotion remains
    # withheld until held-out metrics select a winner; no adapter is silently
    # treated as production-ready.
    candidate_root = project_root / "build/training/image_identity/experiments"
    comfy_lora_root = Path("/Users/voxels/ComfyUI-Shared/models/loras/scene_factory_v4")
    candidate_route_names = []
    if candidate_root.is_dir():
        for experiment in sorted((item for item in identity.read_json(project_root / "build/training/image_identity/training_plan.json").get("experiments", [])
                                  if (candidate_root / item["name"] / "experiment_complete.json").is_file()), key=lambda item: item["name"]):
            source = Path(experiment["output_dir"]) / "pytorch_lora_weights.safetensors"
            target = comfy_lora_root / f"{experiment['name']}.safetensors"
            if not source.is_file():
                reason = "trained adapter is missing"
                candidate_blockers.append(f"{experiment['name']}: {reason}")
                routes.append({"name": experiment["name"], "status": "blocked", "reason": reason})
                continue
            adapter_sha256 = identity.sha256_file(source)
            try:
                staging_record = _stage_adapter(source, target, adapter_sha256)
            except (OSError, ValueError) as error:
                reason = f"ComfyUI LoRA staging failed: {error}"
                candidate_blockers.append(f"{experiment['name']}: {reason}")
                routes.append({"name": experiment["name"], "status": "blocked", "reason": reason})
                continue
            lora_name = f"scene_factory_v4/{target.name}"
            base = _common_graph(prompt, negative, width=width, height=height)
            native = _reference_graph(prompt, negative, refs, width=width, height=height)
            metadata = {"candidate_experiment": experiment["name"], "adapter_sha256": adapter_sha256,
                        "adapter_staging": staging_record,
                        "evaluation_status": "pending_heldout_metrics"}
            subject_name = f"subject_lora_{experiment['name']}"
            native_name = f"lora_reference_{experiment['name']}"
            emit(subject_name, _apply_subject_lora(base, lora_name, f"scene_factory_v4/{experiment['name']}"),
                 required_nodes=["LoraLoaderModelOnly"], required_models=[DIFFUSION_MODEL, TEXT_ENCODER, VAE, lora_name], **metadata)
            emit(native_name, _apply_subject_lora(native, lora_name, f"scene_factory_v4/{experiment['name']}_reference"),
                 required_nodes=["LoraLoaderModelOnly"], required_models=[DIFFUSION_MODEL, TEXT_ENCODER, VAE, lora_name], **metadata)
            candidate_route_names.extend([subject_name, native_name])
    routes.extend([
        {"name": "subject_lora", "status": "blocked", "reason": "winner not promoted; use candidate routes for held-out evaluation"},
        {"name": "lora_plus_native_reference", "status": "blocked", "reason": "winner not promoted; use candidate routes for held-out evaluation"},
        {"name": "refcontrol_or_controlnet", "status": "blocked", "reason": "no compatible local FLUX.2 control checkpoint"},
    ])
    manifest = {
        "schema_version": 1, "identity_id": config["identity"]["id"],
        "status": "blocked" if candidate_blockers else "compiled",
        "blockers": candidate_blockers,
        "prompt": prompt, "negative_prompt": negative, "width": width, "height": height,
        "reference_staging": refs, "staging_manifest": str((out_dir / "staging_manifest.json").resolve()),
        "staged_inputs": staging["records"], "candidate_route_names": candidate_route_names, "routes": routes,
        "invariants": ["all API links resolve", "all model filenames are explicit", "no placeholder checkpoints"],
    }
    identity.write_json(out_dir / "manifest.json", manifest)
    # Keep a runtime contract separate from the graph manifest so a packaged
    # identity bundle can describe invocation without implying that a route has
    # already been promoted or executed.
    identity.write_json(project_root / "build/runtime/image_runtime.json", {
        "schema_version": 1,
        "status": manifest["status"],
        "identity_id": config["identity"]["id"],
        "selected_route": None,
        "route_selection": "held_out_promotion_required",
        "manifest": str((out_dir / "manifest.json").resolve()),
        "staging_manifest": str((out_dir / "staging_manifest.json").resolve()),
        "routes": [{"name": item["name"], "status": item["status"], "graph": item.get("path"),
                    "graph_sha256": item.get("graph_sha256"), "required_models": item.get("required_models", [])}
                   for item in routes],
        "invocation": "scene-factory-v4 execute-image-workflow --route <promoted-route>",
        "promotion_required": True,
        "blockers": candidate_blockers,
    })
    return manifest
