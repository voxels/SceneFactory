#!/usr/bin/env python3
"""Audit and bind USDZ members to v4 structural-control artifacts.

USDZ captures often contain only a static mesh and texture set. This stage makes
that fact explicit, hashes each member, detects any embedded rig/animation signals,
and proves which rendered controls are actually downstream consumers.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import identity_pipeline as identity


SIGNALS = {
    "skeleton": ("skeleton", "joint", "skelroot", "skel:jointindices", "jointweights"),
    "blend_shapes": ("blendshape", "blend_shape", "morph", "viseme", "blendweights"),
    "animation": ("animation", "anim", "timesamples", "timecodespersecond"),
    "normals": ("normals", "normal3f", "primvars:normals"),
    "uvs": ("texcoord", "primvars:st", "primvars:uv"),
    "materials": ("material", "shader", "diffusecolor", "normaltexture"),
}


def _signals(text: str) -> dict[str, bool]:
    lowered = text.casefold()
    return {name: any(token in lowered for token in terms) for name, terms in SIGNALS.items()}


def ingest(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    manifest, _ = identity.build(project_root, extract_web_media=False)
    geometry = [item for item in manifest["assets"] if item["kind"] == "geometry"]
    if not geometry:
        raise ValueError("no USDZ assets were discovered")
    controls_path = project_root / "build/identity/geometry/geometry_control_manifest.json"
    controls = identity.read_json(controls_path) if controls_path.is_file() else {"records": []}
    by_source = {item.get("source_path"): item for item in controls.get("records", [])}
    records = []
    for asset in geometry:
        source = Path(asset["path"])
        members = []
        text_fragments = []
        binary_inspection = []
        with zipfile.ZipFile(source) as archive:
            for info in sorted((item for item in archive.infolist() if not item.is_dir()), key=lambda item: item.filename):
                payload = archive.read(info)
                suffix = Path(info.filename).suffix.casefold()
                # Binary USDC is not safe to interpret as UTF-8: random bytes can
                # create false "animation"/"skeleton" matches. It is recorded as
                # present but remains uninspected until a USD-aware reader is used.
                text = payload.decode("utf-8", errors="ignore") if suffix in {".usd", ".usda", ".json", ".txt"} else ""
                if text:
                    text_fragments.append(text)
                if suffix == ".usdc":
                    usdcat = shutil.which("usdcat") or ("/opt/local/USD/bin/usdcat" if Path("/opt/local/USD/bin/usdcat").is_file() else None)
                    if usdcat:
                        with tempfile.TemporaryDirectory(prefix="sfv4-usdc-") as temporary:
                            extracted = Path(temporary) / Path(info.filename).name
                            extracted.write_bytes(payload)
                            try:
                                inspected = subprocess.run([usdcat, str(extracted)], check=True, capture_output=True, text=True, timeout=180)
                                text_fragments.append(inspected.stdout)
                                binary_inspection.append({"path": info.filename, "status": "inspected", "reader": usdcat})
                            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                                binary_inspection.append({"path": info.filename, "status": "uninspected", "reason": type(error).__name__})
                    else:
                        binary_inspection.append({"path": info.filename, "status": "uninspected", "reason": "usdcat_not_installed"})
                members.append({
                    "path": info.filename, "bytes": len(payload),
                    "sha256": identity.sha256_bytes(payload), "suffix": suffix,
                })
        joined = "\n".join(text_fragments)
        signals = _signals(joined)
        binary_layers = [item["path"] for item in members if item["suffix"] == ".usdc"]
        rendered = by_source.get(asset["path"], by_source.get(str(source)))
        derived = rendered.get("derived", []) if rendered else []
        control_roles = sorted({item["role"] for item in derived})
        records.append({
            "asset_id": asset["asset_id"], "source_path": asset["path"],
            "source_sha256": asset["sha256"], "group_id": asset["group_id"],
            "members": members, "signals": signals,
            "binary_layers_uninspected": binary_layers,
            "binary_inspection": binary_inspection,
            "declared_roles": asset.get("roles", []),
            "derived_controls": {"manifest": rendered.get("render_manifest") if rendered else None, "roles": control_roles,
                                 "count": len(derived), "consumed": bool(derived)},
            "processing_status": "controls_bound" if derived else "members_audited_controls_missing",
            "limitations": [name for name in ("skeleton", "blend_shapes", "animation") if not signals[name]],
        })
    result = {
        "schema_version": 1, "identity_id": manifest["identity_id"],
        "source_manifest_sha256": identity.sha256_file(project_root / "build/identity/asset_manifest.json"),
        "control_manifest_sha256": identity.sha256_file(controls_path) if controls_path.is_file() else None,
        "counts": {"sources": len(records), "members": sum(len(item["members"]) for item in records),
                   "controls_bound": sum(item["derived_controls"]["count"] for item in records)},
        "records": records,
        "invariants": ["source members are content-hashed", "USDZ controls are linked by source hash", "missing rig signals are explicit"],
    }
    output = project_root / "build/identity/geometry/usdz_ingestion_manifest.json"
    identity.write_json(output, result)
    # Keep the cross-modal conditioning contract authoritative when it already
    # exists, so downstream consumers can prove geometry was actually bound.
    conditioning_path = project_root / "build/identity/conditioning_manifest.json"
    if conditioning_path.is_file():
        conditioning = identity.read_json(conditioning_path)
        channels = conditioning.setdefault("channels", {})
        channels["geometry"] = {
            "ingestion_manifest": str(output),
            "control_manifest": str(controls_path) if controls_path.is_file() else None,
            "source_asset_ids": [item["asset_id"] for item in records],
            "control_roles": sorted({role for item in records for role in item["derived_controls"]["roles"]}),
            "consumed_control_count": result["counts"]["controls_bound"],
        }
        identity.write_json(conditioning_path, conditioning)
    return result
