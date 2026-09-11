#!/usr/bin/env python3
"""Execute a compiled LTX video graph with strict promotion/audio gates."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import identity_pipeline as identity
from comfy_executor import ComfyExecutionError, _json_request, _model_exists, _upload_image
from image_workflows import validate_api_graph
import video_audio_pipeline


def _upload_audio(url: str, name: str, source: Path, *, timeout: float = 60.0) -> dict[str, Any]:
    boundary = "----SceneFactoryV4Audio" + identity.sha256_file(source)[:16]
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="audio"; filename="{name}"\r\n'.encode())
    body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
    body.extend(source.read_bytes())
    body.extend(f"\r\n--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="type"\r\n\r\naudio\r\n')
    body.extend(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(url, data=bytes(body), method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode())
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as error:
        raise ComfyExecutionError(f"ComfyUI audio upload failed for {name}: {error}") from error
    if not isinstance(value, dict) or not value.get("name"):
        raise ComfyExecutionError(f"ComfyUI returned an invalid audio upload response: {value}")
    return value


def _download_media(base: str, item: dict[str, Any], destination: Path) -> dict[str, Any]:
    filename = str(item.get("filename", ""))
    subfolder = str(item.get("subfolder", ""))
    if not filename or Path(filename).name != filename or Path(subfolder).is_absolute() or ".." in Path(subfolder).parts:
        raise ComfyExecutionError(f"ComfyUI returned an unsafe video filename: {item}")
    query = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": str(item.get("type", "output"))})
    try:
        with urllib.request.urlopen(f"{base}/view?{query}", timeout=120) as response:
            payload = response.read()
    except (OSError, urllib.error.URLError) as error:
        raise ComfyExecutionError(f"failed to download ComfyUI video {filename}: {error}") from error
    if len(payload) < 64:
        raise ComfyExecutionError(f"ComfyUI video output is empty or truncated: {filename}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ComfyExecutionError(f"refusing to overwrite an existing video output: {destination}")
    destination.write_bytes(payload)
    probe = video_audio_pipeline._probe_video(destination)
    if probe.get("status") != "complete" or not probe.get("width") or probe.get("duration_seconds", 0) <= 0:
        raise ComfyExecutionError(f"downloaded output is not a decodable video: {destination}; {probe}")
    return {"path": str(destination), "sha256": identity.sha256_file(destination), "bytes": len(payload), "source": item}


def validate_execution_contract(project_root: Path, *, server_url: str) -> dict[str, Any]:
    project_root = project_root.resolve()
    contract_path = project_root / "build/workflows/video_runtime/video_runtime_contract.json"
    if not contract_path.is_file():
        raise ComfyExecutionError("video workflow contract is missing; run compile-video-workflow first")
    contract = identity.read_json(contract_path)
    graph_path = Path(contract.get("graph", ""))
    if not graph_path.is_file():
        raise ComfyExecutionError(f"compiled video graph is missing: {graph_path}")
    if identity.sha256_file(graph_path) != contract.get("graph_sha256"):
        raise ComfyExecutionError("compiled video graph hash changed; recompile before execution")
    graph = identity.read_json(graph_path)
    validate_api_graph(graph)
    if not contract.get("execution_allowed") or contract.get("execution_blockers"):
        raise ComfyExecutionError("video execution is gated: " + "; ".join(contract.get("execution_blockers", [])))
    if not contract.get("training", {}).get("identity_lora_bound"):
        raise ComfyExecutionError("video graph has no bound identity LoRA")
    for role, item in contract.get("inputs", {}).items():
        if not item:
            continue
        for path_key, hash_key in (("source", "source_sha256"), ("staged", "staged_sha256")):
            path = Path(item.get(path_key, ""))
            if not path.is_file() or identity.sha256_file(path) != item.get(hash_key):
                raise ComfyExecutionError(f"video input changed or missing: {role}/{path_key}")
    alignment_path = project_root / "build/identity/video/audio_alignment_manifest.json"
    alignment = identity.read_json(alignment_path) if alignment_path.is_file() else {}
    if alignment.get("alignment_status") != "complete":
        raise ComfyExecutionError("word/phoneme/viseme alignment is incomplete")
    missing_models = [name for name in contract.get("required_models", []) if not _model_exists(name)]
    if missing_models:
        raise ComfyExecutionError(f"required LTX models are missing: {missing_models}")
    available = _json_request(server_url.rstrip("/") + "/object_info", timeout=15)
    required_nodes = set(contract.get("required_nodes", [])) | {node["class_type"] for node in graph.values()}
    missing_nodes = sorted(name for name in required_nodes if name not in available)
    if missing_nodes:
        raise ComfyExecutionError(f"ComfyUI LTX node classes are unavailable: {missing_nodes}")
    return {"contract": contract, "graph": graph, "graph_path": graph_path, "server_url": server_url.rstrip("/")}


def execute(project_root: Path, *, server_url: str = "http://127.0.0.1:8188",
            timeout_seconds: int = 7200) -> dict[str, Any]:
    """Run the gated graph and download the generated video artifact."""
    checked = validate_execution_contract(project_root, server_url=server_url)
    contract, graph, base = checked["contract"], checked["graph"], checked["server_url"]
    queue = _json_request(f"{base}/queue", timeout=15)
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise ComfyExecutionError("ComfyUI queue is occupied; existing work was left running")
    uploads: list[dict[str, Any]] = []
    inputs = contract.get("inputs", {})
    visual = inputs.get("visual_identity_keyframe") or {}
    if visual.get("staged"):
        uploaded = _upload_image(f"{base}/upload/image", visual["staged_filename"], Path(visual["staged"]))
        replacement = f"{uploaded.get('subfolder','').strip('/')}/{uploaded['name']}".strip('/')
        for node in graph.values():
            if node.get("class_type") == "LoadImage":
                node["inputs"]["image"] = replacement
        uploads.append({"kind": "image", "response": uploaded, "sha256": visual.get("staged_sha256")})
    audio = inputs.get("authoritative_audio") or {}
    if audio.get("staged"):
        uploaded = _upload_audio(f"{base}/upload/audio", audio["staged_filename"], Path(audio["staged"]))
        replacement = f"{uploaded.get('subfolder','').strip('/')}/{uploaded['name']}".strip('/')
        for node in graph.values():
            if node.get("class_type") == "LoadAudio":
                node["inputs"]["audio"] = replacement
        uploads.append({"kind": "audio", "response": uploaded, "sha256": audio.get("staged_sha256")})
    queued = _json_request(f"{base}/prompt", method="POST", payload={"prompt": graph}, timeout=30)
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise ComfyExecutionError(f"ComfyUI did not return a video prompt_id: {queued}")
    deadline = time.monotonic() + timeout_seconds
    history = None
    while time.monotonic() < deadline:
        history = _json_request(f"{base}/history/{prompt_id}", timeout=15)
        if prompt_id in history:
            break
        time.sleep(2.0)
    if not history or prompt_id not in history:
        raise ComfyExecutionError(f"ComfyUI timed out waiting for video prompt {prompt_id}")
    record = history[prompt_id]
    if record.get("status", {}).get("status_str") == "error" or record.get("status", {}).get("completed") is False:
        raise ComfyExecutionError(f"ComfyUI video execution failed for prompt {prompt_id}: {record.get('status')}")
    outputs = []
    for node_outputs in record.get("outputs", {}).values():
        for key in ("videos", "gifs", "images"):
            outputs.extend(node_outputs.get(key, []))
    if not outputs:
        raise ComfyExecutionError(f"ComfyUI completed video prompt {prompt_id} without media outputs")
    output_root = project_root / "build/identity/video/generated"
    downloaded = [_download_media(base, outputs[0], output_root / f"generated_{prompt_id}.mp4")]
    delivery = finalize_delivery(project_root, downloaded[0], contract, str(prompt_id))
    result = {"schema_version": 1, "status": "rendered_pending_validation", "prompt_id": prompt_id,
              "server": base, "graph_sha256": contract["graph_sha256"], "outputs": outputs,
              "downloaded_outputs": downloaded, "uploaded_inputs": uploads,
              "motion_control_consumed": False, "identity_keyframe_consumed": True,
              "validation_pending": ["identity fidelity", "motion adherence", "lip synchronization"],
              "delivery": delivery,
              "audio_alignment_manifest": str(project_root / "build/identity/video/audio_alignment_manifest.json"),
              "generated_at_unix": time.time()}
    identity.write_json(output_root / f"video_runtime_{prompt_id}.json", result)
    return result


def finalize_delivery(project_root: Path, generated: dict[str, Any],
                      contract: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Produce a separate delivery containing the original performance stream."""
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in run_id):
        raise ComfyExecutionError("invalid video delivery run id")
    video = Path(generated["path"])
    if not video.is_file() or identity.sha256_file(video) != generated.get("sha256"):
        raise ComfyExecutionError("generated video changed before final mux")
    audio = contract.get("inputs", {}).get("authoritative_audio") or {}
    source = Path(audio.get("source", ""))
    expected = audio.get("source_sha256")
    if not expected or not source.is_file():
        raise ComfyExecutionError("original performance source/hash is missing")
    destination = project_root.resolve() / "build/identity/video/deliveries" / run_id
    result = video_audio_pipeline.mux_original_audio(
        video, source, destination / "performance.mkv", expected_audio_sha256=expected)
    result.update({"generated_video": generated, "graph_sha256": contract.get("graph_sha256"),
                   "quality_validation_status": "pending", "production_ready": False})
    identity.write_json(destination / "delivery.json", result)
    return result
