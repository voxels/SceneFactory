#!/usr/bin/env python3
"""Build a reference set by comparing normalized face crops to one approved seed."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene_factory


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def edge_variance(path: Path) -> float:
    with Image.open(path) as image:
        edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
        return round(float(ImageStat.Stat(edges).var[0]), 3)


def rejection_reasons(
    *, distance: float | None, face_area: float, sharpness: float,
    identity_margin: float | None, isolated_path: str | None,
    distance_threshold: float, minimum_face_area: float,
    minimum_sharpness: float, minimum_identity_margin: float,
) -> list[str]:
    reasons = []
    if distance is None:
        reasons.append("no seed similarity score")
    elif distance > distance_threshold:
        reasons.append(f"seed distance {distance:.4f} exceeds {distance_threshold:.4f}")
    if face_area < minimum_face_area:
        reasons.append(f"face area {face_area:.4f} is below {minimum_face_area:.4f}")
    if sharpness < minimum_sharpness:
        reasons.append(f"face sharpness {sharpness:.2f} is below {minimum_sharpness:.2f}")
    if identity_margin is not None and identity_margin < minimum_identity_margin:
        reasons.append(
            f"identity margin {identity_margin:.4f} is below {minimum_identity_margin:.4f}"
        )
    if isolated_path is None:
        reasons.append("no isolated subject derivative")
    return reasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path, help="Scene Factory project folder")
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--seed")
    parser.add_argument("--source-folder", type=Path)
    parser.add_argument("--output-folder", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--distance-threshold", type=float)
    parser.add_argument("--minimum-face-area", type=float)
    parser.add_argument("--minimum-sharpness", type=float)
    parser.add_argument("--minimum-identity-margin", type=float)
    parser.add_argument("--reuse-isolation", action="store_true")
    arguments = parser.parse_args()
    project_root = arguments.project.resolve()
    project, _, content_root, variables = scene_factory.load_project(project_root)
    character = next(
        (item for item in project.get("characters", []) if item.get("id") == arguments.character_id),
        None,
    )
    if character is None:
        raise SystemExit(f"Unknown character ID: {arguments.character_id}")
    config_path = arguments.config.resolve() if arguments.config else (
        project_root / "characters" / f"{arguments.character_id}.identity-selection.json"
    )
    config = scene_factory.read_json(config_path) if config_path.is_file() else {}
    if config.get("character_id") not in {None, arguments.character_id}:
        raise SystemExit(f"Identity-selection config character does not match {arguments.character_id}")
    if arguments.source_folder:
        source_folder = arguments.source_folder.resolve()
    elif config.get("source_folder"):
        source_folder = scene_factory.resolve_pointer(content_root, config["source_folder"], variables)
    else:
        source_folder = scene_factory.resolve_pointer(
            content_root, character.get("source_folder", ""), variables
        )
    sources = sorted(source_folder.rglob("*"))
    sources = [path for path in sources if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    seed_value = arguments.seed or config.get("canonical_seed")
    if not seed_value:
        raise SystemExit(f"Choose --seed or set canonical_seed in {config_path}")
    seed_candidate = Path(seed_value).expanduser()
    seed = seed_candidate.resolve() if seed_candidate.is_absolute() else (source_folder / seed_candidate).resolve()
    if not seed.is_file():
        raise SystemExit(f"Canonical seed does not exist: {seed}")
    non_seed_sources = [path for path in sources if path.resolve() != seed.resolve()]
    if not non_seed_sources:
        raise SystemExit("Identity audit needs at least one non-seed training source")

    configured_output = config.get("output_folder", f"build/identity/{arguments.character_id}")
    output = arguments.output_folder.resolve() if arguments.output_folder else scene_factory.resolve_pointer(
        project_root, configured_output, variables
    )
    thresholds = {
        "maximum_seed_distance": 0.75,
        "minimum_face_area_fraction": 0.06,
        "minimum_edge_variance": 45.0,
        "minimum_multi_face_identity_margin": 0.08,
    }
    thresholds.update(config.get("thresholds", {}))
    cli_thresholds = {
        "maximum_seed_distance": arguments.distance_threshold,
        "minimum_face_area_fraction": arguments.minimum_face_area,
        "minimum_edge_variance": arguments.minimum_sharpness,
        "minimum_multi_face_identity_margin": arguments.minimum_identity_margin,
    }
    thresholds.update({key: value for key, value in cli_thresholds.items() if value is not None})
    maximum_matches = arguments.limit or int(config.get("maximum_matches", 12))
    identity_id = config.get("identity_id", character.get("identity_tag", arguments.character_id))
    isolation_root = output / "isolation"
    isolation_config_path = output / "isolation_config.json"
    write_json(isolation_config_path, {
        "identity_id": identity_id,
        "anchors": [str(seed)],
        "sources": [str(path) for path in sources],
        "output_root": str(isolation_root),
        "manual_face_overrides": config.get("manual_face_overrides", {}),
        "manual_person_overrides": config.get("manual_person_overrides", {}),
        "reject_person_isolation": config.get("reject_person_isolation", []),
    })
    report_path = isolation_root / "isolation_report.json"
    if not arguments.reuse_isolation or not report_path.is_file():
        isolator = Path(__file__).resolve().parents[1] / "bin/k-identity-isolator"
        subprocess.run([str(isolator), str(isolation_config_path)], check=True)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    ranked = []
    seed_face_crop = None
    for record in report["records"]:
        selected_id = record.get("selected_face_id")
        face = next((item for item in record.get("faces", []) if item["face_id"] == selected_id), None)
        if Path(record["source_path"]).resolve() == seed.resolve():
            if face is None:
                raise SystemExit("The canonical seed did not produce a selected normalized face crop")
            seed_face_crop = Path(face["crop_path"])
            continue
        if face is None:
            ranked.append({
                "source_path": record["source_path"], "eligible": False,
                "reason": "no automatically selected face", "warnings": record.get("warnings", []),
            })
            continue
        crop = Path(face["crop_path"])
        face_area = float(face["box"]["width"]) * float(face["box"]["height"])
        sharpness = edge_variance(crop)
        distance = face.get("median_distance")
        other_distances = sorted(
            item["median_distance"] for item in record.get("faces", [])
            if item["face_id"] != selected_id and item.get("median_distance") is not None
        )
        identity_margin = None
        if distance is not None and other_distances:
            identity_margin = other_distances[0] - distance
        reasons = rejection_reasons(
            distance=distance,
            face_area=face_area,
            sharpness=sharpness,
            identity_margin=identity_margin,
            isolated_path=record.get("isolated_path"),
            distance_threshold=thresholds["maximum_seed_distance"],
            minimum_face_area=thresholds["minimum_face_area_fraction"],
            minimum_sharpness=thresholds["minimum_edge_variance"],
            minimum_identity_margin=thresholds["minimum_multi_face_identity_margin"],
        )
        ranked.append({
            "source_path": record["source_path"],
            "source_sha256": record["source_sha256"],
            "eligible": not reasons,
            "rejection_reasons": reasons,
            "face_count": len(record.get("faces", [])),
            "face_area_fraction": round(face_area, 6),
            "seed_distance": distance,
            "identity_margin": identity_margin,
            "edge_variance": sharpness,
            "face_crop": str(crop),
            "isolated_subject": record.get("isolated_path"),
            "warnings": record.get("warnings", []),
        })
    ranked.sort(key=lambda item: (
        not item.get("eligible", False),
        item.get("seed_distance") is None,
        item.get("seed_distance", float("inf")),
        -item.get("face_area_fraction", 0),
        -item.get("edge_variance", 0),
    ))
    candidates = [item for item in ranked if item.get("eligible")][:maximum_matches]
    review_dir = output / "anchor_candidates"
    if review_dir.exists():
        shutil.rmtree(review_dir)
    review_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(candidates, 1):
        source = Path(item["face_crop"])
        destination = review_dir / f"{index:02d}__{Path(item['source_path']).stem}.png"
        shutil.copy2(source, destination)
        item["review_crop"] = str(destination)
    approved_dir = output / "approved_references"
    if approved_dir.exists():
        shutil.rmtree(approved_dir)
    approved_dir.mkdir(parents=True)
    if seed_face_crop is None:
        raise SystemExit("The isolation report does not contain the canonical seed")
    seed_approved_copy = approved_dir / f"00__{seed.stem}.png"
    shutil.copy2(seed_face_crop, seed_approved_copy)
    approved = [{
        "rank": 0,
        "role": "canonical_seed",
        "source_path": str(seed),
        "face_crop": str(seed_face_crop),
        "approved_copy": str(seed_approved_copy),
        "seed_distance": 0.0,
    }]
    for index, item in enumerate(candidates, 1):
        crop = Path(item["face_crop"])
        destination = approved_dir / f"{index:02d}__{Path(item['source_path']).stem}.png"
        shutil.copy2(crop, destination)
        approved.append({
            "rank": index,
            "role": "seed_similarity_match",
            "source_path": item["source_path"],
            "source_sha256": item["source_sha256"],
            "face_crop": item["face_crop"],
            "isolated_subject": item["isolated_subject"],
            "approved_copy": str(destination),
            "seed_distance": item["seed_distance"],
            "identity_margin": item["identity_margin"],
        })
    manifest_path = output / "selected_reference_manifest.json"
    write_json(manifest_path, {
        "schema_version": 1,
        "project_id": project.get("project", {}).get("id"),
        "character_id": arguments.character_id,
        "identity_id": identity_id,
        "canonical_seed": str(seed),
        "selection_method": "Apple Vision normalized face-crop feature-print distance to one user-approved seed",
        "thresholds": thresholds,
        "approved_references": approved,
    })
    summary = {
        "schema_version": 1,
        "method": "Apple Vision face detection and normalized face-crop feature-print distance to one canonical seed; lower distance is more similar",
        "canonical_seed": str(seed),
        "limitations": [
            "The canonical likeness is fixed by the user-selected seed; automatic scores only filter the remaining sources.",
            "Automated scores cannot decide whether expression, styling, lens distortion, or life-stage presentation should be learned as identity.",
        ],
        "counts": {
            "references": 1, "sources": len(non_seed_sources),
            "automatically_eligible": sum(bool(item.get("eligible")) for item in ranked),
            "review_candidates": len(candidates),
        },
        "selected_reference_manifest": str(manifest_path),
        "recommended_anchor_candidates": candidates,
        "all_sources": ranked,
    }
    summary_path = output / "identity_reference_audit.json"
    write_json(summary_path, summary)
    registry_path = project_root / "build/identity/selection_registry.json"
    registry = scene_factory.read_json(registry_path) if registry_path.is_file() else {
        "schema_version": 1, "characters": {}
    }
    registry.setdefault("characters", {})[arguments.character_id] = {
        "status": "seed_selected_and_similarity_filtered",
        "canonical_seed": str(seed),
        "manifest": str(manifest_path),
        "approved_reference_count": len(approved),
    }
    write_json(registry_path, registry)
    print(summary_path)


if __name__ == "__main__":
    main()
