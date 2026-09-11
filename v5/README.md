# Scene Factory v5 — the stabilized API, clean-installed

v5 is a clean version of Scene Factory built **only** on the stabilized API
surface as defined by the repo's own docs. It is not a new feature branch;
it is the stable core, isolated from version sprawl, with the execution-status
truth fix applied at birth.

## What "the stabilized API" means (repo-grounded)

1. **The stable adapter interface** — `execution_adapter.py`
   (`INTERFACE_ID = "scene_factory.comfyui_api_workflow"`,
   `INTERFACE_VERSION = 1`): one compiled task → one versioned ComfyUI API
   workflow. Defined in `v3/docs/07_STATUS_AND_ROADMAP.md` ("Next
   implementation order" item 1) and marked done in
   `v3/docs/20_COMPLETION_PLAN.md` Phase 1.
2. **Read-only execution status** — `execution_status.py` +
   `schemas/execution.schema.json`: generation status derived on read from
   the authority order (user review JSON → compiled plans/graph manifest →
   runner job log → files named by that log → optional live Comfy queue
   overlay). Per `v3/docs/19_EXECUTION_STATUS.md`. Only user review may mark
   output approved/rejected.
3. **The command surface** — `scene_factory.py`
   (`new/validate/index/compile/status/prepare/.../pipeline-status/execution-status/...`)
   per `v3/docs/08_REFERENCE.md`.
4. **The intake pipeline** — `pipeline.py` stages
   (`source_ingestion → structured_captioning → identity_isolation →
   caption_review → concept_datasets → concept_training`).
   `pipeline_state.json` holds **intake stages only**; generation stages are
   never hardcoded here.

## What "clean" means

- `pipeline.py` was copied from v3 **with the status-truth fix already
  applied**: the five hardcoded blocked generation-stage rows
  (`character_sheets`, `storyboards`, `scripted_clips`,
  `extended_sequences`, `final_assembly`) were never present in v5.
- `execution_adapter.py`, `execution_status.py`, `prompt_plan.py`,
  `scene_factory.py`, and `schemas/` are verbatim from v3.
- Deliberately excluded: v4's identity-pipeline branch, `Voice/`, and the
  v0/v1/v2 legacy line. Nothing was invented; no new functionality added.

## Provenance

Copied from `v3/` at commit `df2d6cc` ("archive"). The only delta from v3 is
the `refresh_state` truth fix. See `COMPARISON.md` for the v4-vs-v5
head-to-head.

## Layout

| Path | What |
|---|---|
| `scene_factory.py` | CLI command surface |
| `pipeline.py` | intake pipeline, intake-stages-only state |
| `prompt_plan.py` | prompt planning support |
| `execution_adapter.py` | stable adapter interface (v1) |
| `execution_status.py` | read-only derived execution status |
| `schemas/` | `execution` / `pipeline` / `project` JSON schemas |
| `tests/test_pipeline_state.py` | truth-fix regression tests |
| `docs/` | v5 docs (this file, comparison) |
| `COMPARISON.md` | plain v4-vs-v5 head-to-head (not the user's ACID format — see note) |

## Run

```bash
cd v5
python3 -m unittest discover -s tests -v
./scene_factory.py <command> <project-folder>
```

## Note on ACID

The user's ACID-diff instructions were searched for across the repo
(`docs/`, version folders, top-level files) and were not found. `COMPARISON.md`
is a plain head-to-head written without inventing that format; it is explicitly
not labeled as the user's ACID diff.
