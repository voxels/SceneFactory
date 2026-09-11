#!/usr/bin/env python3
"""Validate rigged USDZ and Gaussian-splat avatar artifacts by hash and structure."""

from __future__ import annotations

import zipfile
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import identity_pipeline as identity


REQUIRED_PLY_FIELDS = {
    "x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2",
    "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3",
}


def _ply_header(path: Path) -> tuple[int, set[str]]:
    header = bytearray()
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                raise ValueError("PLY header is truncated")
            header.extend(line)
            if line.strip() == b"end_header":
                break
            if len(header) > 1_000_000:
                raise ValueError("PLY header exceeds safety limit")
    text = header.decode("ascii", errors="strict")
    if not text.startswith("ply\n") or "format binary_little_endian 1.0" not in text:
        raise ValueError("Gaussian artifact is not binary little-endian PLY")
    count_line = next((line for line in text.splitlines() if line.startswith("element vertex ")), None)
    if not count_line:
        raise ValueError("PLY has no vertex element")
    count = int(count_line.split()[-1])
    fields = {line.split()[-1] for line in text.splitlines() if line.startswith("property ")}
    return count, fields


def _usd_text(mesh: Path) -> str:
    """Return a textual USD view, including binary USDC layers when usdcat exists."""
    with zipfile.ZipFile(mesh) as archive:
        layer = next((name for name in archive.namelist()
                      if name.lower().endswith((".usd", ".usda", ".usdc"))), None)
        if not layer:
            raise ValueError("USDZ contains no USD layer")
        raw = archive.read(layer)
    # USDA is directly inspectable. Binary USDC must be converted; decoding random
    # bytes would create false positives for token checks.
    if layer.lower().endswith((".usd", ".usda")):
        return raw.decode("utf-8", errors="strict")
    usdcat = Path("/opt/local/USD/bin/usdcat")
    if not usdcat.is_file():
        raise ValueError("binary USD layer requires /opt/local/USD/bin/usdcat for semantic validation")
    with tempfile.TemporaryDirectory(prefix="sfv4-usd-validate-") as tmp:
        source = Path(tmp) / layer.replace("/", "_")
        source.write_bytes(raw)
        result = subprocess.run([str(usdcat), str(source)], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ValueError(f"usdcat failed for binary USD layer: {result.stderr[-400:]}")
        return result.stdout


def validate(root: Path, *, require_voice: bool = False) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "avatar_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"avatar manifest is missing: {manifest_path}")
    manifest = identity.read_json(manifest_path)
    mesh = Path(manifest["mesh_usdz"]["path"])
    splat = Path(manifest["gaussian_splat"]["path"])
    for path, key in ((mesh, "mesh_usdz"), (splat, "gaussian_splat")):
        if not path.is_file():
            raise ValueError(f"avatar artifact is missing: {path}")
        digest = identity.sha256_file(path)
        if digest != manifest[key]["sha256"]:
            raise ValueError(f"avatar artifact hash mismatch: {path}")
    with zipfile.ZipFile(mesh) as archive:
        names = set(archive.namelist())
        if not any(name.endswith((".usd", ".usda", ".usdc")) for name in names):
            raise ValueError("USDZ contains no USD layer")
        if not any(name.lower().endswith((".jpg", ".jpeg", ".png", ".exr")) for name in names):
            raise ValueError("USDZ contains no texture/material image")
    usd = _usd_text(mesh)
    required_tokens = {
        "skeleton": ("Skeleton",),
        "blend_shapes": ("BlendShape",),
        "jawOpen": ("jawOpen",),
        "visemes": ("viseme_", "viseme"),
        "normals": ("normal", "normals"),
        "uvs": ("texCoord", "st"),
        "materials": ("material", "Material"),
    }
    missing_tokens = [name for name, alternatives in required_tokens.items()
                      if not any(token in usd for token in alternatives)]
    if missing_tokens:
        raise ValueError(f"USDZ semantic feature tokens missing: {missing_tokens}")
    rig = manifest.get("rig", {})
    if len(rig.get("bones", [])) < 4 or "jaw" not in rig.get("bones", []):
        raise ValueError("avatar manifest does not describe a facial skeleton")
    if len(rig.get("blend_shapes", [])) < 6 or not any(
            str(name).startswith("viseme_") for name in rig.get("blend_shapes", [])):
        raise ValueError("avatar manifest does not describe facial/viseme blend shapes")
    vertex_count, fields = _ply_header(splat)
    missing = sorted(REQUIRED_PLY_FIELDS - fields)
    if missing:
        raise ValueError(f"Gaussian PLY missing fields: {missing}")
    if vertex_count != int(manifest["gaussian_splat"]["vertex_count"]):
        raise ValueError("Gaussian PLY vertex count differs from manifest")
    voice = manifest.get("voice_viseme_timing", {})
    if require_voice and voice.get("status") != "complete":
        raise ValueError("voice/viseme timing is not complete")
    return {"status": "valid", "manifest": str(manifest_path), "mesh_usdz": str(mesh),
            "gaussian_splat": str(splat), "vertex_count": vertex_count,
            "voice_viseme_timing": voice.get("status", "unknown")}
