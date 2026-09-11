#!/usr/bin/env python3
"""Render all configured USDZ captures into executable structural-control maps."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import identity_pipeline as identity


BLENDER = Path("/Applications/Blender.app/Contents/MacOS/blender")
RENDER_SCRIPT = Path(__file__).parent / "tools/render_usdz_blender.py"


def render(project_root: Path, *, size: int = 768) -> dict[str, Any]:
    project_root = project_root.resolve()
    manifest, _ = identity.build(project_root, extract_web_media=False)
    geometry = [item for item in manifest["assets"] if item["kind"] == "geometry"]
    if not geometry:
        raise ValueError("no USDZ geometry assets were discovered")
    if not BLENDER.is_file():
        raise ValueError(f"Blender is missing: {BLENDER}")
    output_root = project_root / "build/identity/geometry"
    records = []
    for asset in geometry:
        destination = output_root / asset["asset_id"]
        # Remove only files produced by this renderer so stale formats from an
        # earlier Blender API revision cannot leak into the manifest.
        for folder in ("rgb", "alpha", "silhouette", "depth_metric", "depth_normalized", "normals", "lineart"):
            generated_dir = destination / folder
            if generated_dir.is_dir():
                for generated in generated_dir.iterdir():
                    if generated.is_file():
                        generated.unlink()
        subprocess.run([
            str(BLENDER), "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(RENDER_SCRIPT), "--",
            asset["path"], str(destination), "--size", str(size),
        ], check=True)
        if not (destination / "render_manifest.json").is_file():
            raise RuntimeError(f"Blender did not produce a render manifest for {asset['asset_id']}")
        rendered = identity.read_json(destination / "render_manifest.json")
        required_png = ("alpha", "silhouette", "depth_normalized", "normals")
        for folder in required_png:
            if len(list((destination / folder).glob("*.png"))) != len(rendered["views"]):
                raise RuntimeError(f"Blender did not produce one PNG {folder} map per canonical view")
        derived = []
        for folder in ("rgb", "alpha", "silhouette", "depth_metric", "depth_normalized", "normals"):
            for path in sorted((destination / folder).glob("*")):
                if path.is_file():
                    derived.append({"role": folder, "path": str(path.resolve()), "sha256": identity.sha256_file(path), "bytes": path.stat().st_size})
        for silhouette in sorted((destination / "silhouette").glob("*.png")):
            edge = destination / "lineart" / silhouette.name
            edge.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(silhouette),
                "-vf", "edgedetect=low=0.05:high=0.15,format=gray", "-frames:v", "1", str(edge),
            ], check=True)
            derived.append({"role": "lineart", "path": str(edge.resolve()), "sha256": identity.sha256_file(edge), "bytes": edge.stat().st_size})
        records.append({
            "asset_id": asset["asset_id"], "source_path": asset["path"], "source_sha256": asset["sha256"],
            "group_id": asset["group_id"], "roles": asset["roles"], "render_manifest": str((destination / "render_manifest.json").resolve()),
            "mesh": rendered["mesh"], "renderer": rendered["renderer"], "views": rendered["views"], "derived": derived,
        })
    result = {
        "schema_version": 4, "identity_id": manifest["identity_id"], "renderer_script_sha256": identity.sha256_file(RENDER_SCRIPT),
        "counts": {"sources": len(records), "derived_controls": sum(len(item["derived"]) for item in records)}, "records": records,
    }
    identity.write_json(output_root / "geometry_control_manifest.json", result)
    return result
