#!/usr/bin/env python3
"""Build a provenance-complete, training-split-only identity reference bank."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

import identity_pipeline as identity


def _copy(source: Path, destination: Path, expected_hash: str | None = None) -> dict[str, Any]:
    actual = identity.sha256_file(source)
    if expected_hash and actual != expected_hash:
        raise ValueError(f"reference source hash changed: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and identity.sha256_file(destination) != actual:
        raise ValueError(f"reference destination collision: {destination}")
    if not destination.exists():
        shutil.copy2(source, destination)
    return {"path": str(destination.resolve()), "sha256": actual, "bytes": destination.stat().st_size}


def build(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    identity_root = project_root / "build/identity"
    selection = identity.read_json(identity_root / "selection_manifest.json")
    annotations = identity.read_json(identity_root / "annotation_manifest.json")
    annotation_by_id = {item["asset_id"]: item for item in annotations["records"]}
    candidates = [
        item for item in selection["selections"]
        if item["split"] == "train" and item.get("eligible_for_export")
    ]

    def view(item: dict[str, Any]) -> str:
        return str(item["annotation"].get("viewpoint", "undetermined"))

    def shot(item: dict[str, Any]) -> str:
        return str(item["annotation"].get("shot_size", "undetermined"))

    categories: list[tuple[str, Callable[[dict[str, Any]], bool], str]] = [
        ("canonical_frontal", lambda item: view(item) == "frontal" and shot(item) in {"close_up", "head_and_shoulders", "medium"}, "primary face identity"),
        ("left_three_quarter", lambda item: view(item) == "left_three_quarter", "left facial structure"),
        ("right_three_quarter", lambda item: view(item) == "right_three_quarter", "right facial structure"),
        ("profile", lambda item: view(item) in {"profile", "profile_or_occluded"}, "profile structure"),
        ("expression", lambda item: any(word in item["caption"].get("semantic_caption", "").lower() for word in ("smile", "laugh", "grin")), "expression variation; model-derived label"),
        ("full_body", lambda item: shot(item) == "wide_or_full_body", "body proportions"),
    ]
    used: set[str] = set()
    records = []
    gaps = []
    bank_root = identity_root / "reference_bank"
    for category, predicate, intended_use in categories:
        eligible = [item for item in candidates if item["asset_id"] not in used and predicate(item)]
        if not eligible:
            gaps.append(category)
            continue
        chosen = max(
            eligible,
            key=lambda item: (
                float(item["caption"].get("clean_shot_score", 0)),
                -float(item["annotation"]["identity_embedding"].get("median_distance") or 99),
                float(item.get("quality_score", 0)),
                item["asset_id"],
            ),
        )
        used.add(chosen["asset_id"])
        annotation = annotation_by_id[chosen["asset_id"]]
        asset_root = bank_root / "assets" / category
        original = _copy(Path(chosen["path"]), asset_root / ("original" + Path(chosen["path"]).suffix.lower()), chosen["sha256"])
        mask = _copy(Path(annotation["person_mask"]), asset_root / "person_mask.png", annotation.get("person_mask_sha256"))
        face = _copy(Path(annotation["face_crop"]), asset_root / ("face_crop" + Path(annotation["face_crop"]).suffix.lower()), annotation.get("face_crop_sha256"))
        alpha = None
        alpha_source = annotation.get("alpha_cutout")
        if alpha_source and Path(alpha_source).is_file():
            alpha = _copy(Path(alpha_source), asset_root / "alpha_cutout.png")
        records.append({
            "category": category,
            "asset_id": chosen["asset_id"],
            "group_id": chosen["group_id"],
            "split": chosen["split"],
            "intended_use": intended_use,
            "viewpoint": view(chosen),
            "shot_size": shot(chosen),
            "modality": chosen["modality"],
            "provenance": chosen["provenance"],
            "quality_score": chosen["quality_score"],
            "clean_shot_score": chosen["caption"].get("clean_shot_score"),
            "identity_embedding": annotation["identity_embedding"],
            "original": original,
            "person_mask": mask,
            "aligned_face_crop": face,
            "alpha_cutout": alpha,
        })
    result = {
        "schema_version": 4,
        "identity_id": selection["identity_id"],
        "status": "candidate_pending_heldout_generation_optimization",
        "selection_manifest_sha256": identity.sha256_file(identity_root / "selection_manifest.json"),
        "annotation_manifest_sha256": identity.sha256_file(identity_root / "annotation_manifest.json"),
        "invariants": ["training split only", "final-test and calibration assets excluded", "no synthetic USDZ appearance renders", "mask-derived alpha cutouts are available for reference conditioning"],
        "counts": {"references": len(records), "gaps": len(gaps)},
        "coverage_gaps": gaps,
        "records": records,
    }
    identity.write_json(bank_root / "reference_bank.json", result)
    return result
