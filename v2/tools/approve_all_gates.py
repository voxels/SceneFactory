#!/usr/bin/env python3
"""Materialize an explicit user authorization across every current review gate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Record the user's explicit approval for candidate 1 at every gate."
    )
    parser.add_argument("project", type=Path)
    parser.add_argument("--authorization-note", required=True)
    arguments = parser.parse_args()
    project = arguments.project.resolve()
    storyboards = read_json(project / "build/storyboard_plan.json")["tasks"]
    videos = read_json(project / "build/scripted_clip_plan.json")["tasks"]
    recorded_at = datetime.now(timezone.utc).isoformat()
    selections = [{
        "storyboard_task_id": task["id"], "candidate": 1,
        "decision": "approved", "approved_by": "user", "issues": [],
        "recorded_at": recorded_at, "note": arguments.authorization_note,
    } for task in storyboards]
    approvals = [{
        "video_task_id": task["id"], "candidate": 1,
        "decision": "approved", "approved_by": "user", "issues": [],
        "extend": True, "recorded_at": recorded_at,
        "note": arguments.authorization_note,
    } for task in videos]
    write_json(project / "build/review/storyboard_selections.json", {
        "schema_version": 1, "selections": selections,
    })
    write_json(project / "build/review/motion_proof_reviews.json", {
        "schema_version": 1, "approvals": approvals,
    })
    print(json.dumps({
        "storyboard_approvals": len(selections),
        "motion_proof_extension_approvals": len(approvals),
        "candidate": 1,
    }, indent=2))


if __name__ == "__main__":
    main()
