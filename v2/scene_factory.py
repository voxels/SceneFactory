#!/usr/bin/env python3

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


MEDIA_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff",
    ".mp4", ".mov", ".mkv", ".webm", ".wav", ".aiff", ".mp3",
}


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Missing JSON file: {path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error}") from None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def stable_id(value):
    return str(value).strip().lower().replace(" ", "_")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def media_files(folder):
    if not folder.exists():
        return []
    return sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES)


def expand_pointer(value, variables):
    if value is None:
        return value
    pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")
    result = str(value)
    for _ in range(10):
        expanded = pattern.sub(lambda match: variables.get(match.group(1), match.group(0)), result)
        if expanded == result:
            break
        result = expanded
    unresolved = pattern.findall(result)
    if unresolved:
        raise ValueError(f"Unresolved path variable: {unresolved[0]}")
    return result


def expand_config_pointers(value, variables):
    if isinstance(value, dict):
        return {key: expand_config_pointers(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_config_pointers(item, variables) for item in value]
    if isinstance(value, str) and "${" in value:
        return expand_pointer(value, variables)
    return value


def build_path_variables(project_root, project):
    variables = {"PROJECT_ROOT": str(project_root.resolve())}
    defaults = project.get("path_defaults", {})
    for key, default in defaults.items():
        environment_name = f"SCENE_FACTORY_{key}"
        variables[key] = os.environ.get(environment_name, str(default))
    for _ in range(10):
        changed = False
        for key, value in list(variables.items()):
            expanded = expand_pointer(value, variables)
            if expanded != value:
                variables[key] = expanded
                changed = True
        if not changed:
            break
    return variables


def resolve_pointer(base, value, variables):
    expanded = Path(expand_pointer(value, variables)).expanduser()
    return expanded.resolve() if expanded.is_absolute() else (base / expanded).resolve()


def glob_files(root, pattern, variables=None):
    expanded = expand_pointer(pattern, variables or {})
    if Path(expanded).is_absolute():
        return sorted(path for item in glob.glob(expanded, recursive=True) if (path := Path(item)).is_file())
    return sorted(path for path in root.glob(expanded) if path.is_file())


def load_project(project_root):
    project_path = project_root / "project.json"
    project = read_json(project_path)
    variables = build_path_variables(project_root, project)
    hierarchy = project.get("hierarchy", {})
    content_root = resolve_pointer(project_root, hierarchy.get("content_root", "."), variables)
    variables["CONTENT_ROOT"] = str(content_root)
    registry_path = resolve_pointer(project_root, project.get("concept_registry", "concepts.json"), variables)
    concepts = read_json(registry_path)
    return project, concepts, content_root, variables


def adapt_scene_factory(document, source):
    if isinstance(document, dict) and isinstance(document.get("scenes"), list):
        return document["scenes"]
    if isinstance(document, dict) and "shots" in document:
        return [document]
    if isinstance(document, list):
        return document
    raise ValueError(f"The scene_factory_v1 adapter cannot read {source}")


def adapt_ad2184(document, source):
    shots = document.get("shot_list")
    if not isinstance(shots, list):
        raise ValueError(f"The ad2184_v1 adapter cannot read {source}")
    scenes = []
    for source_shot in shots:
        number = str(source_shot.get("shot_number", len(scenes) + 1)).zfill(2)
        prompt = source_shot.get("director_level_generation_prompt", {})
        time_range = str(source_shot.get("timestamp_range", ""))
        duration = 1.0
        if number in {"01", "02", "03"}:
            duration = 10.0
        elif number in {"04", "05"}:
            duration = 7.0
        elif number == "06":
            duration = 4.0
        elif number == "07":
            duration = 12.0
        camera = prompt.get("camera_movement", "Use the source camera direction.")
        action = prompt.get("action", source_shot.get("story_milestone", ""))
        scenes.append({
            "id": f"scene_{number}",
            "title": source_shot.get("title", f"Scene {number}"),
            "environment_id": f"environment_{number}",
            "continuity": [prompt.get("context", "")],
            "source_timestamp_range": time_range,
            "shots": [{
                "id": f"shot_{number}",
                "duration_seconds": duration,
                "cast": [],
                "active_concepts": [],
                "action": action,
                "audio": [source_shot.get("primary_audio_engine", "")],
                "continuity": [prompt.get("lighting", "")],
                "negative": [],
                "formations": [
                    {"id": "wide", "framing": "wide", "camera": camera, "lens": "24mm", "subject_priority": "action path and environment"},
                    {"id": "medium", "framing": "medium", "camera": camera, "lens": "50mm", "subject_priority": "main action"},
                    {"id": "detail", "framing": "close", "camera": camera, "lens": "85mm", "subject_priority": "face, hands, prop, or story detail"}
                ]
            }]
        })
    return scenes


ADAPTERS = {
    "scene_factory_v1": adapt_scene_factory,
    "ad2184_v1": adapt_ad2184,
}


def load_scenes(project, content_root, variables):
    scenes = []
    sources = []
    seen = set()
    for source_spec in project.get("hierarchy", {}).get("script_sources", []):
        adapter_name = source_spec.get("adapter")
        adapter = ADAPTERS.get(adapter_name)
        if adapter is None:
            raise ValueError(f"Unknown script adapter: {adapter_name}")
        for path in glob_files(content_root, source_spec.get("glob", ""), variables):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            document = read_json(path)
            scenes.extend(adapter(document, path))
            sources.append({"path": str(path), "adapter": adapter_name})
    return scenes, sources


def validate_project(project_root):
    errors = []
    warnings = []
    try:
        project, registry, content_root, variables = load_project(project_root)
    except ValueError as error:
        return [str(error)], [], None

    for key in ("schema_version", "project", "models", "defaults", "characters", "environments", "hierarchy"):
        if key not in project:
            errors.append(f"project.json is missing {key}")
    if project.get("schema_version") != 1:
        errors.append("project.json schema_version must be 1")
    if registry.get("schema_version") != 1:
        errors.append("concepts.json schema_version must be 1")

    character_ids = [item.get("id") for item in project.get("characters", [])]
    environment_ids = [item.get("id") for item in project.get("environments", [])]
    prop_ids = [item.get("id") for item in project.get("props", [])]
    concept_ids = [item.get("id") for item in registry.get("concepts", [])]
    for label, values in (("character", character_ids), ("environment", environment_ids), ("prop", prop_ids), ("concept", concept_ids)):
        present = [value for value in values if value]
        if len(present) != len(set(present)):
            errors.append(f"Duplicate {label} ID")

    known_concepts = set(concept_ids)
    for character in project.get("characters", []):
        concept_id = character.get("concept_id")
        if concept_id and concept_id not in known_concepts:
            errors.append(f"Character {character.get('id')} uses unknown concept {concept_id}")
        source = resolve_pointer(content_root, character.get("source_folder", ""), variables)
        if not source.exists():
            warnings.append(f"Character source folder does not exist: {source}")
    for environment in project.get("environments", []):
        concept_id = environment.get("concept_id")
        if concept_id and concept_id not in known_concepts:
            errors.append(f"Environment {environment.get('id')} uses unknown concept {concept_id}")
        source = resolve_pointer(content_root, environment.get("reference_folder", ""), variables)
        if not source.exists():
            warnings.append(f"Environment reference folder does not exist: {source}")

    stack_policy = registry.get("stack_policy", {})
    maximum_loras = int(stack_policy.get("maximum_active_loras", 3))
    concept_by_id = {item.get("id"): item for item in registry.get("concepts", []) if item.get("id")}
    for concept in concept_by_id.values():
        training = concept.get("training", {})
        inference = concept.get("inference", {})
        if training.get("enabled") and not training.get("source_globs"):
            errors.append(f"Concept {concept['id']} has training enabled but no source_globs")
        profile = training.get("profile")
        if training.get("enabled") and profile and not resolve_pointer(project_root, profile, variables).exists():
            warnings.append(f"Concept {concept['id']} training profile does not exist under the content root: {profile}")
        if training.get("generated_sources_allowed") is True:
            warnings.append(f"Concept {concept['id']} permits generated training sources. Require provenance review.")
        minimum = inference.get("minimum_weight", 0)
        default = inference.get("default_weight", 0)
        maximum = inference.get("maximum_weight", 0)
        if not minimum <= default <= maximum:
            errors.append(f"Concept {concept['id']} has an invalid inference weight range")

    try:
        scenes, script_sources = load_scenes(project, content_root, variables)
    except ValueError as error:
        errors.append(str(error))
        scenes, script_sources = [], []
    if not script_sources:
        errors.append("No script files match hierarchy.script_sources")

    known_characters = set(character_ids)
    known_environments = set(environment_ids)
    known_props = set(prop_ids)
    motion_ids = {item.get("id") for item in project.get("motion_references", []) if item.get("id")}
    reconstruction = project.get("reference_reconstruction", {})
    if reconstruction.get("enabled") is True:
        if reconstruction.get("reference_id") not in motion_ids:
            errors.append(
                f"reference_reconstruction uses unknown reference {reconstruction.get('reference_id')}"
            )
        required_policy = {
            "contract_derivation": "automatic",
            "audio_policy": "strip_and_ignore",
            "coverage_multiplier": 3.0,
            "approval_authority": "user_only",
        }
        for key, expected in required_policy.items():
            if reconstruction.get(key) != expected:
                errors.append(f"reference_reconstruction.{key} must be {expected!r}")
        master = reconstruction.get("master", {})
        if master.get("fidelity") != "reference_faithful":
            errors.append("reference_reconstruction.master.fidelity must be 'reference_faithful'")
        if master.get("cut_precision") != "approximate":
            errors.append("reference_reconstruction.master.cut_precision must be 'approximate'")
        invariants = set(master.get("invariants", []))
        for invariant in {"narrative boundaries", "story beat order", "relative rhythm"}:
            if invariant not in invariants:
                errors.append(f"reference master is missing invariant: {invariant}")
        alternates = reconstruction.get("alternates", {})
        if alternates.get("scope") != "existing_narrative":
            errors.append("reference alternates must remain within 'existing_narrative'")
        authority = reconstruction.get("source_authority", {})
        required_authority = {
            "k0l3k4.face": "k0l3k4_sources",
            "k0l3k4.body_identity": "k0l3k4_sources",
            "k0l3k4.hair": "k0l3k4_sources",
            "k0l3k4.wardrobe": "reference_video",
            "k0l3k4.pose": "reference_video_skeleton_retarget",
            "workers.design": "reference_video",
            "enforcers.design": "reference_video",
            "hammer": "reference_video_rigid_track",
            "environments": "reference_video",
            "camera": "reference_video",
            "story_beats": "reference_video",
        }
        for key, expected in required_authority.items():
            if authority.get(key) != expected:
                errors.append(f"source_authority {key} must be {expected}")
        layers = reconstruction.get("layers", {})
        if layers.get("separate_k_and_enforcers") is not True:
            errors.append("K and enforcers must be separate render layers")
        if layers.get("held_hammer_owner") != "k0l3k4" or layers.get("released_hammer_owner") != "hammer":
            errors.append("hammer layer ownership must transfer from k0l3k4 to hammer")
        conditioning_policy = reconstruction.get("conditioning_policy", {})
        required_conditioning = {
            "subject_layers": "strict_owner_only",
            "k_identity_lora_scope": "k_only",
            "cross_subject_attribute_transfer": "block",
        }
        for key, expected in required_conditioning.items():
            if conditioning_policy.get(key) != expected:
                errors.append(f"conditioning_policy.{key} must be {expected}")
        control_policy = reconstruction.get("control_policy", {})
        required_controls = {
            "pose_track_scope": "single_shot_no_cross_cut",
            "hammer_control": "independent_rigid_body_layer",
            "held_hammer_alignment": "grip_track",
        }
        for key, expected in required_controls.items():
            if control_policy.get(key) != expected:
                errors.append(f"control_policy.{key} must be {expected}")
        insert = reconstruction.get("screen_insert", {})
        if insert.get("mode") != "tracked_chroma_green_plane" or insert.get("shatter_with_screen") is not True:
            errors.append("screen insert must be a tracked chroma plane that shatters with the screen")
    seen_scene_ids = set()
    seen_shot_ids = set()
    formations_required = int(project.get("defaults", {}).get("formations_per_shot", 3))
    total_duration = 0.0
    for scene in scenes:
        scene_id = scene.get("id")
        if not scene_id:
            errors.append("A scene has no ID")
            continue
        if scene_id in seen_scene_ids:
            errors.append(f"Duplicate scene ID: {scene_id}")
        seen_scene_ids.add(scene_id)
        if scene.get("environment_id") not in known_environments:
            errors.append(f"Scene {scene_id} uses unknown environment {scene.get('environment_id')}")
        for shot in scene.get("shots", []):
            shot_id = shot.get("id")
            if not shot_id:
                errors.append(f"Scene {scene_id} has a shot with no ID")
                continue
            if shot_id in seen_shot_ids:
                errors.append(f"Duplicate shot ID: {shot_id}")
            seen_shot_ids.add(shot_id)
            duration = float(shot.get("duration_seconds", 0))
            if duration <= 0:
                errors.append(f"Shot {shot_id} must have a positive duration")
            total_duration += max(0, duration)
            for character_id in shot.get("cast", []):
                if character_id not in known_characters:
                    errors.append(f"Shot {shot_id} uses unknown character {character_id}")
            motion_reference_id = shot.get("motion_reference_id")
            if reconstruction.get("enabled") is True and motion_reference_id != reconstruction.get("reference_id"):
                errors.append(
                    f"Shot {shot_id} must use reconstruction reference {reconstruction.get('reference_id')}"
                )
            for prop_id in shot.get("props", []):
                if prop_id not in known_props:
                    errors.append(f"Shot {shot_id} uses unknown prop {prop_id}")
            active = shot.get("active_concepts", [])
            for concept_id in active:
                if concept_id not in known_concepts:
                    errors.append(f"Shot {shot_id} uses unknown concept {concept_id}")
            active_loras = [
                concept_id for concept_id in active
                if concept_by_id.get(concept_id, {}).get("inference", {}).get("strategy") == "lora"
            ]
            if len(active_loras) > maximum_loras:
                errors.append(f"Shot {shot_id} has {len(active_loras)} active LoRAs. Maximum: {maximum_loras}")
            for concept_id in active_loras:
                concept = concept_by_id.get(concept_id, {})
                blocked = set(concept.get("inference", {}).get("blocked_with", []))
                conflict = blocked.intersection(active_loras)
                if conflict:
                    errors.append(f"Shot {shot_id} has blocked LoRA combination: {concept_id} with {sorted(conflict)}")
            if stack_policy.get("require_combination_validation") and len(active_loras) > 1:
                for concept_id in active_loras:
                    allowed = set(concept_by_id[concept_id].get("inference", {}).get("allowed_with", []))
                    missing = set(active_loras).difference({concept_id}).difference(allowed)
                    if missing:
                        errors.append(f"Shot {shot_id} has an unvalidated LoRA combination: {concept_id} with {sorted(missing)}")
            formations = shot.get("formations", [])
            if len(formations) < formations_required:
                errors.append(f"Shot {shot_id} has {len(formations)} formations. Required: {formations_required}")
            formation_ids = [item.get("id") for item in formations]
            if len(formation_ids) != len(set(formation_ids)):
                errors.append(f"Shot {shot_id} has duplicate formation IDs")

    expected_duration = project.get("project", {}).get("format", {}).get("duration_seconds")
    if expected_duration is not None and abs(total_duration - float(expected_duration)) > 0.01:
        errors.append(f"Script duration is {total_duration:.3f} seconds. Project duration is {float(expected_duration):.3f} seconds")

    context = {
        "project": project,
        "registry": registry,
        "content_root": content_root,
        "path_variables": variables,
        "scenes": scenes,
        "script_sources": script_sources,
        "total_duration": total_duration,
    }
    return errors, warnings, context


def nearest_video_frames(seconds, fps, rule):
    target = max(1, round(seconds * fps))
    if rule != "mod8_plus1":
        return target
    lower = target - ((target - 1) % 8)
    upper = lower + 8
    candidates = [value for value in (lower, upper) if value >= 1]
    return min(candidates, key=lambda value: (abs(value - target), value))


def build_asset_index(project_root, context):
    project = context["project"]
    registry = context["registry"]
    content_root = context["content_root"]
    variables = context["path_variables"]
    assets = {"characters": [], "environments": [], "motion_references": [], "concepts": []}
    for character in project.get("characters", []):
        folder = resolve_pointer(content_root, character.get("source_folder", ""), variables)
        files = media_files(folder)
        assets["characters"].append({
            "id": character.get("id"), "role": character.get("role"), "folder": str(folder),
            "files": [{"path": str(path), "sha256": sha256(path)} for path in files]
        })
    for environment in project.get("environments", []):
        folder = resolve_pointer(content_root, environment.get("reference_folder", ""), variables)
        files = media_files(folder)
        assets["environments"].append({
            "id": environment.get("id"), "folder": str(folder),
            "files": [{"path": str(path), "sha256": sha256(path)} for path in files]
        })
    for motion in project.get("motion_references", []):
        path = resolve_pointer(content_root, motion.get("path", ""), variables)
        assets["motion_references"].append({
            "id": motion.get("id"), "path": str(path), "exists": path.exists(),
            "sha256": sha256(path) if path.is_file() else None
        })
    for concept in registry.get("concepts", []):
        training = concept.get("training", {})
        source_files = []
        validation_files = []
        for pattern in training.get("source_globs", []):
            source_files.extend(path for path in glob_files(content_root, pattern, variables) if path.suffix.lower() in MEDIA_SUFFIXES)
        for pattern in training.get("validation_globs", []):
            validation_files.extend(path for path in glob_files(content_root, pattern, variables) if path.suffix.lower() in MEDIA_SUFFIXES)
        assets["concepts"].append({
            "id": concept.get("id"), "type": concept.get("type"),
            "training_enabled": training.get("enabled", False),
            "approved_source_count": len(set(source_files)),
            "minimum_approved_images": training.get("minimum_approved_images", 0),
            "validation_source_count": len(set(validation_files)),
        })
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project.get("project", {}).get("id"),
        "content_root": str(content_root),
        "path_variables": variables,
        "script_sources": context["script_sources"],
        "assets": assets,
    }
    write_json(project_root / "build" / "asset_index.json", result)
    return result


def render_layers_for_shot(scene, shot, reconstruction):
    """Compile semantic layer ownership without mixing subject conditioning."""
    cast = set(shot.get("cast", []))
    props = set(shot.get("props", []))
    layers = [{
        "id": "environment_plate",
        "kind": "environment",
        "owner": scene["environment_id"],
        "conditioning_scope": {
            "include_subjects": [],
            "exclude_subjects": sorted(cast),
            "include_props": [],
            "exclude_props": sorted(props),
            "identity_lora": None,
        },
        "z_order": 0,
        "matte_required": False,
    }]
    if scene["environment_id"] == "ideology_hall" and scene["id"] in {"scene_03", "scene_04", "scene_05", "scene_06"}:
        layers.append({
            "id": "tracked_green_insert",
            "kind": "post_insert",
            "owner": "speaker_screen",
            "conditioning_scope": {
                "include_subjects": [],
                "exclude_subjects": sorted(cast),
                "include_props": [],
                "exclude_props": sorted(props),
                "identity_lora": None,
            },
            "z_order": 5,
            "mode": reconstruction.get("screen_insert", {}).get("mode"),
            "color": reconstruction.get("screen_insert", {}).get("color", "#00FF00"),
            "lifetime": "until_screen_impact" if scene["id"] == "scene_06" else "full_shot",
            "shatter_with_screen": reconstruction.get("screen_insert", {}).get("shatter_with_screen", True),
            "generated_content": False,
        })
    if "dystopian_masses" in cast:
        layers.append({
            "id": "workers_group",
            "kind": "subject_group",
            "owner": "dystopian_masses",
            "conditioning_scope": {
                "include_subjects": ["dystopian_masses"],
                "exclude_subjects": sorted(cast - {"dystopian_masses"}),
                "include_props": [],
                "exclude_props": sorted(props),
                "identity_lora": None,
            },
            "z_order": 10,
            "motion_source": "reference_video_group_guidance",
            "matte_required": True,
        })
    if "enforcers" in cast:
        layers.append({
            "id": "enforcers_group",
            "kind": "subject_group",
            "owner": "enforcers",
            "conditioning_scope": {
                "include_subjects": ["enforcers"],
                "exclude_subjects": sorted(cast - {"enforcers"}),
                "include_props": [],
                "exclude_props": sorted(props),
                "identity_lora": None,
                "forbidden_attributes": [
                    "k0l3k4 identity", "k0l3k4 face", "k0l3k4 hair",
                    "white athletic wardrobe", "bare face",
                ],
            },
            "z_order": 20,
            "motion_source": "reference_video_group_guidance",
            "matte_required": True,
            "must_render_separately_from": ["k0l3k4"],
        })
    if "k0l3k4" in cast:
        held_hammer = "hammer" in props and scene["id"] in {"scene_02", "scene_04", "scene_05"}
        layers.append({
            "id": "k0l3k4_foreground",
            "kind": "subject",
            "owner": "k0l3k4",
            "conditioning_scope": {
                "include_subjects": ["k0l3k4"],
                "exclude_subjects": sorted(cast - {"k0l3k4"}),
                "include_props": [],
                "exclude_props": sorted(props),
                "identity_lora": "k0l3k4",
                "forbidden_attributes": [
                    "helmet", "visor", "riot armor", "enforcer identity",
                    "enforcer wardrobe",
                ],
            },
            "z_order": 30,
            "identity_source": "k0l3k4_sources",
            "hair_source": "k0l3k4_sources",
            "wardrobe_source": "reference_video",
            "motion_source": "reference_video_skeleton_retarget",
            "includes_held_hammer": False,
            "matte_required": True,
            "matching": ["lighting", "lens", "grain", "motion_blur"],
        })
        if held_hammer:
            layers.append({
                "id": "held_hammer",
                "kind": "prop",
                "owner": "hammer",
                "interaction_owner": "k0l3k4",
                "z_order": 34,
                "motion_source": "reference_video_rigid_track",
                "conditioning_scope": {
                    "include_subjects": [],
                    "exclude_subjects": sorted(cast),
                    "include_props": ["hammer"],
                    "exclude_props": [],
                    "identity_lora": None,
                    "geometry_lock": [
                        "one straight handle", "one crosswise hammer head",
                        "bare grip end", "no duplicate head",
                    ],
                },
                "matte_required": True,
                "activation": "before_release",
                "ownership_state": "held_by_k0l3k4",
                "requires_grip_alignment": True,
            })
    if "hammer" in props and scene["id"] in {"scene_05", "scene_06"}:
        layers.append({
            "id": "released_hammer",
            "kind": "prop",
            "owner": "hammer",
            "conditioning_scope": {
                "include_subjects": [],
                "exclude_subjects": sorted(cast),
                "include_props": ["hammer"],
                "exclude_props": [],
                "identity_lora": None,
                "geometry_lock": [
                    "one straight handle", "one crosswise hammer head",
                    "bare grip end", "no duplicate head",
                ],
            },
            "z_order": 35,
            "motion_source": "reference_video_rigid_track",
            "matte_required": True,
            "activation": "at_release" if scene["id"] == "scene_05" else "full_shot_until_impact",
            "ownership_transfer_from": "k0l3k4" if scene["id"] == "scene_05" else None,
            "ownership_state": "released",
        })
    layers.append({
        "id": "convenience_occluder",
        "kind": "optional_occluder",
        "owner": "composite",
        "z_order": 40,
        "generation": reconstruction.get("layers", {}).get("convenience_occluders", "allowed_if_invisible"),
        "constraint": "must remain visually invisible and preserve apparent blocking",
        "matte_required": True,
    })
    return layers


def compile_reference_coverage(context, output_root):
    project = context["project"]
    reconstruction = project.get("reference_reconstruction", {})
    if reconstruction.get("enabled") is not True:
        return {"enabled": False, "tasks": [], "summary": {}}
    master_multiplier = float(reconstruction.get("master", {}).get("duration_multiplier", 1.0))
    alternate_multiplier = float(reconstruction.get("alternates", {}).get("duration_multiplier", 2.0))
    tasks = []
    master_order = 0
    for scene in context["scenes"]:
        for shot in scene.get("shots", []):
            duration = float(shot["duration_seconds"])
            master_order += 1
            layers = render_layers_for_shot(scene, shot, reconstruction)
            tasks.append({
                "id": f"coverage__{scene['id']}__{shot['id']}__master",
                "coverage_type": "master",
                "required": True,
                "narrative_order": master_order,
                "scene_id": scene["id"],
                "shot_id": shot["id"],
                "reference_id": reconstruction["reference_id"],
                "target_duration_seconds": duration * master_multiplier,
                "fidelity": reconstruction["master"]["fidelity"],
                "cut_precision": reconstruction["master"]["cut_precision"],
                "invariants": reconstruction["master"].get("invariants", []),
                "layers": layers,
                "audio_policy": reconstruction["audio_policy"],
                "output_root": str(output_root / "coverage" / "master" / scene["id"] / shot["id"]),
            })
            formations = shot.get("formations", [])
            per_alternate = duration * alternate_multiplier / max(1, len(formations))
            for formation in formations:
                tasks.append({
                    "id": f"coverage__{scene['id']}__{shot['id']}__alternate__{formation['id']}",
                    "coverage_type": "alternate_pov",
                    "required": False,
                    "narrative_order": master_order,
                    "scene_id": scene["id"],
                    "shot_id": shot["id"],
                    "formation_id": formation["id"],
                    "reference_id": reconstruction["reference_id"],
                    "target_duration_seconds": per_alternate,
                    "scope": reconstruction["alternates"]["scope"],
                    "purpose": reconstruction["alternates"]["purpose"],
                    "selection": reconstruction["alternates"]["selection"],
                    "layers": layers,
                    "audio_policy": reconstruction["audio_policy"],
                    "output_root": str(output_root / "coverage" / "alternates" / scene["id"] / shot["id"] / formation["id"]),
                })
    master_seconds = sum(item["target_duration_seconds"] for item in tasks if item["coverage_type"] == "master")
    alternate_seconds = sum(item["target_duration_seconds"] for item in tasks if item["coverage_type"] == "alternate_pov")
    return {
        "enabled": True,
        "reference_id": reconstruction["reference_id"],
        "audio_policy": reconstruction["audio_policy"],
        "approval_authority": reconstruction["approval_authority"],
        "tasks": tasks,
        "summary": {
            "master_tasks": sum(item["coverage_type"] == "master" for item in tasks),
            "alternate_tasks": sum(item["coverage_type"] == "alternate_pov" for item in tasks),
            "master_seconds": round(master_seconds, 6),
            "alternate_seconds": round(alternate_seconds, 6),
            "total_seconds": round(master_seconds + alternate_seconds, 6),
            "coverage_multiplier": round((master_seconds + alternate_seconds) / context["total_duration"], 6),
        },
    }


def compile_post_production_manifest(project_root, generation_manifest):
    """Write an explicit, visual-only layer handoff plan for the editor."""
    reference_path = project_root / "build" / "reference" / "reference_manifest.json"
    reference = read_json(reference_path) if reference_path.is_file() else None
    reference_ranges = {
        item["shot_id"]: item for item in (reference or {}).get("shot_ranges", [])
    }
    shots = []
    for task in generation_manifest.get("reference_coverage", {}).get("tasks", []):
        task_root = Path(task["output_root"])
        layers = []
        for layer in task.get("layers", []):
            layer_root = task_root / "layers" / layer["id"]
            layers.append({
                **layer,
                "state": "planned",
                "media_path": str(layer_root.with_suffix(".mov")),
                "matte_path": str(layer_root.with_name(layer_root.name + "__matte").with_suffix(".mov"))
                if layer.get("matte_required") else None,
                "transform_track_path": str(layer_root.with_name(layer_root.name + "__transform").with_suffix(".json")),
                "premultiplication": "premultiplied" if layer.get("matte_required") else "opaque",
            })
        shot_id = task["shot_id"]
        shots.append({
            "task_id": task["id"],
            "coverage_type": task["coverage_type"],
            "required": task["required"],
            "narrative_order": task["narrative_order"],
            "scene_id": task["scene_id"],
            "shot_id": shot_id,
            "target_duration_seconds": task["target_duration_seconds"],
            "source_range": reference_ranges.get(shot_id),
            "layers": layers,
            "k_skeleton_track": str(project_root / "build" / "tracking" / shot_id / "k_body_pose.json"),
            "hammer_track": str(project_root / "build" / "tracking" / shot_id / "hammer_rigid_body.json"),
            "screen_corner_track": str(project_root / "build" / "tracking" / shot_id / "speaker_screen_corners.json"),
            "approval": {"required_actor": "user", "state": "pending"},
        })
    dependency_hashes = {
        "project.json": sha256(project_root / "project.json"),
    }
    for source in generation_manifest.get("source_scripts", []):
        source_path = Path(source["path"])
        if source_path.is_file():
            dependency_hashes[str(source_path)] = sha256(source_path)
    if reference:
        dependency_hashes["reference_video"] = reference["source"]["sha256"]
        dependency_hashes["reference_manifest.json"] = sha256(reference_path)
    result = {
        "schema_version": 1,
        "generated_at": generation_manifest["generated_at"],
        "project": generation_manifest["project"],
        "status": "planned_assets_pending_generation_tracking_and_user_approval",
        "audio_policy": "strip_and_ignore",
        "audio_artifacts": [],
        "coverage_summary": generation_manifest.get("reference_coverage", {}).get("summary", {}),
        "graphics": {
            "speaker_overlay": "replace tracked green insert with user-supplied MP4 in post",
            "final_title_and_logo": "post_only",
        },
        "dependency_hashes": dependency_hashes,
        "shots": shots,
    }
    import reference_contracts
    invalidation_nodes = []
    project_node = "source:project"
    invalidation_nodes.append({
        "id": project_node, "fingerprint": dependency_hashes["project.json"], "dependencies": []
    })
    script_nodes = []
    for source in generation_manifest.get("source_scripts", []):
        source_path = Path(source["path"])
        if source_path.is_file():
            node_id = f"source:script:{source_path.name}"
            script_nodes.append(node_id)
            invalidation_nodes.append({
                "id": node_id, "fingerprint": sha256(source_path), "dependencies": [project_node]
            })
    reference_node = "source:reference_video"
    if reference:
        invalidation_nodes.append({
            "id": reference_node, "fingerprint": reference["source"]["sha256"], "dependencies": []
        })
        for shot_range in reference.get("shot_ranges", []):
            for sample in shot_range.get("samples", []):
                invalidation_nodes.append({
                    "id": f"frame:{sample['vision_contract_task_id']}",
                    "fingerprint": sample.get("sha256") or "missing",
                    "dependencies": [reference_node],
                })
    contract_nodes = []
    contracts_root = project_root / "build" / "reference" / "contracts"
    for contract_path in sorted(contracts_root.glob("*.json")):
        if contract_path.name == "index.json":
            continue
        contract_id = f"contract:{contract_path.stem}"
        contract_nodes.append(contract_id)
        invalidation_nodes.append({
            "id": contract_id, "fingerprint": sha256(contract_path),
            "dependencies": [
                f"frame:{task['id']}" for task in (reference or {}).get("vision_contract_tasks", [])
                if contract_path.stem in task.get("contract_types", [])
            ],
        })
    layer_node_lookup = {}
    for shot in shots:
        track_nodes = []
        for track_type, key in (("k_skeleton", "k_skeleton_track"), ("hammer", "hammer_track"), ("screen", "screen_corner_track")):
            track_path = Path(shot[key])
            track_id = f"track:{shot['task_id']}:{track_type}"
            track_nodes.append(track_id)
            invalidation_nodes.append({
                "id": track_id,
                "fingerprint": sha256(track_path) if track_path.is_file() else "missing",
                "dependencies": [reference_node, *contract_nodes],
            })
        for layer in shot["layers"]:
            media_path = Path(layer["media_path"])
            matte_path = Path(layer["matte_path"]) if layer.get("matte_path") else None
            layer_id = f"layer:{shot['task_id']}:{layer['id']}"
            fingerprint = {
                "media": sha256(media_path) if media_path.is_file() else "missing",
                "matte": sha256(matte_path) if matte_path and matte_path.is_file() else "missing" if matte_path else None,
            }
            invalidation_nodes.append({
                "id": layer_id, "fingerprint": reference_contracts.canonical_hash(fingerprint),
                "dependencies": [project_node, *script_nodes, *contract_nodes, *track_nodes],
            })
            layer_node_lookup[layer_id] = layer
        artifact_id = f"artifact:{shot['task_id']}"
        invalidation_nodes.append({
            "id": artifact_id,
            "fingerprint": reference_contracts.canonical_hash({
                "approval": shot["approval"],
                "layers": [layer["media_path"] for layer in shot["layers"]],
            }),
            "dependencies": [f"layer:{shot['task_id']}:{layer['id']}" for layer in shot["layers"]],
        })
    invalidation = reference_contracts.refresh_invalidation_state(project_root, invalidation_nodes)
    for node_id in invalidation["invalidated"]:
        if node_id in layer_node_lookup:
            layer_node_lookup[node_id]["state"] = "invalidated"
        elif node_id.startswith("artifact:"):
            task_id = node_id.removeprefix("artifact:")
            shot = next((item for item in shots if item["task_id"] == task_id), None)
            if shot:
                shot["approval"] = {"required_actor": "user", "state": "pending", "invalidated": True}
    result["runtime_invalidation"] = {
        "state_path": str(project_root / "build" / "invalidation_state.json"),
        "changed": invalidation["changed"], "removed": invalidation["removed"],
        "invalidated": invalidation["invalidated"],
    }
    output = project_root / "build" / "post_production_manifest.json"
    write_json(output, result)
    return output, result


def compile_manifest(project_root, context):
    project = context["project"]
    registry = context["registry"]
    asset_index = build_asset_index(project_root, context)
    project_id = project["project"]["id"]
    fps = float(project["project"]["format"]["fps"])
    frame_rule = project.get("defaults", {}).get("video_frame_rule", "none")
    character_by_id = {item["id"]: item for item in project.get("characters", [])}
    environment_by_id = {item["id"]: item for item in project.get("environments", [])}
    prop_by_id = {item["id"]: item for item in project.get("props", [])}
    concept_by_id = {item["id"]: item for item in registry.get("concepts", [])}
    variables = context["path_variables"]
    output_root = resolve_pointer(project_root, variables.get("OUTPUT_ROOT", "outputs"), variables)
    reference_count_by_concept = {}
    indexed_characters = {item["id"]: item for item in asset_index["assets"]["characters"]}
    indexed_environments = {item["id"]: item for item in asset_index["assets"]["environments"]}
    for character in project.get("characters", []):
        concept_id = character.get("concept_id")
        if concept_id:
            reference_count_by_concept[concept_id] = reference_count_by_concept.get(concept_id, 0) + len(indexed_characters.get(character["id"], {}).get("files", []))
    for environment in project.get("environments", []):
        concept_id = environment.get("concept_id")
        if concept_id:
            reference_count_by_concept[concept_id] = reference_count_by_concept.get(concept_id, 0) + len(indexed_environments.get(environment["id"], {}).get("files", []))

    training_tasks = []
    for indexed in asset_index["assets"]["concepts"]:
        if not indexed["training_enabled"]:
            continue
        concept = concept_by_id[indexed["id"]]
        training_tasks.append({
            "id": f"train__{concept['id']}",
            "concept_id": concept["id"],
            "concept_type": concept["type"],
            "trigger_token": concept["trigger_token"],
            "source_count": indexed["approved_source_count"],
            "minimum_source_count": indexed["minimum_approved_images"],
            "ready": indexed["approved_source_count"] >= indexed["minimum_approved_images"] and indexed["validation_source_count"] > 0,
            "validation_source_count": indexed["validation_source_count"],
            "base_model": concept.get("training", {}).get("base_model"),
            "training_profile": str(resolve_pointer(project_root, concept.get("training", {}).get("profile"), variables)) if concept.get("training", {}).get("profile") else None,
            "output": expand_pointer(concept.get("inference", {}).get("lora_path"), variables) if concept.get("inference", {}).get("lora_path") else None,
            "gate": "approved sources and separate validation sources"
        })

    keyframe_tasks = []
    video_tasks = []
    assembly = []
    timeline = 0.0
    for scene in context["scenes"]:
        environment = environment_by_id[scene["environment_id"]]
        for shot in scene.get("shots", []):
            formations = shot["formations"]
            segment_trim = float(shot["duration_seconds"]) / len(formations)
            active_concepts = [concept_by_id[item] for item in shot.get("active_concepts", [])]
            active_loras = [item for item in active_concepts if item.get("inference", {}).get("strategy") == "lora"]
            lora_blockers = [
                f"{item['id']}:{item.get('inference', {}).get('status', 'unknown')}"
                for item in active_loras if item.get("inference", {}).get("status") != "ready"
            ]
            reference_blockers = [
                f"{item['id']}:missing_reference_media"
                for item in active_concepts
                if item.get("inference", {}).get("strategy") in {"reference", "prompt_reference"}
                and reference_count_by_concept.get(item["id"], 0) == 0
            ]
            conditioning_blockers = lora_blockers + reference_blockers
            lora_stack = [{
                "concept_id": item["id"],
                "path": expand_pointer(item.get("inference", {}).get("lora_path"), variables) if item.get("inference", {}).get("lora_path") else None,
                "weight": item.get("inference", {}).get("default_weight"),
                "status": item.get("inference", {}).get("status")
            } for item in active_loras]
            concept_conditioning = [{
                "concept_id": item["id"],
                "trigger_token": item.get("trigger_token"),
                "strategy": item.get("inference", {}).get("strategy"),
                "status": item.get("inference", {}).get("status"),
                "reference_media_count": reference_count_by_concept.get(item["id"], 0)
            } for item in active_concepts]
            cast = [character_by_id[item] for item in shot.get("cast", [])]
            props = [prop_by_id[item] for item in shot.get("props", [])]
            for order, formation in enumerate(formations, start=1):
                task_id = f"{scene['id']}__{shot['id']}__{formation['id']}"
                frames = nearest_video_frames(segment_trim, fps, frame_rule)
                identity_tags = [item.get("identity_tag") for item in cast]
                subject_contracts = [{
                    "id": item["id"],
                    "identity_tag": item.get("identity_tag"),
                    "role": item.get("role"),
                    "required_attributes": item.get("attribute_tags", []),
                    "continuity": item.get("continuity", []),
                    "must_have": item.get("visual_rules", {}).get("must_have", []),
                    "must_not_have": item.get("visual_rules", {}).get("must_not_have", []),
                    "anatomy": item.get("visual_rules", {}).get("anatomy", [])
                } for item in cast]
                prop_contracts = [{
                    "id": item["id"],
                    "description": item["description"],
                    "geometry": item.get("geometry", []),
                    "continuity": item.get("continuity", []),
                    "forbidden": item.get("forbidden", [])
                } for item in props]
                prompt_contract = {
                    "identity_tags": identity_tags,
                    "subjects": subject_contracts,
                    "props": prop_contracts,
                    "environment_id": environment["id"],
                    "environment_attributes": environment.get("attribute_tags", []),
                    "action": shot["action"],
                    "framing": formation["framing"],
                    "camera": formation["camera"],
                    "lens": formation.get("lens"),
                    "subject_priority": formation["subject_priority"],
                    "blocking": formation.get("blocking", {}),
                    "global_constraints": project.get("production_constraints", {}),
                    "continuity": scene.get("continuity", []) + shot.get("continuity", []) + environment.get("continuity", []),
                    "negative": shot.get("negative", [])
                }
                keyframe_path = str(output_root / "keyframes" / scene["id"] / shot["id"] / f"{formation['id']}.png")
                clip_path = str(output_root / "clips" / scene["id"] / shot["id"] / f"{formation['id']}.mp4")
                keyframe_tasks.append({
                    "id": f"keyframe__{task_id}", "scene_id": scene["id"], "shot_id": shot["id"],
                    "formation": formation, "prompt_contract": prompt_contract, "concept_conditioning": concept_conditioning, "lora_stack": lora_stack,
                    "model": project["models"]["image_generator"], "output": keyframe_path,
                    "ready": not conditioning_blockers,
                    "blockers": conditioning_blockers,
                    "gate": "all active concepts validated, then human key-frame review"
                })
                video_tasks.append({
                    "id": f"video__{task_id}", "scene_id": scene["id"], "shot_id": shot["id"],
                    "formation_id": formation["id"], "start_keyframe": keyframe_path,
                    "motion_reference_id": shot.get("motion_reference_id"),
                    "direction": {
                        "start_pose": formation.get("start_pose", "match the approved key frame"),
                        "character_action": shot["action"],
                        "end_pose": formation.get("end_pose", "complete this formation beat"),
                        "camera_path": formation["camera"],
                        "lens_behavior": formation.get("lens"),
                        "environment_motion": formation.get("environment_motion", "preserve environment continuity"),
                        "identity_locks": identity_tags,
                        "subject_locks": subject_contracts,
                        "prop_locks": prop_contracts,
                        "negative_motion": formation.get("negative_motion", [])
                    },
                    "fps": fps, "frames": frames, "generated_duration_seconds": frames / fps,
                    "trim_duration_seconds": segment_trim, "model": project["models"]["video_generator"],
                    "output": clip_path, "ready": False,
                    "blockers": ["approved key frame", "approved motion direction"],
                    "gate": "approved key frame and approved motion direction"
                })
                assembly.append({
                    "order": len(assembly) + 1, "scene_id": scene["id"], "shot_id": shot["id"],
                    "formation_id": formation["id"], "source": clip_path,
                    "timeline_start_seconds": round(timeline, 6), "trim_duration_seconds": round(segment_trim, 6),
                    "audio": [], "audio_policy": "strip_and_ignore", "graphics_stage": "post"
                })
                timeline += segment_trim

    reference_coverage = compile_reference_coverage(context, output_root)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": project["project"],
        "models": expand_config_pointers(project["models"], variables),
        "source_scripts": context["script_sources"],
        "path_variables": variables,
        "concept_stack_policy": registry.get("stack_policy", {}),
        "training_tasks": training_tasks,
        "keyframe_tasks": keyframe_tasks,
        "video_tasks": video_tasks,
        "assembly": assembly,
        "reference_coverage": reference_coverage,
        "post_production": {
            "audio_policy": project.get("reference_reconstruction", {}).get("audio_policy", "unspecified"),
            "graphics_stage": "post",
            "final_title_and_logo": "post_only",
            "approval_authority": project.get("reference_reconstruction", {}).get("approval_authority", "unspecified"),
            "layer_manifest_source": "reference_coverage.tasks[].layers",
            "screen_insert": project.get("reference_reconstruction", {}).get("screen_insert", {}),
        },
        "counts": {
            "scenes": len(context["scenes"]),
            "shots": sum(len(scene.get("shots", [])) for scene in context["scenes"]),
            "training_tasks": len(training_tasks),
            "keyframe_tasks": len(keyframe_tasks),
            "video_tasks": len(video_tasks),
            "timeline_seconds": round(timeline, 6)
        },
        "review_gates": [
            "source approval before LoRA training",
            "LoRA validation alone and in allowed combinations",
            "key-frame review before video",
            "motion-direction review before video",
            "clip review before environment and final assembly",
            "exact text, logos, voice, and music in post"
        ]
    }
    output_path = project_root / "build" / "generation_manifest.json"
    write_json(output_path, manifest)
    compile_post_production_manifest(project_root, manifest)
    return output_path, manifest


def command_new(arguments):
    destination = arguments.destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Destination is not empty: {destination}")
    template = Path(__file__).resolve().parent / "template"
    shutil.copytree(template, destination, dirs_exist_ok=True)
    shutil.copytree(Path(__file__).resolve().parent / "profiles", destination / "profiles", dirs_exist_ok=True)
    project_path = destination / "project.json"
    project = read_json(project_path)
    project["project"]["id"] = stable_id(arguments.id)
    project["project"]["title"] = arguments.title
    write_json(project_path, project)
    series_context_path = destination / "series_context.json"
    if series_context_path.exists():
        series_context = read_json(series_context_path)
        series_context["episode_id"] = stable_id(arguments.id)
        write_json(series_context_path, series_context)
    print(f"Project created: {destination}")


def command_validate(arguments):
    errors, warnings, context = validate_project(arguments.project.resolve())
    for warning in warnings:
        print(f"Warning: {warning}")
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Valid project: {context['project']['project']['id']}")
    print(f"Scenes: {len(context['scenes'])}")
    print(f"Duration: {context['total_duration']:.3f} seconds")


def command_index(arguments):
    errors, warnings, context = validate_project(arguments.project.resolve())
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    for warning in warnings:
        print(f"Warning: {warning}")
    result = build_asset_index(arguments.project.resolve(), context)
    print(f"Asset index: {arguments.project.resolve() / 'build' / 'asset_index.json'}")
    print(f"Characters: {len(result['assets']['characters'])}")
    print(f"Environments: {len(result['assets']['environments'])}")


def command_compile(arguments):
    errors, warnings, context = validate_project(arguments.project.resolve())
    for warning in warnings:
        print(f"Warning: {warning}")
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    if context["project"].get("reference_reconstruction", {}).get("enabled"):
        from reference_contracts import enforce_generation_gate
        enforce_generation_gate(arguments.project.resolve())
    output, manifest = compile_manifest(arguments.project.resolve(), context)
    print(f"Generation manifest: {output}")
    print(json.dumps(manifest["counts"], indent=2))


def command_reference_prepare(arguments):
    errors, warnings, context = validate_project(arguments.project.resolve())
    for warning in warnings:
        print(f"Warning: {warning}")
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    from reference_pipeline import ingest_reference
    manifest = ingest_reference(
        arguments.project.resolve(),
        context["project"],
        context["scenes"],
        content_root=context["content_root"],
        path_variables=context["path_variables"],
        extract_frames=not arguments.no_extract_frames,
    )
    output = arguments.project.resolve() / "build" / "reference" / "reference_manifest.json"
    print(f"Reference manifest: {output}")
    print(json.dumps({
        "reference_id": manifest["reference_id"],
        "source_sha256": manifest["source"]["sha256"],
        "duration_seconds": manifest["source"]["duration_seconds"],
        "shot_ranges": len(manifest["shot_ranges"]),
        "vision_contract_tasks": len(manifest["vision_contract_tasks"]),
        "audio_artifacts_emitted": manifest["audio"]["artifacts_emitted"],
    }, indent=2))


def _reference_contract_context(project_root):
    errors, warnings, context = validate_project(project_root)
    if errors:
        raise ValueError("project validation failed: " + "; ".join(errors))
    return warnings, context


def command_reference_contract_run(arguments):
    project_root = arguments.project.resolve()
    warnings, context = _reference_contract_context(project_root)
    for warning in warnings:
        print(f"Warning: {warning}")
    captioner = expand_config_pointers(
        context["project"].get("models", {}).get("captioner", {}), context["path_variables"]
    )
    if captioner.get("provider") != "huggingface":
        raise ValueError("reference contract execution currently needs the configured local Hugging Face vision model")
    configured_python = captioner.get("python")
    if configured_python and Path(configured_python).resolve() != Path(sys.executable).resolve():
        if not Path(configured_python).is_file():
            raise ValueError(f"Configured vision Python does not exist: {configured_python}")
        print(f"Restarting reference contract command with: {configured_python}", flush=True)
        os.execv(configured_python, [configured_python, str(Path(__file__).resolve()), *sys.argv[1:]])
    import reference_contracts
    infer = reference_contracts.make_huggingface_inference(captioner)
    claims = reference_contracts.written_claims(context["project"], context["scenes"])
    result = reference_contracts.execute_tasks(
        project_root, infer, limit=arguments.limit, force=arguments.force, claims=claims,
        model_provenance={
            "provider": "huggingface", "model": captioner.get("model"),
            "model_path": captioner.get("model_path"), "processor_path": captioner.get("processor_path"),
            "deterministic_decode": True,
        },
    )
    audit = reference_contracts.audit_disagreements(
        project_root, context["project"], context["scenes"]
    )
    print(json.dumps({**result, "generation_gate": audit["generation_gate"]}, indent=2))


def command_reference_contract_audit(arguments):
    project_root = arguments.project.resolve()
    warnings, context = _reference_contract_context(project_root)
    for warning in warnings:
        print(f"Warning: {warning}")
    import reference_contracts
    reference_contracts.aggregate_contracts(project_root)
    report = reference_contracts.audit_disagreements(
        project_root, context["project"], context["scenes"]
    )
    print(json.dumps({
        "claims_checked": report["claims_checked"],
        "unresolved_contradictions": len(report["unresolved_contradictions"]),
        "generation_gate": report["generation_gate"],
    }, indent=2))


def command_reference_contract_import(arguments):
    project_root = arguments.project.resolve()
    warnings, context = _reference_contract_context(project_root)
    for warning in warnings:
        print(f"Warning: {warning}")
    import reference_contracts
    claims = reference_contracts.written_claims(context["project"], context["scenes"])
    result = reference_contracts.import_reviewed_observations(
        project_root, arguments.review.resolve(), claims
    )
    report = reference_contracts.audit_disagreements(
        project_root, context["project"], context["scenes"]
    )
    print(json.dumps({
        "completed": result["completed"],
        "generation_gate": report["generation_gate"],
    }, indent=2))


def command_status(arguments):
    root = arguments.project.resolve()
    errors, warnings, context = validate_project(root)
    print(f"Project: {context['project']['project']['title'] if context else root.name}")
    print(f"Validation errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    manifest_path = root / "build" / "generation_manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        print(f"Compiled key frames: {manifest['counts']['keyframe_tasks']}")
        print(f"Compiled clips: {manifest['counts']['video_tasks']}")
        ready_keyframes = sum(1 for item in manifest.get("keyframe_tasks", []) if item.get("ready"))
        print(f"Key-frame tasks ready: {ready_keyframes} of {manifest['counts']['keyframe_tasks']}")
        ready = sum(1 for item in manifest.get("training_tasks", []) if item.get("ready"))
        print(f"LoRA training tasks ready: {ready} of {len(manifest.get('training_tasks', []))}")
    else:
        print("Generation manifest: not compiled")
    for error in errors:
        print(f"Error: {error}")
    for warning in warnings:
        print(f"Warning: {warning}")


def command_prepare(arguments):
    import pipeline
    warnings, state = pipeline.prepare(arguments.project.resolve())
    for warning in warnings:
        print(f"Warning: {warning}")
    print(f"Pipeline prepared: {arguments.project.resolve() / 'build' / 'pipeline_state.json'}")
    print(json.dumps(pipeline.state_summary(state), indent=2))


def command_caption_run(arguments):
    project, _, _, variables = load_project(arguments.project.resolve())
    captioner = project.get("models", {}).get("captioner", {})
    if arguments.model:
        captioner = {"provider": "ollama", "model": arguments.model}
    if not captioner:
        raise ValueError("No caption model is set. Add models.captioner.model or pass --model.")
    if isinstance(captioner, dict):
        captioner = dict(captioner)
        for key in ("model_path", "processor_path", "python"):
            if captioner.get(key):
                captioner[key] = expand_pointer(captioner[key], variables)
        configured_python = captioner.get("python")
        if (
            captioner.get("provider") == "huggingface" and configured_python
            and Path(configured_python).resolve() != Path(sys.executable).resolve()
        ):
            if not Path(configured_python).is_file():
                raise ValueError(f"Configured caption Python does not exist: {configured_python}")
            print(f"Restarting caption command with: {configured_python}", flush=True)
            os.execv(configured_python, [configured_python, str(Path(__file__).resolve()), *sys.argv[1:]])
    import pipeline
    count, failures = pipeline.run_captions(
        arguments.project.resolve(), captioner,
        limit=arguments.limit, base_url=arguments.base_url,
        asset_id=arguments.asset_id, force=arguments.force
    )
    state = pipeline.refresh_state(arguments.project.resolve())
    print(f"Caption results created: {count}")
    if failures:
        print(f"Caption failures: {len(failures)}")
        print(json.dumps(failures, indent=2))
    print(json.dumps(pipeline.state_summary(state), indent=2))


def command_isolation_caption_run(arguments):
    project, _, _, variables = load_project(arguments.project.resolve())
    captioner = dict(project.get("models", {}).get("captioner", {}))
    if not captioner:
        raise ValueError("No caption model is set")
    for key in ("model_path", "processor_path", "python"):
        if captioner.get(key):
            captioner[key] = expand_pointer(captioner[key], variables)
    configured_python = captioner.get("python")
    if (
        captioner.get("provider") == "huggingface" and configured_python
        and Path(configured_python).resolve() != Path(sys.executable).resolve()
    ):
        if not Path(configured_python).is_file():
            raise ValueError(f"Configured caption Python does not exist: {configured_python}")
        print(f"Restarting isolation caption command with: {configured_python}", flush=True)
        os.execv(configured_python, [configured_python, str(Path(__file__).resolve()), *sys.argv[1:]])
    import pipeline
    count, failures = pipeline.run_isolation_captions(
        arguments.project.resolve(), captioner, arguments.identity_id,
        limit=arguments.limit, force=arguments.force
    )
    print(json.dumps({"isolation_caption_results_created": count, "failures": failures}, indent=2))


def command_isolation_caption_audit(arguments):
    import pipeline
    report, path = pipeline.audit_isolation_captions(arguments.project.resolve(), arguments.identity_id)
    print(json.dumps(report["summary"], indent=2))
    print(f"Isolation caption audit: {path}")


def command_isolation_caption_review(arguments):
    import pipeline
    result = pipeline.review_isolation_caption(
        arguments.project.resolve(), arguments.asset_id, arguments.decision,
        arguments.note, arguments.identity_id
    )
    print(json.dumps({
        "asset_id": result["asset_id"],
        "review_state": result["review_state"]
    }, indent=2))


def command_caption_audit(arguments):
    import pipeline
    report, audit_path, review_path = pipeline.audit_captions(arguments.project.resolve())
    print(json.dumps(report["summary"], indent=2))
    print(f"Caption audit: {audit_path}")
    print(f"Manual review: {review_path}")


def command_caption_import(arguments):
    import pipeline
    count = pipeline.import_captions(arguments.project.resolve(), arguments.input.resolve())
    state = pipeline.refresh_state(arguments.project.resolve())
    print(f"Caption results imported: {count}")
    print(json.dumps(pipeline.state_summary(state), indent=2))


def command_caption_normalize(arguments):
    import pipeline
    count = pipeline.normalize_saved_captions(arguments.project.resolve())
    report, audit_path, review_path = pipeline.audit_captions(arguments.project.resolve())
    state = pipeline.refresh_state(arguments.project.resolve())
    print(json.dumps({
        "normalized": count,
        "caption_audit": str(audit_path),
        "manual_review": str(review_path),
        "summary": report["summary"]
    }, indent=2))
    print(json.dumps(pipeline.state_summary(state), indent=2))


def command_caption_review(arguments):
    import pipeline
    result = pipeline.review_caption(
        arguments.project.resolve(), arguments.asset_id,
        arguments.decision, arguments.split, arguments.note
    )
    state = pipeline.refresh_state(arguments.project.resolve())
    print(json.dumps({
        "asset_id": result["asset_id"],
        "review_state": result["review_state"],
        "split": result["split"]
    }, indent=2))
    print(json.dumps(pipeline.state_summary(state), indent=2))


def command_identity_isolation_review(arguments):
    import pipeline
    record = pipeline.review_isolation(
        arguments.project.resolve(), arguments.source_sha256,
        arguments.decision, arguments.note, arguments.identity_id
    )
    state = pipeline.refresh_state(arguments.project.resolve())
    print(json.dumps({
        "source_sha256": record["source_sha256"],
        "selected_face_id": record.get("selected_face_id"),
        "selected_person_instance": record.get("selected_person_instance"),
        "review_state": record.get("review_state")
    }, indent=2))
    print(json.dumps(pipeline.state_summary(state), indent=2))


def command_dataset_build(arguments):
    import pipeline
    outputs = pipeline.build_datasets(arguments.project.resolve())
    state = pipeline.refresh_state(arguments.project.resolve())
    print(json.dumps({"dataset_manifests": outputs}, indent=2))
    print(json.dumps(pipeline.state_summary(state), indent=2))


def command_character_balance(arguments):
    import pipeline
    report, report_path, markdown_path = pipeline.build_character_balance_report(
        arguments.project.resolve(), arguments.character_id
    )
    print(json.dumps({
        "report": str(report_path),
        "review": str(markdown_path),
        "counts": report["counts"],
        "warnings": report["warnings"]
    }, indent=2))


def command_pipeline_status(arguments):
    import pipeline
    state = pipeline.refresh_state(arguments.project.resolve())
    print(json.dumps(pipeline.state_summary(state), indent=2))


def _comfy_paths(project_root, arguments):
    project, _, _, variables = load_project(project_root)
    template_default = project.get("path_defaults", {}).get("LTX_WORKFLOW_TEMPLATE")
    template = arguments.ltx_template or (
        expand_pointer(template_default, variables) if template_default else None
    )
    if not template:
        raise ValueError("Set path_defaults.LTX_WORKFLOW_TEMPLATE or pass --ltx-template")
    return {
        "shared_models": Path(arguments.shared_models_root or variables.get("COMFYUI_MODELS_ROOT", "")).resolve(),
        "shared_input": Path(arguments.shared_input_root or variables.get("COMFYUI_INPUT_ROOT", "")).resolve(),
        "ltx_models": Path(arguments.ltx_models_root or variables.get("LTX_MODELS_ROOT", "")).resolve(),
        "ltx_template": Path(template).resolve()
    }


def command_comfy_build(arguments):
    import comfy_adapter
    import pipeline
    project_root = arguments.project.resolve()
    from reference_contracts import enforce_generation_gate
    enforce_generation_gate(project_root)
    pipeline.prepare(project_root)
    paths = _comfy_paths(project_root, arguments)
    model_links = comfy_adapter.link_ltx_models(paths["shared_models"], paths["ltx_models"])
    manifest, manifest_path = comfy_adapter.build_workflows(project_root, paths["ltx_template"])
    report, preflight_path = comfy_adapter.preflight(
        project_root, paths["shared_models"], paths["shared_input"], paths["ltx_models"]
    )
    print(json.dumps({
        "manifest": str(manifest_path), "counts": manifest["counts"],
        "preflight": str(preflight_path), "summary": report["summary"],
        "ltx_model_links": model_links
    }, indent=2))


def command_comfy_preflight(arguments):
    import comfy_adapter
    project_root = arguments.project.resolve()
    paths = _comfy_paths(project_root, arguments)
    report, preflight_path = comfy_adapter.preflight(
        project_root, paths["shared_models"], paths["shared_input"], paths["ltx_models"]
    )
    print(json.dumps({"preflight": str(preflight_path), **report["summary"]}, indent=2))


def command_rough_cut(arguments):
    import rough_cut
    report, report_path = rough_cut.assemble(
        arguments.project.resolve(), output=arguments.output,
        candidate=arguments.candidate, duration=arguments.duration,
        allow_missing=arguments.allow_missing, ffmpeg=arguments.ffmpeg
    )
    print(json.dumps({
        "output": report["output"],
        "duration_seconds": report["rough_cut_duration_seconds"],
        "timeline_clips": report["timeline_clips"],
        "missing_clips": len(report["missing_clips"]),
        "report": str(report_path)
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Index and compile consistent multi-scene generation projects.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Make a new project folder.")
    new_parser.add_argument("destination", type=Path)
    new_parser.add_argument("--id", required=True)
    new_parser.add_argument("--title", required=True)
    new_parser.set_defaults(function=command_new)

    for name, function in (
        ("validate", command_validate), ("index", command_index),
        ("compile", command_compile), ("status", command_status),
        ("prepare", command_prepare), ("dataset-build", command_dataset_build),
        ("pipeline-status", command_pipeline_status)
    ):
        command_parser = subparsers.add_parser(name)
        command_parser.add_argument("project", type=Path)
        command_parser.set_defaults(function=function)

    reference_parser = subparsers.add_parser(
        "reference-prepare",
        help="Probe the authoritative reference and extract deterministic visual evidence frames.",
    )
    reference_parser.add_argument("project", type=Path)
    reference_parser.add_argument("--no-extract-frames", action="store_true")
    reference_parser.set_defaults(function=command_reference_prepare)

    reference_contract_run_parser = subparsers.add_parser(
        "reference-contract-run",
        help="Execute pending reference-frame contracts with the configured local vision model.",
    )
    reference_contract_run_parser.add_argument("project", type=Path)
    reference_contract_run_parser.add_argument("--limit", type=int)
    reference_contract_run_parser.add_argument("--force", action="store_true")
    reference_contract_run_parser.set_defaults(function=command_reference_contract_run)

    reference_contract_audit_parser = subparsers.add_parser(
        "reference-contract-audit",
        help="Aggregate provenance-bearing contracts and refresh the generation disagreement gate.",
    )
    reference_contract_audit_parser.add_argument("project", type=Path)
    reference_contract_audit_parser.set_defaults(function=command_reference_contract_audit)

    reference_contract_import_parser = subparsers.add_parser(
        "reference-contract-import",
        help="Import an explicitly reviewed multimodal evidence set with provenance.",
    )
    reference_contract_import_parser.add_argument("project", type=Path)
    reference_contract_import_parser.add_argument("review", type=Path)
    reference_contract_import_parser.set_defaults(function=command_reference_contract_import)

    caption_run_parser = subparsers.add_parser("caption-run")
    caption_run_parser.add_argument("project", type=Path)
    caption_run_parser.add_argument("--model")
    caption_run_parser.add_argument("--limit", type=int)
    caption_run_parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    caption_run_parser.add_argument("--asset-id")
    caption_run_parser.add_argument("--force", action="store_true")
    caption_run_parser.set_defaults(function=command_caption_run)

    isolation_caption_run_parser = subparsers.add_parser("isolation-caption-run")
    isolation_caption_run_parser.add_argument("project", type=Path)
    isolation_caption_run_parser.add_argument("--identity-id", default="k0l3k4")
    isolation_caption_run_parser.add_argument("--limit", type=int)
    isolation_caption_run_parser.add_argument("--force", action="store_true")
    isolation_caption_run_parser.set_defaults(function=command_isolation_caption_run)

    isolation_caption_audit_parser = subparsers.add_parser("isolation-caption-audit")
    isolation_caption_audit_parser.add_argument("project", type=Path)
    isolation_caption_audit_parser.add_argument("--identity-id", default="k0l3k4")
    isolation_caption_audit_parser.set_defaults(function=command_isolation_caption_audit)

    isolation_caption_review_parser = subparsers.add_parser("isolation-caption-review")
    isolation_caption_review_parser.add_argument("project", type=Path)
    isolation_caption_review_parser.add_argument("asset_id")
    isolation_caption_review_parser.add_argument("--identity-id", default="k0l3k4")
    isolation_caption_review_parser.add_argument("--decision", choices=["approved", "rejected"], required=True)
    isolation_caption_review_parser.add_argument("--note")
    isolation_caption_review_parser.set_defaults(function=command_isolation_caption_review)

    caption_audit_parser = subparsers.add_parser("caption-audit")
    caption_audit_parser.add_argument("project", type=Path)
    caption_audit_parser.set_defaults(function=command_caption_audit)

    for name, function in (("comfy-build", command_comfy_build), ("comfy-preflight", command_comfy_preflight)):
        comfy_parser = subparsers.add_parser(name)
        comfy_parser.add_argument("project", type=Path)
        comfy_parser.add_argument("--shared-models-root")
        comfy_parser.add_argument("--shared-input-root")
        comfy_parser.add_argument("--ltx-models-root")
        comfy_parser.add_argument("--ltx-template")
        comfy_parser.set_defaults(function=function)

    caption_import_parser = subparsers.add_parser("caption-import")
    caption_import_parser.add_argument("project", type=Path)
    caption_import_parser.add_argument("input", type=Path)
    caption_import_parser.set_defaults(function=command_caption_import)

    caption_normalize_parser = subparsers.add_parser("caption-normalize")
    caption_normalize_parser.add_argument("project", type=Path)
    caption_normalize_parser.set_defaults(function=command_caption_normalize)

    caption_review_parser = subparsers.add_parser("caption-review")
    caption_review_parser.add_argument("project", type=Path)
    caption_review_parser.add_argument("asset_id")
    caption_review_parser.add_argument("--decision", choices=["approved", "rejected"], required=True)
    caption_review_parser.add_argument("--split", choices=["train", "validation", "reject"], required=True)
    caption_review_parser.add_argument("--note")
    caption_review_parser.set_defaults(function=command_caption_review)

    isolation_review_parser = subparsers.add_parser("identity-isolation-review")
    isolation_review_parser.add_argument("project", type=Path)
    isolation_review_parser.add_argument("source_sha256")
    isolation_review_parser.add_argument("--identity-id", default="k0l3k4")
    isolation_review_parser.add_argument("--decision", choices=["approved", "rejected"], required=True)
    isolation_review_parser.add_argument("--note")
    isolation_review_parser.set_defaults(function=command_identity_isolation_review)

    balance_parser = subparsers.add_parser("character-balance")
    balance_parser.add_argument("project", type=Path)
    balance_parser.add_argument("--character-id", default="k0l3k4")
    balance_parser.set_defaults(function=command_character_balance)

    rough_cut_parser = subparsers.add_parser(
        "rough-cut", help="Assemble completed ComfyUI clips in script order with FFmpeg."
    )
    rough_cut_parser.add_argument("project", type=Path)
    rough_cut_parser.add_argument("--candidate", type=int, choices=range(1, 5), default=1)
    rough_cut_parser.add_argument("--duration", type=int, choices=(5, 10), default=5)
    rough_cut_parser.add_argument("--output", type=Path)
    rough_cut_parser.add_argument("--allow-missing", action="store_true")
    rough_cut_parser.add_argument("--ffmpeg", default="ffmpeg")
    rough_cut_parser.set_defaults(function=command_rough_cut)

    arguments = parser.parse_args()
    try:
        arguments.function(arguments)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
