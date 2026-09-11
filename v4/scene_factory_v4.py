#!/usr/bin/env python3
"""Scene Factory v4 resumable identity-pipeline command line."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import identity_pipeline as identity
import training_harness as training
import identity_annotations
import identity_captions
import reference_bank
import image_training
import image_evaluation
import motion_tracking
import usdz_controls
import image_workflows
import usdz_ingestion
import avatar_validation
import comfy_executor
import adapter_validation
import identity_bundle
import modality_audit
import stage_stubs
import goal_audit
import video_workflows
import video_audio_pipeline
import video_executor
import voice_flow


DEFAULT_PROJECT = Path(__file__).parent / "examples" / "modeling_interview"
FLUX_TRAINER_ROOT = Path("/Users/voxels/ComfyUI-Installs/FLUX2-Trainer")
COMFY_ROOT = Path("/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI")
FLUX_BASE = Path("/Users/voxels/.cache/huggingface/hub/models--black-forest-labs--FLUX.2-klein-base-4B/snapshots/a3b4f4849157f664bdbc776fd7453c2783562f4d")
FLUX_DISTILLED = Path("/Users/voxels/ComfyUI-Shared/models/diffusion_models/flux-2-klein-4b.safetensors")
LTX_ROOT = Path("/Users/voxels/Library/Application Support/LTXDesktop/models/ltx-2.5")


def git_commit(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def file_contract(path: Path, *, hash_now: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path), "present": path.is_file()}
    if not path.is_file():
        return record
    stat = path.stat()
    record.update({"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    if hash_now:
        record["sha256"] = identity.sha256_file(path)
        record["hash_status"] = "complete"
    else:
        record["sha256"] = None
        record["hash_status"] = "deferred_until_consumption"
    return record


def torch_backend(python: Path) -> dict[str, Any]:
    if not python.is_file():
        return {"python": str(python), "available": False, "reason": "python_not_found"}
    code = (
        "import json, torch; print(json.dumps({"
        "'torch':torch.__version__,'cuda':torch.cuda.is_available(),"
        "'mps':bool(getattr(torch.backends,'mps',None) and torch.backends.mps.is_available())}))"
    )
    try:
        result = subprocess.run([str(python), "-c", code], check=True, capture_output=True, text=True, timeout=30)
        value = json.loads(result.stdout)
        value.update({"python": str(python), "available": bool(value["cuda"] or value["mps"])})
        return value
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        return {"python": str(python), "available": False, "reason": type(error).__name__}


def comfy_api_contract(server_url: str = "http://127.0.0.1:8188") -> dict[str, Any]:
    """Probe the already-running local ComfyUI API; never downloads models."""
    url = server_url.rstrip("/") + "/system_stats"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode())
        system = payload.get("system", {})
        devices = payload.get("devices", [])
        return {
            "status": "available", "server": server_url.rstrip("/"),
            "version": system.get("comfyui_version"),
            "python": system.get("python_version"),
            "pytorch": system.get("pytorch_version"),
            "devices": [{"name": d.get("name"), "type": d.get("type"),
                         "vram_total": d.get("vram_total"), "vram_free": d.get("vram_free")}
                        for d in devices],
            "inference_accelerator_available": any(d.get("type") in {"cuda", "mps"} for d in devices),
        }
    except (OSError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return {"status": "unavailable", "server": server_url.rstrip("/"), "reason": type(error).__name__,
                "inference_accelerator_available": False}


def unreal_contract(editor: Path | None) -> dict[str, Any]:
    """Return an auditable Unreal installation contract without launching the editor."""
    if editor is None:
        return {"path": None, "present": False, "status": "not_found"}
    engine_root = editor.parents[3]
    build_file = engine_root / "Engine/Build/Build.version"
    build: dict[str, Any] = {}
    if build_file.is_file():
        try:
            build = json.loads(build_file.read_text())
        except (OSError, json.JSONDecodeError):
            build = {"status": "unreadable"}
    plugin_specs = {
        "ControlRig": engine_root / "Engine/Plugins/Animation/ControlRig/ControlRig.uplugin",
        "LiveLink": engine_root / "Engine/Plugins/Animation/LiveLink/LiveLink.uplugin",
        "RigLogic": engine_root / "Engine/Plugins/Animation/RigLogic/RigLogic.uplugin",
        "USDImporter": engine_root / "Engine/Plugins/Importers/USDImporter/USDImporter.uplugin",
        "MetaHumanAnimator": engine_root / "Engine/Plugins/MetaHuman/MetaHumanAnimator/MetaHuman.uplugin",
        "AppleARKit": engine_root / "Engine/Plugins/Runtime/AR/AppleAR/AppleARKit/AppleARKit.uplugin",
        "AppleARKitFaceSupport": engine_root / "Engine/Plugins/Runtime/AR/AppleAR/AppleARKitFaceSupport/AppleARKitFaceSupport.uplugin",
    }
    plugins = {}
    for name, path in plugin_specs.items():
        item: dict[str, Any] = {"path": str(path), "present": path.is_file()}
        if path.is_file():
            try:
                spec = json.loads(path.read_text())
                item.update({
                    "version_name": spec.get("VersionName"),
                    "enabled_by_default": spec.get("EnabledByDefault"),
                    "can_contain_content": spec.get("CanContainContent"),
                    "modules": [module.get("Name") for module in spec.get("Modules", []) if isinstance(module, dict)],
                })
            except (OSError, json.JSONDecodeError):
                item["metadata_status"] = "unreadable"
        plugins[name] = item
    architectures = None
    try:
        result = subprocess.run(["file", str(editor)], capture_output=True, text=True, timeout=15)
        architectures = (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        architectures = None
    return {
        "path": str(editor),
        "present": True,
        "engine_root": str(engine_root),
        "build_file": str(build_file),
        "build": build,
        "platform": {"target": "Mac", "binary_file": architectures},
        "plugins": plugins,
        "status": "available" if build else "build_metadata_unavailable",
    }


def metal_toolchain_contract() -> dict[str, Any]:
    """Probe the Xcode Metal compiler without launching Unreal or a GUI.

    UE's macOS renderer is Metal-only in the installed distribution.  Keeping
    this probe in preflight makes a missing Xcode component an explicit,
    actionable dependency instead of a mysterious editor crash.  The probe is
    deliberately read-only; installing Apple's component remains an explicit
    operator action.
    """
    developer_dir = None
    sdk_version = None
    sdk_path = None
    metal_path = None
    metal_probe = None
    for args, key in (
        (["xcode-select", "-p"], "developer_dir"),
        (["xcrun", "--sdk", "macosx", "--show-sdk-version"], "sdk_version"),
        (["xcrun", "--sdk", "macosx", "--show-sdk-path"], "sdk_path"),
        (["xcrun", "--find", "metal"], "metal_path"),
    ):
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=15)
            value = (result.stdout or "").strip()
            if result.returncode != 0:
                value = value or (result.stderr or "").strip()
            if key == "developer_dir":
                developer_dir = value or None
            elif key == "sdk_version":
                sdk_version = value or None
            elif key == "sdk_path":
                sdk_path = value or None
            else:
                metal_path = value or None
        except (OSError, subprocess.TimeoutExpired):
            continue
    if metal_path and Path(metal_path).is_file():
        try:
            result = subprocess.run([metal_path, "-v"], capture_output=True, text=True, timeout=20)
            metal_probe = {
                "returncode": result.returncode,
                "stdout": (result.stdout or "")[-1000:],
                "stderr": (result.stderr or "")[-1000:],
            }
        except (OSError, subprocess.TimeoutExpired) as error:
            metal_probe = {"status": type(error).__name__}
    available = bool(metal_path and Path(metal_path).is_file() and metal_probe and metal_probe.get("returncode") == 0)
    return {
        "status": "available" if available else "missing_or_unusable",
        "developer_dir": developer_dir,
        "sdk_version": sdk_version,
        "sdk_path": sdk_path,
        "metal_path": metal_path,
        "metal_probe": metal_probe,
        "install_command": "xcodebuild -downloadComponent MetalToolchain",
        "editor_launch_attempted": False,
        "safe_commandlet_flags": ["-nullrhi", "-unattended", "-nop4", "-nosplash", "-nosound"],
        "note": (
            "UE macOS rendering uses Metal; do not launch the editor until the "
            "Xcode Metal Toolchain is installed. Headless metadata/import checks "
            "may be attempted with UnrealEditor-Cmd -nullrhi after preflight."
        ),
    }


def preflight(project_root: Path, *, hash_models: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    identity.validate_config(config)
    source_root = identity.resolve_source_root(project_root, config["source_root"])
    trainer_script = FLUX_TRAINER_ROOT / "diffusers/examples/dreambooth/train_dreambooth_lora_flux2_klein.py"
    ltx_transformer = LTX_ROOT / "ltx-2.5-22b-distilled-transformer-bf16.safetensors"
    ltx_video_vae = LTX_ROOT / "ltx-2.5-video-vae-bf16.safetensors"
    ltx_audio_vae = LTX_ROOT / "ltx-2.5-audio-vae-bf16.safetensors"
    comfy_python = Path("/Users/voxels/ComfyUI-Installs/ComfyUI/standalone-env/bin/python")
    trainer_python = FLUX_TRAINER_ROOT / ".venv/bin/python"
    backends = {
        "flux_trainer": torch_backend(trainer_python),
        "comfyui": torch_backend(comfy_python),
    }
    comfy_api = comfy_api_contract()
    consent = config["identity"]["consent"]["status"]
    audio_files = []
    for _, spec in config["modalities"].items():
        if spec["kind"] == "audio":
            audio_files.extend(identity.discover(source_root, spec["globs"], "audio"))
    local_voice = project_root / "voice"
    if local_voice.is_dir():
        audio_files.extend(sorted(path for path in local_voice.iterdir()
                                  if path.is_file() and path.suffix.lower() in
                                  {".wav", ".aiff", ".aif", ".flac", ".m4a", ".mp3", ".ogg"}))
    audio_files = sorted({item.resolve() for item in audio_files})
    voice_input = voice_flow.build_voice_manifest(project_root, config)
    performance_audio = [Path(item["path"]).resolve() for item in voice_input.get("channels", {}).get("performance_audio", [])]
    reference_audio = [Path(item["path"]).resolve() for item in voice_input.get("channels", {}).get("reference_audio", [])]
    # Only performance audio is a final-delivery prerequisite. Reference audio
    # is reported separately so it cannot be silently used as the TTS master.
    if config.get("voice_root"):
        audio_files = performance_audio
    else:
        audio_files = sorted(set(audio_files) | set(performance_audio))
    executables = {
        name: {"path": shutil.which(name), "present": shutil.which(name) is not None}
        for name in ("ffmpeg", "ffprobe", "swift", "xcrun", "git")
    }
    blender = Path("/Applications/Blender.app/Contents/MacOS/blender")
    executables["blender"] = {"path": str(blender), "present": blender.is_file()}
    unreal_candidates = [
        Path("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor"),
        Path("/Applications/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor"),
        Path("/Users/voxels/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor"),
    ]
    unreal_editor = next((item for item in unreal_candidates if item.is_file()), None)
    metal = metal_toolchain_contract()
    models = {
        "flux_klein_4b_base_transformer": file_contract(FLUX_BASE / "transformer/diffusion_pytorch_model.safetensors", hash_now=hash_models),
        "flux_klein_4b_distilled": file_contract(FLUX_DISTILLED, hash_now=hash_models),
        "ltx_2_5_distilled_transformer": file_contract(ltx_transformer, hash_now=hash_models),
        "ltx_2_5_video_vae": file_contract(ltx_video_vae, hash_now=hash_models),
        "ltx_2_5_audio_vae": file_contract(ltx_audio_vae, hash_now=hash_models),
    }
    nodes = {
        "ltx_video": COMFY_ROOT / "custom_nodes/ComfyUI-LTXVideo",
        # Current ComfyUI ships the LTX 2.5 graph nodes in-tree.  Keep the
        # historical plugin probe, but do not call native inference unavailable
        # merely because that separate plugin directory is absent.
        "ltx_native_video_nodes": COMFY_ROOT / "comfy_extras/nodes_lt.py",
        "ltx_native_audio_nodes": COMFY_ROOT / "comfy_extras/nodes_lt_audio.py",
        "ltx_video_lora_nodes": COMFY_ROOT / "custom_nodes/comfyui-ltxvideolora",
        "pulid_flux2": COMFY_ROOT / "custom_nodes/ComfyUI-PuLID-Flux2",
        "jlc_flux2_controlnet": COMFY_ROOT / "custom_nodes/JLC-Flux2-ControlNet",
    }
    # Blender is an optional USD conversion fallback; it must not block the
    # preferred Unreal path (or the image/video tracks) when unavailable.
    stable_missing = [name for name, item in executables.items() if name in {"ffmpeg", "ffprobe", "swift"} and not item["present"]]
    stable_missing.extend(name for name, item in models.items() if not item["present"])
    if not trainer_script.is_file():
        stable_missing.append("flux2_klein_trainer")
    safety_blockers = []
    if consent != "verified":
        safety_blockers.append(f"consent status is {consent}")
    if not audio_files:
        safety_blockers.append("supplied TTS audio is missing")
    execution_blockers = []
    if not any(item.get("available") for item in backends.values()) and not comfy_api.get("inference_accelerator_available"):
        execution_blockers.append("no CUDA or MPS PyTorch backend is available in the installed trainer/runtime environments")
    avatar_blockers = []
    if unreal_editor and metal["status"] != "available":
        avatar_blockers.append(
            "Unreal Engine is installed but the Xcode Metal Toolchain is missing or unusable; "
            "install it with xcodebuild -downloadComponent MetalToolchain before editor/render tests"
        )
    report = {
        "schema_version": 4,
        "project": str(project_root),
        "identity_id": config["identity"]["id"],
        "run_mode": config["run_mode"],
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "python": sys.version.split()[0], "cpu_count": os.cpu_count()},
        "source": {"root": str(source_root), "consent_status": consent, "audio_files": [str(item) for item in audio_files],
                    "reference_audio_files": [str(item) for item in reference_audio],
                    "voice_input_manifest": str((project_root / "build/identity/voice/voice_input_manifest.json").resolve())},
        "executables": executables,
        "torch_backends": backends,
        "comfy_api": comfy_api,
        "models": models,
        "trainers": {
            "flux2_klein": {"path": str(trainer_script), "present": trainer_script.is_file(), "upstream_commit": git_commit(FLUX_TRAINER_ROOT / "diffusers")},
            "ltx2": {"present": False, "status": "unavailable", "reason": "official LTX-2 trainer repository is not installed"},
        },
        "nodes": {name: {"path": str(path), "present": path.is_file() or path.is_dir(), "upstream_commit": git_commit(path)} for name, path in nodes.items()},
        "avatar_backend": {
            "preferred": "unreal_engine_5.8",
            "editor": unreal_contract(unreal_editor),
            "fallback": {"name": "blender_usd_conversion", "path": str(blender), "present": blender.is_file()},
            "metal_toolchain": metal,
            "status": (
                "available" if unreal_editor and metal["status"] == "available"
                else "installed_but_render_blocked" if unreal_editor
                else "awaiting_unreal_install"
            ),
        },
        "routes": {
            "flux_klein_4b_lora": {"status": "installed_but_execution_blocked" if execution_blockers else "stable"},
            "flux_klein_9b_refcontrol": {"status": "unavailable", "reason": "model and RefControl adapters are not installed"},
            "flux2_dev_controlnet_union": {"status": "unavailable", "reason": "FLUX.2 dev model, Union checkpoint, and JLC node are not installed"},
            "pulid_flux2": {"status": "experimental" if nodes["pulid_flux2"].is_dir() else "unavailable"},
            "ltx_2_5_identity_lora": {"status": "unavailable", "reason": "runtime weights exist but official trainer and supported accelerator backend are unavailable"},
            "ltx_2_5_native_inference": {
                "status": "stable" if (
                    models["ltx_2_5_distilled_transformer"]["present"]
                    and models["ltx_2_5_video_vae"]["present"]
                    and nodes["ltx_native_video_nodes"].is_file()
                    and nodes["ltx_native_audio_nodes"].is_file()
                ) else "blocked",
                "reason": None if (
                    models["ltx_2_5_distilled_transformer"]["present"]
                    and models["ltx_2_5_video_vae"]["present"]
                    and nodes["ltx_native_video_nodes"].is_file()
                    and nodes["ltx_native_audio_nodes"].is_file()
                ) else "native ComfyUI LTX nodes or runtime weights are missing",
            },
            "persona_avatar_unreal": {
                "status": (
                    "stable" if unreal_editor and metal["status"] == "available"
                    else "blocked_metal_toolchain" if unreal_editor
                    else "blocked"
                ),
                "reason": (
                    None if unreal_editor and metal["status"] == "available"
                    else "Xcode Metal Toolchain is missing or unusable" if unreal_editor
                    else "Unreal Engine 5.8 is not installed"
                ),
            },
        },
        "blockers": {
            "safety": safety_blockers,
            "dependencies": stable_missing,
            "execution": execution_blockers,
            "avatar": avatar_blockers,
        },
    }
    # Audio is a final-delivery prerequisite, but it is not needed to inventory,
    # annotate, select, or train the photographic identity.  Keep it visible in
    # the safety blockers while allowing those earlier stages to proceed.
    deferred_safety = [item for item in safety_blockers if item == "supplied TTS audio is missing"]
    hard_safety = [item for item in safety_blockers if item not in deferred_safety]
    report["blockers"]["deferred"] = deferred_safety
    report["ready_for_ingest"] = not stable_missing and not hard_safety
    report["ready_for_complete_run"] = (
        report["ready_for_ingest"] and not safety_blockers and not execution_blockers and not avatar_blockers
        and report["trainers"]["ltx2"]["present"]
    )
    # A preflight report is complete only when the entire automatic delivery
    # contract is satisfiable.  Partial readiness remains explicitly blocked so
    # the CLI cannot present diagnostics as a successful run.
    report["status"] = "complete" if report["ready_for_complete_run"] else "blocked"
    output = project_root / "build/pipeline/preflight.json"
    identity.write_json(output, report)
    return report


def unavailable_stage(name: str) -> None:
    raise RuntimeError(
        f"{name} is not yet implemented as an executing v4 stage; refusing to emit a placeholder success"
    )


def _source_fingerprint(project: Path) -> str:
    """Content fingerprint for source inputs used by automatic-run skipping."""
    config = identity.read_json(project / "identity.json")
    source_root = identity.resolve_source_root(project, config["source_root"])
    records = []
    for path in sorted(item for item in source_root.rglob("*") if item.is_file()):
        lowered = str(path).casefold()
        if "koleka" in lowered or "k0l3k4" in lowered:
            continue
        records.append({"path": str(path.relative_to(source_root)), "sha256": identity.sha256_file(path)})
    return identity.sha256_bytes(json.dumps(records, sort_keys=True, separators=(",", ":")).encode())


def _stage_signature(project: Path, name: str, source_fingerprint: str,
                     inputs: list[Path]) -> str:
    records = []
    for path in inputs:
        path = path.resolve()
        records.append({"path": str(path), "sha256": identity.sha256_file(path) if path.is_file() else None})
    payload = {"stage": name, "source_fingerprint": source_fingerprint,
               "config_sha256": identity.sha256_file(project / "identity.json"),
               "code_sha256": identity.sha256_file(Path(__file__)), "inputs": records}
    return identity.sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _outputs_match(stage: dict[str, Any], outputs: list[Path]) -> bool:
    recorded = stage.get("output_hashes", {})
    if not outputs or set(recorded) != {str(path.resolve()) for path in outputs}:
        return False
    return all(path.is_file() and identity.sha256_file(path) == recorded[str(path.resolve())]
               for path in outputs)


def _raise_for_blocked_stage(name: str, result: Any) -> None:
    """Prevent a stage returning a blocked contract from being marked complete."""
    if isinstance(result, dict) and result.get("status") in {"blocked", "incomplete", "error"}:
        blockers = result.get("blockers") or result.get("reason") or result.get("error") or result.get("status")
        raise RuntimeError(f"{name} returned {result.get('status')}: {blockers}")


def _automatic_run(project: Path, *, hash_models: bool = False,
                   server_url: str | None = None) -> dict[str, Any]:
    """Orchestrate the complete automatic pipeline with resumable stage records."""
    project = project.resolve()
    pipeline_root = project / "build/pipeline"
    pipeline_root.mkdir(parents=True, exist_ok=True)
    run_path = pipeline_root / "automatic_run.json"
    previous = identity.read_json(run_path) if run_path.is_file() else None
    preflight_report = preflight(project, hash_models=hash_models)
    blockers = preflight_report.get("blockers", {})
    hard_preflight_blockers = (
        list(blockers.get("dependencies", []))
        + list(blockers.get("execution", []))
        + [item for item in blockers.get("safety", [])
           if item not in blockers.get("deferred", [])]
    )
    if hard_preflight_blockers:
        # Preserve a same-identity ledger on dependency blocks so a later retry
        # can skip stages whose signatures and output hashes are still intact.
        if (previous and previous.get("identity_id") == preflight_report["identity_id"]
                and previous.get("status") in {"running", "blocked", "complete"}):
            report = previous
            report["status"] = "blocked"
            report["blockers"] = preflight_report["blockers"]
        else:
            report = {"schema_version": 1, "status": "blocked", "identity_id": preflight_report["identity_id"],
                      "completed_stages": [], "blockers": preflight_report["blockers"]}
        identity.write_json(run_path, report)
        raise RuntimeError(f"preflight blocked complete run: {preflight_report['blockers']}")

    # A completed ledger is also resumable: intact stages are skipped by signature
    # and output hash, while changed inputs invalidate that stage and downstream work.
    report = previous if (previous and previous.get("identity_id") == preflight_report["identity_id"]
                          and previous.get("status") in {"running", "blocked", "complete"}) else {
        "schema_version": 1, "status": "running", "identity_id": preflight_report["identity_id"],
        "completed_stages": [], "stages": {}, "preflight": str((pipeline_root / "preflight.json").resolve())}
    report["status"] = "running"
    report.pop("blocked_stage", None)
    report.pop("error", None)
    report.setdefault("stages", {})
    report["preflight"] = str((pipeline_root / "preflight.json").resolve())
    identity.write_json(run_path, report)
    source_fingerprint = _source_fingerprint(project)
    stages = [
        ("ingest", lambda: identity.build(project, extract_web_media=True), [project / "identity.json"], [project / "build/identity/asset_manifest.json"]),
        ("render_usdz_controls", lambda: usdz_controls.render(project), [project / "build/identity/asset_manifest.json"], [project / "build/identity/geometry/geometry_control_manifest.json"]),
        ("ingest_usdz", lambda: usdz_ingestion.ingest(project), [project / "build/identity/geometry/geometry_control_manifest.json"], [project / "build/identity/geometry/usdz_ingestion_manifest.json"]),
        ("process_identity", lambda: {
            "annotations": identity_annotations.annotate(project),
            "motion": motion_tracking.track(project),
            "video_audio": video_audio_pipeline.prepare_video_audio(project),
            "captions": identity_captions.generate_pinned(project),
            "selection": training.select(project),
            "reference_bank": reference_bank.build(project),
        }, [project / "build/identity/asset_manifest.json"], [project / "build/identity/selection_manifest.json", project / "build/identity/reference_bank/reference_bank.json"]),
        ("train_image_identity", lambda: image_training.train(project), [project / "build/identity/selection_manifest.json"], [project / "build/training/image_identity/training_plan.json"]),
        ("benchmark_image_controls", lambda: image_workflows.compile_workflows(project), [project / "build/identity/reference_bank/reference_bank.json", project / "build/training/image_identity/training_plan.json"], [project / "build/workflows/image_ablation/manifest.json"]),
        ("evaluate_image_identity", lambda: image_evaluation.evaluate(project, server_url=server_url or "http://127.0.0.1:8188"), [project / "build/workflows/image_ablation/manifest.json"], [project / "build/training/image_identity/heldout_evaluation_plan.json"]),
        ("train_video_identity", lambda: video_audio_pipeline.train_video_identity(project), [project / "build/identity/video/visual_identity_manifest.json"], [project / "build/training/video_identity/training_plan.json"]),
        ("validate", lambda: modality_audit.build_consumption_report(project), [project / "build/identity/video_audio_manifest.json"], [project / "build/validation/modality_consumption_report.json"]),
        ("package_identity_bundle", lambda: identity_bundle.build_bundle(project, project / "build/identity_bundle"), [project / "build/validation/modality_consumption_report.json"], [project / "build/identity_bundle/bundle.json"]),
    ]
    for name, action, inputs, outputs in stages:
        signature = _stage_signature(project, name, source_fingerprint, inputs)
        prior = report["stages"].get(name, {})
        if prior.get("signature") == signature and prior.get("status") in {"complete", "skipped"} and _outputs_match(prior, outputs):
            report["stages"][name] = {**prior, "status": "skipped", "signature": signature}
            if name not in report["completed_stages"]:
                report["completed_stages"].append(name)
            identity.write_json(run_path, report)
            continue
        try:
            result = action()
            _raise_for_blocked_stage(name, result)
        except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
            report["status"] = "blocked"
            report["blocked_stage"] = name
            report["error"] = str(error)
            identity.write_json(run_path, report)
            raise RuntimeError(f"automatic run blocked at {name}: {error}") from error
        report["stages"][name] = {"status": "complete", "signature": signature,
                                   "output_hashes": {str(path.resolve()): identity.sha256_file(path) for path in outputs if path.is_file()}}
        if name not in report["completed_stages"]:
            report["completed_stages"].append(name)
        identity.write_json(run_path, report)
    # A run with all executable stages complete can still be blocked from final
    # delivery by deferred inputs (for example audio) or avatar-runtime proof.
    # Preserve the completed stage evidence but never call that final state
    # complete while those blockers remain.
    final_blockers = preflight_report.get("blockers", {})
    report["blockers"] = final_blockers
    report["status"] = "blocked" if any(final_blockers.get(key, [])
                                         for key in ("safety", "dependencies", "execution", "avatar")) else "complete"
    identity.write_json(run_path, report)
    return report


def _promoted_image_route(project: Path) -> str:
    """Resolve the production image route only after explicit promotion evidence."""
    runtime_path = project.resolve() / "build/runtime/image_runtime.json"
    if not runtime_path.is_file():
        raise RuntimeError("image runtime contract is missing; compile and promote an image route first")
    runtime = identity.read_json(runtime_path)
    selected = runtime.get("selected_route")
    if not isinstance(selected, str) or not selected:
        raise RuntimeError("no promoted image route; held-out evaluation must select a production route first")
    if runtime.get("promotion_required") is True and runtime.get("route_selection") != "promoted":
        raise RuntimeError("image runtime promotion is not complete; refusing to generate from an unpromoted route")
    return selected


def run_command(command: str, project: Path, hash_models: bool = False, *, route: str | None = None,
                server_url: str | None = None, adapter_path: str | None = None,
                prompt_override: str | None = None, negative_prompt_override: str | None = None,
                seed: int | None = None, filename_prefix: str | None = None) -> dict[str, Any]:
    if command == "preflight":
        return preflight(project, hash_models=hash_models)
    if command == "ingest":
        manifest, characteristics = identity.build(project, extract_web_media=True)
        return {"manifest": manifest, "characteristics": characteristics}
    if command == "process-identity":
        annotations = identity_annotations.annotate(project)
        motion = motion_tracking.track(project)
        video_audio = video_audio_pipeline.prepare_video_audio(project)
        captions = identity_captions.generate_pinned(project)
        selection, conditioning = training.select(project)
        references = reference_bank.build(project)
        return {"annotations": annotations, "motion": motion, "video_audio": video_audio, "captions": captions, "selection": selection, "conditioning": conditioning, "reference_bank": references}
    if command == "render-usdz-controls":
        return usdz_controls.render(project)
    if command == "ingest-usdz":
        return usdz_ingestion.ingest(project)
    if command == "validate-avatar":
        roots = sorted(path.parent for path in (project / "build/avatar").glob("*/avatar_manifest.json"))
        if not roots:
            raise RuntimeError("no avatar manifests found; run the configured avatar export stage first")
        return {"avatars": [avatar_validation.validate(path) for path in roots]}
    if command == "train-image-identity":
        return image_training.train(project)
    if command == "benchmark-image-controls":
        return image_workflows.compile_workflows(project)
    if command == "execute-image-workflow":
        return comfy_executor.execute(
            project, route or "native_reference", server_url=server_url or "http://127.0.0.1:8188",
            prompt_override=prompt_override, negative_prompt_override=negative_prompt_override,
            seed=seed, filename_prefix=filename_prefix,
        )
    if command == "generate-image":
        selected = _promoted_image_route(project)
        if route is not None and route != selected:
            raise RuntimeError(f"requested image route {route!r} is not the promoted route {selected!r}")
        return comfy_executor.execute(
            project, selected, server_url=server_url or "http://127.0.0.1:8188",
            prompt_override=prompt_override, negative_prompt_override=negative_prompt_override,
            seed=seed, filename_prefix=filename_prefix,
        )
    if command == "validate-image-adapter":
        if not adapter_path:
            raise RuntimeError("--adapter is required for validate-image-adapter")
        return adapter_validation.validate(Path(adapter_path))
    if command == "audit-image-matrix":
        return image_training.audit_completed(project)
    if command == "prepare-video-audio":
        return video_audio_pipeline.prepare_video_audio(project)
    if command == "inspect-voice-flow":
        config = identity.read_json(project / "identity.json")
        return voice_flow.build_voice_manifest(project, config)
    if command == "train-video-identity":
        return video_audio_pipeline.train_video_identity(project)
    if command == "generate-video":
        return video_executor.execute(project, server_url=server_url or "http://127.0.0.1:8188")
    if command == "compile-video-workflow":
        return video_workflows.compile_workflow(project, server_url=server_url)
    if command == "plan-image-evaluation":
        return image_evaluation.build_plan(project)
    if command == "evaluate-image-identity":
        return image_evaluation.evaluate(project, server_url=server_url or "http://127.0.0.1:8188")
    if command == "package-identity-bundle":
        if not adapter_path:
            raise RuntimeError("--destination is required for package-identity-bundle")
        return identity_bundle.build_bundle(project, Path(adapter_path))
    if command == "validate":
        return modality_audit.build_consumption_report(project)
    if command == "emit-stubs":
        return stage_stubs.emit(project)
    if command == "audit-goal":
        return goal_audit.audit(project)
    if command == "run":
        return _automatic_run(project, hash_models=hash_models, server_url=server_url)
    unavailable_stage(command)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=[
        "preflight", "ingest", "process-identity", "ingest-usdz", "render-usdz-controls", "validate-avatar",
        "train-image-identity", "audit-image-matrix", "plan-image-evaluation", "evaluate-image-identity", "benchmark-image-controls", "execute-image-workflow", "validate-image-adapter", "prepare-video-audio", "inspect-voice-flow", "train-video-identity",
        "generate-image", "generate-video", "compile-video-workflow", "validate", "emit-stubs", "audit-goal", "package-identity-bundle", "run",
    ])
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--hash-models", action="store_true", help="compute full SHA-256 hashes for large model files")
    parser.add_argument("--route", default=None, help="compiled image route (production route for generate-image)")
    parser.add_argument("--server-url", default=None, help="ComfyUI API base URL for execute-image-workflow")
    parser.add_argument("--adapter", default=None, help="LoRA safetensors path for validate-image-adapter")
    parser.add_argument("--destination", default=None, help="output directory for package-identity-bundle")
    parser.add_argument("--prompt", dest="prompt_override", default=None, help="prompt override for image generation")
    parser.add_argument("--negative-prompt", dest="negative_prompt_override", default=None, help="negative prompt override")
    parser.add_argument("--seed", type=int, default=None, help="fixed seed for image generation")
    parser.add_argument("--filename-prefix", default=None, help="safe output filename prefix for image generation")
    arguments = parser.parse_args(argv)
    try:
        result = run_command(arguments.command, arguments.project, hash_models=arguments.hash_models,
                             route=arguments.route, server_url=arguments.server_url,
                             adapter_path=arguments.adapter or arguments.destination,
                             prompt_override=arguments.prompt_override,
                             negative_prompt_override=arguments.negative_prompt_override,
                             seed=arguments.seed, filename_prefix=arguments.filename_prefix)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "blocked", "command": arguments.command, "error": str(error)}, indent=2), file=sys.stderr)
        return 2
    result_status = result.get("status") if isinstance(result, dict) else None
    command_status = result_status if result_status in {"blocked", "incomplete", "error", "stubbed"} else "complete"
    print(json.dumps({"status": command_status, "command": arguments.command, "result": result}, indent=2))
    return 2 if command_status != "complete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
