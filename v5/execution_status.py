#!/usr/bin/env python3
"""Read-only rollup of compiled graphs, the Comfy job log, output files, and user approvals.

This module does not write pipeline_state, comfy_state, review JSON, or media.
It does not POST to ComfyUI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path


STAGE_ORDER = (
    "character_sheets",
    "storyboards",
    "scripted_clips",
    "extended_sequences",
    "final_assembly",
)

PHASE_TO_STAGE = {
    "identity_candidates": "character_sheets",
    "identity_first_review": "character_sheets",
    "identity_expansion": "character_sheets",
    "storyboard_candidates": "storyboards",
    "motion_proofs": "scripted_clips",
    "extended_clips": "extended_sequences",
}

CANDIDATE_RE = re.compile(r"__candidate_(\d+)")


def read_optional(path: Path, default):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def user_approved_without_issues(item) -> bool:
    return (
        item.get("decision") == "approved"
        and item.get("approved_by") == "user"
        and item.get("issues") == []
    )


def expand_output_root(project_root: Path, project: dict) -> str:
    raw = project.get("path_defaults", {}).get("OUTPUT_ROOT", "${PROJECT_ROOT}/outputs")
    return str(Path(str(raw).replace("${PROJECT_ROOT}", str(project_root))).resolve())


def namespace_from_prefix(prefix: str | None, fallback: str) -> str:
    if not prefix:
        return fallback
    return prefix.split("/", 1)[0]


def candidate_number(job_id: str, item: dict) -> int | None:
    candidate = item.get("candidate")
    if isinstance(candidate, dict) and candidate.get("number") is not None:
        return int(candidate["number"])
    if isinstance(candidate, int):
        return candidate
    match = CANDIDATE_RE.search(job_id)
    return int(match.group(1)) if match else None


def base_task_id(job_id: str) -> str:
    without_candidate = CANDIDATE_RE.split(job_id, maxsplit=1)[0]
    return re.sub(r"__\d+s__portrait$", "", without_candidate)


def stage_for_item(item: dict) -> str:
    phase = item.get("execution_phase")
    if phase in PHASE_TO_STAGE:
        return PHASE_TO_STAGE[phase]
    job_id = item.get("id", "")
    if job_id.startswith("storyboard__"):
        return "storyboards"
    if "character_sheet" in job_id or item.get("priority") in {"first_review", "expansion"}:
        return "character_sheets"
    if job_id.startswith("video__"):
        duration = item.get("duration_seconds")
        if duration == 3 or phase == "motion_proofs":
            return "scripted_clips"
        if duration == 5 or phase == "extended_clips":
            return "extended_sequences"
        return "scripted_clips"
    return "character_sheets"


def is_required(item: dict, stage: str) -> bool:
    if stage == "character_sheets":
        priority = item.get("priority")
        if priority == "expansion":
            return False
        if priority == "first_review":
            return True
        number = candidate_number(item.get("id", ""), item)
        return number is None or number <= 2
    if stage == "storyboards":
        return False
    return True


def collect_graph_items(manifest: dict) -> list[dict]:
    items = []
    items.extend(manifest.get("character_sheets") or [])
    items.extend(manifest.get("storyboards") or [])
    items.extend(manifest.get("videos") or [])
    return [item for item in items if item.get("id")]


def collect_uncompiled_plan_items(project_root: Path, graph_items: list[dict]) -> list[dict]:
    compiled_bases = {base_task_id(item["id"]) for item in graph_items}
    plan_sources = (
        ("character_sheet_plan.json", "tasks", "character_sheets"),
        ("storyboard_plan.json", "tasks", "storyboards"),
        ("scripted_clip_plan.json", "tasks", "scripted_clips"),
    )
    items = []
    for filename, collection, stage in plan_sources:
        value = read_optional(project_root / "build" / filename, {})
        for task in value.get(collection) or []:
            task_id = task.get("id")
            if not task_id or task_id in compiled_bases:
                continue
            items.append({"id": task_id, "stage": stage, "phase": "not_compiled"})
    return items


def tagged_reviews(path: Path, records: list) -> list:
    return [{**item, "_record_path": str(path)} for item in records if isinstance(item, dict)]


def artifact_review_records(path: Path) -> list:
    value = read_optional(path, {})
    if isinstance(value, list):
        records = value
    elif isinstance(value, dict) and isinstance(value.get("artifacts"), list):
        records = value["artifacts"]
    elif isinstance(value, dict) and value:
        records = [value]
    else:
        records = []
    return tagged_reviews(path, records)


def review_for_job(
    job_id: str, item: dict, stage: str, selections: list,
    proof_reviews: list, artifact_reviews: list,
) -> dict | None:
    number = candidate_number(job_id, item)
    base = base_task_id(job_id)
    if stage == "storyboards":
        for record in selections:
            if record.get("storyboard_task_id") == base and int(record.get("candidate", 0)) == number:
                return record
    if stage in {"scripted_clips", "extended_sequences"}:
        for record in proof_reviews:
            if record.get("video_task_id") == base and int(record.get("candidate", 0)) == number:
                return record
    for record in artifact_reviews:
        if record.get("artifact_id") in {job_id, base}:
            return record
    return None


def describe_outputs(paths: list[str]) -> list[dict]:
    described = []
    for value in paths:
        path = Path(value)
        described.append({
            "path": str(path),
            "exists": path.is_file(),
            "sha256": sha256_file(path),
        })
    return described


def job_state(log_entry: dict, outputs: list[dict], review: dict | None, live_state: str | None) -> str:
    if review and review.get("decision") == "rejected":
        return "rejected"
    if live_state in {"running", "queued"}:
        return live_state
    status = log_entry.get("status")
    if status == "running":
        return "running"
    if status == "failed":
        return "failed"
    if status == "complete":
        if not outputs or any(not item["exists"] for item in outputs):
            return "output_missing"
        if review and user_approved_without_issues(review):
            return "approved"
        return "output_present"
    if log_entry:
        return "graph_ready"
    return "graph_ready"


def live_match(_job_id: str, log_entry: dict, prefix: str | None, namespace: str, live: dict | None) -> str | None:
    if not live:
        return None
    prompt_id = log_entry.get("prompt_id")
    running_ids = set(live.get("running_prompt_ids") or [])
    pending_ids = set(live.get("pending_prompt_ids") or [])
    running_prefixes = set(live.get("running_prefixes") or [])
    pending_prefixes = set(live.get("pending_prefixes") or [])
    if prompt_id and prompt_id in running_ids:
        return "running"
    if prompt_id and prompt_id in pending_ids:
        return "queued"
    if prefix and prefix in running_prefixes and namespace_from_prefix(prefix, "") == namespace:
        return "running"
    if prefix and prefix in pending_prefixes and namespace_from_prefix(prefix, "") == namespace:
        return "queued"
    return None


def storyboard_group_counts(stage_jobs: list[dict]) -> tuple[int, int]:
    groups = {}
    for item in stage_jobs:
        groups.setdefault(base_task_id(item["id"]), []).append(item)
    approved_groups = sum(
        1 for members in groups.values()
        if any(item["state"] == "approved" for item in members)
    )
    return len(groups), approved_groups


def live_overlay_from_queue(payload: dict) -> dict:
    def collect(items):
        prompt_ids = []
        prefixes = []
        for item in items or []:
            if not isinstance(item, list) or len(item) < 2:
                continue
            prompt_ids.append(item[1])
            prompt = item[2] if len(item) > 2 else {}
            if not isinstance(prompt, dict):
                continue
            for node in prompt.values():
                if not isinstance(node, dict):
                    continue
                prefix = (node.get("inputs") or {}).get("filename_prefix")
                if prefix:
                    prefixes.append(prefix)
        return prompt_ids, prefixes

    running_ids, running_prefixes = collect(payload.get("queue_running"))
    pending_ids, pending_prefixes = collect(payload.get("queue_pending"))
    return {
        "running_prompt_ids": running_ids,
        "pending_prompt_ids": pending_ids,
        "running_prefixes": running_prefixes,
        "pending_prefixes": pending_prefixes,
    }


def fetch_live_queue(host: str = "127.0.0.1", port: int = 8188, timeout: float = 3) -> dict | None:
    url = f"http://{host}:{port}/queue"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    return live_overlay_from_queue(payload)


def rollup_stage(stage_id: str, jobs: list[dict]) -> dict:
    stage_jobs = [item for item in jobs if item["stage"] == stage_id]
    required_jobs = [item for item in stage_jobs if item.get("required", True)]
    blockers = []
    if not stage_jobs:
        return {
            "id": stage_id,
            "status": "not_started",
            "required": 0,
            "approved": 0,
            "running": [],
            "blockers": ["no compiled graphs"],
        }
    running = [item["id"] for item in stage_jobs if item["state"] in {"running", "queued"}]
    if stage_id == "storyboards":
        required_count, approved = storyboard_group_counts(stage_jobs)
        required_jobs = stage_jobs
        rejected_required = []
        failed = [item["id"] for item in stage_jobs if item["state"] == "failed"]
        missing = [item["id"] for item in stage_jobs if item["state"] == "output_missing"]
    else:
        required_count = len(required_jobs)
        approved = sum(1 for item in required_jobs if item["state"] == "approved")
        rejected_required = [item["id"] for item in required_jobs if item["state"] == "rejected"]
        failed = [item["id"] for item in required_jobs if item["state"] == "failed"]
        missing = [item["id"] for item in required_jobs if item["state"] == "output_missing"]
    if running:
        status = "active"
    elif rejected_required:
        status = "failed"
        blockers = [f"rejected required jobs: {', '.join(rejected_required)}"]
    elif required_count and approved == required_count:
        status = "complete"
    elif failed:
        status = "failed"
        blockers = [f"failed jobs: {', '.join(failed)}"]
    elif missing:
        status = "blocked"
        blockers = [f"output missing: {', '.join(missing)}"]
    elif any(item["state"] == "graph_ready" for item in stage_jobs):
        status = "ready"
        blockers = [f"graphs waiting: {sum(item['state'] == 'graph_ready' for item in stage_jobs)}"]
    elif any(item["state"] == "output_present" for item in required_jobs):
        status = "needs_approval"
        blockers = ["outputs present; user approval required"]
    else:
        status = "blocked"
        blockers = ["no required jobs in an executable state"]
    return {
        "id": stage_id,
        "status": status,
        "required": required_count,
        "approved": approved,
        "running": running,
        "blockers": blockers,
    }


def collect_status(project_root: Path, live: dict | None = None) -> dict:
    project_root = project_root.resolve()
    project = read_optional(project_root / "project.json", {})
    project_id = project.get("project", {}).get("id") or project_root.name
    output_root = expand_output_root(project_root, project) if project else str(project_root / "outputs")
    manifest = read_optional(project_root / "build" / "comfyui" / "full_visual_graph_manifest.json", {})
    job_log = read_optional(project_root / "build" / "execution" / "comfy_state.json", {})
    log_jobs = job_log.get("jobs") or {}
    selection_path = project_root / "build" / "review" / "storyboard_selections.json"
    selections = tagged_reviews(
        selection_path,
        read_optional(selection_path, {"selections": []}).get("selections") or [],
    )
    proof_review_path = project_root / "build" / "review" / "motion_proof_reviews.json"
    proof_reviews = tagged_reviews(
        proof_review_path,
        read_optional(proof_review_path, {"approvals": []}).get("approvals") or [],
    )
    artifact_reviews = artifact_review_records(project_root / "reviews" / "episode_artifact_review.json")
    generation_manifest = read_optional(project_root / "build" / "generation_manifest.json", {})

    graph_items = collect_graph_items(manifest)
    prefixes = [item.get("output_prefix") for item in graph_items if item.get("output_prefix")]
    namespace = namespace_from_prefix(prefixes[0] if prefixes else None, project_id)

    jobs = []
    for item in graph_items:
        job_id = item["id"]
        prefix = item.get("output_prefix")
        if prefix and namespace_from_prefix(prefix, namespace) != namespace:
            continue
        stage = stage_for_item(item)
        phase = item.get("execution_phase") or stage
        log_entry = log_jobs.get(job_id) or {}
        output_paths = [value for value in log_entry.get("outputs") or [] if value]
        if log_entry.get("staged_keyframe"):
            output_paths.append(log_entry["staged_keyframe"])
        outputs = describe_outputs(output_paths)
        review = review_for_job(job_id, item, stage, selections, proof_reviews, artifact_reviews)
        live_state = live_match(job_id, log_entry, prefix, namespace, live)
        state = job_state(log_entry, outputs, review, live_state) if log_entry or live_state else "graph_ready"
        jobs.append({
            "id": job_id,
            "stage": stage,
            "phase": phase,
            "state": state,
            "required": is_required(item, stage),
            "prompt_id": log_entry.get("prompt_id"),
            "output_prefix": prefix,
            "outputs": outputs,
            "review": None if review is None else {
                "path": review.get("_record_path"),
                "decision": review.get("decision"),
                "approved_by": review.get("approved_by"),
                "issues": review.get("issues"),
            },
        })

    for item in collect_uncompiled_plan_items(project_root, graph_items):
        jobs.append({
            **item,
            "state": "not_compiled",
            "required": True,
            "prompt_id": None,
            "output_prefix": None,
            "outputs": [],
            "review": None,
        })

    if generation_manifest.get("assembly"):
        cut_path = project_root / "build" / "rough_cut" / "candidate_01_5s.mp4"
        outputs = describe_outputs([str(cut_path)])
        cut_review = next((
            item for item in artifact_reviews
            if item.get("artifact_id") == "rough_cut__candidate_01_5s"
            or (item.get("path") and Path(item["path"]).resolve() == cut_path.resolve())
        ), None)
        if cut_path.is_file() and cut_review and user_approved_without_issues(cut_review):
            cut_state = "approved"
        elif cut_path.is_file():
            cut_state = "output_present"
        else:
            cut_state = "not_compiled"
        jobs.append({
            "id": "rough_cut__candidate_01_5s",
            "stage": "final_assembly",
            "phase": "rough_cut",
            "state": cut_state,
            "required": True,
            "prompt_id": None,
            "output_prefix": None,
            "outputs": outputs,
            "review": None if cut_review is None else {
                "path": cut_review.get("_record_path"),
                "decision": cut_review.get("decision"),
                "approved_by": cut_review.get("approved_by"),
                "issues": cut_review.get("issues"),
            },
        })

    stages = [rollup_stage(stage_id, jobs) for stage_id in STAGE_ORDER]
    counts = {
        "jobs": len(jobs),
        "running": sum(item["state"] == "running" for item in jobs),
        "queued": sum(item["state"] == "queued" for item in jobs),
        "output_present": sum(item["state"] == "output_present" for item in jobs),
        "approved": sum(item["state"] == "approved" for item in jobs),
        "failed": sum(item["state"] == "failed" for item in jobs),
        "output_missing": sum(item["state"] == "output_missing" for item in jobs),
    }
    return {
        "schema_version": 1,
        "project_id": project_id,
        "output_root": output_root,
        "comfy_output_namespace": namespace,
        "live": {"available": bool(live)},
        "counts": counts,
        "stages": stages,
        "jobs": jobs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Scene Factory execution status. Does not write job logs or POST to ComfyUI."
    )
    parser.add_argument("project", type=Path)
    parser.add_argument(
        "--live",
        action="store_true",
        help="GET the ComfyUI queue. Never posts. Foreign output namespaces are ignored.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8188)
    arguments = parser.parse_args()
    live = None
    live_error = None
    if arguments.live:
        live = fetch_live_queue(arguments.host, arguments.port)
        if live is None:
            live_error = "comfy queue unavailable"
    report = collect_status(arguments.project, live=live)
    if arguments.live and live is None:
        report["live"] = {"available": False, "error": live_error}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
