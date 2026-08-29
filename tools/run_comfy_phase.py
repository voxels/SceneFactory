#!/usr/bin/env python3

import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_NAMESPACE = "scene_factory_v3_generated"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


PHASES = (
    "identity_first_review",
    "identity_expansion",
    "storyboard_candidates",
    "motion_proofs",
    "extended_clips",
    "all",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def request_json(url, payload=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ComfyUI HTTP {error.code}: {detail}") from None


def phase_items(manifest, phase):
    identity = sorted(
        manifest["character_sheets"],
        key=lambda item: (item.get("priority") != "first_review", item["id"]),
    )
    first = [item for item in identity if item.get("priority") == "first_review"]
    expansion = [item for item in identity if item.get("priority") != "first_review"]
    groups = {
        "identity_first_review": first,
        "identity_expansion": expansion,
        "storyboard_candidates": manifest["storyboards"],
        "motion_proofs": [item for item in manifest["videos"] if item["execution_phase"] == "motion_proofs"],
        "extended_clips": [item for item in manifest["videos"] if item["execution_phase"] == "extended_clips"],
    }
    if phase == "all":
        return [item for name in PHASES[:-1] for item in groups[name]]
    return groups[phase]


def wait_for_job(base_url, prompt_id, timeout_seconds):
    start = time.monotonic()
    next_update = start
    while True:
        history = request_json(f"{base_url}/history/{prompt_id}", timeout=30)
        record = history.get(prompt_id)
        if record:
            status = record.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI job failed: {json.dumps(status, ensure_ascii=False)}")
            if status.get("completed") is True:
                return record
        elapsed = time.monotonic() - start
        if elapsed > timeout_seconds:
            raise TimeoutError(f"ComfyUI job timed out after {timeout_seconds} seconds: {prompt_id}")
        if time.monotonic() >= next_update:
            queue = request_json(f"{base_url}/queue", timeout=30)
            running = len(queue.get("queue_running", []))
            pending = len(queue.get("queue_pending", []))
            print(f"  running={running} queued={pending} elapsed={int(elapsed)}s", flush=True)
            next_update = time.monotonic() + 30
        time.sleep(2)


def output_files(record, output_root):
    files = []
    for node in record.get("outputs", {}).values():
        for key in ("images", "videos", "audio"):
            for item in node.get(key, []):
                filename = item.get("filename")
                if not filename:
                    continue
                subfolder = item.get("subfolder", "")
                files.append(output_root / subfolder / filename)
    return files


def stage_storyboard(item, files, input_root):
    image = next((path for path in files if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}), None)
    if image is None or not image.is_file():
        raise RuntimeError(f"Storyboard output image was not found for {item['id']}")
    parts = item["output_prefix"].split("/")
    if len(parts) < 7:
        raise RuntimeError(f"Unexpected storyboard output prefix: {item['output_prefix']}")
    target = input_root / INPUT_NAMESPACE / parts[-4] / parts[-3] / parts[-2] / f"{parts[-1]}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image, target)
    return target


def completed_outputs_exist(job):
    outputs = [Path(value) for value in job.get("outputs", [])]
    return job.get("status") == "complete" and bool(outputs) and all(path.is_file() for path in outputs)


def main():
    parser = argparse.ArgumentParser(description="Run a resumable SceneFactory ComfyUI phase.")
    parser.add_argument("project", type=Path)
    parser.add_argument("phase", choices=PHASES)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--input-root", type=Path, default=Path("/Users/voxels/ComfyUI-Shared/input"))
    parser.add_argument("--output-root", type=Path, default=Path("/Users/voxels/ComfyUI-Shared/output"))
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--candidate", type=int, choices=range(1, 5),
        help="Run only one candidate number; useful for prioritizing a rough cut."
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rough-cut-candidate", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--rough-cut-duration", type=int, choices=(5, 10), default=5)
    parser.add_argument("--rough-cut-output", type=Path)
    parser.add_argument("--skip-rough-cut", action="store_true")
    arguments = parser.parse_args()

    project = arguments.project.resolve()
    manifest_path = project / "build" / "comfyui" / "full_visual_graph_manifest.json"
    manifest = read_json(manifest_path)
    state_path = project / "build" / "execution" / "comfy_state.json"
    state = read_json(state_path) if state_path.exists() else {"schema_version": 1, "jobs": {}}
    items = phase_items(manifest, arguments.phase)
    if arguments.candidate is not None:
        candidate_token = f"__candidate_{arguments.candidate:02d}"
        items = [item for item in items if candidate_token in item["id"]]
    if arguments.limit is not None:
        items = items[:arguments.limit]

    base_url = f"http://{arguments.host}:{arguments.port}"
    object_info = None if arguments.dry_run else request_json(f"{base_url}/object_info", timeout=10)
    print(f"Phase: {arguments.phase}", flush=True)
    print(f"Jobs selected: {len(items)}", flush=True)
    print(f"State: {state_path}", flush=True)

    completed = 0
    skipped = 0
    for index, item in enumerate(items, 1):
        prior = state["jobs"].get(item["id"], {})
        if not arguments.force and completed_outputs_exist(prior):
            skipped += 1
            print(f"[{index}/{len(items)}] skip complete: {item['id']}", flush=True)
            continue
        if not arguments.force and prior.get("status") == "complete":
            print(f"[{index}/{len(items)}] rerun; recorded output is missing: {item['id']}", flush=True)
        workflow_path = Path(item["workflow"])
        graph = read_json(workflow_path)
        missing_nodes = sorted({node["class_type"] for node in graph.values()} - set(object_info or {}))
        if object_info is not None and missing_nodes:
            raise RuntimeError(f"Missing ComfyUI node types for {item['id']}: {missing_nodes}")
        if not arguments.dry_run and item.get("execution_phase") in {"motion_proofs", "extended_clips"}:
            staged = arguments.input_root / item["staged_keyframe"]
            if not staged.is_file():
                raise RuntimeError(f"Staged key frame does not exist: {staged}")
        if arguments.dry_run:
            print(f"[{index}/{len(items)}] valid: {item['id']}", flush=True)
            continue

        client_id = str(uuid.uuid4())
        print(f"[{index}/{len(items)}] queue: {item['id']}", flush=True)
        response = request_json(f"{base_url}/prompt", {"prompt": graph, "client_id": client_id}, timeout=30)
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return a prompt ID: {response}")
        state["jobs"][item["id"]] = {"status": "running", "prompt_id": prompt_id, "started_at": now()}
        write_json(state_path, state)
        try:
            record = wait_for_job(base_url, prompt_id, arguments.timeout)
            files = output_files(record, arguments.output_root)
            staged_path = None
            if item.get("execution_phase") == "storyboard_candidates":
                staged_path = stage_storyboard(item, files, arguments.input_root)
            state["jobs"][item["id"]] = {
                "status": "complete",
                "prompt_id": prompt_id,
                "completed_at": now(),
                "outputs": [str(path) for path in files],
                "staged_keyframe": str(staged_path) if staged_path else None,
            }
            completed += 1
            print(f"[{index}/{len(items)}] complete: {item['id']}", flush=True)
        except Exception as error:
            state["jobs"][item["id"]] = {
                "status": "failed", "prompt_id": prompt_id, "failed_at": now(), "error": str(error)
            }
            write_json(state_path, state)
            raise
        write_json(state_path, state)

    summary = {"selected": len(items), "completed_now": completed, "skipped": skipped}
    print(json.dumps(summary, indent=2), flush=True)

    should_assemble = (
        arguments.phase == "all"
        and arguments.limit is None
        and not arguments.dry_run
        and not arguments.skip_rough_cut
    )
    if should_assemble:
        import rough_cut
        print("All generation jobs are complete. Starting final FFmpeg rough cut.", flush=True)
        report, report_path = rough_cut.assemble(
            project,
            output=arguments.rough_cut_output,
            candidate=arguments.rough_cut_candidate,
            duration=arguments.rough_cut_duration,
            allow_missing=False,
        )
        print(json.dumps({
            "rough_cut": report["output"],
            "duration_seconds": report["rough_cut_duration_seconds"],
            "timeline_clips": report["timeline_clips"],
            "report": str(report_path),
        }, indent=2), flush=True)


if __name__ == "__main__":
    main()
