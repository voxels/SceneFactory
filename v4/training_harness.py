#!/usr/bin/env python3
"""Process, review, and select all Scene Factory v4 identity evidence."""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import shutil
import statistics
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import identity_pipeline as identity


def write_json(path: Path, value: Any) -> None:
    identity.write_json(path, value)


def ffmpeg_gray(path: Path, size: int = 64) -> bytes | None:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-vf", f"scale={size}:{size}:force_original_aspect_ratio=disable,format=gray",
             "-frames:v", "1", "-f", "rawvideo", "pipe:1"],
            check=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout if len(result.stdout) == size * size else None


def visual_metrics(path: Path, dimensions: Mapping[str, Any] | None = None) -> dict[str, Any]:
    dimensions = dict(dimensions or identity.image_dimensions(path))
    raw = ffmpeg_gray(path)
    if raw is None:
        return {**dimensions, "analysis_status": "decoder_unavailable"}
    values = list(raw)
    brightness = statistics.fmean(values)
    contrast = statistics.pstdev(values)
    size = int(math.sqrt(len(values)))
    laplacian = []
    for y in range(1, size - 1):
        row = y * size
        for x in range(1, size - 1):
            center = values[row + x]
            laplacian.append(abs(4 * center - values[row + x - 1] - values[row + x + 1] - values[row - size + x] - values[row + size + x]))
    sharpness = statistics.fmean(laplacian) if laplacian else 0.0
    bits = []
    for y in [round(index * (size - 1) / 7) for index in range(8)]:
        xs = [round(index * (size - 1) / 8) for index in range(9)]
        bits.extend(values[y * size + xs[index]] > values[y * size + xs[index + 1]] for index in range(8))
    dhash = sum(int(bit) << index for index, bit in enumerate(bits))
    return {
        **dimensions,
        "analysis_status": "complete",
        "brightness": round(brightness, 4),
        "contrast": round(contrast, 4),
        "sharpness": round(sharpness, 4),
        "dhash64": f"{dhash:016x}",
    }


def audio_metrics(path: Path, transcript_words: int | None = None) -> dict[str, Any]:
    sample_rate = 16000
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1"],
            check=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {"analysis_status": "decoder_unavailable"}
    samples = array.array("h")
    samples.frombytes(result.stdout)
    if not samples:
        return {"analysis_status": "empty_audio"}
    if __import__("sys").byteorder != "little":
        samples.byteswap()
    count = len(samples)
    peak = max(abs(value) for value in samples)
    rms = math.sqrt(sum(float(value) * float(value) for value in samples) / count)
    duration = count / sample_rate
    value = {
        "analysis_status": "complete",
        "decoded_sample_rate": sample_rate,
        "decoded_channels": 1,
        "sample_count": count,
        "duration_seconds": round(duration, 6),
        "peak_dbfs": round(20 * math.log10(max(1.0, peak) / 32768), 4),
        "rms_dbfs": round(20 * math.log10(max(1.0, rms) / 32768), 4),
        "clipping_fraction": round(sum(abs(sample) >= 32760 for sample in samples) / count, 8),
        "silence_fraction": round(sum(abs(sample) <= 327 for sample in samples) / count, 8),
        "dc_offset": round(statistics.fmean(samples) / 32768, 8),
    }
    if transcript_words is not None and duration > 0:
        value["transcript_words"] = transcript_words
        value["estimated_words_per_minute"] = round(transcript_words * 60 / duration, 4)
    return value


def audio_quality_assessment(metrics: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    if metrics.get("analysis_status") != "complete":
        return ["audio_decode_failed"]
    reasons = []
    if float(metrics.get("duration_seconds", 0)) < float(policy["audio_minimum_duration_seconds"]):
        reasons.append("duration_below_minimum")
    if float(metrics.get("clipping_fraction", 1)) > float(policy["audio_maximum_clipping_fraction"]):
        reasons.append("excessive_clipping")
    if float(metrics.get("silence_fraction", 1)) > float(policy["audio_maximum_silence_fraction"]):
        reasons.append("excessive_silence")
    return reasons


def quality_assessment(metrics: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[float, list[str]]:
    reasons = []
    width = int(metrics.get("width") or 0)
    height = int(metrics.get("height") or 0)
    contrast = float(metrics.get("contrast") or 0)
    sharpness = float(metrics.get("sharpness") or 0)
    brightness = float(metrics.get("brightness") or 0)
    low_brightness, high_brightness = policy["brightness_range"]
    if width < int(policy["minimum_width"]):
        reasons.append("width_below_minimum")
    if height < int(policy["minimum_height"]):
        reasons.append("height_below_minimum")
    if contrast < float(policy["minimum_contrast"]):
        reasons.append("contrast_below_minimum")
    if sharpness < float(policy["minimum_sharpness"]):
        reasons.append("sharpness_below_minimum")
    if brightness < float(low_brightness):
        reasons.append("too_dark")
    if brightness > float(high_brightness):
        reasons.append("too_bright")
    megapixels = width * height / 1_000_000
    score = min(30.0, 10.0 * math.log2(max(1.0, megapixels + 1.0)))
    score += min(25.0, contrast / 2.5)
    score += min(30.0, sharpness * 1.5)
    score += max(0.0, 15.0 - abs(brightness - 128.0) / 8.0)
    return round(score, 4), reasons


def extract_video_frames(asset: Mapping[str, Any], destination: Path, count: int) -> list[dict[str, Any]]:
    duration = float(asset.get("metadata", {}).get("format", {}).get("duration") or 0)
    if duration <= 0:
        return []
    results = []
    for index in range(count):
        timestamp = duration * (index + 1) / (count + 1)
        output = destination / f"{asset['asset_id']}__{index + 1:02d}.jpg"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                 "-ss", f"{timestamp:.6f}", "-i", asset["path"], "-map", "0:v:0",
                 "-frames:v", "1", "-an", "-q:v", "2", str(output)],
                check=True, capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            continue
        digest = identity.sha256_file(output)
        results.append({
            "asset_id": f"video_frame__{asset['asset_id']}__{index + 1:02d}__{digest[:12]}",
            "kind": "image",
            "modality": "captured_video_frames",
            "path": str(output.resolve()),
            "sha256": digest,
            "bytes": output.stat().st_size,
            "derived_from": [asset["asset_id"]],
            "group_id": asset.get("group_id", f"source_asset:{asset['asset_id']}"),
            "timestamp_seconds": round(timestamp, 6),
            "roles": list(asset.get("roles", [])),
            "usage_roles": list(asset.get("usage_roles", [])),
            "training_policy": "derive_then_review",
            "provenance": "sampled_user_video_frame",
        })
    return results


def extract_usdz_textures(asset: Mapping[str, Any], destination: Path) -> list[dict[str, Any]]:
    results = []
    try:
        with zipfile.ZipFile(asset["path"]) as archive:
            for member in asset.get("metadata", {}).get("texture_members", []):
                data = archive.read(member)
                digest = identity.sha256_bytes(data)
                suffix = Path(member).suffix.lower() or ".bin"
                output = destination / f"{digest}{suffix}"
                output.parent.mkdir(parents=True, exist_ok=True)
                if not output.exists() or identity.sha256_file(output) != digest:
                    output.write_bytes(data)
                results.append({
                    "asset_id": f"usdz_texture__{asset['asset_id']}__{digest[:12]}",
                    "kind": "image",
                    "modality": "three_dimensional_capture_textures",
                    "path": str(output.resolve()),
                    "sha256": digest,
                    "bytes": len(data),
                    "derived_from": [asset["asset_id"]],
                    "group_id": asset.get("group_id", f"source_asset:{asset['asset_id']}"),
                    "member": member,
                    "roles": ["surface_texture_reference", "scan_cross_check"],
                    "training_policy": "conditioning_only",
                    "provenance": "usdz_embedded_texture",
                })
    except (OSError, KeyError, zipfile.BadZipFile):
        return []
    return results


def deduplicate(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hash: dict[str, dict[str, Any]] = {}
    for record in records:
        existing = by_hash.get(record["sha256"])
        if existing is None:
            record["derived_from"] = list(record.get("derived_from", []))
            by_hash[record["sha256"]] = record
        else:
            for source in record.get("derived_from", []):
                if source not in existing["derived_from"]:
                    existing["derived_from"].append(source)
    return sorted(by_hash.values(), key=lambda item: item["asset_id"])


def process(project_root: Path, *, run_mode: str | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    mode = run_mode or config["run_mode"]
    manifest, characteristics = identity.build(project_root, extract_web_media=True, run_mode=mode)
    policy = config["selection_policy"]
    output_root = project_root / "build" / "identity"
    processed_root = output_root / "processed"

    direct_visuals = [dict(item) for item in manifest["assets"] if item["kind"] == "image"]
    web_visuals = [dict(item) for item in manifest["derived_review_candidates"]]
    video_frames = []
    for asset in manifest["assets"]:
        if asset["kind"] == "video":
            video_frames.extend(extract_video_frames(asset, processed_root / "video_frames", int(policy["video_frames_per_source"])))
    usdz_textures = []
    for asset in manifest["assets"]:
        if asset["kind"] == "geometry":
            usdz_textures.extend(extract_usdz_textures(asset, processed_root / "usdz_textures"))
    derived_visuals = deduplicate([*web_visuals, *video_frames, *usdz_textures])
    visuals = [*direct_visuals, *derived_visuals]
    for item in visuals:
        item["visual_metrics"] = visual_metrics(Path(item["path"]), item.get("metadata"))
        score, reasons = quality_assessment(item["visual_metrics"], policy)
        item["quality_score"] = score
        item["quality_rejections"] = reasons
        item["automatic_quality_pass"] = not reasons

    transcripts = [item for item in manifest["assets"] if item["kind"] == "transcript"]
    transcript_words = sum(int(item.get("metadata", {}).get("words") or 0) for item in transcripts)
    audio_analysis = []
    for item in manifest["assets"]:
        if item["kind"] != "audio":
            continue
        metrics = audio_metrics(Path(item["path"]), transcript_words if transcript_words else None)
        rejections = audio_quality_assessment(metrics, policy)
        audio_analysis.append({
            "asset_id": item["asset_id"],
            "path": item["path"],
            "sha256": item["sha256"],
            "metrics": metrics,
            "quality_rejections": rejections,
            "automatic_quality_pass": not rejections,
            "transcript_asset_ids": [entry["asset_id"] for entry in transcripts],
        })

    matched = {Path(item["path"]).resolve() for item in manifest["assets"]}
    source_root = Path(manifest["source_root"])
    ignored = []
    unmatched = []
    ignore_globs = config.get("ignore_globs", [])
    for path in sorted(item for item in source_root.rglob("*") if item.is_file()):
        if path.resolve() in matched:
            continue
        relative = path.relative_to(source_root).as_posix()
        if any(path.match(pattern) or Path(relative).match(pattern) for pattern in ignore_globs):
            ignored.append({"path": str(path.resolve()), "relative_path": relative, "reason": "configured_ignore"})
        else:
            unmatched.append({"path": str(path.resolve()), "relative_path": relative, "suffix": path.suffix.lower()})

    processed = {
        "schema_version": 4,
        "run_mode": mode,
        "generated_at": manifest["generated_at"],
        "identity_id": manifest["identity_id"],
        "source_root": manifest["source_root"],
        "source_inventory": manifest["inventory"],
        "visuals": visuals,
        "audio_analysis": audio_analysis,
        "audio_transcript_pairing": {
            "audio_asset_ids": [item["asset_id"] for item in manifest["assets"] if item["kind"] == "audio"],
            "transcript_asset_ids": [item["asset_id"] for item in transcripts],
            "status": "ready_for_review" if audio_analysis and transcripts else "incomplete",
        },
        "derived_counts": {
            "webarchive_images": len(web_visuals),
            "video_frames": len(video_frames),
            "usdz_textures": len(usdz_textures),
            "unique_derived_visuals": len(derived_visuals),
        },
        "ignored_files": ignored,
        "unmatched_files": unmatched,
    }
    write_json(output_root / "processed_manifest.json", processed)
    return manifest, characteristics, processed


def hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def near_duplicate_clusters(records: list[dict[str, Any]], maximum_distance: int) -> list[list[dict[str, Any]]]:
    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(records)):
        left_hash = records[left]["visual_metrics"].get("dhash64")
        if not left_hash:
            continue
        for right in range(left + 1, len(records)):
            right_hash = records[right]["visual_metrics"].get("dhash64")
            if right_hash and hamming(left_hash, right_hash) <= maximum_distance:
                union(left, right)
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[find(index)].append(record)
    return list(groups.values())


def coverage_constrained_select(
    records: list[dict[str, Any]],
    annotations: Mapping[str, Mapping[str, Any]],
    captions: Mapping[str, Mapping[str, Any]],
    maximum: int,
) -> list[dict[str, Any]]:
    """Round-robin semantic strata so one framing/source type cannot dominate."""
    strata: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        annotation = annotations.get(item["asset_id"], {})
        shot = str(annotation.get("shot_size", "undetermined"))
        viewpoint = facial_viewpoint(annotation)
        body_visibility = "body_pose" if annotation.get("body_poses") else "face_only"
        provenance = "archived_web" if item.get("provenance") == "extracted_webarchive_media" else "direct_or_video"
        strata[(shot, viewpoint, body_visibility, provenance)].append(item)
    for key in strata:
        strata[key].sort(key=lambda item: (
            -float(captions.get(item["asset_id"], {}).get("clean_shot_score", 0)),
            -float(item.get("quality_score", 0)), item["asset_id"],
        ))
    selected = []
    keys = sorted(strata)
    while keys and len(selected) < maximum:
        remaining = []
        for key in keys:
            if len(selected) >= maximum:
                break
            if strata[key]:
                selected.append(strata[key].pop(0))
            if strata[key]:
                remaining.append(key)
        keys = remaining
    return selected


def _landmark_centroid(face: Mapping[str, Any], name: str) -> tuple[float, float] | None:
    region = next((item for item in face.get("landmarks", []) if item.get("name") == name), None)
    points = (region or {}).get("points", [])
    if not points:
        return None
    return (
        statistics.fmean(float(item["x"]) for item in points),
        statistics.fmean(float(item["y"]) for item in points),
    )


def facial_viewpoint(annotation: Mapping[str, Any]) -> str:
    """Estimate coarse yaw from deterministic Vision eye/nose landmarks."""
    faces = annotation.get("face_landmarks", [])
    if not faces:
        return "undetermined"
    face = faces[0]
    left = _landmark_centroid(face, "left_eye")
    right = _landmark_centroid(face, "right_eye")
    nose = _landmark_centroid(face, "nose")
    if not left or not right or not nose:
        return "undetermined"
    eye_min, eye_max = sorted((left[0], right[0]))
    width = eye_max - eye_min
    if width <= 0.02:
        return "profile_or_occluded"
    normalized = (nose[0] - eye_min) / width
    if 0.38 <= normalized <= 0.62:
        return "frontal"
    if -0.15 <= normalized <= 1.15:
        return "left_three_quarter" if normalized < 0.5 else "right_three_quarter"
    return "profile"


def group_safe_splits(records: list[dict[str, Any]], policy: Mapping[str, Any]) -> dict[str, str]:
    """Assign deterministic held-out groups and guarantee all splits when possible."""
    groups = sorted(
        {item.get("group_id", f"source_sha256:{item['sha256']}") for item in records},
        key=lambda value: hashlib.sha256(value.encode()).hexdigest(),
    )
    if len(groups) < 4:
        return {group: "train" for group in groups}
    remaining = len(groups)
    counts: dict[str, int] = {}
    for split, key in (
        ("final_test", "final_test_fraction"),
        ("calibration", "calibration_fraction"),
        ("validation", "validation_fraction"),
    ):
        count = max(1, round(len(groups) * float(policy[key])))
        count = min(count, remaining - (3 - len(counts)))
        counts[split] = count
        remaining -= count
    assignments: dict[str, str] = {}
    offset = 0
    for split in ("final_test", "calibration", "validation"):
        for group in groups[offset:offset + counts[split]]:
            assignments[group] = split
        offset += counts[split]
    for group in groups[offset:]:
        assignments[group] = "train"
    return assignments


def load_or_create_reviews(output_root: Path, records: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    path = output_root / "review_manifest.json"
    previous = {}
    if path.is_file():
        previous = {item["asset_id"]: item for item in identity.read_json(path).get("records", [])}
    values = []
    for record in records:
        old = previous.get(record["asset_id"], {})
        decision = old.get("decision", "pending")
        if decision not in {"pending", "approved", "rejected"}:
            decision = "pending"
        dataset_split = old.get("dataset_split")
        if dataset_split not in {None, "train", "validation", "calibration", "final_test"}:
            dataset_split = None
        notes = old.get("notes", [])
        if not isinstance(notes, list):
            notes = [str(notes)]
        kind = record["kind"]
        checks = ["correct_gage_subject", "source_permission", "hash_unchanged"]
        if kind == "image":
            checks.extend(["identity_visible", "no_unrelated_people", "quality_acceptable", "split_assignment_acceptable"])
        elif kind == "audio":
            checks.extend(["correct_voice", "transcript_alignment_verified", "prosody_approved", "no_unrelated_speaker", "audio_quality_acceptable"])
        elif kind == "transcript":
            checks.extend(["spoken_content_approved", "pause_markers_verified"])
        elif kind == "geometry":
            checks.extend(["scan_belongs_to_gage", "coordinate_scale_verified", "head_or_body_role_verified"])
        elif kind == "video":
            checks.extend(["motion_use_approved", "frame_samples_reviewed"])
        elif kind in {"webarchive", "document"}:
            checks.extend(["page_belongs_to_gage_source_set", "embedded_media_provenance_reviewed"])
        values.append({
            "asset_id": record["asset_id"],
            "kind": kind,
            "modality": record["modality"],
            "path": record["path"],
            "sha256": record["sha256"],
            "required_checks": checks,
            "decision": decision,
            "dataset_split": dataset_split,
            "notes": notes,
            "reviewed_by": old.get("reviewed_by"),
            "reviewed_at": old.get("reviewed_at"),
        })
    result = {"schema_version": 4, "generated_at": generated_at, "records": sorted(values, key=lambda item: item["asset_id"])}
    write_json(path, result)
    return result


def select(project_root: Path, *, run_mode: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    mode = run_mode or config["run_mode"]
    if mode not in {"automatic", "fine_tuning"}:
        raise ValueError("run_mode must be automatic or fine_tuning")
    fine_tuning = mode == "fine_tuning"
    manifest, characteristics, processed = process(project_root, run_mode=mode)
    output_root = project_root / "build" / "identity"
    all_reviewable = [*manifest["assets"], *manifest["derived_review_candidates"]]
    processed_ids = {item["asset_id"] for item in all_reviewable}
    all_reviewable.extend(item for item in processed["visuals"] if item["asset_id"] not in processed_ids)
    reviews = load_or_create_reviews(output_root, all_reviewable, manifest["generated_at"])
    decisions = {item["asset_id"]: item["decision"] for item in reviews["records"]}
    annotation_path = output_root / "annotation_manifest.json"
    annotation_manifest = identity.read_json(annotation_path) if annotation_path.is_file() else None
    annotation_by_id = {
        item["asset_id"]: item for item in (annotation_manifest or {}).get("records", [])
    }
    caption_path = output_root / "caption_manifest.json"
    caption_manifest = identity.read_json(caption_path) if caption_path.is_file() else None
    caption_by_id = {item["asset_id"]: item for item in (caption_manifest or {}).get("records", [])}

    visual_candidates = [
        item for item in processed["visuals"]
        if item["training_policy"] in {"direct_after_review", "derive_then_review"}
        and (
            item.get("provenance") != "sampled_user_video_frame"
            or any(role in {"visual_identity", "both"} for role in item.get("usage_roles", []))
        )
        and item["automatic_quality_pass"]
        and annotation_by_id.get(item["asset_id"], {}).get("identity_pass") is True
        and item["asset_id"] in caption_by_id
        and (not fine_tuning or decisions.get(item["asset_id"], "pending") != "rejected")
    ]

    def authority(item: Mapping[str, Any]) -> int:
        if item["modality"] == "portrait_photography":
            return 50
        if item["modality"] in {"video_contact_images", "captured_video_frames"}:
            return 40
        if item["modality"] == "archived_web_evidence":
            return 30
        return 20

    exact_best: dict[str, dict[str, Any]] = {}
    for item in visual_candidates:
        current = exact_best.get(item["sha256"])
        if current is None or (authority(item), item["quality_score"], item["asset_id"]) > (authority(current), current["quality_score"], current["asset_id"]):
            exact_best[item["sha256"]] = item
    exact_unique = list(exact_best.values())
    clusters = near_duplicate_clusters(exact_unique, int(config["selection_policy"]["near_duplicate_hamming_distance"]))
    representatives = [max(cluster, key=lambda item: (authority(item), item["quality_score"], item["asset_id"])) for cluster in clusters]
    representatives = coverage_constrained_select(
        representatives, annotation_by_id, caption_by_id,
        int(config["selection_policy"]["maximum_visual_training_images"]),
    )
    split_assignments = group_safe_splits(representatives, config["selection_policy"])
    selections = []
    for item in representatives:
        group_id = item.get("group_id", f"source_sha256:{item['sha256']}")
        split = split_assignments[group_id]
        review_decision = decisions.get(item["asset_id"], "pending") if fine_tuning else None
        selections.append({
            "asset_id": item["asset_id"],
            "path": item["path"],
            "sha256": item["sha256"],
            "group_id": group_id,
            "quality_score": item["quality_score"],
            "modality": item["modality"],
            "provenance": item.get("provenance", "user_supplied_source"),
            "split": split,
            "review_decision": review_decision,
            "status": ("selected" if review_decision == "approved" else "provisionally_selected") if fine_tuning else "automatically_selected",
            "eligible_for_export": not fine_tuning or review_decision == "approved",
            "annotation": {
                "identity_embedding": annotation_by_id[item["asset_id"]]["identity_embedding"],
                "person_mask": annotation_by_id[item["asset_id"]]["person_mask"],
                "face_crop": annotation_by_id[item["asset_id"]]["face_crop"],
                "shot_size": annotation_by_id[item["asset_id"]]["shot_size"],
                "viewpoint": facial_viewpoint(annotation_by_id[item["asset_id"]]),
                "body_pose_count": len(annotation_by_id[item["asset_id"]].get("body_poses", [])),
            },
            "caption": caption_by_id[item["asset_id"]],
        })
    approved = [item for item in selections if item["eligible_for_export"]]
    pending_selected = [item for item in selections if fine_tuning and item["review_decision"] == "pending"]
    consent_verified = config["identity"]["consent"]["status"] == "verified"
    audio_present = any(item["kind"] == "audio" for item in manifest["assets"])
    transcript_present = any(item["kind"] == "transcript" for item in manifest["assets"])
    audio_quality_pass = bool(processed["audio_analysis"]) and all(item["automatic_quality_pass"] for item in processed["audio_analysis"])
    required_nonvisual_ids = [
        item["asset_id"] for item in manifest["assets"]
        if item["kind"] in {"geometry", "audio", "transcript"}
    ]
    pending_required_nonvisual = [asset_id for asset_id in required_nonvisual_ids if fine_tuning and decisions.get(asset_id) != "approved"]
    has_approved_train = any(item["split"] == "train" for item in approved)
    has_approved_validation = any(item["split"] == "validation" for item in approved)
    has_approved_calibration = any(item["split"] == "calibration" for item in approved)
    has_approved_final_test = any(item["split"] == "final_test" for item in approved)
    caption_coverage_complete = bool(annotation_by_id) and all(
        item["asset_id"] in caption_by_id for item in annotation_by_id.values() if item.get("identity_pass")
    )
    safety_ready = consent_verified
    if fine_tuning:
        final_ready = bool(approved) and has_approved_train and has_approved_validation and has_approved_calibration and has_approved_final_test and caption_coverage_complete and not pending_selected and not pending_required_nonvisual and safety_ready and audio_present and transcript_present and audio_quality_pass and not processed["unmatched_files"]
    else:
        final_ready = bool(approved) and has_approved_train and has_approved_validation and has_approved_calibration and has_approved_final_test and caption_coverage_complete and safety_ready and not processed["unmatched_files"]
    selection = {
        "schema_version": 4,
        "run_mode": mode,
        "generated_at": manifest["generated_at"],
        "identity_id": manifest["identity_id"],
        "policy": config["selection_policy"],
        "counts": {
            "identity_annotated": len(annotation_by_id),
            "identity_annotation_pass": sum(item.get("identity_pass") is True for item in annotation_by_id.values()),
            "semantic_captioned": len(caption_by_id),
            "quality_pass_visual_candidates": len(visual_candidates),
            "exact_unique_images": len(exact_unique),
            "near_duplicate_clusters": len(clusters),
            "selected": len(selections),
            "export_eligible_selected": len(approved),
            "pending_selected": len(pending_selected),
            "train": sum(item["split"] == "train" for item in selections),
            "validation": sum(item["split"] == "validation" for item in selections),
            "calibration": sum(item["split"] == "calibration" for item in selections),
            "final_test": sum(item["split"] == "final_test" for item in selections),
        },
        "selections": selections,
        "derived_candidates_requiring_review": [item["asset_id"] for item in processed["visuals"] if fine_tuning and item["provenance"] != "user_supplied_source" and item["automatic_quality_pass"]],
        "near_duplicate_clusters": [[item["asset_id"] for item in cluster] for cluster in clusters if len(cluster) > 1],
        "ready_for_training": final_ready,
        "blockers": ([
            *([] if annotation_manifest else ["identity annotation manifest is missing"]),
            *([] if caption_manifest else ["semantic caption manifest is missing"]),
            *([] if not caption_manifest or caption_coverage_complete else ["semantic caption coverage is incomplete"]),
            *([] if consent_verified else ["consent is not verified"]),
            *([] if audio_present else ["generated voice audio has not been supplied"]),
            *([] if not audio_present or audio_quality_pass else ["generated voice audio failed automatic quality checks"]),
            *([] if transcript_present else ["voice transcript is missing"]),
            *([] if approved else ["no provisionally selected visual assets have been approved"]),
            *([] if not pending_selected else [f"{len(pending_selected)} selected visual assets still need approval or rejection"]),
            *([] if has_approved_train else ["approved selection has no training split"]),
            *([] if has_approved_validation else ["approved selection has no validation split"]),
            *([] if has_approved_calibration else ["approved selection has no calibration split"]),
            *([] if has_approved_final_test else ["approved selection has no final-test split"]),
            *([] if not pending_required_nonvisual else [f"{len(pending_required_nonvisual)} required geometry/audio/transcript assets still need approval"]),
            *([] if not processed["unmatched_files"] else ["unmatched source files remain"]),
        ] if fine_tuning else [
            *([] if consent_verified else ["consent is not verified"]),
            *([] if annotation_manifest else ["identity annotation manifest is missing"]),
            *([] if caption_manifest else ["semantic caption manifest is missing"]),
            *([] if not caption_manifest or caption_coverage_complete else ["semantic caption coverage is incomplete"]),
            *([] if approved else ["automatic selection produced no usable visual assets"]),
            *([] if has_approved_train else ["automatic selection has no training split"]),
            *([] if has_approved_validation else ["automatic selection has no validation split"]),
            *([] if has_approved_calibration else ["automatic selection has no calibration split"]),
            *([] if has_approved_final_test else ["automatic selection has no final-test split"]),
            *([] if not processed["unmatched_files"] else ["unmatched source files remain"]),
        ]),
        "warnings": ([] if fine_tuning else [
            *([] if audio_present else ["voice channel is empty; the run completed with available modalities"]),
            *([] if not audio_present or audio_quality_pass else ["voice audio failed quality checks and was excluded from automatic conditioning"]),
        ]),
    }
    write_json(output_root / "selection_manifest.json", selection)

    conditioning = {
        "schema_version": 4,
        "run_mode": mode,
        "generated_at": manifest["generated_at"],
        "identity_id": manifest["identity_id"],
        "channels": {
            "visual_identity": {"selection_manifest": str((output_root / "selection_manifest.json").resolve()), "selected_asset_ids": [item["asset_id"] for item in approved]},
            "person_masks": {"asset_ids": [item["asset_id"] for item in annotation_by_id.values() if item.get("identity_pass") and item.get("person_mask")], "annotation_manifest": str(annotation_path.resolve())},
            "body_pose": {"asset_ids": [item["asset_id"] for item in annotation_by_id.values() if item.get("identity_pass") and item.get("body_poses")], "annotation_manifest": str(annotation_path.resolve())},
            "semantic_captions": {"asset_ids": list(sorted(caption_by_id)), "caption_manifest": str(caption_path.resolve())},
            "webarchive_derivatives": {"asset_ids": [item["asset_id"] for item in manifest["derived_review_candidates"]], "requires_review": fine_tuning},
            "motion": {"source_asset_ids": [item["asset_id"] for item in manifest["assets"] if item["kind"] == "video" and any(role in {"motion_reference", "both"} for role in item.get("usage_roles", []))], "frame_asset_ids": [item["asset_id"] for item in processed["visuals"] if item["provenance"] == "sampled_user_video_frame" and any(role in {"motion_reference", "both"} for role in item.get("usage_roles", []))], "skeleton_manifest": str((output_root / "motion/skeleton_manifest.json").resolve()) if (output_root / "motion/skeleton_manifest.json").is_file() else None},
            "geometry": {"native_usdz_asset_ids": [item["asset_id"] for item in manifest["assets"] if item["kind"] == "geometry"], "texture_asset_ids": [item["asset_id"] for item in processed["visuals"] if item["provenance"] == "usdz_embedded_texture"]},
            "voice": {"audio_asset_ids": [item["asset_id"] for item in manifest["assets"] if item["kind"] == "audio"], "transcript_asset_ids": [item["asset_id"] for item in manifest["assets"] if item["kind"] == "transcript"], "scope": "voice_and_performance_only"},
        },
        "fusion_invariants": ["Gage-only evidence", "native USDZ geometry remains separate", "audio cannot alter visual identity", "duplicates cannot cross dataset splits", *( ["derived images require review"] if fine_tuning else ["quality-passing derived images are selected automatically"] )],
    }
    write_json(output_root / "conditioning_manifest.json", conditioning)
    return selection, conditioning


def decide(
    project_root: Path,
    asset_id: str,
    decision: str,
    *,
    reviewer: str,
    note: str | None = None,
    dataset_split: str | None = None,
) -> dict[str, Any]:
    if decision not in {"approved", "rejected", "pending"}:
        raise ValueError("decision must be approved, rejected, or pending")
    if dataset_split not in {None, "train", "validation"}:
        raise ValueError("dataset_split must be train or validation")
    project_root = project_root.resolve()
    review_path = project_root / "build" / "identity" / "review_manifest.json"
    if not review_path.is_file():
        select(project_root)
    review = identity.read_json(review_path)
    record = next((item for item in review["records"] if item["asset_id"] == asset_id), None)
    if record is None:
        raise ValueError(f"Unknown review asset: {asset_id}")
    if decision == "approved" and record["kind"] == "image" and dataset_split is None:
        selection_path = project_root / "build" / "identity" / "selection_manifest.json"
        selection = identity.read_json(selection_path)
        selected = next((item for item in selection["selections"] if item["asset_id"] == asset_id), None)
        if selected is None:
            raise ValueError("An image can be approved for training only when it is in the current selection manifest")
        dataset_split = selected["split"]
    record["decision"] = decision
    record["dataset_split"] = dataset_split if decision == "approved" else None
    record["reviewed_by"] = reviewer if decision != "pending" else None
    record["reviewed_at"] = identity.now() if decision != "pending" else None
    if note:
        record.setdefault("notes", []).append(note)
    write_json(review_path, review)
    return record


def copy_verified(source: Path, destination: Path, expected_hash: str) -> dict[str, Any]:
    if identity.sha256_file(source) != expected_hash:
        raise ValueError(f"Source hash changed before export: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and identity.sha256_file(destination) != expected_hash:
        raise ValueError(f"Export destination already contains different data: {destination}")
    if not destination.exists():
        shutil.copy2(source, destination)
    return {"path": str(destination.resolve()), "sha256": expected_hash, "bytes": destination.stat().st_size}


def export_training_package(project_root: Path, destination: Path, *, run_mode: str | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    destination = destination.resolve()
    selection, conditioning = select(project_root, run_mode=run_mode)
    fine_tuning = selection["run_mode"] == "fine_tuning"
    if not selection["ready_for_training"]:
        raise ValueError("Training package is not ready: " + "; ".join(selection["blockers"]))
    output_root = project_root / "build" / "identity"
    manifest = identity.read_json(output_root / "asset_manifest.json")
    reviews = identity.read_json(output_root / "review_manifest.json")
    review_by_id = {item["asset_id"]: item for item in reviews["records"]}
    exported_visuals = []
    for item in selection["selections"]:
        if not item["eligible_for_export"]:
            continue
        source = Path(item["path"])
        suffix = source.suffix.lower() or ".img"
        target = destination / "visual" / item["split"] / f"{item['asset_id']}{suffix}"
        copied = copy_verified(source, target, item["sha256"])
        exported_visuals.append({**item, "export": copied})

    exported_channels: dict[str, list[dict[str, Any]]] = {"geometry": [], "voice": [], "transcript": []}
    for asset in manifest["assets"]:
        if asset["kind"] not in {"geometry", "audio", "transcript"}:
            continue
        review = review_by_id.get(asset["asset_id"], {})
        if fine_tuning and review.get("decision") != "approved":
            raise ValueError(f"Required conditioning asset is not approved: {asset['asset_id']}")
        channel = "voice" if asset["kind"] == "audio" else asset["kind"]
        source = Path(asset["path"])
        target = destination / channel / f"{asset['asset_id']}{source.suffix.lower()}"
        copied = copy_verified(source, target, asset["sha256"])
        exported_channels[channel].append({"asset_id": asset["asset_id"], "roles": asset["roles"], "export": copied})

    package = {
        "schema_version": 4,
        "run_mode": selection["run_mode"],
        "generated_at": identity.now(),
        "identity_id": selection["identity_id"],
        "source_selection": str((output_root / "selection_manifest.json").resolve()),
        "source_conditioning": str((output_root / "conditioning_manifest.json").resolve()),
        "visual": exported_visuals,
        "channels": exported_channels,
        "invariants": conditioning["fusion_invariants"],
    }
    write_json(destination / "training_package.json", package)
    return package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="build, process, review-index, and select all identity evidence")
    run_parser.add_argument("project", type=Path)
    run_parser.add_argument("--mode", choices=["automatic", "fine_tuning"])
    decide_parser = subparsers.add_parser("decide", help="approve, reject, or reset one reviewed asset")
    decide_parser.add_argument("project", type=Path)
    decide_parser.add_argument("asset_id")
    decide_parser.add_argument("decision", choices=["approved", "rejected", "pending"])
    decide_parser.add_argument("--reviewer", required=True)
    decide_parser.add_argument("--note")
    decide_parser.add_argument("--split", choices=["train", "validation"])
    export_parser = subparsers.add_parser("export", help="emit a guarded, hash-verified training package")
    export_parser.add_argument("project", type=Path)
    export_parser.add_argument("destination", type=Path)
    export_parser.add_argument("--mode", choices=["automatic", "fine_tuning"])
    arguments = parser.parse_args(argv)
    if arguments.command == "decide":
        record = decide(
            arguments.project, arguments.asset_id, arguments.decision,
            reviewer=arguments.reviewer, note=arguments.note, dataset_split=arguments.split,
        )
        print(json.dumps(record, indent=2))
        return 0
    if arguments.command == "export":
        package = export_training_package(arguments.project, arguments.destination, run_mode=arguments.mode)
        print(json.dumps({"training_package": str((arguments.destination / "training_package.json").resolve()), "visual_count": len(package["visual"])}, indent=2))
        return 0
    selection, conditioning = select(arguments.project, run_mode=arguments.mode)
    print(json.dumps({
        "identity_id": selection["identity_id"],
        "counts": selection["counts"],
        "conditioning_channels": list(conditioning["channels"]),
        "ready_for_training": selection["ready_for_training"],
        "blockers": selection["blockers"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
