#!/usr/bin/env python3
"""Produce deterministic Apple Vision masks, face identity distances, landmarks, and skeletons."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

import identity_pipeline as identity
import training_harness as training


V4_ROOT = Path(__file__).parent.resolve()


def compile_swift(source: Path, output: Path, frameworks: list[str]) -> None:
    signature = identity.sha256_file(source)
    stamp = output.with_suffix(output.suffix + ".sha256")
    if output.is_file() and stamp.is_file() and stamp.read_text().strip() == signature:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    module_cache = output.parent / "swift-module-cache"
    module_cache.mkdir(parents=True, exist_ok=True)
    command = ["swiftc", "-module-cache-path", str(module_cache), str(source)]
    for framework in frameworks:
        command.extend(["-framework", framework])
    command.extend(["-o", str(output)])
    subprocess.run(command, check=True)
    stamp.write_text(signature + "\n")


def shot_size(face_area: float, pose_count: int) -> str:
    if face_area >= 0.18:
        return "close_up"
    if face_area >= 0.07:
        return "head_and_shoulders"
    if face_area >= 0.025:
        return "medium"
    if pose_count:
        return "wide_or_full_body"
    return "undetermined"


def annotate(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    manifest, _, processed = training.process(project_root)
    output_root = project_root / "build/identity/annotations"
    bin_root = project_root / "build/bin"
    isolator = bin_root / "k-identity-isolator"
    visual_analyzer = bin_root / "analyze-visual-frames"
    compile_swift(
        V4_ROOT.parent / "v3/tools/k_identity_isolator.swift",
        isolator,
        ["AppKit", "CoreImage", "Vision"],
    )
    compile_swift(V4_ROOT / "tools/analyze_visual_frames.swift", visual_analyzer, ["Vision"])

    candidates = [
        item for item in processed["visuals"]
        if item.get("automatic_quality_pass")
        and item.get("training_policy") in {"direct_after_review", "derive_then_review"}
        and item.get("provenance") != "usdz_embedded_texture"
        and (
            item.get("provenance") != "sampled_user_video_frame"
            or any(role in {"visual_identity", "both"} for role in item.get("usage_roles", []))
        )
    ]
    source_root = Path(manifest["source_root"])
    policy = config["identity_matching"]
    anchors = [(source_root / item).resolve() for item in policy["anchors"]]
    missing = [str(item) for item in anchors if not item.is_file()]
    if missing:
        raise ValueError(f"Configured identity anchors are missing: {missing}")

    annotation_manifest_path = project_root / "build/identity/annotation_manifest.json"
    signature_payload = {
        "schema_version": 4,
        "identity_id": manifest["identity_id"],
        "policy": policy,
        "anchors": [{"path": str(item), "sha256": identity.sha256_file(item)} for item in anchors],
        "candidates": [{"asset_id": item["asset_id"], "sha256": item["sha256"]} for item in candidates],
        "isolator_source_sha256": identity.sha256_file(V4_ROOT.parent / "v3/tools/k_identity_isolator.swift"),
        "visual_analyzer_source_sha256": identity.sha256_file(V4_ROOT / "tools/analyze_visual_frames.swift"),
    }
    input_signature = identity.sha256_bytes(
        json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    if annotation_manifest_path.is_file():
        existing = identity.read_json(annotation_manifest_path)
        referenced = [
            Path(path)
            for record in existing.get("records", [])
            for key in ("face_crop", "person_mask", "alpha_cutout", "review_overlay")
            if (path := record.get(key))
        ]
        artifact_set_complete = all(path.is_file() for path in referenced)
        legacy_inputs_match = (
            existing.get("policy") == policy
            and existing.get("anchors") == signature_payload["anchors"]
            and sorted((item["asset_id"], item["sha256"]) for item in existing.get("records", []))
            == sorted((item["asset_id"], item["sha256"]) for item in candidates)
        )
        if not existing.get("input_signature") and legacy_inputs_match and artifact_set_complete:
            existing["input_signature"] = input_signature
            identity.write_json(annotation_manifest_path, existing)
            return existing
        if existing.get("input_signature") == input_signature and artifact_set_complete:
            return existing

    isolation_config = {
        "identity_id": manifest["identity_id"],
        "anchors": [str(item) for item in anchors],
        "sources": [item["path"] for item in candidates],
        "output_root": str(output_root / "isolation"),
        "manual_face_overrides": {},
        "manual_person_overrides": {},
        "reject_person_isolation": [],
    }
    identity.write_json(output_root / "isolation_config.json", isolation_config)
    subprocess.run([str(isolator), str(output_root / "isolation_config.json")], check=True)
    frame_inputs = [{"asset_id": item["asset_id"], "path": item["path"]} for item in candidates]
    identity.write_json(output_root / "visual_inputs.json", frame_inputs)
    subprocess.run([str(visual_analyzer), str(output_root / "visual_inputs.json"), str(output_root / "vision_report.json")], check=True)

    isolation = identity.read_json(output_root / "isolation/isolation_report.json")
    vision = identity.read_json(output_root / "vision_report.json")
    candidate_by_path = {str(Path(item["path"]).resolve()): item for item in candidates}
    vision_by_path = {str(Path(item["path"]).resolve()): item for item in vision["records"]}
    records = []
    for isolated in isolation["records"]:
        path = str(Path(isolated["source_path"]).resolve())
        source = candidate_by_path[path]
        selected_id = isolated.get("selected_face_id")
        selected_face = next((item for item in isolated.get("faces", []) if item["face_id"] == selected_id), None)
        distance = selected_face.get("median_distance") if selected_face else None
        face_area = (selected_face["box"]["width"] * selected_face["box"]["height"]) if selected_face else 0.0
        other_distances = sorted(
            item["median_distance"] for item in isolated.get("faces", [])
            if item.get("face_id") != selected_id and item.get("median_distance") is not None
        )
        margin = (other_distances[0] - distance) if distance is not None and other_distances else None
        details = vision_by_path[path]
        reasons = []
        if selected_face is None:
            reasons.append("no_identity_face")
        if distance is None or distance > float(policy["maximum_anchor_distance"]):
            reasons.append("identity_distance_outlier")
        if face_area < float(policy["minimum_face_area_fraction"]):
            reasons.append("face_too_small_for_identity_training")
        if margin is not None and margin < float(policy["minimum_multi_face_identity_margin"]):
            reasons.append("ambiguous_multiple_people")
        if not isolated.get("mask_path"):
            reasons.append("subject_mask_missing")
        mask_path = isolated.get("mask_path")
        face_crop = selected_face.get("crop_path") if selected_face else None
        records.append({
            "asset_id": source["asset_id"],
            "path": path,
            "sha256": source["sha256"],
            "group_id": source.get("group_id", f"source_sha256:{source['sha256']}"),
            "provenance": source.get("provenance"),
            "modality": source["modality"],
            "identity_embedding": {"type": "apple_vision_feature_print_distance_vector", "anchor_paths": [str(item) for item in anchors], "distances": selected_face.get("anchor_distances", []) if selected_face else [], "median_distance": distance},
            "identity_margin": margin,
            "identity_pass": not reasons,
            "rejection_reasons": reasons,
            "face_count": len(isolated.get("faces", [])),
            "face_area_fraction": round(face_area, 8),
            "face_crop": face_crop,
            "face_crop_sha256": identity.sha256_file(Path(face_crop)) if face_crop and Path(face_crop).is_file() else None,
            "person_mask": mask_path,
            "person_mask_sha256": identity.sha256_file(Path(mask_path)) if mask_path and Path(mask_path).is_file() else None,
            "alpha_cutout": isolated.get("isolated_path"),
            "review_overlay": isolated.get("overlay_path"),
            "selected_person_instance": isolated.get("selected_person_instance"),
            "face_landmarks": details.get("faces", []),
            "body_poses": details.get("body_poses", []),
            "shot_size": shot_size(face_area, len(details.get("body_poses", []))),
            "annotation_versions": {
                "mask_and_identity": isolation["segmenter"] + "; " + isolation["identity_matcher"],
                "face_landmarks": vision["face_detector"],
                "body_pose": vision["body_detector"],
            },
        })
    result = {
        "schema_version": 4,
        "input_signature": input_signature,
        "identity_id": manifest["identity_id"],
        "coordinate_space": vision["coordinate_space"],
        "policy": policy,
        "anchors": [{"path": str(item), "sha256": identity.sha256_file(item)} for item in anchors],
        "counts": {"candidates": len(records), "identity_pass": sum(item["identity_pass"] for item in records), "rejected": sum(not item["identity_pass"] for item in records)},
        "records": records,
    }
    identity.write_json(annotation_manifest_path, result)
    return result
