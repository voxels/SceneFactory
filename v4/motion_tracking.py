#!/usr/bin/env python3
"""Extract deterministic motion-reference frames, body skeletons, and tracks."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

import identity_annotations
import identity_pipeline as identity


ANALYZER_SOURCE = Path(__file__).parent / "tools/analyze_visual_frames.swift"


def _centroid(pose: dict[str, Any], minimum_confidence: float) -> tuple[float, float] | None:
    joints = [item for item in pose.get("joints", []) if float(item.get("confidence", 0)) >= minimum_confidence]
    if not joints:
        return None
    return (
        sum(float(item["x"]) for item in joints) / len(joints),
        sum(float(item["y"]) for item in joints) / len(joints),
    )


def _assign_tracks(frames: list[dict[str, Any]], minimum_confidence: float, maximum_distance: float) -> None:
    next_track_id = 0
    previous: dict[int, tuple[float, float]] = {}
    for frame in frames:
        detections = []
        for pose in frame.get("body_poses", []):
            center = _centroid(pose, minimum_confidence)
            if center is not None:
                detections.append((pose, center))
        candidates = sorted(
            (math.dist(center, old_center), index, track_id)
            for index, (_, center) in enumerate(detections)
            for track_id, old_center in previous.items()
            if math.dist(center, old_center) <= maximum_distance
        )
        assigned_detections: set[int] = set()
        assigned_tracks: set[int] = set()
        current: dict[int, tuple[float, float]] = {}
        for _, index, track_id in candidates:
            if index in assigned_detections or track_id in assigned_tracks:
                continue
            pose, center = detections[index]
            pose["track_id"] = track_id
            pose["centroid"] = [center[0], center[1]]
            assigned_detections.add(index)
            assigned_tracks.add(track_id)
            current[track_id] = center
        for index, (pose, center) in enumerate(detections):
            if index in assigned_detections:
                continue
            pose["track_id"] = next_track_id
            pose["centroid"] = [center[0], center[1]]
            current[next_track_id] = center
            next_track_id += 1
        previous = current


def track(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = identity.read_json(project_root / "identity.json")
    manifest, _ = identity.build(project_root, extract_web_media=False)
    policy = config.get("motion_processing", {
        "tracking_fps": 6, "maximum_frames_per_source": 360,
        "minimum_joint_confidence": 0.25, "maximum_track_centroid_distance": 0.2,
    })
    sources = [
        item for item in manifest["assets"]
        if item["kind"] == "video"
        and any(role in {"motion_reference", "both"} for role in item.get("usage_roles", []))
    ]
    output_root = project_root / "build/identity/motion"
    signature_payload = {
        "policy": policy,
        "analyzer_sha256": identity.sha256_file(ANALYZER_SOURCE),
        "sources": [{"asset_id": item["asset_id"], "sha256": item["sha256"], "group_id": item["group_id"]} for item in sources],
    }
    input_signature = identity.sha256_bytes(json.dumps(signature_payload, sort_keys=True).encode())
    manifest_path = output_root / "skeleton_manifest.json"
    if manifest_path.is_file():
        previous = identity.read_json(manifest_path)
        if previous.get("input_signature") == input_signature and all(Path(item["path"]).is_file() for item in previous.get("frames", [])):
            return previous

    analyzer = project_root / "build/bin/analyze-visual-frames"
    identity_annotations.compile_swift(ANALYZER_SOURCE, analyzer, ["Vision"])
    all_frames = []
    source_records = []
    fps = float(policy["tracking_fps"])
    maximum = int(policy["maximum_frames_per_source"])
    for source in sources:
        frame_root = output_root / "frames" / source["asset_id"]
        frame_root.mkdir(parents=True, exist_ok=True)
        for stale in frame_root.glob("frame_*.jpg"):
            stale.unlink()
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", source["path"],
            "-vf", f"fps={fps}", "-frames:v", str(maximum), "-q:v", "2", str(frame_root / "frame_%06d.jpg"),
        ], check=True)
        frames = []
        for index, path in enumerate(sorted(frame_root.glob("frame_*.jpg"))):
            record = {
                "asset_id": f"motion_frame__{source['asset_id']}__{index:06d}",
                "source_asset_id": source["asset_id"], "group_id": source["group_id"],
                "path": str(path.resolve()), "sha256": identity.sha256_file(path),
                "frame_index": index, "timestamp_seconds": round(index / fps, 6),
                "timecode_basis": {"type": "constant_rate_extraction", "fps": fps},
            }
            frames.append(record)
            all_frames.append({"asset_id": record["asset_id"], "path": record["path"]})
        source_records.append({
            "asset_id": source["asset_id"], "path": source["path"], "sha256": source["sha256"],
            "group_id": source["group_id"], "usage_roles": source["usage_roles"], "frame_count": len(frames),
        })
    inputs = output_root / "vision_inputs.json"
    report_path = output_root / "vision_report.json"
    identity.write_json(inputs, all_frames)
    subprocess.run([str(analyzer), str(inputs), str(report_path)], check=True)
    vision = identity.read_json(report_path)
    by_asset = {item["asset_id"]: item for item in vision["records"]}
    frame_records = []
    for item in all_frames:
        details = by_asset[item["asset_id"]]
        source_asset, index = item["asset_id"].removeprefix("motion_frame__").rsplit("__", 1)
        source = next(value for value in source_records if value["asset_id"] == source_asset)
        frame_records.append({
            **item, "sha256": identity.sha256_file(Path(item["path"])),
            "source_asset_id": source_asset, "group_id": source["group_id"],
            "frame_index": int(index), "timestamp_seconds": round(int(index) / fps, 6),
            "timecode_basis": {"type": "constant_rate_extraction", "fps": fps},
            "body_poses": details.get("body_poses", []), "face_landmarks": details.get("faces", []),
        })
    for source in source_records:
        source_frames = [item for item in frame_records if item["source_asset_id"] == source["asset_id"]]
        _assign_tracks(
            source_frames, float(policy["minimum_joint_confidence"]),
            float(policy["maximum_track_centroid_distance"]),
        )
    tracks: dict[str, list[dict[str, Any]]] = {}
    for frame in frame_records:
        for pose in frame["body_poses"]:
            if "track_id" not in pose:
                continue
            key = f"{frame['source_asset_id']}:{pose['track_id']}"
            root = next((item for item in pose["joints"] if item["name"] == "root"), None)
            tracks.setdefault(key, []).append({
                "frame_index": frame["frame_index"], "timestamp_seconds": frame["timestamp_seconds"],
                "centroid": pose["centroid"], "root": root,
            })
    result = {
        "schema_version": 4, "identity_id": manifest["identity_id"], "input_signature": input_signature,
        "policy": policy, "coordinate_space": vision["coordinate_space"],
        "sources": source_records,
        "counts": {"sources": len(source_records), "frames": len(frame_records), "frames_with_pose": sum(bool(item["body_poses"]) for item in frame_records), "tracks": len(tracks)},
        "frames": frame_records,
        "tracks": [{"track_id": key, "samples": value} for key, value in sorted(tracks.items())],
    }
    identity.write_json(manifest_path, result)
    return result
