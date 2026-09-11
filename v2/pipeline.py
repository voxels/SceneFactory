#!/usr/bin/env python3

import base64
import json
import re
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import scene_factory as core


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
CAPTION_REQUIRED_FIELDS = [
    "description", "composition", "lighting", "quality",
    "identity_tags", "attribute_tags", "apparent_life_stage",
    "visible_traits", "training_caption"
]


def now():
    return datetime.now(timezone.utc).isoformat()


def build_dir(project_root):
    return project_root / "build"


def caption_result_dir(project_root):
    return build_dir(project_root) / "captions" / "results"


def isolation_report_path(project_root, identity_id="k0l3k4"):
    return build_dir(project_root) / "isolation" / identity_id / "isolation_report.json"


def isolation_caption_result_dir(project_root, identity_id="k0l3k4"):
    return build_dir(project_root) / "isolation" / identity_id / "captions" / "results"


def isolation_caption_task_path(project_root, identity_id="k0l3k4"):
    return build_dir(project_root) / "isolation" / identity_id / "caption_tasks.json"


def isolation_records(project_root, identity_id="k0l3k4"):
    path = isolation_report_path(project_root, identity_id)
    if not path.exists():
        return []
    return core.read_json(path).get("records", [])


def isolation_record_for_hash(project_root, source_sha256, identity_id="k0l3k4"):
    return next(
        (item for item in isolation_records(project_root, identity_id)
         if item.get("source_sha256") == source_sha256),
        None
    )


def isolation_caption_result_for_asset(project_root, asset_id, identity_id="k0l3k4"):
    path = isolation_caption_result_dir(project_root, identity_id) / f"{asset_id}__isolated.json"
    return core.read_json(path) if path.exists() else None


def read_optional(path, default):
    return core.read_json(path) if path.exists() else default


def checked_context(project_root):
    errors, warnings, context = core.validate_project(project_root)
    if errors:
        raise ValueError("Project validation failed: " + "; ".join(errors))
    return warnings, context


def concept_for_character(project, character_id):
    for character in project.get("characters", []):
        if character.get("id") == character_id:
            return character.get("concept_id")
    return None


def concept_for_environment(project, environment_id):
    for environment in project.get("environments", []):
        if environment.get("id") == environment_id:
            return environment.get("concept_id")
    return None


def make_source_catalog(project_root, context, asset_index):
    project = context["project"]
    records = []
    seen_hashes = defaultdict(list)
    for category in ("characters", "environments"):
        for owner in asset_index["assets"][category]:
            concept_id = (
                concept_for_character(project, owner["id"])
                if category == "characters"
                else concept_for_environment(project, owner["id"])
            )
            for item in owner.get("files", []):
                path = Path(item["path"])
                if path.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                asset_id = f"{owner['id']}__{item['sha256'][:16]}"
                record = {
                    "asset_id": asset_id,
                    "owner_type": category[:-1],
                    "owner_id": owner["id"],
                    "concept_id": concept_id,
                    "path": str(path),
                    "sha256": item["sha256"],
                    "suffix": path.suffix.lower(),
                    "provenance": "user_source",
                    "caption_status": "pending",
                    "review_state": "pending"
                }
                records.append(record)
                seen_hashes[item["sha256"]].append(asset_id)
    duplicates = [
        {"sha256": digest, "asset_ids": ids}
        for digest, ids in seen_hashes.items() if len(ids) > 1
    ]
    catalog = {
        "schema_version": 1,
        "generated_at": now(),
        "project_id": project["project"]["id"],
        "assets": records,
        "exact_duplicate_groups": duplicates,
        "counts": {"images": len(records), "exact_duplicate_groups": len(duplicates)}
    }
    core.write_json(build_dir(project_root) / "source_catalog.json", catalog)
    return catalog


def caption_prompt(asset, project, registry):
    concept = next((item for item in registry.get("concepts", []) if item.get("id") == asset.get("concept_id")), None)
    concept_context = {
        "concept_id": asset.get("concept_id"),
        "trigger_token": concept.get("trigger_token") if concept else None,
        "class_token": concept.get("class_token") if concept else None,
        "stable_attributes": concept.get("stable_attributes", []) if concept else [],
        "variable_attributes": concept.get("variable_attributes", []) if concept else [],
        "caption_order": concept.get("training", {}).get("caption_order", []) if concept else []
    }
    return (
        "Describe only what is visibly supported by the image. Return JSON that follows the supplied schema. "
        "Do not infer identity, ethnicity, medical facts, or exact age. Use supplied identity tags only as labels. "
        "Set apparent_life_stage to child, adolescent, young_adult, adult, later_adult, or uncertain. "
        "Do not use the production cultural direction as a source-photo ethnicity label. "
        "Describe subjects, framing, view, camera angle, lighting, environment, visible text, sharpness, occlusion, "
        "visible face, hair, expression, makeup, wardrobe, pose, body visibility, training risks, and whether the image "
        "is usable for concept training. Make a concise training_caption in the "
        "declared order. Keep fixed identity attributes separate from visible variable attributes.\n\n"
        f"Project context: {json.dumps(project.get('project', {}), ensure_ascii=False)}\n"
        f"Concept context: {json.dumps(concept_context, ensure_ascii=False)}"
    )


def make_caption_tasks(project_root, context, catalog):
    existing = read_optional(build_dir(project_root) / "caption_tasks.json", {"tasks": []})
    existing_by_id = {item["asset_id"]: item for item in existing.get("tasks", [])}
    results_dir = caption_result_dir(project_root)
    tasks = []
    for asset in catalog["assets"]:
        concept = next((item for item in context["registry"].get("concepts", []) if item.get("id") == asset.get("concept_id")), None)
        required_identity_tags = []
        if concept and concept.get("type") == "character_identity" and concept.get("trigger_token"):
            required_identity_tags.append(concept["trigger_token"])
        prior = existing_by_id.get(asset["asset_id"], {})
        result_path = results_dir / f"{asset['asset_id']}.json"
        status = "complete" if result_path.exists() else prior.get("status", "pending")
        tasks.append({
            "asset_id": asset["asset_id"],
            "source_path": asset["path"],
            "source_sha256": asset["sha256"],
            "owner_type": asset["owner_type"],
            "owner_id": asset["owner_id"],
            "concept_id": asset.get("concept_id"),
            "prompt": caption_prompt(asset, context["project"], context["registry"]),
            "required_fields": CAPTION_REQUIRED_FIELDS,
            "required_identity_tags": required_identity_tags,
            "class_token": concept.get("class_token") if concept else None,
            "caption_order": concept.get("training", {}).get("caption_order", []) if concept else [],
            "status": status,
            "result_path": str(result_path)
        })
    value = {
        "schema_version": 1,
        "generated_at": now(),
        "caption_schema": str((Path(__file__).resolve().parent / "schemas" / "caption.schema.json")),
        "tasks": tasks,
        "counts": {
            "total": len(tasks),
            "pending": sum(item["status"] == "pending" for item in tasks),
            "complete": sum(item["status"] == "complete" for item in tasks)
        }
    }
    core.write_json(build_dir(project_root) / "caption_tasks.json", value)
    return value


def make_character_sheet_plan(project_root, context):
    tasks = []
    views = [
        ("face_front", "close portrait, front view, neutral expression"),
        ("face_three_quarter_left", "close portrait, left three-quarter view"),
        ("face_three_quarter_right", "close portrait, right three-quarter view"),
        ("profile_left", "left profile portrait"),
        ("profile_right", "right profile portrait"),
        ("full_front", "full body, front view, neutral stance"),
        ("full_back", "full body, back view, neutral stance"),
        ("expression_sheet", "approved expression sheet with consistent identity"),
        ("wardrobe_sheet", "approved wardrobe turnaround with consistent identity")
    ]
    for character in context["project"].get("characters", []):
        if character.get("role") != "foreground":
            continue
        for view_id, description in views:
            tasks.append({
                "id": f"character_sheet__{character['id']}__{view_id}",
                "character_id": character["id"],
                "concept_id": character.get("concept_id"),
                "identity_tag": character.get("identity_tag"),
                "view_id": view_id,
                "prompt_contract": {
                    "description": description,
                    "identity_tag": character.get("identity_tag"),
                    "attribute_tags": character.get("attribute_tags", []),
                    "continuity": character.get("continuity", []),
                    "background": "plain neutral review background"
                },
                "output": f"outputs/character_sheets/{character['id']}/{view_id}.png",
                "status": "blocked",
                "blockers": ["approved captions", "ready identity concept", "generation adapter"]
            })
    value = {"schema_version": 1, "generated_at": now(), "tasks": tasks}
    core.write_json(build_dir(project_root) / "character_sheet_plan.json", value)
    return value


def make_storyboard_plan(project_root, context, manifest):
    tasks = []
    for item in manifest.get("keyframe_tasks", []):
        tasks.append({
            "id": item["id"].replace("keyframe__", "storyboard__"),
            "scene_id": item["scene_id"],
            "shot_id": item["shot_id"],
            "formation": item["formation"],
            "prompt_contract": item["prompt_contract"],
            "concept_conditioning": item.get("concept_conditioning", []),
            "purpose": "low-cost composition, blocking, lens, and continuity approval",
            "output": item["output"].replace("/keyframes/", "/storyboards/"),
            "status": "blocked",
            "blockers": ["approved reference captions", "storyboard generation adapter"]
        })
    value = {"schema_version": 1, "generated_at": now(), "tasks": tasks}
    core.write_json(build_dir(project_root) / "storyboard_plan.json", value)
    return value


def make_clip_and_sequence_plans(project_root, manifest):
    clips = []
    for item in manifest.get("video_tasks", []):
        clips.append({
            **item,
            "required_inputs": ["approved storyboard", "approved production key frame", "approved motion direction"],
            "handles": {"head_frames": 8, "tail_frames": 8},
            "continuity_review": ["identity", "wardrobe", "screen direction", "prop state", "environment geometry", "motion landing"],
            "status": "blocked"
        })
    by_scene = defaultdict(list)
    for item in manifest.get("assembly", []):
        by_scene[item["scene_id"]].append(item)
    sequences = []
    for scene_id, items in by_scene.items():
        sequences.append({
            "id": f"sequence__{scene_id}",
            "scene_id": scene_id,
            "clips": [item["source"] for item in items],
            "timeline_start_seconds": items[0]["timeline_start_seconds"],
            "duration_seconds": round(sum(item["trim_duration_seconds"] for item in items), 6),
            "transition_policy": "continuity cut unless the script declares another transition",
            "extension_policy": "extend only from approved clip boundary frames; preserve identity, wardrobe, prop state, environment, screen direction, and motion velocity",
            "audio": [cue for item in items for cue in item.get("audio", [])],
            "status": "blocked",
            "blockers": ["approved scripted clips", "sequence assembly adapter", "sequence review"]
        })
    clip_value = {"schema_version": 1, "generated_at": now(), "tasks": clips}
    sequence_value = {"schema_version": 1, "generated_at": now(), "sequences": sequences, "final_timeline": manifest.get("assembly", [])}
    core.write_json(build_dir(project_root) / "scripted_clip_plan.json", clip_value)
    core.write_json(build_dir(project_root) / "sequence_plan.json", sequence_value)
    return clip_value, sequence_value


def prepare(project_root):
    warnings, context = checked_context(project_root)
    asset_index = core.build_asset_index(project_root, context)
    _, manifest = core.compile_manifest(project_root, context)
    catalog = make_source_catalog(project_root, context, asset_index)
    captions = make_caption_tasks(project_root, context, catalog)
    character_sheets = make_character_sheet_plan(project_root, context)
    storyboards = make_storyboard_plan(project_root, context, manifest)
    clips, sequences = make_clip_and_sequence_plans(project_root, manifest)
    state = refresh_state(project_root, context, catalog, captions, character_sheets, storyboards, clips, sequences)
    return warnings, state


def caption_schema_for_model():
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "subjects": {"type": "array", "items": {"type": "object"}},
            "composition": {
                "type": "object",
                "properties": {"framing": {"type": "string"}, "view": {"type": "string"}, "camera_angle": {"type": "string"}},
                "required": ["framing", "view", "camera_angle"]
            },
            "lighting": {"type": "array", "items": {"type": "string"}},
            "environment": {"type": "array", "items": {"type": "string"}},
            "visible_text": {"type": "array", "items": {"type": "string"}},
            "quality": {
                "type": "object",
                "properties": {
                    "sharpness": {"type": "string"}, "occlusion": {"type": "string"},
                    "training_usable": {"type": "boolean"}, "risks": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["sharpness", "occlusion", "training_usable", "risks"]
            },
            "identity_tags": {"type": "array", "items": {"type": "string"}},
            "attribute_tags": {"type": "array", "items": {"type": "string"}},
            "apparent_life_stage": {
                "enum": ["child", "adolescent", "young_adult", "adult", "later_adult", "uncertain"]
            },
            "visible_traits": {
                "type": "object",
                "properties": {
                    "face_visibility": {"type": "string"},
                    "hair_color": {"type": "string"},
                    "hair_texture": {"type": "string"},
                    "hair_style": {"type": "string"},
                    "expression": {"type": "string"},
                    "makeup": {"type": "string"},
                    "body_visibility": {"type": "string"},
                    "wardrobe": {"type": "array", "items": {"type": "string"}},
                    "pose": {"type": "string"}
                },
                "required": [
                    "face_visibility", "hair_color", "hair_texture", "hair_style",
                    "expression", "makeup", "body_visibility", "wardrobe", "pose"
                ]
            },
            "training_caption": {"type": "string"}
        },
        "required": CAPTION_REQUIRED_FIELDS
    }


def ollama_json(url, payload=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as error:
        raise ValueError(f"Ollama request failed: {error}") from None


def available_ollama_models(base_url):
    response = ollama_json(f"{base_url.rstrip('/')}/api/tags")
    return {item.get("name") for item in response.get("models", [])}


def _parse_caption_json(content, asset_id):
    content = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if fenced:
        content = fenced.group(1)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", content):
            try:
                value, _ = decoder.raw_decode(content[match.start():])
                if isinstance(value, dict) and all(field in value for field in CAPTION_REQUIRED_FIELDS):
                    return value
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Caption model returned invalid JSON for {asset_id}") from None


def caption_has_multiple_people(result):
    subjects = result.get("subjects", [])
    if isinstance(subjects, list) and len(subjects) > 1:
        return True
    labels = []
    for value in result.get("identity_tags", []):
        if isinstance(value, str):
            labels.append(value.lower())
    if isinstance(subjects, list):
        for subject in subjects:
            if not isinstance(subject, dict):
                continue
            identity = subject.get("identity")
            if isinstance(identity, str):
                labels.append(identity.lower())
            for value in subject.get("identity_tags", []):
                if isinstance(value, str):
                    labels.append(value.lower())
    other_person_labels = {"man", "boy", "girl", "child", "baby", "toddler", "infant", "people", "group"}
    if any(label in other_person_labels for label in labels):
        return True
    description = result.get("description", "")
    return isinstance(description, str) and bool(re.search(r"\b(group of|people|children|family)\b", description, re.IGNORECASE))


def review_isolation(project_root, source_sha256, decision, note=None, identity_id="k0l3k4"):
    path = isolation_report_path(project_root, identity_id)
    if not path.exists():
        raise ValueError(f"Isolation report does not exist: {path}")
    report = core.read_json(path)
    record = next(
        (item for item in report.get("records", []) if item.get("source_sha256") == source_sha256),
        None
    )
    if record is None:
        raise ValueError(f"Unknown isolation source fingerprint: {source_sha256}")
    if decision == "approved":
        required = ["selected_face_id", "selected_person_instance", "mask_path", "isolated_path", "overlay_path"]
        missing = [key for key in required if record.get(key) in {None, ""}]
        if missing:
            raise ValueError("Isolation approval is missing: " + ", ".join(missing))
        for key in ("mask_path", "isolated_path", "overlay_path"):
            if not Path(record[key]).is_file():
                raise ValueError(f"Isolation artifact does not exist: {record[key]}")
    record["review_state"] = decision
    record["reviewed_at"] = now()
    if note:
        record.setdefault("review_notes", []).append(note)
    core.write_json(path, report)
    return record


def normalize_caption_structure(task, result):
    subjects = [item for item in result.get("subjects", []) if isinstance(item, dict)]
    class_token = str(task.get("class_token") or "").lower()
    target = next((item for item in subjects if class_token and class_token in [
        str(value).lower() for value in item.get("identity_tags", [])
    ]), subjects[0] if subjects else {})
    if target:
        result["identity_tags"] = [
            value for value in target.get("identity_tags", []) if isinstance(value, str)
        ]
        result["attribute_tags"] = [
            value for value in target.get("attribute_tags", []) if isinstance(value, str)
        ]
        result["apparent_life_stage"] = target.get("apparent_life_stage", "uncertain")
        result["visible_traits"] = dict(target.get("visible_traits", {}))
    else:
        result.setdefault("identity_tags", [])
        result.setdefault("attribute_tags", [])
        result.setdefault("apparent_life_stage", "uncertain")
        result.setdefault("visible_traits", {})
    allowed_stages = {"child", "adolescent", "young_adult", "adult", "later_adult", "uncertain"}
    if result.get("apparent_life_stage") not in allowed_stages:
        result["apparent_life_stage"] = "uncertain"
    traits = result.get("visible_traits", {})
    if isinstance(traits, dict):
        wardrobe = traits.get("wardrobe", [])
        if isinstance(wardrobe, str):
            traits["wardrobe"] = [] if wardrobe.lower() in {"", "none", "not visible", "unspecified"} else [wardrobe]
    for subject in subjects:
        traits = subject.get("visible_traits")
        if isinstance(traits, dict) and isinstance(traits.get("wardrobe"), str):
            wardrobe = traits["wardrobe"]
            traits["wardrobe"] = [] if wardrobe.lower() in {"", "none", "not visible", "unspecified"} else [wardrobe]
    traits = result.get("visible_traits", {})
    if isinstance(traits, dict):
        expression = str(traits.get("expression", "uncertain")).lower()
        traits["expression"] = next(
            (value for value in ("neutral", "smiling", "laughing", "serious", "determined") if value in expression),
            "uncertain"
        )
        texture = str(traits.get("hair_texture", "uncertain")).lower()
        traits["hair_texture"] = next(
            (value for value in ("curly", "wavy", "straight", "coily") if value in texture),
            "uncertain"
        )
        body = str(traits.get("body_visibility", "uncertain")).lower()
        if "full" in body:
            traits["body_visibility"] = "full_body"
        elif "leg" in body or "three-quarter" in body:
            traits["body_visibility"] = "three_quarter_body"
        elif "upper" in body or "torso" in body or "arm" in body:
            traits["body_visibility"] = "upper_body"
        elif "head" in body or "neck" in body or "shoulder" in body:
            traits["body_visibility"] = "head_and_shoulders"
        else:
            traits["body_visibility"] = "partial_or_uncertain"
    composition = result.get("composition", {})
    if isinstance(composition, dict):
        view = str(composition.get("view", "uncertain")).lower()
        if "profile" in view and "left" in view:
            composition["view"] = "left_profile"
        elif "profile" in view and "right" in view:
            composition["view"] = "right_profile"
        elif "three" in view and "left" in view:
            composition["view"] = "left_three_quarter"
        elif "three" in view and "right" in view:
            composition["view"] = "right_three_quarter"
        elif "front" in view or "portrait" in view or "interior" in view:
            composition["view"] = "frontal"
        else:
            composition["view"] = "uncertain"
    return result


def apply_caption_policies(task, result):
    result = normalize_caption_structure(task, result)
    visible_identity_labels = [
        value.lower() for value in result.get("identity_tags", []) if isinstance(value, str)
    ]
    for subject in result.get("subjects", []):
        if not isinstance(subject, dict):
            continue
        if isinstance(subject.get("identity"), str):
            visible_identity_labels.append(subject["identity"].lower())
        visible_identity_labels.extend(
            value.lower() for value in subject.get("identity_tags", []) if isinstance(value, str)
        )
    identity_tags = result.get("identity_tags")
    if not isinstance(identity_tags, list):
        identity_tags = []
    training_caption = result.get("training_caption", "")
    original_training_caption = training_caption
    for identity_tag in task.get("required_identity_tags", []):
        if identity_tag not in identity_tags:
            identity_tags.append(identity_tag)
        if identity_tag not in training_caption:
            training_caption = f"{identity_tag}, {training_caption}".rstrip(", ")
    result["identity_tags"] = identity_tags
    caption_order = task.get("caption_order", [])
    canonical_markers = ["view", "framing", "visible expression", "visible occlusion"]
    if len(caption_order) >= 7 and caption_order[-4:] == canonical_markers:
        composition = result.get("composition", {})
        quality = result.get("quality", {})
        expression = None
        existing_match = re.search(
            r"visible expression\s+(.+?)(?:,?\s+visible occlusion|$)", training_caption, re.IGNORECASE
        )
        if existing_match:
            expression = existing_match.group(1).strip(" ,")
        if not expression:
            for subject in result.get("subjects", []):
                if isinstance(subject, dict) and isinstance(subject.get("expression"), str):
                    expression = subject["expression"].strip()
                    break
        if not expression:
            expression_tags = {
                "smiling", "neutral expression", "serious expression", "laughing", "frowning"
            }
            expression = next(
                (tag for tag in result.get("attribute_tags", []) if isinstance(tag, str) and tag.lower() in expression_tags),
                "unspecified"
            )
        training_caption = ", ".join([
            *caption_order[:-4],
            f"view {composition.get('view', 'unspecified')}",
            f"framing {composition.get('framing', 'unspecified')}",
            f"visible expression {expression}",
            f"visible occlusion {quality.get('occlusion', 'unspecified')}"
        ])
    result["training_caption"] = training_caption
    if re.search(
        r"\b(?:early|mid|late)[ -]?\d{2}s\b|\b\d{1,2}[ -]?years?[ -]?old\b",
        f"{original_training_caption} {training_caption}", re.IGNORECASE
    ):
        quality = result.setdefault("quality", {})
        risks = quality.setdefault("risks", [])
        risk = "exact or narrow age estimate is not allowed; use apparent_life_stage"
        if risk not in risks:
            risks.append(risk)
        quality["training_usable"] = False
    class_token = task.get("class_token")
    if class_token and class_token.lower() not in visible_identity_labels:
        quality = result.setdefault("quality", {})
        risks = quality.setdefault("risks", [])
        class_risk = f"declared class {class_token} is not visibly supported; verify target identity"
        if class_risk not in risks:
            risks.append(class_risk)
        quality["training_usable"] = False
    if task.get("required_identity_tags") and caption_has_multiple_people(result):
        quality = result.setdefault("quality", {})
        risks = quality.setdefault("risks", [])
        isolation_risk = "multiple visible people; isolate the target subject before identity training"
        if isolation_risk not in risks:
            risks.append(isolation_risk)
        quality["training_usable"] = False
    return result


def _caption_result(task, content, model_name):
    result = apply_caption_policies(task, _parse_caption_json(content, task["asset_id"]))
    result.update({
        "asset_id": task["asset_id"],
        "source_sha256": task["source_sha256"],
        "concept_id": task.get("concept_id"),
        "caption_model": model_name,
        "review_state": "pending",
        "split": "unassigned",
        "review_notes": []
    })
    validate_caption_result(result, task)
    return result


def _raw_caption_path(task):
    result_path = Path(task["result_path"])
    return result_path.parent.parent / "raw" / f"{task['asset_id']}.txt"


def _write_raw_caption(task, content):
    raw_path = _raw_caption_path(task)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _write_caption_failure(task, error):
    result_path = Path(task["result_path"])
    failure_path = result_path.parent.parent / "failures" / f"{task['asset_id']}.json"
    core.write_json(failure_path, {
        "asset_id": task["asset_id"],
        "source_path": task["source_path"],
        "source_sha256": task["source_sha256"],
        "raw_path": str(_raw_caption_path(task)),
        "error": str(error),
        "failed_at": now()
    })


def _clear_caption_failure(task):
    result_path = Path(task["result_path"])
    failure_path = result_path.parent.parent / "failures" / f"{task['asset_id']}.json"
    if failure_path.exists():
        failure_path.unlink()


def _run_huggingface_captions(pending, captioner):
    try:
        import torch
        from PIL import Image
        from transformers import AutoModelForImageTextToText, AutoProcessor
    except ImportError as error:
        raise ValueError(
            "The Hugging Face caption provider needs torch, Pillow, and transformers. "
            "Run Scene Factory with the Python executable set in models.captioner.python. "
            f"Missing import: {error}"
        ) from None

    model_path = Path(captioner["model_path"]).expanduser().resolve()
    processor_path = Path(captioner.get("processor_path", model_path)).expanduser().resolve()
    if not model_path.is_dir():
        raise ValueError(f"Hugging Face model path does not exist: {model_path}")
    if not processor_path.is_dir():
        raise ValueError(f"Hugging Face processor path does not exist: {processor_path}")

    device = captioner.get("device", "mps" if torch.backends.mps.is_available() else "cpu")
    dtype_name = captioner.get("dtype", "bfloat16")
    dtype = getattr(torch, dtype_name, None)
    if dtype is None:
        raise ValueError(f"Unsupported torch dtype: {dtype_name}")
    max_new_tokens = int(captioner.get("max_new_tokens", 1024))
    retry_max_new_tokens = int(captioner.get("retry_max_new_tokens", 2048))
    min_image_pixels = int(captioner.get("min_image_pixels", 65536))
    max_image_pixels = int(captioner.get("max_image_pixels", 1048576))
    if min_image_pixels > max_image_pixels:
        raise ValueError("min_image_pixels must not be larger than max_image_pixels")
    print(f"Loading caption processor: {processor_path}", flush=True)
    processor = AutoProcessor.from_pretrained(processor_path, local_files_only=True)
    print(f"Loading caption model: {model_path}", flush=True)
    model = AutoModelForImageTextToText.from_pretrained(
        model_path, local_files_only=True, dtype=dtype
    ).to(device)
    model.eval()
    schema_text = json.dumps(caption_schema_for_model(), separators=(",", ":"))
    for number, task in enumerate(pending, 1):
        print(f"Captioning {number}/{len(pending)}: {task['source_path']}", flush=True)
        with Image.open(task["source_path"]) as source_image:
            image = source_image.convert("RGB")
        prompt = (
            task["prompt"]
            + "\n\nKeep each subject record concise. Do not repeat composition, lighting, "
            "background, camera, or wardrobe fields inside each subject. Return only one JSON object. JSON schema: "
            + schema_text
        )
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt}
            ]
        }]
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        inputs = processor(
            text=[text], images=[image], return_tensors="pt",
            images_kwargs={"min_pixels": min_image_pixels, "max_pixels": max_image_pixels}
        )
        inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
        input_length = inputs["input_ids"].shape[1]
        token_limits = [max_new_tokens]
        if retry_max_new_tokens > max_new_tokens:
            token_limits.append(retry_max_new_tokens)
        last_error = None
        for attempt, token_limit in enumerate(token_limits, 1):
            if attempt > 1:
                print(
                    f"Retrying {task['asset_id']} with {token_limit} output tokens after: {last_error}",
                    flush=True
                )
            with torch.inference_mode():
                generated = model.generate(**inputs, max_new_tokens=token_limit, do_sample=False)
            content = processor.batch_decode(
                generated[:, input_length:], skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]
            _write_raw_caption(task, content)
            try:
                yield task, _caption_result(task, content, str(model_path)), None
                break
            except ValueError as error:
                last_error = str(error)
        else:
            yield task, None, last_error


def run_captions(
    project_root, captioner, limit=None, base_url="http://127.0.0.1:11434",
    asset_id=None, force=False
):
    tasks_path = build_dir(project_root) / "caption_tasks.json"
    if not tasks_path.exists():
        prepare(project_root)
    task_file = core.read_json(tasks_path)
    if isinstance(captioner, str):
        captioner = {"provider": "ollama", "model": captioner}
    provider = captioner.get("provider", "ollama")
    model_name = captioner.get("model_path") if provider == "huggingface" else captioner.get("model")
    if asset_id and not any(task["asset_id"] == asset_id for task in task_file["tasks"]):
        raise ValueError(f"Unknown caption asset_id: {asset_id}")
    recovered = 0
    for task in task_file["tasks"]:
        result_path = Path(task["result_path"])
        raw_path = _raw_caption_path(task)
        if force or (asset_id and task["asset_id"] != asset_id):
            continue
        if task["status"] == "complete" or result_path.exists() or not raw_path.exists():
            continue
        try:
            result = _caption_result(task, raw_path.read_text(encoding="utf-8"), str(model_name))
            core.write_json(result_path, result)
            _clear_caption_failure(task)
            task["status"] = "complete"
            recovered += 1
            print(f"Recovered caption from saved raw response: {task['asset_id']}", flush=True)
        except ValueError:
            pass
    if recovered:
        task_file["counts"] = {
            "total": len(task_file["tasks"]),
            "pending": sum(item["status"] == "pending" for item in task_file["tasks"]),
            "complete": sum(item["status"] == "complete" for item in task_file["tasks"])
        }
        core.write_json(tasks_path, task_file)
    pending = [
        item for item in task_file["tasks"]
        if (not asset_id or item["asset_id"] == asset_id)
        and (force or item["status"] != "complete")
    ]
    if limit is not None:
        pending = pending[:limit]
    results_dir = caption_result_dir(project_root)
    results_dir.mkdir(parents=True, exist_ok=True)
    if not pending:
        return recovered, []
    if provider == "huggingface":
        generated_results = _run_huggingface_captions(pending, captioner)
    elif provider == "ollama":
        model = captioner.get("model")
        if not model:
            raise ValueError("The Ollama caption provider needs models.captioner.model")
        models = available_ollama_models(base_url)
        if model not in models and not any(name and name.split(":")[0] == model for name in models):
            raise ValueError(f"Ollama model is not installed: {model}. Installed: {sorted(models)}")
        generated_results = []
        for number, task in enumerate(pending, 1):
            print(f"Captioning {number}/{len(pending)}: {task['source_path']}", flush=True)
            image_data = base64.b64encode(Path(task["source_path"]).read_bytes()).decode("ascii")
            response = ollama_json(f"{base_url.rstrip('/')}/api/chat", {
                "model": model,
                "stream": False,
                "format": caption_schema_for_model(),
                "messages": [{"role": "user", "content": task["prompt"], "images": [image_data]}],
                "options": {"temperature": 0}
            })
            content = response.get("message", {}).get("content", "")
            _write_raw_caption(task, content)
            try:
                generated_results.append((task, _caption_result(task, content, model), None))
            except ValueError as error:
                generated_results.append((task, None, str(error)))
    else:
        raise ValueError(f"Unsupported caption provider: {provider}")

    completed = 0
    failures = []
    for task, result, error in generated_results:
        if error:
            _write_caption_failure(task, error)
            failures.append({"asset_id": task["asset_id"], "error": error})
            print(f"Caption failed for {task['asset_id']}: {error}", flush=True)
            continue
        core.write_json(results_dir / f"{task['asset_id']}.json", result)
        _clear_caption_failure(task)
        task["status"] = "complete"
        completed += 1
        task_file["counts"] = {
            "total": len(task_file["tasks"]),
            "pending": sum(item["status"] == "pending" for item in task_file["tasks"]),
            "complete": sum(item["status"] == "complete" for item in task_file["tasks"])
        }
        core.write_json(tasks_path, task_file)
    return completed + recovered, failures


def make_isolation_caption_tasks(project_root, identity_id="k0l3k4"):
    source_tasks = core.read_json(build_dir(project_root) / "caption_tasks.json").get("tasks", [])
    source_by_hash = {item.get("source_sha256"): item for item in source_tasks}
    result_dir = isolation_caption_result_dir(project_root, identity_id)
    tasks = []
    for isolation in isolation_records(project_root, identity_id):
        isolated_path = isolation.get("isolated_path")
        source_task = source_by_hash.get(isolation.get("source_sha256"))
        if not isolated_path or not source_task or not Path(isolated_path).is_file():
            continue
        source_result_path = Path(source_task["result_path"])
        if not source_result_path.exists() or not caption_has_multiple_people(core.read_json(source_result_path)):
            continue
        asset_id = f"{source_task['asset_id']}__isolated"
        result_path = result_dir / f"{asset_id}.json"
        tasks.append({
            **source_task,
            "asset_id": asset_id,
            "source_path": isolated_path,
            "source_sha256": core.sha256(Path(isolated_path)),
            "original_asset_id": source_task["asset_id"],
            "original_source_path": source_task["source_path"],
            "original_source_sha256": source_task["source_sha256"],
            "prompt": source_task["prompt"] + (
                "\n\nThis is a reviewed isolated derivative of the target subject. "
                "Ignore transparent or black background areas and small mask artifacts. "
                "Describe only the visible target subject."
            ),
            "status": "complete" if result_path.exists() else "pending",
            "result_path": str(result_path)
        })
    value = {
        "schema_version": 1,
        "generated_at": now(),
        "identity_id": identity_id,
        "tasks": tasks,
        "counts": {
            "total": len(tasks),
            "pending": sum(item["status"] == "pending" for item in tasks),
            "complete": sum(item["status"] == "complete" for item in tasks)
        }
    }
    core.write_json(isolation_caption_task_path(project_root, identity_id), value)
    return value


def run_isolation_captions(project_root, captioner, identity_id="k0l3k4", limit=None, force=False):
    task_file = make_isolation_caption_tasks(project_root, identity_id)
    if captioner.get("provider") != "huggingface":
        raise ValueError("Isolation captioning currently needs the configured local Hugging Face Qwen model")
    pending = [item for item in task_file["tasks"] if force or item["status"] != "complete"]
    if limit is not None:
        pending = pending[:limit]
    completed = 0
    failures = []
    for task, result, error in _run_huggingface_captions(pending, captioner):
        if error:
            _write_caption_failure(task, error)
            failures.append({"asset_id": task["asset_id"], "error": error})
            continue
        result.update({
            "original_asset_id": task["original_asset_id"],
            "original_source_path": task["original_source_path"],
            "original_source_sha256": task["original_source_sha256"],
            "derivative_type": "reviewed_identity_isolation"
        })
        core.write_json(Path(task["result_path"]), result)
        _clear_caption_failure(task)
        task["status"] = "complete"
        completed += 1
        task_file["counts"] = {
            "total": len(task_file["tasks"]),
            "pending": sum(item["status"] == "pending" for item in task_file["tasks"]),
            "complete": sum(item["status"] == "complete" for item in task_file["tasks"])
        }
        core.write_json(isolation_caption_task_path(project_root, identity_id), task_file)
    return completed, failures


def audit_isolation_captions(project_root, identity_id="k0l3k4"):
    task_file = make_isolation_caption_tasks(project_root, identity_id)
    results = []
    errors = []
    for task in task_file["tasks"]:
        path = Path(task["result_path"])
        if not path.exists():
            errors.append({"asset_id": task["asset_id"], "error": "missing result"})
            continue
        try:
            result = core.read_json(path)
            validate_caption_result(result, task)
            results.append(result)
        except ValueError as error:
            errors.append({"asset_id": task["asset_id"], "error": str(error)})
    report = {
        "schema_version": 1,
        "generated_at": now(),
        "identity_id": identity_id,
        "summary": {
            "total": len(task_file["tasks"]),
            "valid": len(results),
            "approved": sum(item.get("review_state") == "approved" for item in results),
            "rejected": sum(item.get("review_state") == "rejected" for item in results),
            "pending_review": sum(item.get("review_state") == "pending" for item in results),
            "errors": len(errors)
        },
        "errors": errors
    }
    path = build_dir(project_root) / "isolation" / identity_id / "captions" / "audit.json"
    core.write_json(path, report)
    return report, path


def review_isolation_caption(project_root, original_asset_id, decision, note=None, identity_id="k0l3k4"):
    path = isolation_caption_result_dir(project_root, identity_id) / f"{original_asset_id}__isolated.json"
    if not path.exists():
        raise ValueError(f"Isolation caption result does not exist: {original_asset_id}")
    result = core.read_json(path)
    validate_caption_result(result)
    if decision == "approved" and caption_has_multiple_people(result):
        raise ValueError("An isolation caption cannot be approved when it still describes multiple people")
    result["review_state"] = decision
    if note:
        result.setdefault("review_notes", []).append(note)
    result["reviewed_at"] = now()
    core.write_json(path, result)
    return result


def audit_captions(project_root):
    task_file = core.read_json(build_dir(project_root) / "caption_tasks.json")
    _, context = checked_context(project_root)
    concepts = {
        item.get("id"): item for item in context["registry"].get("concepts", [])
        if item.get("id")
    }
    records = []
    errors = []
    for task in task_file["tasks"]:
        result_path = Path(task["result_path"])
        raw_path = _raw_caption_path(task)
        item_errors = []
        result = None
        source_path = Path(task["source_path"])
        if not source_path.is_file():
            item_errors.append("source image is missing")
        elif core.sha256(source_path) != task["source_sha256"]:
            item_errors.append("source image fingerprint changed")
        if not result_path.exists():
            item_errors.append("missing validated result")
        else:
            try:
                result = core.read_json(result_path)
                validate_caption_result(result, task)
            except ValueError as error:
                item_errors.append(str(error))
        if not raw_path.exists():
            item_errors.append("missing raw model response")
        if result:
            if not isinstance(result.get("description"), str) or not result["description"].strip():
                item_errors.append("description is empty or not text")
            composition = result.get("composition")
            if not isinstance(composition, dict) or not all(
                isinstance(composition.get(key), str) and composition[key].strip()
                for key in ("framing", "view", "camera_angle")
            ):
                item_errors.append("composition is incomplete")
            if not isinstance(result.get("lighting"), list):
                item_errors.append("lighting is not a list")
            quality = result.get("quality")
            if not isinstance(quality, dict) or not isinstance(quality.get("training_usable"), bool):
                item_errors.append("quality.training_usable is not a Boolean")
            if not isinstance(quality, dict) or not isinstance(quality.get("risks"), list):
                item_errors.append("quality.risks is not a list")
            for key in ("identity_tags", "attribute_tags"):
                if not isinstance(result.get(key), list) or not all(isinstance(tag, str) for tag in result[key]):
                    item_errors.append(f"{key} is not a text list")
            concept = concepts.get(task.get("concept_id"), {})
            caption_order = concept.get("training", {}).get("caption_order", [])
            if (
                len(caption_order) >= 2
                and caption_order[0] == concept.get("trigger_token")
                and caption_order[1] == concept.get("class_token")
            ):
                caption_text = result.get("training_caption", "").lower()
                positions = [caption_text.find(token.lower()) for token in caption_order]
                if any(position < 0 for position in positions):
                    item_errors.append("training caption is missing a required ordered token")
                elif positions != sorted(positions):
                    item_errors.append("training caption tokens are out of the declared order")
        if item_errors:
            errors.append({"asset_id": task["asset_id"], "errors": item_errors})
        quality = result.get("quality", {}) if result else {}
        subjects = result.get("subjects", []) if result else []
        multiple_people = caption_has_multiple_people(result) if result else None
        records.append({
            "asset_id": task["asset_id"],
            "source_path": task["source_path"],
            "source_sha256": task["source_sha256"],
            "result_path": str(result_path),
            "raw_path": str(raw_path),
            "subject_count": len(subjects) if isinstance(subjects, list) else None,
            "multiple_people": multiple_people,
            "training_usable": quality.get("training_usable"),
            "risks": quality.get("risks", []),
            "review_state": result.get("review_state") if result else None,
            "split": result.get("split") if result else None,
            "errors": item_errors
        })
    failures_dir = build_dir(project_root) / "captions" / "failures"
    failure_records = list(failures_dir.glob("*.json")) if failures_dir.exists() else []
    summary = {
        "total": len(records),
        "valid": sum(not item["errors"] for item in records),
        "invalid": sum(bool(item["errors"]) for item in records),
        "training_usable": sum(item["training_usable"] is True for item in records),
        "needs_isolation_or_rejection": sum(item["training_usable"] is False for item in records),
        "reviewed": sum(item["review_state"] in {"approved", "rejected"} for item in records),
        "pending_review": sum(item["review_state"] == "pending" for item in records),
        "failure_records": len(failure_records)
    }
    report = {"generated_at": now(), "summary": summary, "errors": errors, "records": records}
    audit_path = build_dir(project_root) / "captions" / "audit.json"
    core.write_json(audit_path, report)
    lines = [
        "# Caption Manual Review", "",
        f"Generated: {report['generated_at']}", "",
        f"- Total: {summary['total']}",
        f"- Structurally valid: {summary['valid']}",
        f"- Invalid: {summary['invalid']}",
        f"- Model-marked training usable: {summary['training_usable']}",
        f"- Needs isolation or rejection: {summary['needs_isolation_or_rejection']}",
        f"- Pending human review: {summary['pending_review']}", "",
        f"- Failure records: {summary['failure_records']}", "",
        "Do not approve an identity-training image until you confirm the correct person, face visibility, age-range label, source hash, and caption.", "",
        "| Source | Asset ID | Subjects | Multiple people | Usable | Risks | Evidence |", "|---|---|---:|---|---|---|---|"
    ]
    for record in records:
        risks = "; ".join(record["risks"]) if record["risks"] else "none"
        lines.append(
            f"| [{Path(record['source_path']).name}](<{record['source_path']}>) | `{record['asset_id']}` | "
            f"{record['subject_count']} | {record['multiple_people']} | {record['training_usable']} | {risks} | "
            f"[raw](<{record['raw_path']}>) [result](<{record['result_path']}>) |"
        )
    review_path = build_dir(project_root) / "captions" / "MANUAL_REVIEW.md"
    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report, audit_path, review_path


def validate_caption_result(result, task=None):
    for field in CAPTION_REQUIRED_FIELDS:
        if field not in result:
            raise ValueError(f"Caption result is missing {field}")
    if task:
        if result.get("asset_id") != task.get("asset_id"):
            raise ValueError("Caption asset_id does not match the task")
        if result.get("source_sha256") != task.get("source_sha256"):
            raise ValueError("Caption source fingerprint does not match the task")
        for identity_tag in task.get("required_identity_tags", []):
            if identity_tag not in result.get("identity_tags", []):
                raise ValueError(f"Caption is missing required identity tag: {identity_tag}")
            if identity_tag not in result.get("training_caption", ""):
                raise ValueError(f"Training caption is missing required identity tag: {identity_tag}")
    if not isinstance(result.get("training_caption"), str) or not result["training_caption"].strip():
        raise ValueError("Caption training_caption is empty")


def import_captions(project_root, input_path):
    tasks = core.read_json(build_dir(project_root) / "caption_tasks.json")
    task_by_id = {item["asset_id"]: item for item in tasks["tasks"]}
    document = core.read_json(input_path)
    records = document if isinstance(document, list) else document.get("results", [document])
    results_dir = caption_result_dir(project_root)
    results_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for result in records:
        task = task_by_id.get(result.get("asset_id"))
        if task is None:
            raise ValueError(f"Unknown caption asset_id: {result.get('asset_id')}")
        result.setdefault("caption_model", "imported")
        result["review_state"] = "pending"
        result["split"] = "unassigned"
        result.setdefault("review_notes", [])
        validate_caption_result(result, task)
        core.write_json(results_dir / f"{task['asset_id']}.json", result)
        task["status"] = "complete"
        count += 1
    tasks["counts"] = {
        "total": len(tasks["tasks"]),
        "pending": sum(item["status"] == "pending" for item in tasks["tasks"]),
        "complete": sum(item["status"] == "complete" for item in tasks["tasks"])
    }
    core.write_json(build_dir(project_root) / "caption_tasks.json", tasks)
    return count


def normalize_saved_captions(project_root):
    tasks = core.read_json(build_dir(project_root) / "caption_tasks.json")
    task_by_id = {item["asset_id"]: item for item in tasks["tasks"]}
    count = 0
    for path in sorted(caption_result_dir(project_root).glob("*.json")):
        result = core.read_json(path)
        task = task_by_id.get(result.get("asset_id"))
        if task is None:
            continue
        result = apply_caption_policies(task, result)
        result["review_state"] = "pending"
        result["split"] = "unassigned"
        result.setdefault("review_notes", [])
        validate_caption_result(result, task)
        core.write_json(path, result)
        count += 1
    return count


def review_caption(project_root, asset_id, decision, split, note=None):
    path = caption_result_dir(project_root) / f"{asset_id}.json"
    if not path.exists():
        raise ValueError(f"Caption result does not exist: {asset_id}")
    result = core.read_json(path)
    validate_caption_result(result)
    if decision == "approved" and split not in {"train", "validation"}:
        raise ValueError("An approved caption needs train or validation split")
    if decision == "approved" and caption_has_multiple_people(result):
        isolation = isolation_record_for_hash(project_root, result.get("source_sha256"))
        if not isolation or isolation.get("review_state") != "approved":
            raise ValueError(
                "A multi-person identity source needs an approved face match and full-subject isolation before caption approval"
            )
        isolated_caption = isolation_caption_result_for_asset(project_root, result.get("asset_id"))
        if not isolated_caption or isolated_caption.get("review_state") != "approved":
            raise ValueError(
                "A multi-person identity source needs an approved caption of the isolated derivative before caption approval"
            )
    result["review_state"] = decision
    result["split"] = split if decision == "approved" else "reject"
    if note:
        result.setdefault("review_notes", []).append(note)
    result["reviewed_at"] = now()
    core.write_json(path, result)
    return result


def build_datasets(project_root):
    _, context = checked_context(project_root)
    minimum_by_concept = {
        item["id"]: int(item.get("training", {}).get("minimum_approved_images", 0))
        for item in context["registry"].get("concepts", [])
    }
    tasks = core.read_json(build_dir(project_root) / "caption_tasks.json")
    task_by_id = {item["asset_id"]: item for item in tasks["tasks"]}
    grouped = defaultdict(lambda: {"train": [], "validation": []})
    for path in sorted(caption_result_dir(project_root).glob("*.json")):
        result = core.read_json(path)
        if result.get("review_state") != "approved":
            continue
        task = task_by_id.get(result.get("asset_id"))
        if task is None or not task.get("concept_id"):
            continue
        source_path = task["source_path"]
        source_sha256 = result["source_sha256"]
        provenance = "user_source"
        original_source_path = None
        original_source_sha256 = None
        if caption_has_multiple_people(result):
            isolation = isolation_record_for_hash(project_root, result["source_sha256"])
            if not isolation or isolation.get("review_state") != "approved":
                continue
            isolated_caption_path = isolation_caption_result_dir(project_root) / f"{result['asset_id']}__isolated.json"
            if not isolated_caption_path.exists():
                continue
            isolated_caption = core.read_json(isolated_caption_path)
            if isolated_caption.get("review_state") != "approved":
                continue
            original_source_path = source_path
            original_source_sha256 = source_sha256
            source_path = isolation["isolated_path"]
            source_sha256 = core.sha256(Path(source_path))
            provenance = "approved_isolated_user_source"
            caption_result_path = isolated_caption_path
            training_caption = isolated_caption["training_caption"]
        else:
            caption_result_path = path
            training_caption = result["training_caption"]
        entry = {
            "asset_id": result["asset_id"],
            "source_path": source_path,
            "source_sha256": source_sha256,
            "provenance": provenance,
            "original_source_path": original_source_path,
            "original_source_sha256": original_source_sha256,
            "caption": training_caption,
            "caption_result": str(caption_result_path)
        }
        grouped[task["concept_id"]][result["split"]].append(entry)
    outputs = []
    for concept_id, splits in grouped.items():
        train_hashes = {item["source_sha256"] for item in splits["train"]}
        validation_hashes = {item["source_sha256"] for item in splits["validation"]}
        leakage = sorted(train_hashes.intersection(validation_hashes))
        manifest = {
            "schema_version": 1,
            "generated_at": now(),
            "concept_id": concept_id,
            "train": splits["train"],
            "validation": splits["validation"],
            "counts": {"train": len(splits["train"]), "validation": len(splits["validation"])},
            "minimum_train_images": minimum_by_concept.get(concept_id, 0),
            "cross_split_exact_duplicates": leakage,
            "ready": bool(
                len(splits["train"]) >= minimum_by_concept.get(concept_id, 0)
                and splits["validation"] and not leakage
            )
        }
        output = build_dir(project_root) / "datasets" / concept_id / "manifest.json"
        core.write_json(output, manifest)
        outputs.append(str(output))
    return outputs


def build_character_balance_report(project_root, character_id="k0l3k4"):
    contract_path = project_root / "characters" / f"{character_id}.character.json"
    if not contract_path.exists():
        raise ValueError(f"Character contract does not exist: {contract_path}")
    contract = core.read_json(contract_path)
    results = [core.read_json(path) for path in sorted(caption_result_dir(project_root).glob("*.json"))]
    results = [item for item in results if item.get("concept_id") == contract.get("identity_concept")]
    isolation_by_hash = {
        item.get("source_sha256"): item for item in isolation_records(project_root, character_id)
        if item.get("source_sha256")
    }

    def value(item, group):
        if group == "apparent_life_stage":
            return item.get(group, "uncertain")
        if group == "view":
            return item.get("composition", {}).get("view", "uncertain")
        return item.get("visible_traits", {}).get(group, "uncertain")

    groups = ["apparent_life_stage", "view", "expression", "hair_texture", "body_visibility"]
    allowed_stages = {"young_adult", "adult"}
    direct = [
        item for item in results
        if item.get("quality", {}).get("training_usable") is True
        and item.get("apparent_life_stage") in allowed_stages
        and not caption_has_multiple_people(item)
        and item.get("review_state") != "rejected"
    ]
    isolated = []
    for item in results:
        if not caption_has_multiple_people(item) or item.get("review_state") == "rejected":
            continue
        isolation = isolation_by_hash.get(item.get("source_sha256"), {})
        if isolation.get("review_state") != "approved":
            continue
        isolated_caption = isolation_caption_result_for_asset(project_root, item.get("asset_id"), character_id)
        if not isolated_caption or isolated_caption.get("review_state") != "approved":
            continue
        if isolated_caption.get("quality", {}).get("training_usable") is not True:
            continue
        if isolated_caption.get("apparent_life_stage") not in allowed_stages:
            continue
        isolated.append({**isolated_caption, "asset_id": item.get("asset_id")})
    eligible = direct + isolated

    def counts(items):
        output = {}
        for group in groups:
            values = defaultdict(int)
            for item in items:
                values[str(value(item, group))] += 1
            output[group] = dict(sorted(values.items()))
        return output

    targets = contract.get("balance_targets", {})
    eligible_counts = counts(eligible)
    gaps = {}
    for group in groups:
        gaps[group] = {
            key: max(0, int(target) - int(eligible_counts.get(group, {}).get(key, 0)))
            for key, target in targets.get(group, {}).items()
        }
    warnings = []
    if len(eligible) < int(targets.get("minimum_train_images", 0)) + int(targets.get("minimum_validation_images", 0)):
        warnings.append("Not enough eligible images for the required training and validation sets")
    if sum(eligible_counts.get("view", {}).get(key, 0) for key in ("left_three_quarter", "right_three_quarter", "left_profile", "right_profile")) == 0:
        warnings.append("No eligible three-quarter or profile views")
    if eligible_counts.get("expression", {}).get("smiling", 0) > max(1, len(eligible) * 0.60):
        warnings.append("Smiling expressions exceed sixty percent of the eligible set")
    if eligible_counts.get("body_visibility", {}).get("full_body", 0) < targets.get("body_visibility", {}).get("full_body", 0):
        warnings.append("Full-body evidence is below the target")
    report = {
        "schema_version": 1,
        "generated_at": now(),
        "character_id": character_id,
        "contract_path": str(contract_path),
        "counts": {
            "source_results": len(results),
            "direct_eligible": len(direct),
            "approved_isolated_eligible": len(isolated),
            "total_eligible": len(eligible)
        },
        "all_sources": counts(results),
        "eligible_sources": eligible_counts,
        "targets": targets,
        "gaps": gaps,
        "warnings": warnings,
        "eligible_asset_ids": [item.get("asset_id") for item in eligible]
    }
    output_root = build_dir(project_root) / "training" / character_id
    report_path = output_root / "balance_report.json"
    core.write_json(report_path, report)
    lines = [
        f"# {character_id} Training Balance", "",
        f"Generated: {report['generated_at']}", "",
        f"- Source records: {len(results)}",
        f"- Direct eligible records: {len(direct)}",
        f"- Approved isolated records: {len(isolated)}",
        f"- Total eligible records: {len(eligible)}", "",
        "## Warnings", ""
    ]
    lines.extend([f"- {item}" for item in warnings] or ["- None"])
    lines.extend(["", "## Coverage and gaps", "", "| Group | Value | Eligible | Target | Gap |", "|---|---|---:|---:|---:|"])
    for group in groups:
        keys = sorted(set(eligible_counts.get(group, {})) | set(targets.get(group, {})))
        for key in keys:
            lines.append(
                f"| {group} | {key} | {eligible_counts.get(group, {}).get(key, 0)} | "
                f"{targets.get(group, {}).get(key, 0)} | {gaps.get(group, {}).get(key, 0)} |"
            )
    markdown_path = output_root / "BALANCE_REPORT.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report, report_path, markdown_path


def refresh_state(project_root, context=None, catalog=None, captions=None, character_sheets=None, storyboards=None, clips=None, sequences=None):
    if context is None:
        _, context = checked_context(project_root)
    catalog = catalog or read_optional(build_dir(project_root) / "source_catalog.json", {"assets": []})
    captions = captions or read_optional(build_dir(project_root) / "caption_tasks.json", {"tasks": []})
    results = [core.read_json(path) for path in caption_result_dir(project_root).glob("*.json")] if caption_result_dir(project_root).exists() else []
    approved = [item for item in results if item.get("review_state") == "approved"]
    reviewed = [item for item in results if item.get("review_state") in {"approved", "rejected"}]
    datasets = list((build_dir(project_root) / "datasets").glob("*/manifest.json")) if (build_dir(project_root) / "datasets").exists() else []
    dataset_ready = any(core.read_json(path).get("ready") for path in datasets)
    caption_total = len(captions.get("tasks", []))
    caption_complete = sum(item.get("status") == "complete" for item in captions.get("tasks", []))
    identity_sources = [item for item in results if caption_has_multiple_people(item)]
    isolation_by_hash = {
        item.get("source_sha256"): item for item in isolation_records(project_root)
        if item.get("source_sha256")
    }
    approved_isolations = [
        item for item in identity_sources
        if isolation_by_hash.get(item.get("source_sha256"), {}).get("review_state") == "approved"
    ]
    rejected_isolations = [
        item for item in identity_sources
        if isolation_by_hash.get(item.get("source_sha256"), {}).get("review_state") == "rejected"
    ]
    reviewed_isolations = approved_isolations + rejected_isolations
    isolation_complete = len(reviewed_isolations) == len(identity_sources)
    stages = [
        {"id": "source_ingestion", "status": "complete" if catalog.get("assets") else "blocked", "inputs": ["project sources"], "outputs": ["build/source_catalog.json"], "blockers": [] if catalog.get("assets") else ["no source images"]},
        {"id": "structured_captioning", "status": "complete" if caption_total and caption_complete == caption_total else "blocked", "inputs": ["build/source_catalog.json", "vision caption model or imported results"], "outputs": ["build/captions/results/*.json"], "blockers": [] if caption_total and caption_complete == caption_total else [f"caption results {caption_complete}/{caption_total}"]},
        {"id": "identity_isolation", "status": "complete" if isolation_complete else "blocked", "inputs": ["caption results", "face anchors", "face matches", "person masks"], "outputs": ["reviewed isolated user-source images"], "blockers": [] if isolation_complete else [f"reviewed isolations {len(reviewed_isolations)}/{len(identity_sources)}; approved {len(approved_isolations)}; rejected {len(rejected_isolations)}"]},
        {"id": "caption_review", "status": "complete" if caption_total and len(reviewed) == caption_total else "blocked", "inputs": ["caption results", "approved identity isolations for multi-person images"], "outputs": ["approved caption records with train or validation split", "rejected caption records"], "blockers": [] if caption_total and len(reviewed) == caption_total else [f"reviewed captions {len(reviewed)}/{caption_total}", f"approved captions {len(approved)}"]},
        {"id": "concept_datasets", "status": "complete" if dataset_ready else "blocked", "inputs": ["approved caption records"], "outputs": ["build/datasets/*/manifest.json"], "blockers": [] if dataset_ready else ["no ready train and validation dataset"]},
        {"id": "concept_training", "status": "blocked", "inputs": ["ready dataset", "training profile"], "outputs": ["validated concept models"], "blockers": ["training execution adapter", "model validation"]},
        {"id": "character_sheets", "status": "blocked", "inputs": ["approved captions", "ready identity model"], "outputs": ["approved character sheets"], "blockers": ["ready identity model", "image execution adapter", "human review"]},
        {"id": "storyboards", "status": "blocked", "inputs": ["script", "approved references", "character sheets"], "outputs": ["approved storyboard frames"], "blockers": ["approved references", "storyboard execution adapter", "human review"]},
        {"id": "scripted_clips", "status": "blocked", "inputs": ["approved storyboards", "production key frames", "motion direction"], "outputs": ["approved clips"], "blockers": ["image and video execution adapters", "human review"]},
        {"id": "extended_sequences", "status": "blocked", "inputs": ["approved clips", "continuity records"], "outputs": ["approved sequences"], "blockers": ["approved clips", "sequence assembly adapter", "human review"]},
        {"id": "final_assembly", "status": "blocked", "inputs": ["approved sequences", "audio", "graphics"], "outputs": ["final master"], "blockers": ["approved sequences", "audio and graphics", "assembly adapter", "final review"]}
    ]
    state = {"schema_version": 1, "generated_at": now(), "project_id": context["project"]["project"]["id"], "stages": stages}
    core.write_json(build_dir(project_root) / "pipeline_state.json", state)
    return state


def state_summary(state):
    return [{"stage": item["id"], "status": item["status"], "blockers": item["blockers"]} for item in state["stages"]]
