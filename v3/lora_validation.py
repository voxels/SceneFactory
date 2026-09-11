"""Compile fixed FLUX.2 Klein LoRA validation grids and promotion records."""

from __future__ import annotations

import re
from pathlib import Path

import comfy_adapter
import execution_adapter
import scene_factory as core


VALIDATION_SEEDS = (2184, 2185, 2186)


def safe_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def lora_name_from_path(path: str, models_root: str) -> str:
    lora_root = (Path(models_root) / "loras").resolve()
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(lora_root))
    except ValueError:
        raise ValueError(f"LoRA output must be under {lora_root}: {resolved}") from None


def build(project_root: Path, concept_id: str) -> tuple[dict, Path, Path]:
    project_root = project_root.resolve()
    project, registry, _, variables = core.load_project(project_root)
    concept = next((item for item in registry.get("concepts", []) if item.get("id") == concept_id), None)
    if concept is None:
        raise ValueError(f"Unknown concept: {concept_id}")
    prompts = concept.get("validation_prompts") or []
    if not prompts:
        raise ValueError(f"Concept has no validation_prompts: {concept_id}")
    inference = concept.get("inference", {})
    lora_path = core.expand_pointer(inference.get("lora_path"), variables)
    lora_name = lora_name_from_path(lora_path, variables["COMFYUI_MODELS_ROOT"])
    profile_path = core.resolve_pointer(
        project_root, concept.get("training", {}).get("profile"), variables
    )
    profile = core.read_json(profile_path)
    weights = profile.get("validation", {}).get("weight_sweep") or [0.85]
    workflow_dir = project_root / "build" / "comfyui" / "workflows" / "lora_validation" / concept_id
    workflow_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for prompt_number, prompt in enumerate(prompts, 1):
        for weight in weights:
            for seed in VALIDATION_SEEDS:
                job_id = f"lora_validation__{safe_token(concept_id)}__p{prompt_number:02d}__w{int(weight * 100):03d}__s{seed}"
                prefix = f"SceneFactory/validation/{concept_id}/prompt_{prompt_number:02d}/weight_{weight:.2f}/seed_{seed}"
                workflow_path = workflow_dir / f"{job_id}.api.json"
                core.write_json(workflow_path, comfy_adapter.text_image_graph(
                    prompt, comfy_adapter.NEGATIVE, prefix, seed,
                    width=768, height=768, lora_name=lora_name, lora_strength=float(weight),
                ))
                record = {
                    "id": job_id,
                    "adapter": {"interface": execution_adapter.INTERFACE_ID, "version": 1},
                    "execution_phase": "lora_validation",
                    "workflow": str(workflow_path),
                    "output_prefix": prefix,
                    "concept_id": concept_id,
                    "prompt": prompt,
                    "seed": seed,
                    "weight": float(weight),
                }
                execution_adapter.validate_job(record, require_workflow_file=True)
                records.append(record)
    manifest = {
        "schema_version": 1,
        "concept_id": concept_id,
        "lora_name": lora_name,
        "fixed_seeds": list(VALIDATION_SEEDS),
        "weight_sweep": [float(item) for item in weights],
        "jobs": records,
    }
    manifest_path = project_root / "build" / "comfyui" / f"{concept_id}_lora_validation_manifest.json"
    core.write_json(manifest_path, manifest)
    promotion_path = project_root / "build" / "review" / "lora_promotions" / f"{concept_id}.json"
    if not promotion_path.exists():
        core.write_json(promotion_path, {
            "schema_version": 1,
            "concept_id": concept_id,
            "validation_manifest": str(manifest_path),
            "required_job_ids": [item["id"] for item in records],
            "decision": "pending",
            "approved_by": None,
            "issues": [],
            "promoted_lora": None,
            "notes": "Only the user may promote a LoRA after reviewing every fixed validation cell.",
        })
    return manifest, manifest_path, promotion_path
