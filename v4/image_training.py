#!/usr/bin/env python3
"""Prepare and execute reproducible FLUX.2 Klein identity-LoRA experiments."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import identity_pipeline as identity
import adapter_validation


TRAINER_ROOT = Path("/Users/voxels/ComfyUI-Installs/FLUX2-Trainer")
TRAINER = TRAINER_ROOT / "diffusers/examples/dreambooth/train_dreambooth_lora_flux2_klein.py"
TRAINER_PYTHON = TRAINER_ROOT / ".venv/bin/python"
BASE_MODEL = Path("/Users/voxels/.cache/huggingface/hub/models--black-forest-labs--FLUX.2-klein-base-4B/snapshots/a3b4f4849157f664bdbc776fd7453c2783562f4d")


def _copy_verified(source: Path, destination: Path, digest: str) -> None:
    if identity.sha256_file(source) != digest:
        raise ValueError(f"training source hash changed: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and identity.sha256_file(destination) == digest:
        return
    if destination.exists():
        raise ValueError(f"dataset destination collision: {destination}")
    shutil.copy2(source, destination)


def _experiment_signature(experiment: dict[str, Any], plan: dict[str, Any]) -> str:
    """Content signature used to make completed experiments safely resumable."""
    payload = {
        "name": experiment["name"],
        "command": experiment["command"],
        "selection_manifest_sha256": plan["selection_manifest_sha256"],
        "trainer": plan["trainer"],
        "base_model": plan["base_model"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _training_environment() -> dict[str, str]:
    """Return the hermetic local-only environment used for trainer subprocesses."""
    environment = os.environ.copy()
    environment.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    environment.setdefault("TOKENIZERS_PARALLELISM", "false")
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    environment["DIFFUSERS_OFFLINE"] = "1"
    return environment


def prepare(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    selection_path = project_root / "build/identity/selection_manifest.json"
    if not selection_path.is_file():
        raise ValueError("selection manifest is missing; run process-identity first")
    selection = identity.read_json(selection_path)
    selected = [item for item in selection["selections"] if item.get("eligible_for_export")]
    if not selected:
        raise ValueError("selection contains no export-eligible identity images")
    dataset_root = project_root / "build/training/image_identity/dataset"
    split_records: dict[str, list[dict[str, Any]]] = {}
    for split in ("train", "validation", "calibration", "final_test"):
        records = []
        split_root = dataset_root / split
        for item in sorted((entry for entry in selected if entry["split"] == split), key=lambda entry: entry["asset_id"]):
            source = Path(item["path"])
            file_name = f"{item['asset_id']}{source.suffix.lower()}"
            _copy_verified(source, split_root / file_name, item["sha256"])
            records.append({
                "file_name": file_name,
                "text": item["caption"]["caption"],
                "asset_id": item["asset_id"],
                "group_id": item["group_id"],
                "source_sha256": item["sha256"],
                "person_mask": item["annotation"]["person_mask"],
                "shot_size": item["annotation"]["shot_size"],
                "viewpoint": item["annotation"].get("viewpoint"),
                "modality": item["modality"],
                "provenance": item["provenance"],
            })
        split_root.mkdir(parents=True, exist_ok=True)
        metadata = split_root / "metadata.jsonl"
        metadata.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in records))
        split_records[split] = records

    trigger = config["identity"]["trigger_token"]
    experiments = []
    # With 43 images and batch size one, these correspond to roughly 7, 12,
    # and 17 passes through the corpus. The previous accumulation-four plan
    # implied 56-112 passes and was rejected as an overfitting risk.
    for rank, learning_rate, steps in ((8, 1e-4, 300), (16, 1e-4, 500), (16, 5e-5, 700)):
        name = f"rank{rank}_lr{learning_rate:g}_steps{steps}"
        output = project_root / "build/training/image_identity/experiments" / name
        args = [
            str(TRAINER_PYTHON), "-m", "accelerate.commands.launch", str(TRAINER),
            "--pretrained_model_name_or_path", str(BASE_MODEL),
            "--dataset_name", str(dataset_root / "train"),
            "--image_column", "image", "--caption_column", "text",
            "--instance_prompt", f"{trigger}, a person",
            "--output_dir", str(output), "--rank", str(rank), "--lora_alpha", str(rank),
            "--lora_dropout", "0.05", "--learning_rate", str(learning_rate),
            "--max_train_steps", str(steps), "--caption_dropout", "0.1",
            "--train_batch_size", "1", "--gradient_accumulation_steps", "1",
            "--gradient_checkpointing", "--use_aspect_ratio_buckets", "--cache_latents", "--offload",
            "--mixed_precision", "fp16", "--seed", "260801", "--checkpointing_steps", "100",
            "--checkpoints_total_limit", "4", "--resume_from_checkpoint", "latest",
            # MPS validation reloads the full Flux pipeline and can exhaust the
            # unified memory budget mid-run. Held-out validation is performed by
            # the fixed-seed Comfy ablation stage, so the trainer is explicitly
            # instructed to avoid its intermediate/final inference path.
            "--skip_final_inference", "--report_to", "tensorboard",
        ]
        experiments.append({
            "name": name, "rank": rank, "alpha": rank, "dropout": 0.05,
            "learning_rate": learning_rate, "max_train_steps": steps,
            "seed": 260801, "output_dir": str(output), "command": args,
        })
    result = {
        "schema_version": 4,
        "identity_id": selection["identity_id"],
        "status": "prepared_not_trained",
        "trainer": {"path": str(TRAINER), "sha256": identity.sha256_file(TRAINER) if TRAINER.is_file() else None},
        "base_model": {"path": str(BASE_MODEL), "config_sha256": identity.sha256_file(BASE_MODEL / "model_index.json") if (BASE_MODEL / "model_index.json").is_file() else None},
        "selection_manifest_sha256": identity.sha256_file(selection_path),
        "dataset": {"root": str(dataset_root), "counts": {key: len(value) for key, value in split_records.items()}},
        "experiments": experiments,
    }
    output = project_root / "build/training/image_identity/training_plan.json"
    identity.write_json(output, result)
    return result


def train(project_root: Path) -> dict[str, Any]:
    plan = prepare(project_root)
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    selection = identity.read_json(project_root / "build/identity/selection_manifest.json")
    blockers = []
    if config["identity"]["consent"]["status"] != "verified":
        blockers.append("consent is not verified")
    if not selection.get("ready_for_training"):
        blockers.extend(selection.get("blockers", []))
    if not TRAINER.is_file() or not TRAINER_PYTHON.is_file():
        blockers.append("official FLUX.2 Klein trainer runtime is incomplete")
    backend = subprocess.run(
        [str(TRAINER_PYTHON), "-c", "import torch; print(int(torch.cuda.is_available() or (hasattr(torch.backends,'mps') and torch.backends.mps.is_available())))"],
        check=True, capture_output=True, text=True,
    ).stdout.strip() if TRAINER_PYTHON.is_file() else "0"
    if backend != "1":
        blockers.append("trainer runtime has neither CUDA nor MPS acceleration")
    if blockers:
        plan["status"] = "blocked_before_training"
        plan["blockers"] = list(dict.fromkeys(blockers))
        identity.write_json(project_root / "build/training/image_identity/training_plan.json", plan)
        raise RuntimeError("image identity training blocked: " + "; ".join(plan["blockers"]))
    # The project contract is fully local: all checkpoints, trainer code, and
    # datasets must already be on disk.  Prevent Hugging Face helpers invoked by
    # the trainer from attempting metadata lookups or implicit downloads.
    environment = _training_environment()
    smoke_root = project_root / "build/training/image_identity/smoke"
    smoke_complete = smoke_root / "smoke_complete.json"
    if not smoke_complete.is_file():
        smoke_command = list(plan["experiments"][0]["command"])

        def replace_value(flag: str, value: str) -> None:
            position = smoke_command.index(flag)
            smoke_command[position + 1] = value

        replace_value("--output_dir", str(smoke_root))
        replace_value("--max_train_steps", "1")
        replace_value("--checkpointing_steps", "1")
        replace_value("--checkpoints_total_limit", "1")
        resume = smoke_command.index("--resume_from_checkpoint")
        del smoke_command[resume:resume + 2]
        validation = smoke_command.index("--validation_prompt")
        del smoke_command[validation:validation + 2]
        validation_count = smoke_command.index("--num_validation_images")
        del smoke_command[validation_count:validation_count + 2]
        smoke_command.append("--skip_final_inference")
        identity.write_json(smoke_root / "command.json", {"command": smoke_command})
        subprocess.run(smoke_command, check=True, env=environment)
        smoke_adapters = sorted(smoke_root.glob("*.safetensors"))
        if not smoke_adapters:
            raise RuntimeError("one-step FLUX trainer smoke test emitted no safetensors adapter")
        identity.write_json(smoke_complete, {
            "status": "complete", "steps": 1,
            "adapters": [{"path": str(item), "sha256": identity.sha256_file(item)} for item in smoke_adapters],
        })
    completed = []
    for experiment in plan["experiments"]:
        output_root = Path(experiment["output_dir"])
        marker = output_root / "experiment_complete.json"
        signature = _experiment_signature(experiment, plan)
        if marker.is_file():
            try:
                prior = identity.read_json(marker)
            except (OSError, ValueError):
                prior = {}
            adapters = sorted(output_root.glob("*.safetensors"))
            if prior.get("signature") == signature and adapters and all(item.is_file() for item in adapters):
                audits = [adapter_validation.validate(item, expected_rank=experiment["rank"]) for item in adapters]
                completed.append({"name": experiment["name"], "adapters": [str(item) for item in adapters], "audits": audits, "resumed": False, "skipped": True})
                continue
        plan["status"] = "training"
        plan["current_experiment"] = experiment["name"]
        plan["current_signature"] = signature
        identity.write_json(project_root / "build/training/image_identity/training_plan.json", plan)
        subprocess.run(experiment["command"], check=True, env=environment)
        adapters = sorted(output_root.glob("*.safetensors"))
        if not adapters:
            raise RuntimeError(f"trainer emitted no safetensors adapter for {experiment['name']}")
        adapter_records = [{"path": str(item), "sha256": identity.sha256_file(item)} for item in adapters]
        audits = [adapter_validation.validate(item, expected_rank=experiment["rank"]) for item in adapters]
        identity.write_json(marker, {"status": "complete", "name": experiment["name"], "signature": signature,
                                     "adapters": adapter_records, "audits": audits})
        completed.append({"name": experiment["name"], "adapters": [str(item) for item in adapters], "audits": audits, "resumed": False, "skipped": False})
    plan["status"] = "trained_pending_heldout_evaluation"
    plan.pop("current_experiment", None)
    plan.pop("current_signature", None)
    plan["completed"] = completed
    identity.write_json(project_root / "build/training/image_identity/training_plan.json", plan)
    return plan


def audit_completed(project_root: Path) -> dict[str, Any]:
    """Audit already-completed matrix outputs without touching trainer state."""
    project_root = project_root.resolve()
    plan_path = project_root / "build/training/image_identity/training_plan.json"
    if not plan_path.is_file():
        raise ValueError("image training plan is missing; run train-image-identity first")
    plan = identity.read_json(plan_path)
    audited = []
    for experiment in plan.get("experiments", []):
        root = Path(experiment["output_dir"])
        marker_path = root / "experiment_complete.json"
        if not marker_path.is_file():
            raise ValueError(f"experiment is not complete: {experiment['name']}")
        marker = identity.read_json(marker_path)
        adapters = [Path(item["path"]) for item in marker.get("adapters", [])]
        if not adapters:
            adapters = sorted(root.glob("pytorch_lora_weights.safetensors"))
        if not adapters:
            raise ValueError(f"completed experiment has no adapter: {experiment['name']}")
        audits = [adapter_validation.validate(item, expected_rank=experiment["rank"]) for item in adapters]
        marker["audits"] = audits
        identity.write_json(marker_path, marker)
        audited.append({"name": experiment["name"], "audits": audits})
    plan["status"] = "trained_pending_heldout_evaluation"
    plan["adapter_audits"] = audited
    identity.write_json(plan_path, plan)
    return {"status": plan["status"], "experiments": audited}
