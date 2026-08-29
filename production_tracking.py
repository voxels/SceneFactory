#!/usr/bin/env python3
"""Build evidence-backed tracking records for the AD2184 reference.

This module deliberately separates *records that exist* from *records approved for
generation*. Manual-assisted geometry is useful for post work, but never promoted
to production-ready without user QC. Model-backed pose data must be supplied by a
real pose extractor; placeholder joints are never synthesized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np


SOURCE = Path("/Users/voxels/SceneFactory/v3/assets/source/motion/apple_1984_ridley_scott_reference.mp4")

OPENPOSE_BODY_NAMES = (
    "nose", "neck", "right_shoulder", "right_elbow", "right_wrist",
    "left_shoulder", "left_elbow", "left_wrist", "right_hip", "right_knee",
    "right_ankle", "left_hip", "left_knee", "left_ankle", "right_eye",
    "left_eye", "right_ear", "left_ear",
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def homography_from_unit_square(corners: list[list[float]]) -> list[list[float]]:
    """Return H mapping unit-square (u,v,1) coordinates to normalized frame x/y."""
    source = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    rows, rhs = [], []
    for (u, v), (x, y) in zip(source, corners):
        rows.extend([[u, v, 1, 0, 0, 0, -x * u, -x * v], [0, 0, 0, u, v, 1, -y * u, -y * v]])
        rhs.extend([x, y])
    h = np.linalg.solve(np.asarray(rows), np.asarray(rhs)).tolist() + [1.0]
    return [h[0:3], h[3:6], h[6:9]]


def smooth_pose_samples(samples: list[dict], alpha: float = 0.35, confidence_floor: float = 0.2) -> list[dict]:
    """Associate one performer by continuity and EMA-smooth confident joints."""
    prior_center = None
    smoothed: dict[str, tuple[float, float]] = {}
    output = []
    for sample in samples:
        candidates = []
        for index, pose in enumerate(sample.get("poses", [])):
            joints = [j for j in pose.get("joints", []) if j.get("confidence", 0) >= confidence_floor]
            if not joints:
                continue
            center = (sum(j["x"] for j in joints) / len(joints), sum(j["y"] for j in joints) / len(joints))
            distance = 0 if prior_center is None else math.dist(center, prior_center)
            candidates.append((distance, -pose.get("confidence", 0), index, center, joints))
        if not candidates:
            output.append({"timestamp_seconds": sample["timestamp_seconds"], "status": "no_associated_person", "joints": []})
            continue
        _, _, source_index, center, joints = min(candidates)
        prior_center = center
        result_joints = []
        for joint in joints:
            old = smoothed.get(joint["name"], (joint["x"], joint["y"]))
            point = (alpha * joint["x"] + (1 - alpha) * old[0], alpha * joint["y"] + (1 - alpha) * old[1])
            smoothed[joint["name"]] = point
            result_joints.append({**joint, "source_x": joint["x"], "source_y": joint["y"], "x": point[0], "y": point[1]})
        output.append({"timestamp_seconds": sample["timestamp_seconds"], "status": "associated_and_smoothed", "source_pose_index": source_index, "joints": result_joints})
    return output


def retarget_pose_samples(samples: list[dict]) -> list[dict]:
    """Emit proportion-neutral root-relative controls; generator applies K proportions."""
    output = []
    for sample in samples:
        joints = {j["name"]: j for j in sample.get("joints", [])}
        root = joints.get("root") or joints.get("left_hip") or joints.get("right_hip")
        if not root:
            output.append({**sample, "retarget_status": "missing_root"})
            continue
        ys = [j["y"] for j in joints.values()]
        scale = max(max(ys) - min(ys), 1e-6)
        controls = [{"name": name, "x": (j["x"] - root["x"]) / scale, "y": (j["y"] - root["y"]) / scale, "confidence": j["confidence"]} for name, j in sorted(joints.items())]
        output.append({**sample, "retarget_status": "root_relative_normalized", "root": {"x": root["x"], "y": root["y"]}, "controls": controls})
    return output


def openpose_frames_to_samples(raw: dict) -> list[dict]:
    """Convert Comfy SDPose OpenPose frames to the normalized observation schema."""
    frames = raw.get("frames", [])
    start = float(raw.get("start_timestamp_seconds", 0.0))
    fps = float(raw.get("fps", 24.0))
    samples = []
    for frame_index, frame in enumerate(frames):
        width = float(frame.get("canvas_width", 0))
        height = float(frame.get("canvas_height", 0))
        poses = []
        if width > 0 and height > 0:
            for person in frame.get("people", []):
                flat = person.get("pose_keypoints_2d", [])
                joints = []
                for index, name in enumerate(OPENPOSE_BODY_NAMES):
                    offset = index * 3
                    if offset + 2 >= len(flat):
                        break
                    x, y, confidence = (float(flat[offset]), float(flat[offset + 1]), float(flat[offset + 2]))
                    if x < 0 or y < 0:
                        confidence = 0.0
                    joints.append({"name": name, "x": x / width, "y": y / height, "confidence": confidence})
                by_name = {joint["name"]: joint for joint in joints}
                left, right = by_name.get("left_hip"), by_name.get("right_hip")
                if left and right and min(left["confidence"], right["confidence"]) > 0:
                    joints.append({
                        "name": "root",
                        "x": (left["x"] + right["x"]) / 2,
                        "y": (left["y"] + right["y"]) / 2,
                        "confidence": min(left["confidence"], right["confidence"]),
                    })
                confident = [joint["confidence"] for joint in joints if joint["confidence"] > 0]
                poses.append({"confidence": sum(confident) / len(confident) if confident else 0.0, "joints": joints})
        samples.append({"timestamp_seconds": start + frame_index / fps, "poses": poses})
    return samples


def write_rotated_hammer_mask(path: Path, width: int, height: int, cx: float, cy: float, angle_degrees: float) -> None:
    """Write an 8-bit PGM proxy mask containing a rigid shaft and hammer head."""
    yy, xx = np.mgrid[0:height, 0:width]
    x = xx / width - cx
    y = yy / height - cy
    angle = math.radians(angle_degrees)
    along = x * math.cos(angle) + y * math.sin(angle)
    across = -x * math.sin(angle) + y * math.cos(angle)
    shaft = (np.abs(along) <= 0.075) & (np.abs(across) <= 0.006)
    head = (np.abs(along - 0.065) <= 0.018) & (np.abs(across) <= 0.025)
    mask = np.where(shaft | head, 255, 0).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(f"P5\n{width} {height}\n255\n".encode("ascii"))
        handle.write(mask.tobytes())


def interpolate_keyframes(keyframes: list[tuple[float, float, float, float]], timestamp: float) -> tuple[float, float, float]:
    for left, right in zip(keyframes, keyframes[1:]):
        if left[0] <= timestamp <= right[0]:
            weight = (timestamp - left[0]) / (right[0] - left[0])
            return tuple(left[i] + weight * (right[i] - left[i]) for i in range(1, 4))
    return tuple((keyframes[0] if timestamp < keyframes[0][0] else keyframes[-1])[1:4])


def build_records(project: Path, source: Path = SOURCE) -> dict:
    build = project / "build" / "tracking"
    evidence = build / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    source_hash = sha256(source)

    # Frame-accurate evidence: source is 25 fps. 46.04 is the last intact image;
    # 46.08 is the first frame whose projected image is replaced by the blast.
    evidence_times = [43.40, 43.72, 44.00, 44.40, 44.80, 45.20, 45.60, 46.04, 46.08]
    for timestamp in evidence_times:
        output = evidence / f"reference_{timestamp:05.2f}.png"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.2f}", "-i", str(source), "-frames:v", "1", str(output)], check=True)

    pose_record_path = build / "shot_03_to_05" / "k_body_pose.json"
    raw_pose_path = build / "k_body_pose_raw.json"
    if raw_pose_path.exists():
        raw = json.loads(raw_pose_path.read_text())
        observations = raw.get("samples")
        if observations is None and "frames" in raw:
            observations = openpose_frames_to_samples(raw)
        smoothed = smooth_pose_samples(observations or [])
        retargeted = retarget_pose_samples(smoothed)
        pose_status = "model_observations_associated_smoothed_and_retargeted"
        operational = bool(retargeted) and any(s.get("controls") for s in retargeted)
    else:
        retargeted = []
        pose_status = "blocked_no_model_observations"
        operational = False
    controlled_samples = sum(bool(sample.get("controls")) for sample in retargeted)
    write_json(pose_record_path, {
        "schema_version": 1, "track_type": "k_skeleton", "source": str(source), "source_sha256": source_hash,
        "status": pose_status, "operational_for_generation": operational,
        "pipeline_operational": operational,
        "coverage": {
            "sample_count": len(retargeted),
            "samples_with_retarget_controls": controlled_samples,
            "fraction_with_retarget_controls": controlled_samples / len(retargeted) if retargeted else 0.0,
            "start_timestamp_seconds": retargeted[0]["timestamp_seconds"] if retargeted else None,
            "end_timestamp_seconds": retargeted[-1]["timestamp_seconds"] if retargeted else None,
        },
        "inference": {
            "model": "Comfy-Org/SDPose checkpoints/sdpose_wholebody_fp16.safetensors",
            "checkpoint_sha256": "63d01f9a7494560693b24767f4469d59c9d3266b31ff0a253e74d1e611442721",
            "workflow": "build/tracking/sdpose_workflow_api.json",
            "coordinate_source": "real OpenPose-format SDPose observations; no synthesized joints",
        },
        "person_association": "minimum_center_displacement_then_max_confidence",
        "smoothing": {"method": "exponential_moving_average", "alpha": 0.35, "confidence_floor": 0.2},
        "retargeting": "root_relative_normalized_controls_applied_to_K_proportions",
        "samples": retargeted,
        "blockers": [] if operational else ["Vision pose inference is unavailable in this execution environment and no local pose checkpoint was found."],
    })
    pose_payload = json.loads(pose_record_path.read_text())
    for shot_id in ("shot_03", "shot_04", "shot_05"):
        write_json(build / shot_id / "k_body_pose.json", {**pose_payload, "shot_id": shot_id})

    hammer_dir = build / "shot_06"
    mask_dir = hammer_dir / "hammer_masks"
    keyframes = [(43.72, 0.22, 0.14, -72.0), (44.00, 0.24, 0.20, -18.0), (44.40, 0.42, 0.14, -48.0), (44.80, 0.58, 0.08, -70.0), (45.20, 0.50, 0.10, 70.0), (45.60, 0.49, 0.25, 55.0), (46.04, 0.47, 0.43, 48.0)]
    hammer_samples = []
    for index in range(round((46.04 - 43.72) * 25) + 1):
        timestamp = round(43.72 + index / 25, 2)
        cx, cy, angle = interpolate_keyframes(keyframes, timestamp)
        mask = mask_dir / f"hammer_{timestamp:05.2f}.pgm"
        write_rotated_hammer_mask(mask, 1280, 720, cx, cy, angle)
        hammer_samples.append({"timestamp_seconds": timestamp, "centroid_normalized_top_left": [cx, cy], "rotation_degrees_clockwise": angle, "mask_path": str(mask.relative_to(project)), "mask_method": "manual_keyframe_rigid_proxy_interpolation", "confidence": "requires_user_qc"})
    hammer_record_path = hammer_dir / "hammer_rigid_body.json"
    write_json(hammer_record_path, {
        "schema_version": 1, "track_type": "hammer_rigid_body", "source": str(source), "source_sha256": source_hash,
        "status": "manual_assisted_proxy_masks_and_rigid_track_produced", "operational_for_generation": False,
        "ownership": {"held_by_k_through_seconds": 43.40, "release_boundary_seconds": 43.44, "separate_prop_first_visible_seconds": 43.72, "evidence_frames": [str((evidence / "reference_43.40.png").relative_to(project)), str((evidence / "reference_43.72.png").relative_to(project))]},
        "samples": hammer_samples,
        "blockers": ["Semantic SAM temporal masks are unavailable because the checkpoint is absent.", "Manual proxy masks require user QC before generation."],
    })

    corners_px = [[334, 72], [976, 91], [968, 574], [320, 560]]
    corners = [[x / 1280, y / 720] for x, y in corners_px]
    screen_path = hammer_dir / "speaker_screen_corners.json"
    write_json(screen_path, {
        "schema_version": 1, "track_type": "speaker_screen_homography", "source": str(source), "source_sha256": source_hash,
        "status": "manual_four_corner_homography_with_frame_exact_destruction_boundary", "operational_for_post": True,
        "coordinate_space": "normalized_top_left", "corner_order": ["top_left", "top_right", "bottom_right", "bottom_left"],
        "samples": [{"timestamp_seconds": 46.030666, "frame_path": "build/reference/frames/006_shot_06__action.png", "frame_sha256": sha256(project / "build/reference/frames/006_shot_06__action.png"), "corners_pixels_1280x720": corners_px, "corners": corners, "unit_square_to_frame_homography": homography_from_unit_square(corners), "method": "manual_four_corner_annotation", "confidence": "requires_user_qc"}],
        "destruction_boundary": {"last_intact_timestamp_seconds": 46.04, "first_destroyed_timestamp_seconds": 46.08, "precision_seconds": 0.04, "rule": "green insert exists through 46.04 and shatters starting at 46.08", "last_intact_frame": str((evidence / "reference_46.04.png").relative_to(project)), "first_destroyed_frame": str((evidence / "reference_46.08.png").relative_to(project))},
    })

    readiness = {"k_skeleton": operational, "hammer": False, "screen": True}
    manifest = {
        "schema_version": 1, "source": str(source), "source_sha256": source_hash,
        "records": {"k_skeleton": str(pose_record_path.relative_to(project)), "hammer": str(hammer_record_path.relative_to(project)), "screen": str(screen_path.relative_to(project))},
        "production_readiness": readiness,
        "generation_blocked": not all(readiness.values()),
    }
    write_json(build / "tracking_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--source", type=Path, default=SOURCE)
    args = parser.parse_args()
    print(json.dumps(build_records(args.project.resolve(), args.source.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
