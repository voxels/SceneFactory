#!/usr/bin/env python3
"""Execute and audit source-grounded visual contracts for reference frames."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


REQUIRED_CONTRACT_TYPES = {
    "wardrobe", "workers_design", "workers_group_motion", "enforcers_design",
    "enforcers_group_motion", "hammer_geometry", "hammer_state",
    "environment_design", "camera", "lighting", "blocking", "screen_state",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def canonical_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def vision_schema(contract_types: list[str], claims: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Schema intentionally allows contract-specific fields but not uncited prose."""
    return {
        "type": "object",
        "required": ["contracts", "claim_findings"],
        "properties": {
            "contracts": {
                "type": "object",
                "required": contract_types,
                "properties": {
                    name: {
                        "type": "object",
                        "description": "Directly visible facts only; concise snake_case field names.",
                        "additionalProperties": {
                            "type": ["string", "number", "boolean", "array", "null"],
                        },
                    }
                    for name in contract_types
                },
                "additionalProperties": False,
            },
            "claim_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["claim_id", "status", "reason"],
                    "properties": {
                        "claim_id": {"enum": [item["claim_id"] for item in (claims or [])]},
                        "status": {"enum": ["supported", "contradicted", "not_visible"]},
                        "reason": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
        },
        "additionalProperties": False,
    }


def task_prompt(task: Mapping[str, Any], claims: list[dict[str, Any]] | None = None) -> str:
    exclusions = ", ".join(task.get("identity_exclusions", []))
    types = ", ".join(task["contract_types"])
    return (
        "Analyze only directly visible evidence in this single reference-video frame. "
        f"Return contracts for: {types}. Use concise snake_case field names and JSON values. "
        "Use null when a requested fact is not visible; do not infer facts outside the frame. "
        f"Do not derive or describe excluded identity traits: {exclusions}. "
        "For each supplied written claim, classify it as supported, contradicted, or not_visible "
        "using this frame alone. A contradiction means visible evidence is incompatible, not merely absent. "
        f"Written claims: {json.dumps(claims or [], separators=(',', ':'))}. "
        "Do not include explanations or markdown."
    )


def validate_response(task: Mapping[str, Any], response: Mapping[str, Any], claims: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    contracts = response.get("contracts")
    if not isinstance(contracts, dict):
        raise ValueError("vision response must contain a contracts object")
    expected = set(task["contract_types"])
    missing = expected - set(contracts)
    extra = set(contracts) - expected
    if missing:
        raise ValueError(f"vision response missing contracts: {sorted(missing)}")
    if extra:
        raise ValueError(f"vision response has undeclared contracts: {sorted(extra)}")
    for name, fields in contracts.items():
        if not isinstance(fields, dict):
            raise ValueError(f"contract {name} must be an object")
        if not fields:
            raise ValueError(f"contract {name} must contain at least one observed field")
    findings = response.get("claim_findings")
    if not isinstance(findings, list):
        raise ValueError("vision response must contain a claim_findings list")
    expected_claims = {item["claim_id"] for item in (claims or [])}
    if {item.get("claim_id") for item in findings} != expected_claims:
        raise ValueError("vision response must classify every supplied written claim exactly once")
    if any(item.get("status") not in {"supported", "contradicted", "not_visible"} for item in findings):
        raise ValueError("vision response contains an invalid claim status")
    return dict(response)


def _unwrap_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"vision model returned invalid JSON: {error}") from None
    if not isinstance(value, dict):
        raise ValueError("vision model response must be an object")
    return value


def make_huggingface_inference(captioner: Mapping[str, Any]) -> Callable[[Path, str, dict], dict]:
    """Load the configured local image-text model once and return an inference closure."""
    try:
        import torch
        from PIL import Image
        from transformers import AutoModelForImageTextToText, AutoProcessor
    except ImportError as error:
        raise ValueError(f"reference contracts need torch, Pillow, and transformers: {error}") from None
    model_path = Path(captioner["model_path"]).expanduser().resolve()
    processor_path = Path(captioner.get("processor_path", model_path)).expanduser().resolve()
    if not model_path.is_dir() or not processor_path.is_dir():
        raise ValueError("configured local vision model or processor path does not exist")
    device = captioner.get("device", "mps" if torch.backends.mps.is_available() else "cpu")
    dtype = getattr(torch, captioner.get("dtype", "bfloat16"), None)
    if dtype is None:
        raise ValueError("configured vision dtype is unsupported")
    print(f"Loading reference-contract processor: {processor_path}", flush=True)
    processor = AutoProcessor.from_pretrained(processor_path, local_files_only=True)
    print(f"Loading reference-contract model: {model_path}", flush=True)
    model = AutoModelForImageTextToText.from_pretrained(
        model_path, local_files_only=True, dtype=dtype
    ).to(device)
    model.eval()
    min_pixels = int(captioner.get("min_image_pixels", 65536))
    max_pixels = int(captioner.get("max_image_pixels", 1048576))
    max_tokens = int(captioner.get("retry_max_new_tokens", 2048))

    def infer(image_path: Path, prompt: str, schema: dict) -> dict:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        full_prompt = prompt + " JSON schema: " + json.dumps(schema, separators=(",", ":"))
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image}, {"type": "text", "text": full_prompt}
        ]}]
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        inputs = processor(
            text=[text], images=[image], return_tensors="pt",
            images_kwargs={"min_pixels": min_pixels, "max_pixels": max_pixels},
        )
        inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
        input_length = inputs["input_ids"].shape[1]
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)
        content = processor.batch_decode(
            generated[:, input_length:], skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        return _unwrap_json(content)
    return infer


def execute_tasks(
    project_root: Path,
    infer: Callable[[Path, str, dict], Mapping[str, Any]],
    *,
    limit: int | None = None,
    force: bool = False,
    model_provenance: Mapping[str, Any] | None = None,
    claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute pending tasks, persist raw structured observations, then aggregate."""
    project_root = project_root.resolve()
    manifest_path = project_root / "build/reference/reference_manifest.json"
    manifest = read_json(manifest_path)
    selected = [task for task in manifest["vision_contract_tasks"] if force or task["status"] != "complete"]
    if limit is not None:
        selected = selected[:limit]
    results_root = project_root / "build/reference/task_results"
    completed = 0
    failures = []
    for number, task in enumerate(selected, 1):
        frame_path = project_root / task["frame_path"] if task.get("frame_path") else None
        if not frame_path or not frame_path.is_file():
            failures.append({"task_id": task["id"], "error": "evidence frame is missing"})
            continue
        print(f"Reference contract {number}/{len(selected)}: {task['id']}", flush=True)
        try:
            task_claims = [
                item for item in (claims or [])
                if item.get("shot_id") == task["shot_id"]
                or (item.get("shot_id") is None and item.get("resource_tag") in task.get("resource_tags", []))
            ]
            response = validate_response(
                task,
                infer(frame_path, task_prompt(task, task_claims), vision_schema(task["contract_types"], task_claims)),
                task_claims,
            )
            result = {
                "schema_version": 1,
                "task_id": task["id"],
                "shot_id": task["shot_id"],
                "sample": task["sample"],
                "source_authority": "reference_video",
                "model_provenance": dict(model_provenance or {}),
                "evidence": {
                    "frame_path": task["frame_path"],
                    "frame_sha256": task["frame_sha256"],
                    "timestamp_seconds": task["timestamp_seconds"],
                },
                "contracts": response["contracts"],
                "claim_findings": [
                    {**item, "evidence": {
                        "task_id": task["id"], "shot_id": task["shot_id"],
                        "frame_path": task["frame_path"], "frame_sha256": task["frame_sha256"],
                        "timestamp_seconds": task["timestamp_seconds"],
                    }} for item in response["claim_findings"]
                ],
            }
            output = results_root / f"{task['id']}.json"
            write_json(output, result)
            task.update({"status": "complete", "result_path": str(output.relative_to(project_root))})
            completed += 1
        except (ValueError, RuntimeError) as error:
            task["status"] = "failed"
            task["error"] = str(error)
            failures.append({"task_id": task["id"], "error": str(error)})
        write_json(manifest_path, manifest)
    aggregate_contracts(project_root)
    return {"selected": len(selected), "completed": completed, "failures": failures}


def import_reviewed_observations(
    project_root: Path,
    review_path: Path,
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    """Import an explicitly identified multimodal review; never label it as local-model output."""
    project_root = project_root.resolve()
    manifest_path = project_root / "build/reference/reference_manifest.json"
    manifest = read_json(manifest_path)
    review = read_json(review_path)
    observations = {item["task_id"]: item for item in review.get("observations", [])}
    if not observations and review.get("shot_observations"):
        by_shot = {item["shot_id"]: item for item in review["shot_observations"]}
        observations = {
            task["id"]: {**by_shot[task["shot_id"]], "task_id": task["id"]}
            for task in manifest["vision_contract_tasks"]
            if task["shot_id"] in by_shot
        }
    expected = {task["id"] for task in manifest["vision_contract_tasks"]}
    if set(observations) != expected:
        missing, extra = sorted(expected - set(observations)), sorted(set(observations) - expected)
        raise ValueError(f"review task coverage mismatch; missing={missing}, extra={extra}")
    results_root = project_root / "build/reference/task_results"
    for task in manifest["vision_contract_tasks"]:
        observation = observations[task["id"]]
        facts = observation.get("facts", {})
        visible_types = set(observation.get("visible_contract_types", []))
        contracts = {}
        for contract_type in task["contract_types"]:
            fields = {
                "visibility": "visible" if contract_type in visible_types else "not_visible",
                "visible_summary": observation["visible_summary"],
            }
            fields.update(facts.get(contract_type, {}))
            contracts[contract_type] = fields
        task_claims = [
            item for item in claims
            if item.get("shot_id") == task["shot_id"]
            or (item.get("shot_id") is None and item.get("resource_tag") in task.get("resource_tags", []))
        ]
        overrides = observation.get("claim_statuses", {})
        findings = []
        for claim in task_claims:
            override = overrides.get(claim["claim_id"], {})
            findings.append({
                "claim_id": claim["claim_id"],
                "status": override.get("status", "not_visible"),
                "reason": override.get("reason", "This single sampled frame does not establish or contradict the claim."),
                "evidence": {
                    "task_id": task["id"], "shot_id": task["shot_id"],
                    "frame_path": task["frame_path"], "frame_sha256": task["frame_sha256"],
                    "timestamp_seconds": task["timestamp_seconds"],
                },
            })
        result = {
            "schema_version": 1, "task_id": task["id"], "shot_id": task["shot_id"],
            "sample": task["sample"], "source_authority": "reference_video",
            "model_provenance": dict(review["execution_provenance"]),
            "evidence": {
                "frame_path": task["frame_path"], "frame_sha256": task["frame_sha256"],
                "timestamp_seconds": task["timestamp_seconds"],
            },
            "contracts": contracts, "claim_findings": findings,
        }
        output = results_root / f"{task['id']}.json"
        write_json(output, result)
        task.update({"status": "complete", "result_path": str(output.relative_to(project_root))})
        task.pop("error", None)
    write_json(manifest_path, manifest)
    index = aggregate_contracts(project_root)
    return {"completed": len(expected), "contract_index": index}


def aggregate_contracts(project_root: Path) -> dict[str, Any]:
    """Write per-type contracts with provenance attached to every observed field."""
    project_root = project_root.resolve()
    manifest = read_json(project_root / "build/reference/reference_manifest.json")
    grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    completed_tasks = 0
    for task in manifest["vision_contract_tasks"]:
        result_path = task.get("result_path")
        if task.get("status") != "complete" or not result_path:
            continue
        result = read_json(project_root / result_path)
        completed_tasks += 1
        provenance = {
            "task_id": task["id"], "shot_id": task["shot_id"], "sample": task["sample"],
            "frame_path": task["frame_path"], "frame_sha256": task["frame_sha256"],
            "timestamp_seconds": task["timestamp_seconds"],
        }
        for contract_type, fields in result["contracts"].items():
            for field, value in fields.items():
                grouped[contract_type][field].append({"value": value, "provenance": provenance})
    contracts_root = project_root / "build/reference/contracts"
    emitted = []
    for contract_type, fields in sorted(grouped.items()):
        document = {
            "schema_version": 1, "contract_type": contract_type,
            "derivation": "vision_model_observations", "source_authority": "reference_video",
            "fields": dict(sorted(fields.items())),
        }
        output = contracts_root / f"{contract_type}.json"
        write_json(output, document)
        emitted.append(str(output.relative_to(project_root)))
    index = {
        "schema_version": 1,
        "task_summary": {
            "total": len(manifest["vision_contract_tasks"]),
            "complete": completed_tasks,
            "pending": sum(task.get("status") == "pending" for task in manifest["vision_contract_tasks"]),
            "failed": sum(task.get("status") == "failed" for task in manifest["vision_contract_tasks"]),
        },
        "required_contract_types": sorted(REQUIRED_CONTRACT_TYPES),
        "emitted_contract_types": sorted(grouped),
        "contracts": emitted,
    }
    write_json(contracts_root / "index.json", index)
    return index


def written_claims(project: Mapping[str, Any], scenes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Extract explicit visual claims that can contradict authoritative evidence."""
    claims = []
    for scene in scenes:
        for shot in scene.get("shots", []):
            for field in ("action", "framing", "camera", "lens"):
                value = shot.get(field)
                if isinstance(value, str) and value.strip():
                    claims.append({"claim_id": f"{shot['id']}.{field}", "shot_id": shot["id"], "field": field, "value": value.strip()})
            for index, value in enumerate(shot.get("continuity", [])):
                if isinstance(value, str) and value.strip():
                    claims.append({"claim_id": f"{shot['id']}.continuity.{index}", "shot_id": shot["id"], "field": "continuity", "value": value.strip()})
    for prop in project.get("props", []):
        for field in ("description", "geometry", "continuity", "forbidden"):
            value = prop.get(field)
            if value:
                claims.append({
                    "claim_id": f"prop.{prop['id']}.{field}", "shot_id": None,
                    "field": field, "value": value, "resource_tag": prop["id"],
                })
    return claims


def audit_disagreements(
    project_root: Path,
    project: Mapping[str, Any],
    scenes: list[Mapping[str, Any]],
    compare: Callable[[dict, list[dict]], list[dict]] | None = None,
) -> dict[str, Any]:
    """Audit written claims. A comparator must cite contract observations for contradictions."""
    index_path = project_root / "build/reference/contracts/index.json"
    index = read_json(index_path) if index_path.is_file() else {"task_summary": {}, "emitted_contract_types": []}
    claims = written_claims(project, scenes)
    evidence = []
    for path in sorted((project_root / "build/reference/contracts").glob("*.json")):
        if path.name != "index.json":
            evidence.append(read_json(path))
    findings = compare({"claims": claims}, evidence) if compare else []
    if compare is None:
        for task in read_json(project_root / "build/reference/reference_manifest.json").get("vision_contract_tasks", []):
            result_path = task.get("result_path")
            if task.get("status") == "complete" and result_path:
                findings.extend(read_json(project_root / result_path).get("claim_findings", []))
    normalized = []
    for item in findings:
        status = item.get("status")
        if status not in {"supported", "contradicted", "not_visible"}:
            raise ValueError("comparison status must be supported, contradicted, or not_visible")
        if status == "contradicted" and not item.get("evidence"):
            raise ValueError("a contradiction must cite field-level evidence")
        normalized.append(item)
    complete = index.get("task_summary", {}).get("complete", 0)
    total = index.get("task_summary", {}).get("total", 0)
    missing_types = sorted(REQUIRED_CONTRACT_TYPES - set(index.get("emitted_contract_types", [])))
    contradictions = [item for item in normalized if item["status"] == "contradicted" and not item.get("resolution")]
    input_files = [project_root / "project.json", project_root / "script.json", index_path]
    input_files.extend(sorted((project_root / "build/reference/contracts").glob("*.json")))
    input_hashes = {
        str(path.relative_to(project_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in input_files if path.is_file()
    }
    report = {
        "schema_version": 1, "generated_at": now(), "claims_checked": len(claims),
        "gate_input_hashes": input_hashes,
        "task_summary": index.get("task_summary", {}), "missing_contract_types": missing_types,
        "findings": normalized, "unresolved_contradictions": contradictions,
        "generation_gate": {
            "allowed": bool(total and complete == total and not missing_types and not contradictions),
            "reasons": ([f"reference contract tasks incomplete: {complete}/{total}"] if complete != total or not total else [])
            + ([f"missing contract types: {', '.join(missing_types)}"] if missing_types else [])
            + ([f"unresolved written-contract contradictions: {len(contradictions)}"] if contradictions else []),
        },
    }
    write_json(project_root / "build/reference/disagreement_report.json", report)
    return report


def enforce_generation_gate(project_root: Path) -> None:
    path = project_root / "build/reference/disagreement_report.json"
    if not path.is_file():
        raise ValueError("reference disagreement audit is missing; run reference-contract-audit")
    report = read_json(path)
    for relative, expected in report.get("gate_input_hashes", {}).items():
        source = project_root / relative
        actual = hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else "missing"
        if actual != expected:
            raise ValueError(f"reference disagreement audit is stale because {relative} changed; rerun reference-contract-audit")
    if not report.get("generation_gate", {}).get("allowed"):
        reasons = "; ".join(report.get("generation_gate", {}).get("reasons", []))
        raise ValueError(f"reference contract generation gate blocked: {reasons}")


def refresh_invalidation_state(project_root: Path, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare runtime fingerprints and invalidate every transitive descendant."""
    state_path = project_root / "build/invalidation_state.json"
    previous = read_json(state_path) if state_path.is_file() else {"nodes": {}}
    current = {node["id"]: {"fingerprint": node["fingerprint"], "dependencies": sorted(node.get("dependencies", []))} for node in nodes}
    changed = {node_id for node_id, node in current.items() if previous.get("nodes", {}).get(node_id, {}).get("fingerprint") != node["fingerprint"]}
    removed = set(previous.get("nodes", {})) - set(current)
    reverse: dict[str, set[str]] = defaultdict(set)
    for node_id, node in current.items():
        for dependency in node["dependencies"]:
            reverse[dependency].add(node_id)
    invalidated = set(changed)
    queue = deque(changed | removed)
    while queue:
        parent = queue.popleft()
        for child in reverse.get(parent, ()):
            if child not in invalidated:
                invalidated.add(child)
                queue.append(child)
    result = {
        "schema_version": 1, "updated_at": now(), "nodes": current,
        "changed": sorted(changed), "removed": sorted(removed),
        "invalidated": sorted(invalidated),
    }
    write_json(state_path, result)
    return result
