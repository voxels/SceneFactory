# Execution Status

Specified 2026-08-29; Phase 1 status integration implemented 2026-08-31. The read-only reporter is wired into `scene_factory.py`, and `pipeline-status` now computes a read-only intake summary plus the execution rollup without rewriting `pipeline_state.json`.

Scene Factory owns production truth and gates. ComfyUI executes graphs. Status must be derived from Scene Factory records plus on-disk outputs. A live queue view is optional diagnostics. A process exit, a saved file, and a Comfy history row are not visual approval.

This spec is the next v3 compiler change after the [next-run playbook](18_NEXT_RUN_PLAYBOOK.md). It does not replace the reconstruction render queue in [render pipeline status](14_RENDER_PIPELINE_STATUS_2026-08-26.md).

## Observed split (2026-08-29)

Three independent surfaces already disagree on the same machine:

| Surface | What it reported | Writer |
|---|---|---|
| `examples/ad2184/build/pipeline_state.json` | Project `ad2184_v3_identity_fidelity`. `source_ingestion` blocked (`no source images`). Character sheets, storyboards, clips, sequences, and assembly hardcoded `blocked` with adapter-missing reasons. | `pipeline.refresh_state` via `prepare` / `pipeline-status` |
| `tools/run_comfy_phase.py examples/ad2184 all --candidate 1` | One runner posting graphs to ComfyUI. | Codex / operator |
| ComfyUI `GET /queue` | One running LTX I2V job writing `Ad2184_v2/generated/clips/scene_04/shot_04/frontal_run/candidate_01/5s`. Zero pending. | ComfyUI |

`examples/ad2184/build/execution/comfy_state.json` did not exist on the v3 tree while that job ran. `path_defaults.OUTPUT_ROOT` is `${PROJECT_ROOT}/outputs`. Comfy Desktop was writing `/Users/voxels/ComfyUI-Shared/output`. `pipeline-status` currently *writes* `pipeline_state.json`, so a status query can race a live `prepare`.

The playbook says Scene Factory owns durable status. Today it does not.

## Authority order

When records disagree, use this order. Do not invent a fourth database.

1. **User review JSON** — `decision`, `approved_by: user`, `issues: []`. Nothing else can mark a generated artifact approved.
2. **Compiled plans and graph manifest** — `build/character_sheet_plan.json`, `build/storyboard_plan.json`, `build/scripted_clip_plan.json`, `build/sequence_plan.json`, `build/generation_manifest.json`, `build/comfyui/full_visual_graph_manifest.json`. These define the job list.
3. **Runner job log** — `build/execution/comfy_state.json`. The runner may write this file. Status only reads it.
4. **Files named by that job log** — each path in `jobs[id].outputs`, plus staged keyframes. Existence and hash, not mtime.
5. **Optional live Comfy `GET /queue`** — overlay `running` / `queued` for prompt IDs already in the job log, or whose `filename_prefix` matches this project's output namespace. Never POST. Never treat Comfy history as the project database.

`OUTPUT_ROOT` is the project-declared delivery folder. It is not automatically where Comfy writes. Status must report both the configured `OUTPUT_ROOT` and the actual Comfy output paths from the graph prefix / job log.

Do not scan the entire Comfy shared output tree. One Comfy server is serving v2 and v3. Per-project status must not mix their files.

## Job states

Every compiled graph row becomes one execution job. Derived state is computed on read.

| State | Meaning |
|---|---|
| `not_compiled` | Plan exists, no graph row. |
| `graph_ready` | Graph row exists, no job log entry. |
| `queued` | Live queue overlay only: pending behind another prompt. |
| `running` | Job log `status=running`, or live queue has that `prompt_id`. |
| `failed` | Job log `status=failed`. |
| `output_missing` | Job log `status=complete` but a named output path is absent. |
| `output_present` | Named outputs exist. Not approved. |
| `approved` | `output_present` and a user approval record with empty issues. |
| `rejected` | User review `decision=rejected`. Output may still exist. |

`complete` is not a job state. Files on disk are `output_present`. Only user review can move a job to `approved`.

## Stage rollup

Map existing pipeline stages onto execution phases without renaming the intake stages.

| Pipeline stage | Graph source | Runner phase names today |
|---|---|---|
| `character_sheets` | `full_visual_graph_manifest.json` `character_sheets[]` | Adapter: `identity_candidates`. Runner: `identity_first_review` + `identity_expansion` |
| `storyboards` | `storyboards[]` | `storyboard_candidates` |
| `scripted_clips` | `videos[]` where `execution_phase=motion_proofs` | `motion_proofs` |
| `extended_sequences` | `videos[]` where `execution_phase=extended_clips` | `extended_clips` |
| `final_assembly` | `generation_manifest.json` `assembly[]` plus `build/rough_cut/` | `run_comfy_phase` rough-cut after `phase=all` |

Normalize runner aliases on read. Do not change `run_comfy_phase.py` while a job is in flight.

Stage status:

| Stage status | Rule |
|---|---|
| `blocked` | Required inputs missing (no plan, no graphs, missing staged keyframe, missing approval that the current review policy requires before this phase). List the actual missing ids. Do not use the frozen string `image execution adapter` if graphs already exist. |
| `ready` | Graphs exist, nothing running, required previous-stage approvals present, some jobs still `graph_ready`. |
| `active` | Any job `running` or `queued`. |
| `complete` | Every *required* job in the stage is `approved`. Optional expansion candidates may remain unapproved. |
| `failed` | A required job failed, or was rejected with no approved replacement. |
| `needs_approval` | Required outputs exist but do not yet have an issue-free user approval. |
| `not_started` | No jobs or graphs exist for the stage. |

Required vs optional follows the current review policy already encoded in `comfy_adapter.build_workflows`:

- Identity: `priority=first_review` (candidates 1–2) is required before storyboards start. Expansion candidates are optional coverage.
- Storyboards: no video graph exists until exactly one candidate is user-approved with zero issues (`build/review/storyboard_selections.json`).
- Motion proofs: one proof per approved storyboard.
- Extended clips: only if `build/review/motion_proof_reviews.json` has `extend: true` and user approval.
- Rough cut: one candidate, one duration, every assembly row has an `approved` clip, zero audio.

Intake stages (`source_ingestion` through `concept_datasets`) stay in `pipeline_state.json`. This spec does not retell caption review. It does require that generation-stage rows stop being hardcoded `blocked` once graphs or job-log entries exist.

## Read vs write

| Action | May write | Must not write |
|---|---|---|
| `execution-status` | Nothing required. Optional snapshot under `build/execution/status_snapshot.json` labeled `generated_at` and source file mtimes/hashes | `comfy_state.json`, Comfy queue, review JSON, plans, graphs, `OUTPUT_ROOT` media |
| `pipeline-status` after this ships | Nothing. Read-only. | `pipeline_state.json` |
| `prepare` | Intake catalogs, caption tasks, sheet/storyboard/clip/sequence *plans*, `pipeline_state.json` intake rows | Job log, Comfy outputs, approvals |
| `run_comfy_phase.py` | `build/execution/comfy_state.json` only | Approvals, pipeline_state generation rows |

Today `pipeline-status` calls `refresh_state`, which rewrites `pipeline_state.json`. That write is a bug relative to this spec. Fix it only after the live Codex jobs finish.

## Command

Available now without touching the Scene Factory CLI or the live runner:

```sh
python3 execution_status.py ./projects/PROJECT_ID
python3 execution_status.py ./projects/PROJECT_ID --live
```

`--live` only `GET`s `/queue`. It never posts. Default remains files-only.

Wired CLI:

```sh
./scene_factory.py execution-status ./projects/PROJECT_ID
./scene_factory.py execution-status ./projects/PROJECT_ID --live
```

`--live` may `GET http://127.0.0.1:8188/queue` (host/port overridable). If Comfy is down, report `live: unavailable` and continue from files. Timeout must be short (seconds, not the two-hour job timeout).

Print JSON. Minimum shape:

```json
{
  "schema_version": 1,
  "project_id": "ad2184_v3_identity_fidelity",
  "output_root": "/absolute/project/outputs",
  "comfy_output_namespace": "Ad2184_v3",
  "live": {"available": false},
  "counts": {
    "jobs": 0,
    "running": 0,
    "output_present": 0,
    "approved": 0,
    "failed": 0,
    "output_missing": 0
  },
  "stages": [
    {
      "id": "scripted_clips",
      "status": "active",
      "required": 7,
      "approved": 0,
      "running": ["video__scene_04__shot_04__frontal_run__candidate_01__5s__portrait"],
      "blockers": []
    }
  ],
  "jobs": []
}
```

Each job object: `id`, `stage`, `phase`, `state`, `prompt_id`, `output_prefix`, `outputs` (path, exists, sha256 if present), `review` (path, decision, approved_by, issues). Missing files are listed, not guessed.

`pipeline-status` prints intake stages plus this rollup. `execution-status` remains the detailed generation view.

## Files

| File | Role after this ships |
|---|---|
| `build/pipeline_state.json` | Intake stages only, written by `prepare` |
| `build/comfyui/full_visual_graph_manifest.json` | Compiled graphs and phase counts |
| `build/execution/comfy_state.json` | Runner job log |
| `build/execution/status_snapshot.json` | Optional derived snapshot from the last status command |
| `build/review/storyboard_selections.json` | Storyboard candidate approvals |
| `build/review/motion_proof_reviews.json` | Motion-proof approvals and extend flags |
| `reviews/episode_artifact_review.json` | Per-artifact review template; copy per delivered file |
| `build/rough_cut/*.mp4` and `*.json` | Assembly output; still needs user approval to enter the edit pool |

Add `schemas/execution.schema.json` for the status document. Do not reuse `pipeline.schema.json` status enum as-is: it allows `complete` without defining approval.

## Live-job safety

Until Codex v2/v3 asset jobs exit:

- Do not edit `tools/run_comfy_phase.py`, `comfy_adapter.py`, or `examples/ad2184/`.
- Do not POST to `/prompt` or change Comfy input/output directories.
- Do not call `comfy-build` (it rewrites graphs and can `prepare`).
- Do not run `tools/approve_all_gates.py` against a live project.
- A new `execution_status.py` that only reads JSON and `stat()`s named files is allowed after the jobs finish. Implementing it while the runner holds `comfy_state.json` is still a race if anyone else writes that file; wait.

## Implementation order

1. This document and playbook pointer.
2. Read-only `execution_status.py` plus fixture tests, no Comfy, no writes to the job log, no `scene_factory.py` edit. Done 2026-08-29 while v2/v3 Comfy jobs were still running.
3. Point `pipeline-status` at a read-only intake summary plus the execution rollup. Stop hardcoded `blocked` on generation stages when graphs exist. Done 2026-08-31.
4. Optional `--live`. Filter by this project's namespace and known `prompt_id`s. Done 2026-08-31.
5. Review Console Generation Queue and Gate Approvals screens consume this JSON. They do not query Comfy as authority.

## Acceptance

- Given a temp project with a graph manifest, a job log `complete` row, and a missing file, status is `output_missing`, not `approved` or pipeline `complete`.
- Given the same plus an on-disk file and no review JSON, status is `output_present`.
- Given a user approval with `approved_by: user` and empty issues, that job is `approved`.
- Given `approved_by` omitted or `issues` nonempty, the job is not `approved`.
- `execution-status` does not create or modify `comfy_state.json`.
- `pipeline-status` after step 3 does not rewrite `pipeline_state.json`.
- Two projects sharing one Comfy server do not appear in each other's job lists.
- A running Comfy prefix of `Ad2184_v2/...` does not mark a v3 stage `active` unless that job id is in the v3 job log or v3 graph namespace.

## Out of scope

- Genericizing `comfy_adapter.py` off Koleka paths.
- Changing isolation CLI defaults from `k0l3k4`.
- The reconstruction queue in `render_pipeline.py`.
- Building the Review Console.
- Treating `build/identity/` as `source_catalog.json`. That is a separate intake-status lie (`no source images` while identity audit folders exist) and must not be papered over here.

## Related pages

- [Next run playbook](18_NEXT_RUN_PLAYBOOK.md)
- [Complete production process](09_PRODUCTION_PROCESS.md)
- [Feature-episode production handbook](17_FEATURE_EPISODE_PRODUCTION_HANDBOOK.md)
- [Status and roadmap](07_STATUS_AND_ROADMAP.md)
