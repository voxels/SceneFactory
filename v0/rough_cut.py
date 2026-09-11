import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Missing JSON file: {path}") from None


def select_clips(project_root, candidate=1, duration=5):
    build = project_root / "build"
    manifest = read_json(build / "generation_manifest.json")
    state = read_json(build / "execution" / "comfy_state.json")
    jobs = state.get("jobs", {})
    selected = []
    missing = []
    candidate_id = f"candidate_{candidate:02d}"

    for item in sorted(manifest.get("assembly", []), key=lambda value: value["order"]):
        job_id = (
            f"video__{item['scene_id']}__{item['shot_id']}__{item['formation_id']}"
            f"__{candidate_id}__{duration}s__portrait"
        )
        job = jobs.get(job_id, {})
        output = next(
            (Path(value) for value in job.get("outputs", []) if Path(value).suffix.lower() == ".mp4"),
            None,
        )
        if job.get("status") != "complete" or output is None or not output.is_file():
            missing.append({
                "order": item["order"],
                "scene_id": item["scene_id"],
                "shot_id": item["shot_id"],
                "formation_id": item["formation_id"],
                "job_id": job_id,
                "status": job.get("status", "not_started"),
            })
            continue
        selected.append({
            **item,
            "job_id": job_id,
            "source": str(output),
        })
    return selected, missing


def assemble(project_root, output=None, candidate=1, duration=5, allow_missing=False, ffmpeg="ffmpeg"):
    executable = shutil.which(ffmpeg)
    if executable is None:
        raise ValueError(f"FFmpeg executable was not found: {ffmpeg}")
    selected, missing = select_clips(project_root, candidate, duration)
    if missing and not allow_missing:
        first = missing[0]
        raise ValueError(
            f"{len(missing)} timeline clips are missing; first missing job: {first['job_id']}. "
            "Use --allow-missing for a partial cut."
        )
    if not selected:
        raise ValueError("No completed clips match the requested candidate and duration")

    output = output or (
        project_root / "build" / "rough_cut" / f"candidate_{candidate:02d}_{duration}s.mp4"
    )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    command = [executable, "-y"]
    filters = []
    concat_inputs = []
    for index, item in enumerate(selected):
        command.extend(["-i", item["source"]])
        trim = float(item["trim_duration_seconds"])
        filters.append(
            f"[{index}:v]trim=start=0:duration={trim:.6f},setpts=PTS-STARTPTS,"
            f"fps=24,scale=544:960:force_original_aspect_ratio=decrease,"
            f"pad=544:960:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p[v{index}]"
        )
        concat_inputs.append(f"[v{index}]")
    filters.append(f"{''.join(concat_inputs)}concat=n={len(selected)}:v=1:a=0[outv]")
    command.extend([
        "-filter_complex", ";".join(filters),
        "-map", "[outv]", "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-movflags", "+faststart", str(output),
    ])
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        raise ValueError(f"FFmpeg rough-cut assembly failed with exit code {error.returncode}") from None

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output": str(output),
        "candidate": candidate,
        "source_duration_seconds": duration,
        "timeline_clips": len(selected),
        "missing_clips": missing,
        "rough_cut_duration_seconds": round(
            sum(float(item["trim_duration_seconds"]) for item in selected), 6
        ),
        "clips": selected,
    }
    report_path = output.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report, report_path
