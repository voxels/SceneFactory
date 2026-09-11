#!/usr/bin/env python3
"""Execute compiled ComfyUI API graphs with fail-closed input/model checks."""

from __future__ import annotations

import json
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
import copy
import re
from pathlib import Path
from typing import Any

import identity_pipeline as identity
from image_workflows import validate_api_graph


COMFY_ROOT = Path("/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI")


class ComfyExecutionError(RuntimeError):
    """A missing runtime contract or failed ComfyUI execution."""


def _json_request(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
                  timeout: float = 10.0) -> dict[str, Any]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8", errors="replace")
        except OSError:
            detail = ""
        raise ComfyExecutionError(
            f"ComfyUI HTTP {error.code} for {url}: {detail[:1200]}"
        ) from error
    except (OSError, urllib.error.URLError) as error:
        raise ComfyExecutionError(f"ComfyUI is not reachable at {url}: {error}") from error
    try:
        value = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComfyExecutionError(f"ComfyUI returned non-JSON data for {url}") from error
    if not isinstance(value, dict):
        raise ComfyExecutionError(f"ComfyUI returned an invalid JSON object for {url}")
    return value


def _upload_image(url: str, name: str, source: Path, *, timeout: float = 30.0) -> dict[str, Any]:
    """Upload a staged input through ComfyUI so Desktop and standalone paths agree."""
    boundary = "----SceneFactoryV4" + uuid.uuid4().hex
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode())
    body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
    body.extend(source.read_bytes())
    body.extend(f"\r\n--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="type"\r\n\r\ninput\r\n')
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n')
    body.extend(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        url, data=bytes(body), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1200]
        raise ComfyExecutionError(f"ComfyUI upload HTTP {error.code} for {name}: {detail}") from error
    except (OSError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComfyExecutionError(f"ComfyUI image upload failed for {name}: {error}") from error
    if not isinstance(value, dict) or not value.get("name"):
        raise ComfyExecutionError(f"ComfyUI returned an invalid upload response for {name}: {value}")
    return value


def _model_exists(filename: str) -> bool:
    # Search only the two configured model roots; never accept a similarly named
    # file from an unrelated project or silently substitute a different model.
    for root in (COMFY_ROOT / "models", Path("/Users/voxels/ComfyUI-Shared/models")):
        if not root.is_dir():
            continue
        # Workflow manifests may use a model-root-relative path such as
        # ``scene_factory_v4/adapter.safetensors``.  Check that exact path first,
        # then fall back to a basename search only for legacy flat manifests.
        exact = root / filename
        if exact.is_file():
            return True
        if "/" not in filename and any(path.name == filename for path in root.rglob(filename)):
            return True
        if "/" in filename:
            relative_suffix = Path(filename).as_posix().lstrip("/")
            if any(path.is_file() and path.relative_to(root).as_posix().endswith(relative_suffix)
                   for path in root.rglob(Path(filename).name)):
                return True
    return False


def _download_output(base: str, item: dict[str, Any], destination: Path) -> dict[str, Any]:
    """Download one Comfy output into the project and record its content hash."""
    filename = str(item.get("filename", ""))
    subfolder = str(item.get("subfolder", ""))
    if (not filename or Path(filename).name != filename
            or Path(subfolder).is_absolute() or ".." in Path(subfolder).parts):
        raise ComfyExecutionError(f"ComfyUI returned an unsafe output filename: {item}")
    query = urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder,
        "type": str(item.get("type", "output")),
    })
    try:
        with urllib.request.urlopen(f"{base}/view?{query}", timeout=60) as response:
            payload = response.read()
    except (OSError, urllib.error.URLError) as error:
        raise ComfyExecutionError(f"failed to download ComfyUI output {filename}: {error}") from error
    if (len(payload) < 16
            or not (payload.startswith(b"\x89PNG\r\n\x1a\n") or payload.startswith(b"\xff\xd8\xff"))):
        raise ComfyExecutionError(f"ComfyUI output is empty, truncated, or not an image: {filename}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {"path": str(destination), "sha256": identity.sha256_file(destination), "bytes": len(payload)}


def _upstream_text_node(graph: dict[str, Any], link: Any) -> str | None:
    """Find a CLIPTextEncode ancestor through reference/control nodes."""
    seen: set[str] = set()
    pending = [link[0]] if isinstance(link, list) and link and isinstance(link[0], str) else []
    while pending:
        node_id = pending.pop()
        if node_id in seen or node_id not in graph:
            continue
        seen.add(node_id)
        node = graph[node_id]
        if node.get("class_type") == "CLIPTextEncode":
            return node_id
        for value in node.get("inputs", {}).values():
            if isinstance(value, list) and value and isinstance(value[0], str):
                pending.append(value[0])
    return None


def validate_execution_contract(project_root: Path, route_name: str) -> dict[str, Any]:
    """Validate a compiled route, staged files, node availability, and models."""
    project_root = project_root.resolve()
    root = project_root / "build/workflows/image_ablation"
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ComfyExecutionError("image workflow manifest is missing; compile workflows first")
    manifest = identity.read_json(manifest_path)
    route = next((item for item in manifest.get("routes", []) if item.get("name") == route_name), None)
    if not route:
        raise ComfyExecutionError(f"unknown image workflow route: {route_name}")
    if route.get("status") != "compiled":
        reason = route.get("reason", "")
        if "winner not promoted" in reason or route_name in {"subject_lora", "lora_plus_native_reference"}:
            raise ComfyExecutionError(
                f"no promoted image identity LoRA; route {route_name} is {route.get('status')}: {reason}"
            )
        raise ComfyExecutionError(f"image workflow route {route_name} is {route.get('status')}: {reason}")
    graph_path = Path(route["path"])
    if not graph_path.is_file():
        raise ComfyExecutionError(f"compiled graph is missing: {graph_path}")
    graph = identity.read_json(graph_path)
    validate_api_graph(graph)
    staging = identity.read_json(Path(manifest["staging_manifest"]))
    staged = {item["staged_filename"]: item for item in staging.get("records", [])}
    referenced = [node["inputs"]["image"] for node in graph.values()
                  if node.get("class_type") == "LoadImage" and "image" in node.get("inputs", {})]
    missing_inputs = [name for name in referenced if name not in staged]
    if missing_inputs:
        raise ComfyExecutionError(f"graph references unstaged inputs: {missing_inputs}")
    stale_inputs = []
    for name in referenced:
        item = staged[name]
        path = Path(item["staged"])
        expected_staged = item.get("staged_sha256", item["source_sha256"])
        if not path.is_file() or identity.sha256_file(path) != expected_staged:
            stale_inputs.append(name)
    if stale_inputs:
        raise ComfyExecutionError(f"staged graph inputs failed hash validation: {stale_inputs}")
    missing_models = [name for name in route.get("required_models", []) if not _model_exists(name)]
    if missing_models:
        raise ComfyExecutionError(f"required ComfyUI model files are missing: {missing_models}")
    # A model listed in required_models is not evidence of consumption by
    # itself. Require each declaration to be bound to a concrete loader/control
    # node in the submitted API graph before runtime execution is allowed.
    model_inputs = {
        str(value)
        for node in graph.values()
        for key, value in node.get("inputs", {}).items()
        if key in {"unet_name", "clip_name", "vae_name", "lora_name", "pulid_file",
                   "model_name", "checkpoint_name", "control_net_name"}
        and isinstance(value, str)
    }
    unbound_models = [name for name in route.get("required_models", [])
                      if str(name) not in model_inputs]
    if unbound_models:
        raise ComfyExecutionError(f"required ComfyUI models are not bound to graph nodes: {unbound_models}")
    return {"manifest": manifest, "route": route, "graph": graph,
            "required_node_types": sorted({node["class_type"] for node in graph.values()}),
            "referenced_inputs": referenced, "missing_models": missing_models,
            "bound_models": sorted(model_inputs)}


def execute(project_root: Path, route_name: str, *, server_url: str = "http://127.0.0.1:8188",
            timeout_seconds: int = 3600, poll_seconds: float = 2.0,
            prompt_override: str | None = None, negative_prompt_override: str | None = None,
            seed: int | None = None, filename_prefix: str | None = None) -> dict[str, Any]:
    """Execute one immutable compiled route.

    Evaluation callers may override only the prompt, negative prompt, seed, and
    output prefix.  The compiled graph on disk is never modified; the exact
    overrides are recorded in the execution manifest so a run is reproducible.
    """
    started_monotonic = time.monotonic()
    started_unix = time.time()
    contract = validate_execution_contract(project_root, route_name)
    base = server_url.rstrip("/")
    object_info = _json_request(f"{base}/object_info", timeout=15)
    available_nodes = set(object_info)
    missing_nodes = [name for name in contract["required_node_types"] if name not in available_nodes]
    if missing_nodes:
        raise ComfyExecutionError(f"ComfyUI node classes are unavailable: {missing_nodes}")
    upload_records = []
    graph = copy.deepcopy(contract["graph"])
    sampler = next((node for node in graph.values() if node.get("class_type") == "KSampler"), None)
    if not sampler:
        raise ComfyExecutionError("compiled graph has no KSampler node")
    positive_id = _upstream_text_node(graph, sampler.get("inputs", {}).get("positive"))
    negative_id = _upstream_text_node(graph, sampler.get("inputs", {}).get("negative"))
    if prompt_override is not None:
        if not positive_id:
            raise ComfyExecutionError("compiled graph has no generic positive CLIPTextEncode node")
        graph[positive_id]["inputs"]["text"] = prompt_override
    if negative_prompt_override is not None:
        if not negative_id:
            raise ComfyExecutionError("compiled graph has no generic negative CLIPTextEncode node")
        graph[negative_id]["inputs"]["text"] = negative_prompt_override
    if seed is not None:
        sampler["inputs"]["seed"] = int(seed)
    if filename_prefix is not None:
        safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename_prefix).strip("._")
        if not safe_prefix:
            raise ComfyExecutionError("filename prefix is empty after sanitization")
        save_nodes = [node for node in graph.values() if node.get("class_type") == "SaveImage"]
        if not save_nodes:
            raise ComfyExecutionError("compiled graph has no SaveImage node")
        for node in save_nodes:
            node["inputs"]["filename_prefix"] = safe_prefix
    input_names = {}
    for name in contract["referenced_inputs"]:
        source = Path(next(item["staged"] for item in identity.read_json(
            Path(contract["manifest"]["staging_manifest"])).get("records", [])
            if item["staged_filename"] == name))
        uploaded = _upload_image(f"{base}/upload/image", name, source)
        uploaded_name = str(uploaded["name"])
        if uploaded.get("subfolder"):
            uploaded_name = f"{uploaded['subfolder'].strip('/')}/{uploaded_name}"
        input_names[name] = uploaded_name
        upload_records.append({"requested": name, "response": uploaded,
                               "source_sha256": identity.sha256_file(source)})
    for node in graph.values():
        if node.get("class_type") == "LoadImage" and "image" in node.get("inputs", {}):
            node["inputs"]["image"] = input_names[node["inputs"]["image"]]
    queued = _json_request(f"{base}/prompt", method="POST", payload={"prompt": graph}, timeout=30)
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise ComfyExecutionError(f"ComfyUI did not return prompt_id: {queued}")
    deadline = time.monotonic() + timeout_seconds
    history: dict[str, Any] | None = None
    history_failures = 0
    while time.monotonic() < deadline:
        try:
            history = _json_request(f"{base}/history/{prompt_id}", timeout=15)
            history_failures = 0
        except ComfyExecutionError as error:
            history_failures += 1
            if history_failures >= 5:
                raise ComfyExecutionError(
                    f"ComfyUI became unreachable while waiting for prompt {prompt_id}: {error}"
                ) from error
            history = None
        if history and prompt_id in history:
            break
        time.sleep(poll_seconds)
    if not history or prompt_id not in history:
        raise ComfyExecutionError(f"ComfyUI timed out waiting for prompt {prompt_id}")
    record = history[prompt_id]
    if record.get("status", {}).get("status_str") == "error" or record.get("status", {}).get("completed") is False:
        raise ComfyExecutionError(f"ComfyUI execution failed for prompt {prompt_id}: {record.get('status')}")
    outputs = []
    for node_outputs in record.get("outputs", {}).values():
        for item in node_outputs.get("images", []):
            outputs.append(item)
    if not outputs:
        raise ComfyExecutionError(f"ComfyUI completed prompt {prompt_id} without image outputs")
    output_root = Path(project_root) / "build/workflows/image_ablation/executions"
    output_root.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for index, item in enumerate(outputs):
        suffix = Path(str(item.get("filename", ""))).suffix.lower() or ".bin"
        downloaded.append(_download_output(
            base, item, output_root / "outputs" / f"{route_name}_{prompt_id}_{index:02d}{suffix}"
        ))
    result = {"schema_version": 1, "status": "complete", "route": route_name,
              "prompt_id": prompt_id, "server": base, "outputs": outputs,
              "downloaded_outputs": downloaded,
              "uploaded_inputs": upload_records,
              "graph_sha256": identity.sha256_file(Path(contract["route"]["path"])),
              "prompt_override": prompt_override,
              "negative_prompt_override": negative_prompt_override,
              "seed": seed,
              "filename_prefix": filename_prefix,
              "started_at_unix": started_unix,
              "elapsed_seconds": round(time.monotonic() - started_monotonic, 3)}
    identity.write_json(output_root / f"{route_name}_{prompt_id}.json", result)
    return result
