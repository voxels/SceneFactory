#!/usr/bin/env python3

import copy
import json
import os
from pathlib import Path

import scene_factory as core


FLUX_MODEL = "flux-2-klein-4b.safetensors"
FLUX_TEXT_ENCODER = "qwen_3_4b.safetensors"
FLUX_VAE = "flux2-vae.safetensors"
K0L3K4_LORA = "Ad2184/k0l3k4_flux2_klein/pytorch_lora_weights.safetensors"
LTX_TEXT_ENCODER = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
REFERENCE_IMAGES = ["1_k0ll3k4.jpeg", "2_k0l3k4.jpeg", "3_k0l3k4.jpeg"]
LTX_MODELS = {
    "diffusion_model": "ltx-2.5-22b-distilled-transformer-bf16.safetensors",
    "audio_vae": "ltx-2.5-audio-vae-bf16.safetensors",
    "video_vae": "ltx-2.5-video-vae-bf16.safetensors"
}
LTX_OPTIONAL_MODELS = {
    "latent_upscaler": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
}
NEGATIVE = (
    "duplicate subject, identity change, wrong apparent age, malformed face, malformed hands, "
    "extra limbs, extra people, text artifacts, watermark"
)
CANDIDATE_VARIANTS = [
    {"number": 1, "angle": "base approved camera axis", "style": "baseline cinematic contrast"},
    {"number": 2, "angle": "camera shifted slightly left by about ten degrees", "style": "harder contrast and cleaner edge light"},
    {"number": 3, "angle": "camera shifted slightly right by about ten degrees", "style": "softer highlight rolloff and subtle film halation"},
    {"number": 4, "angle": "camera raised slightly while preserving the same screen axis", "style": "deeper shadows and restrained industrial haze"},
]


def build_root(project_root):
    return project_root / "build" / "comfyui"


def write_json(path, value):
    core.write_json(path, value)
    return str(path)


def reference_image_graph(prompt, output_prefix, seed, width=512, height=768):
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": FLUX_MODEL, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": FLUX_TEXT_ENCODER, "type": "flux2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": FLUX_VAE}},
        "4": {"class_type": "LoadImage", "inputs": {"image": REFERENCE_IMAGES[0]}},
        "5": {"class_type": "LoadImage", "inputs": {"image": REFERENCE_IMAGES[1]}},
        "6": {"class_type": "LoadImage", "inputs": {"image": REFERENCE_IMAGES[2]}},
        "7": {"class_type": "ImageScale", "inputs": {"image": ["4", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"}},
        "8": {"class_type": "ImageScale", "inputs": {"image": ["5", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"}},
        "9": {"class_type": "ImageScale", "inputs": {"image": ["6", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"}},
        "10": {"class_type": "ImageBatch", "inputs": {"image1": ["7", 0], "image2": ["8", 0]}},
        "11": {"class_type": "ImageBatch", "inputs": {"image1": ["10", 0], "image2": ["9", 0]}},
        "12": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "13": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEGATIVE}},
        "14": {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}},
        "15": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["12", 0], "latent": ["14", 0]}},
        "16": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["13", 0], "latent": ["14", 0]}},
        "17": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "18": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "19": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["15", 0], "negative": ["16", 0], "cfg": 5.0}},
        "20": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "21": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": width, "height": height}},
        "22": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["18", 0], "guider": ["19", 0], "sampler": ["20", 0], "sigmas": ["21", 0], "latent_image": ["17", 0]}},
        "23": {"class_type": "VAEDecode", "inputs": {"samples": ["22", 0], "vae": ["3", 0]}},
        "24": {"class_type": "SaveImage", "inputs": {"images": ["23", 0], "filename_prefix": output_prefix}}
    }
    return graph


def text_image_graph(prompt, negative, output_prefix, seed, width=768, height=432, lora_name=None, lora_strength=0.85):
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": FLUX_MODEL, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": FLUX_TEXT_ENCODER, "type": "flux2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": FLUX_VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative}},
        "6": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "8": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": 1.0}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": width, "height": height}},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["7", 0], "guider": ["8", 0], "sampler": ["9", 0], "sigmas": ["10", 0], "latent_image": ["6", 0]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": output_prefix}}
    }
    if lora_name:
        graph["14"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": ["1", 0], "lora_name": lora_name, "strength_model": lora_strength}
        }
        graph["8"]["inputs"]["model"] = ["14", 0]
    return graph


def character_prompt(task):
    contract = task["prompt_contract"]
    return ", ".join([
        f"same adult woman {contract['identity_tag']} from all three reference photographs",
        contract["description"],
        *contract.get("attribute_tags", []),
        *contract.get("continuity", []),
        contract.get("background", "plain neutral review background"),
        "photorealistic identity reference image, natural skin texture, one person only"
    ])


def storyboard_prompt(task, candidate=None):
    contract = task["prompt_contract"]
    parts = [
        *contract.get("identity_tags", []),
        *contract.get("character_attributes", []),
        *contract.get("environment_attributes", []),
        contract.get("action", ""),
        contract.get("framing", ""),
        contract.get("camera", ""),
        contract.get("lens", ""),
        contract.get("subject_priority", ""),
        *contract.get("continuity", []),
        "cinematic storyboard key frame, coherent anatomy and environment geometry"
    ]
    if candidate:
        parts.extend([candidate["angle"], candidate["style"]])
    return ", ".join(parts)


def ltx_motion_prompt(task, duration_seconds=None, candidate=None):
    direction = task.get("direction", {})
    base = ", ".join(str(value) for value in [
        direction.get("start_pose"), direction.get("character_action"), direction.get("end_pose"),
        direction.get("camera_path"), direction.get("lens_behavior"), direction.get("environment_motion")
    ] if value)
    if candidate:
        base = f"{base}, {candidate['angle']}, {candidate['style']}"
    if duration_seconds == 5:
        return (
            f"{base}, slow deliberate pace, restrained body motion, long readable movement arcs, "
            "stable camera timing, one clear action beat, preserve frames suitable for slow motion and hold extensions"
        )
    if duration_seconds == 10:
        return (
            f"{base}, fast urgent pace, strong forward momentum, rapid coordinated movement, "
            "multiple clear action beats, energetic camera travel, preserve continuity for editorial speed ramps and trims"
        )
    return base


def set_ui_widget(node, input_name, value):
    """Set a named UI widget while preserving the template node layout."""
    widget_index = 0
    for input_spec in node.get("inputs", []):
        if "widget" not in input_spec:
            continue
        if input_spec.get("name") == input_name:
            node["widgets_values"][widget_index] = value
            return True
        widget_index += 1
    return False


def replace_ui_model_name(value, old_name, new_name):
    """Replace one model filename throughout a copied ComfyUI UI workflow."""
    if isinstance(value, dict):
        for key, item in value.items():
            value[key] = replace_ui_model_name(item, old_name, new_name)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            value[index] = replace_ui_model_name(item, old_name, new_name)
    elif isinstance(value, str):
        return value.replace(old_name, new_name)
    return value


def configure_ltx_ui_workflow(workflow, task, duration_seconds, candidate):
    """Configure one LTX 2.5 portrait I2V workflow from the official template."""
    replace_ui_model_name(
        workflow,
        "gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
        LTX_TEXT_ENCODER,
    )
    motion_prompt = ltx_motion_prompt(task, duration_seconds, candidate)
    candidate_id = f"candidate_{candidate['number']:02d}"
    staged_keyframe = (
        f"scene_factory_generated/{task['scene_id']}/{task['shot_id']}/"
        f"{task['formation_id']}/{candidate_id}.png"
    )
    for node in workflow.get("nodes", []):
        title = node.get("title", "")
        if node.get("type") == "PrimitiveStringMultiline" and title == "Prompt (positive)":
            node["widgets_values"] = [motion_prompt]
        elif node.get("type") == "LoadImage":
            node["widgets_values"] = [staged_keyframe, "image"]
        elif node.get("type") == "SaveVideo":
            node["widgets_values"] = [
                f"Ad2184/generated/clips/{task['scene_id']}/{task['shot_id']}/"
                f"{task['formation_id']}/{candidate_id}/{duration_seconds}s",
                "auto",
                "auto"
            ]
        elif node.get("type") == "PrimitiveFloat" and title.startswith("fps"):
            node["widgets_values"] = [24]
        elif node.get("type") == "PrimitiveFloat" and title.startswith("duration in seconds"):
            node["widgets_values"] = [duration_seconds]

        input_names = {item.get("name") for item in node.get("inputs", [])}
        if {"width", "height"}.issubset(input_names) and node.get("outputs", [{}])[0].get("type") == "LATENT":
            set_ui_widget(node, "width", 544)
            set_ui_widget(node, "height", 960)
    return staged_keyframe, motion_prompt


def native_ltx_api_graph(task, duration_seconds, candidate, output_prefix):
    """Build a local ComfyUI LTX 2.5 I2V graph with projected Gemma conditioning."""
    candidate_id = f"candidate_{candidate['number']:02d}"
    staged_keyframe = (
        f"scene_factory_generated/{task['scene_id']}/{task['shot_id']}/"
        f"{task['formation_id']}/{candidate_id}.png"
    )
    frames = duration_seconds * 24 + 1
    prompt = ltx_motion_prompt(task, duration_seconds, candidate)
    negative = (
        "scene cut, camera jump, identity drift, fused bodies, extra limbs, malformed faces, "
        "unstable geometry, flicker, text, watermark"
    )
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": LTX_MODELS["diffusion_model"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": LTX_TEXT_ENCODER, "type": "ltxv", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": LTX_MODELS["video_vae"]}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": LTX_MODELS["audio_vae"]}},
        "5": {"class_type": "LoadImage", "inputs": {"image": staged_keyframe}},
        "6": {"class_type": "LTXVPreprocess", "inputs": {"image": ["5", 0], "img_compression": 18}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative}},
        "9": {"class_type": "LTXVConditioning", "inputs": {"positive": ["7", 0], "negative": ["8", 0], "frame_rate": 24.0}},
        "10": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": 544, "height": 960, "length": frames, "batch_size": 1}},
        "11": {"class_type": "LTXVImgToVideoInplace", "inputs": {"vae": ["3", 0], "image": ["6", 0], "latent": ["10", 0], "strength": 0.7, "bypass": False}},
        "12": {"class_type": "LTXVEmptyLatentAudio", "inputs": {"frames_number": frames, "frame_rate": 24.0, "batch_size": 1, "audio_vae": ["4", 0]}},
        "13": {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["11", 0], "audio_latent": ["12", 0]}},
        "14": {"class_type": "RandomNoise", "inputs": {"noise_seed": 32184 + candidate["number"]}},
        "15": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["9", 0], "negative": ["9", 1], "cfg": 1.0}},
        "16": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}},
        "17": {"class_type": "ManualSigmas", "inputs": {"sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}},
        "18": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["14", 0], "guider": ["15", 0], "sampler": ["16", 0], "sigmas": ["17", 0], "latent_image": ["13", 0]}},
        "19": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["18", 0]}},
        "20": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["19", 0], "vae": ["3", 0], "tile_size": 512, "overlap": 64, "temporal_size": 128, "temporal_overlap": 32}},
        "22": {"class_type": "CreateVideo", "inputs": {"images": ["20", 0], "fps": 24.0, "bit_depth": 8}},
        "23": {"class_type": "SaveVideo", "inputs": {"video": ["22", 0], "filename_prefix": output_prefix, "format": "mp4", "codec": "auto"}}
    }


def build_workflows(project_root, ltx_template_path):
    output_root = build_root(project_root)
    character_dir = output_root / "workflows" / "character_sheets"
    storyboard_dir = output_root / "workflows" / "storyboards"
    video_dir = output_root / "workflows" / "videos"
    for folder in (character_dir, storyboard_dir, video_dir):
        folder.mkdir(parents=True, exist_ok=True)

    characters = core.read_json(project_root / "build" / "character_sheet_plan.json")["tasks"]
    storyboards = core.read_json(project_root / "build" / "storyboard_plan.json")["tasks"]
    clips = core.read_json(project_root / "build" / "scripted_clip_plan.json")["tasks"]
    character_records = []
    for number, task in enumerate(characters, 1):
        for candidate in CANDIDATE_VARIANTS:
            candidate_id = f"candidate_{candidate['number']:02d}"
            variant_id = f"{task['id']}__{candidate_id}"
            prefix = f"Ad2184/generated/character_sheets/{task['character_id']}/{task['view_id']}/{candidate_id}"
            path = character_dir / f"{variant_id}.api.json"
            prompt = f"{character_prompt(task)}, {candidate['style']}"
            seed = 12184 + number * 10 + candidate["number"]
            write_json(
                path,
                text_image_graph(
                    prompt, NEGATIVE, prefix, seed, width=512, height=768,
                    lora_name=K0L3K4_LORA, lora_strength=0.85
                )
            )
            character_records.append({
                "id": variant_id, "candidate": candidate, "seed": seed,
                "workflow": str(path), "output_prefix": prefix,
                "execution_phase": "identity_candidates",
                "priority": "first_review" if candidate["number"] <= 2 else "expansion",
                "identity_conditioning": {"type": "lora", "name": K0L3K4_LORA, "strength": 0.85}
            })
    storyboard_records = []
    for number, task in enumerate(storyboards, 1):
        contract = task["prompt_contract"]
        negative = ", ".join([*contract.get("negative", []), NEGATIVE])
        for candidate in CANDIDATE_VARIANTS:
            candidate_id = f"candidate_{candidate['number']:02d}"
            variant_id = f"{task['id']}__{candidate_id}"
            prefix = (
                f"Ad2184/generated/storyboards/{task['scene_id']}/{task['shot_id']}/"
                f"{task['formation']['id']}/{candidate_id}"
            )
            path = storyboard_dir / f"{variant_id}.api.json"
            seed = 22184 + number * 10 + candidate["number"]
            write_json(
                path,
                text_image_graph(
                    storyboard_prompt(task, candidate), negative, prefix, seed,
                    width=544, height=960,
                    lora_name=K0L3K4_LORA if "k0l3k4" in contract.get("identity_tags", []) else None,
                    lora_strength=0.85
                )
            )
            storyboard_records.append({
                "id": variant_id, "candidate": candidate, "seed": seed,
                "workflow": str(path), "output_prefix": prefix,
                "execution_phase": "storyboard_candidates",
                "priority": "after_identity_selection"
            })

    template = core.read_json(ltx_template_path)
    video_records = []
    for task in clips:
        for candidate in CANDIDATE_VARIANTS:
            candidate_id = f"candidate_{candidate['number']:02d}"
            for duration_seconds in (5, 10):
                workflow = copy.deepcopy(template)
                staged_keyframe, motion_prompt = configure_ltx_ui_workflow(
                    workflow, task, duration_seconds, candidate
                )
                variant_id = f"{task['id']}__{candidate_id}__{duration_seconds}s__portrait"
                path = video_dir / f"{variant_id}.ui.json"
                write_json(path, workflow)
                api_path = video_dir / f"{variant_id}.api.json"
                output_prefix = (
                    f"Ad2184/generated/clips/{task['scene_id']}/{task['shot_id']}/"
                    f"{task['formation_id']}/{candidate_id}/{duration_seconds}s"
                )
                write_json(
                    api_path,
                    native_ltx_api_graph(task, duration_seconds, candidate, output_prefix)
                )
                video_records.append({
                    "id": variant_id,
                    "candidate": candidate,
                    "seed": 32184 + candidate["number"],
                    "workflow": str(api_path),
                    "api_workflow": str(api_path),
                    "ui_reference_workflow": str(path),
                    "source_keyframe": task["start_keyframe"],
                    "staged_keyframe": staged_keyframe,
                    "motion_prompt": motion_prompt,
                    "duration_seconds": duration_seconds,
                    "pace": "slow" if duration_seconds == 5 else "fast",
                    "fps": 24,
                    "aspect_ratio": "9:16",
                    "width": 544,
                    "height": 960,
                    "required_models": LTX_MODELS,
                    "execution_phase": "motion_proofs" if duration_seconds == 5 else "extended_clips",
                    "priority": "before_10_second_clips" if duration_seconds == 5 else "after_5_second_approval"
                })
    manifest = {
        "schema_version": 1,
        "project": project_root.name,
        "provisional_identity_conditioning": False,
        "identity_conditioning": {"type": "lora", "name": K0L3K4_LORA, "strength": 0.85},
        "review_policy": "visual artifacts are provisional and do not approve caption or training records",
        "models": {
            "flux": {"diffusion_model": FLUX_MODEL, "text_encoder": FLUX_TEXT_ENCODER, "vae": FLUX_VAE, "identity_lora": K0L3K4_LORA},
            "ltx_2_5": {
                **LTX_MODELS,
                **LTX_OPTIONAL_MODELS,
                "conditioning_model": LTX_TEXT_ENCODER,
                "conditioning_contract": "LTX-tuned Gemma 4 INT8 ConvRot with learned video/audio projection",
                "backend": "local_comfyui"
            }
        },
        "counts": {"character_sheets": len(character_records), "storyboards": len(storyboard_records), "videos": len(video_records)},
        "execution_phases": [
            {"order": 1, "id": "identity_candidates", "model_family": "FLUX.2 Klein", "count": len(character_records), "first_review_count": sum(item["priority"] == "first_review" for item in character_records)},
            {"order": 2, "id": "storyboard_candidates", "model_family": "FLUX.2 Klein", "count": len(storyboard_records), "rule": "Keep FLUX loaded and start only after identity selection."},
            {"order": 3, "id": "motion_proofs", "model_family": "LTX 2.5", "count": sum(item["duration_seconds"] == 5 for item in video_records), "rule": "Generate all five-second proofs before ten-second clips."},
            {"order": 4, "id": "extended_clips", "model_family": "LTX 2.5", "count": sum(item["duration_seconds"] == 10 for item in video_records), "rule": "Generate after the matching five-second motion proof passes."}
        ],
        "character_sheets": character_records,
        "storyboards": storyboard_records,
        "videos": video_records
    }
    manifest_path = output_root / "full_visual_graph_manifest.json"
    write_json(manifest_path, manifest)
    extra_paths = output_root / "extra_model_paths.yaml"
    extra_paths.write_text(
        "scene_factory_shared:\n"
        "  base_path: /Users/voxels/ComfyUI-Shared/models\n"
        "  diffusion_models: diffusion_models\n"
        "  text_encoders: text_encoders\n"
        "  vae: vae\n"
        "  loras: loras\n"
        "ltx_desktop:\n"
        "  base_path: /Users/voxels/Library/Application Support/LTXDesktop/models/ltx-2.5\n"
        "  diffusion_models: .\n"
        "  text_encoders: text_encoders\n"
        "  vae: .\n"
        "  latent_upscale_models: .\n",
        encoding="utf-8"
    )
    return manifest, manifest_path


def link_ltx_models(shared_models_root, external_ltx_root):
    """Expose LTX Desktop weights to ComfyUI without copying large files."""
    shared_models_root = Path(shared_models_root)
    external_ltx_root = Path(external_ltx_root)
    destinations = {
        "diffusion_model": shared_models_root / "diffusion_models",
        "audio_vae": shared_models_root / "vae",
        "video_vae": shared_models_root / "vae",
        "latent_upscaler": shared_models_root / "latent_upscale_models",
    }
    results = []
    for role, name in {**LTX_MODELS, **LTX_OPTIONAL_MODELS}.items():
        source = external_ltx_root / name
        destination = destinations[role] / name
        result = {
            "role": role,
            "name": name,
            "source": str(source),
            "destination": str(destination),
            "present": False,
            "linked": False,
        }
        if not source.is_file():
            result["status"] = "missing_source"
        elif destination.is_symlink():
            result["present"] = destination.is_file()
            result["linked"] = destination.resolve() == source.resolve()
            result["status"] = "linked" if result["linked"] else "conflict"
        elif destination.exists():
            result["present"] = destination.is_file()
            result["status"] = "existing_file" if result["present"] else "conflict"
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(source, destination)
            result["present"] = True
            result["linked"] = True
            result["status"] = "linked"
        results.append(result)
    return results


def preflight(project_root, shared_models_root, shared_input_root, external_ltx_root=None):
    manifest = core.read_json(build_root(project_root) / "full_visual_graph_manifest.json")
    checks = []
    model_folders = {
        "diffusion_model": shared_models_root / "diffusion_models",
        "text_encoder": shared_models_root / "text_encoders",
        "vae": shared_models_root / "vae"
    }
    for role, name in manifest["models"]["flux"].items():
        if role == "identity_lora":
            checks.append({"kind": "flux_lora", "name": name, "present": (shared_models_root / "loras" / name).is_file()})
        else:
            checks.append({"kind": "flux_model", "name": name, "present": (model_folders[role] / name).is_file()})
    ltx_paths = {
        "diffusion_model": shared_models_root / "diffusion_models",
        "audio_vae": shared_models_root / "vae",
        "video_vae": shared_models_root / "vae",
    }
    for role, name in LTX_MODELS.items():
        shared_path = ltx_paths[role] / name
        external_path = external_ltx_root / name if external_ltx_root else None
        resolved_path = shared_path if shared_path.is_file() else external_path
        checks.append({
            "kind": "ltx_model", "name": name,
            "present": bool(resolved_path and resolved_path.is_file()),
            "resolved_path": str(resolved_path) if resolved_path and resolved_path.is_file() else None
        })
    shared_text_encoder = shared_models_root / "text_encoders" / LTX_TEXT_ENCODER
    external_text_encoder = (
        external_ltx_root / "text_encoders" / LTX_TEXT_ENCODER
        if external_ltx_root else None
    )
    resolved_text_encoder = (
        shared_text_encoder if shared_text_encoder.is_file() else external_text_encoder
    )
    checks.append({
        "kind": "ltx_text_encoder",
        "name": LTX_TEXT_ENCODER,
        "present": bool(resolved_text_encoder and resolved_text_encoder.is_file()),
        "resolved_path": (
            str(resolved_text_encoder)
            if resolved_text_encoder and resolved_text_encoder.is_file() else None
        )
    })
    for role, name in LTX_OPTIONAL_MODELS.items():
        shared_path = shared_models_root / "latent_upscale_models" / name
        external_path = external_ltx_root / name if external_ltx_root else None
        resolved_path = shared_path if shared_path.is_file() else external_path
        checks.append({
            "kind": "ltx_optional_model", "name": name,
            "present": bool(resolved_path and resolved_path.is_file()),
            "resolved_path": str(resolved_path) if resolved_path and resolved_path.is_file() else None,
        })
    for group in ("character_sheets", "storyboards", "videos"):
        for item in manifest[group]:
            checks.append({"kind": "workflow", "name": item["workflow"], "present": Path(item["workflow"]).is_file()})
    report = {
        "checks": checks,
        "summary": {
            "total": len(checks), "present": sum(item["present"] for item in checks),
            "missing": sum(not item["present"] for item in checks),
            "missing_ltx_models": [item["name"] for item in checks if item["kind"] == "ltx_model" and not item["present"]]
            + [item["name"] for item in checks if item["kind"] == "ltx_text_encoder" and not item["present"]]
        }
    }
    path = build_root(project_root) / "preflight.json"
    write_json(path, report)
    return report, path
