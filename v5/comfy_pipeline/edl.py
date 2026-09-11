"""Assembly EDL generation from shot + take manifests.

Mirrors the logic of assemble_reel.sh as data: ordered cut list, source take
file per shot, in/out durations, gate state. A missing take for any shot is
a hard, named failure — assembly is blocked until every shot has an accepted
take (accepted = identity-gated take with a user approval record).
"""

from __future__ import annotations

from .manifests import is_approved


def build_edl(shot_manifest: dict, take_records: list[dict]) -> dict:
    """Build the assembly edit decision list.

    take_records: take manifest records keyed by shot index (see
    manifests.build_take_record). Only takes with a user approval record
    count as accepted.

    Returns {"cuts": [...], "blocked": [...]}. A nonempty blocked list means
    assembly must not run; each entry names the shot and the reason.
    """
    by_shot = {}
    for take in take_records:
        shot_idx = take["shot"]
        # Keep the approved take when several exist for one shot.
        if shot_idx not in by_shot or (
            is_approved(take.get("review")) and not is_approved(by_shot[shot_idx].get("review"))
        ):
            by_shot[shot_idx] = take

    cuts = []
    blocked = []
    for event_id in sorted(shot_manifest["events"]):
        for shot in shot_manifest["events"][event_id]["shots"]:
            idx = shot["shot"]
            take = by_shot.get(idx)
            if take is None:
                blocked.append(
                    {"shot": idx, "event": shot["event"],
                     "reason": "no take recorded — gate failed or never ran"}
                )
                continue
            if not is_approved(take.get("review")):
                blocked.append(
                    {"shot": idx, "event": shot["event"],
                     "reason": f"take present but not user-approved "
                              f"(gate_verdict={take.get('gate_verdict')})"}
                )
                continue
            cuts.append(
                {
                    "shot": idx,
                    "event": shot["event"],
                    "start_sec": shot["start_sec"],
                    "duration_sec": shot["duration_sec"],
                    "source_take": f"take_{idx:03d}_{shot['event']}.mp4",
                    "gate_verdict": take.get("gate_verdict"),
                    "scale": "768x1344",
                }
            )
    cuts.sort(key=lambda c: c["shot"])
    return {
        "track": shot_manifest.get("track"),
        "track_sec": shot_manifest.get("track_sec"),
        "cuts": cuts,
        "blocked": blocked,
        "assembly_blocked": bool(blocked),
    }
