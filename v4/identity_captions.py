#!/usr/bin/env python3
"""Generate resumable semantic captions for identity-passing visual evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import identity_pipeline as identity


CAPTION_MODEL = Path("/Users/voxels/ComfyUI-Shared/models/LLM/Florence-2-large-PromptGen-v2.0")
CAPTION_PROMPT = "<MORE_DETAILED_CAPTION>"
PINNED_PYTHON = Path("/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI/custom_nodes/TTS-Audio-Suite/runtimes/shared_legacy_t4/bin/python")
VENDORED_TRANSFORMERS = Path(__file__).parent / "vendor/transformers_4_49"


def structured_caption(record: dict[str, Any], semantic: str, trigger_token: str) -> dict[str, Any]:
    pose_count = len(record.get("body_poses", []))
    other_people = max(0, int(record.get("face_count", 0)) - 1)
    visible_regions = {
        "close_up": ["face", "hair", "neck"],
        "head_and_shoulders": ["face", "hair", "neck", "shoulders"],
        "medium": ["face", "hair", "upper_body"],
        "wide_or_full_body": ["face", "hair", "upper_body", "lower_body", "hands", "feet"],
    }.get(record.get("shot_size"), [])
    distance = record.get("identity_embedding", {}).get("median_distance")
    identity_component = max(0.0, 1.0 - float(distance or 1.5) / 1.5)
    clean_score = identity_component * 0.55
    clean_score += 0.2 if record.get("person_mask") else 0
    clean_score += 0.15 if other_people == 0 else 0
    clean_score += 0.1 if record.get("face_area_fraction", 0) >= 0.025 else 0
    clean_score = round(min(1.0, clean_score), 6)
    stable_prefix = f"{trigger_token}, a person"
    caption = f"{stable_prefix}. {semantic.strip()}" if semantic.strip() else stable_prefix
    return {
        "caption": caption,
        "semantic_caption": semantic.strip(),
        "identity_token": trigger_token,
        "subject_class": "person",
        "shot_size": record.get("shot_size"),
        "viewpoint": "not_reliably_classified",
        "expression": "described_by_caption_model",
        "visible_body_regions": visible_regions,
        "body_pose_detected": pose_count > 0,
        "body_pose_count": pose_count,
        "other_person_face_count": other_people,
        "occlusion": "requires_mask_and_caption_cross_check",
        "wardrobe": "described_by_caption_model",
        "scene": "described_by_caption_model",
        "lighting": "described_by_caption_model",
        "clean_shot_score": clean_score,
        "script_relevance": "clean_identity_shot" if clean_score >= 0.65 else "supporting_identity_evidence",
    }


def generate(project_root: Path, *, limit: int | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    annotation_path = project_root / "build/identity/annotation_manifest.json"
    if not annotation_path.is_file():
        raise ValueError("identity annotation manifest is missing")
    if not (CAPTION_MODEL / "model.safetensors").is_file():
        raise ValueError(f"caption model is incomplete or missing: {CAPTION_MODEL}")

    import torch
    from PIL import Image, ImageOps
    from transformers import AutoModelForCausalLM, AutoProcessor

    annotations = identity.read_json(annotation_path)
    output = project_root / "build/identity/caption_manifest.json"
    previous = identity.read_json(output) if output.is_file() else {"records": []}
    prior = {item["asset_id"]: item for item in previous.get("records", [])}
    candidates = [item for item in annotations["records"] if item.get("identity_pass")]
    if limit is not None:
        candidates = candidates[:limit]
    model = AutoModelForCausalLM.from_pretrained(
        str(CAPTION_MODEL), trust_remote_code=True, local_files_only=True,
        torch_dtype=torch.float32, attn_implementation="eager",
    ).eval()
    # The model's pinned remote code predates Transformers 4.50, when
    # PreTrainedModel stopped inheriting GenerationMixin. Restore that public
    # mixin without modifying the downloaded model snapshot.
    if not hasattr(model.language_model, "generate"):
        from transformers.generation.utils import GenerationMixin
        original_class = model.language_model.__class__
        compatibility_class = type(
            f"{original_class.__name__}WithGeneration", (original_class, GenerationMixin), {}
        )
        model.language_model.__class__ = compatibility_class
    if model.language_model.generation_config is None:
        from transformers import GenerationConfig
        model.language_model.generation_config = GenerationConfig.from_model_config(model.language_model.config)
    processor = AutoProcessor.from_pretrained(str(CAPTION_MODEL), trust_remote_code=True, local_files_only=True)
    records = dict(prior)
    trigger = config["identity"].get("trigger_token", config["identity"]["id"])
    for index, record in enumerate(candidates, 1):
        old = records.get(record["asset_id"])
        if old and old.get("source_sha256") == record["sha256"] and old.get("model") == CAPTION_MODEL.name and old.get("prompt") == CAPTION_PROMPT:
            continue
        with Image.open(record["path"]) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
            inputs = processor(text=CAPTION_PROMPT, images=image, return_tensors="pt")
            with torch.inference_mode():
                generated = model.generate(
                    input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"],
                    max_new_tokens=384, do_sample=False, num_beams=3,
                )
            text = processor.batch_decode(generated, skip_special_tokens=False)[0]
            parsed = processor.post_process_generation(text, task=CAPTION_PROMPT, image_size=image.size)
        semantic = parsed.get(CAPTION_PROMPT, parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(semantic, str):
            semantic = json.dumps(semantic, sort_keys=True)
        records[record["asset_id"]] = {
            "asset_id": record["asset_id"],
            "source_path": record["path"],
            "source_sha256": record["sha256"],
            "group_id": record["group_id"],
            "model": CAPTION_MODEL.name,
            "model_path": str(CAPTION_MODEL),
            "prompt": CAPTION_PROMPT,
            **structured_caption(record, semantic, trigger),
        }
        result = {
            "schema_version": 4,
            "identity_id": annotations["identity_id"],
            "model": {"path": str(CAPTION_MODEL), "name": CAPTION_MODEL.name, "prompt": CAPTION_PROMPT},
            "counts": {"eligible": len([item for item in annotations["records"] if item.get("identity_pass")]), "captioned": len(records)},
            "records": sorted(records.values(), key=lambda item: item["asset_id"]),
        }
        identity.write_json(output, result)
        print(f"[{index}/{len(candidates)}] captioned {record['asset_id']}", flush=True)
    return identity.read_json(output)


def generate_pinned(project_root: Path, *, limit: int | None = None) -> dict[str, Any]:
    """Run captions in the isolated, compatibility-pinned Florence runtime."""
    if not PINNED_PYTHON.is_file():
        raise ValueError(f"caption Python runtime is missing: {PINNED_PYTHON}")
    if not (VENDORED_TRANSFORMERS / "transformers/__init__.py").is_file():
        raise ValueError(f"pinned Transformers runtime is missing: {VENDORED_TRANSFORMERS}")
    project_root = project_root.resolve()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join((str(VENDORED_TRANSFORMERS), str(Path(__file__).parent)))
    environment["HF_MODULES_CACHE"] = str(project_root / "build/cache/huggingface_modules_449")
    command = [str(PINNED_PYTHON), str(Path(__file__).resolve()), "--project", str(project_root)]
    if limit is not None:
        command.extend(("--limit", str(limit)))
    subprocess.run(command, check=True, env=environment)
    return identity.read_json(project_root / "build/identity/caption_manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    arguments = parser.parse_args()
    result = generate(arguments.project, limit=arguments.limit)
    print(json.dumps({"status": "complete", "counts": result["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
