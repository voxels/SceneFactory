# Koleka AD2184 local-agent handoff

This runbook executes the Koleka-first AD2184 generation process from `/Users/voxels/SceneFactory/v3`. Scene Factory owns manifests and approvals; ComfyUI executes generated API graphs.

## Current state

- Project: `/Users/voxels/SceneFactory/v3/examples/ad2184`.
- Canonical approved source: `assets/source/characters/k0l3k4/training/SSK_Koleka - 1 of 45.jpeg`, declared by the project's `pulid_reference`.
- Identity audit: `examples/ad2184/build/identity_fidelity/selected_reference_manifest.json`.
- `ComfyUI-PuLID-Flux2` and `pulid_flux2_klein_v2.safetensors` are installed.
- The full graph manifest must be compiled before the runner starts.
- A file on disk is not an approval. Only the operator may approve identity or production media.

## Compile and validate

```sh
cd /Users/voxels/SceneFactory/v3
./scene_factory.py validate ./examples/ad2184
./scene_factory.py index ./examples/ad2184
./scene_factory.py compile ./examples/ad2184
./scene_factory.py prepare ./examples/ad2184
./scene_factory.py comfy-build ./examples/ad2184
./scene_factory.py comfy-preflight ./examples/ad2184
python3 tools/run_comfy_phase.py ./examples/ad2184 identity_first_review --dry-run
```

Stop on any failure. `comfy-preflight` is the authoritative list of missing runtime assets.

## First milestone: one PuLID proof

ComfyUI must answer on port 8188 and its queue must be idle:

```sh
curl -fsS http://127.0.0.1:8188/queue
./scene_factory.py execution-status ./examples/ad2184 --live
```

Run one highest-priority identity job:

```sh
python3 tools/run_comfy_phase.py ./examples/ad2184 identity_first_review \
  --limit 1 --timeout 7200 --max-attempts 1
```

Resumable state is written to `examples/ad2184/build/execution/comfy_state.json`. A timeout is never automatically retried; inspect state, `/queue`, and `/history/PROMPT_ID` before deciding whether to rerun.

## Human review gate

Stop and ask the operator to inspect the first output for Koleka identity, approved adult life-stage presentation, unobstructed face, coherent anatomy, correct single-hammer geometry, and absence of helmet/visor/mask/enforcer-armor transfer. Never use `tools/approve_all_gates.py` for production or write `approved_by: user` without an actual decision.

```sh
./scene_factory.py execution-status ./examples/ad2184
./scene_factory.py pipeline-status ./examples/ad2184
```

## Resume order after each approval

Run one dependency stage at a time and stop for review between stages:

```sh
python3 tools/run_comfy_phase.py ./examples/ad2184 identity_expansion --timeout 7200 --max-attempts 1
python3 tools/run_comfy_phase.py ./examples/ad2184 storyboard_candidates --candidate 1 --timeout 7200 --max-attempts 1
python3 tools/run_comfy_phase.py ./examples/ad2184 motion_proofs --candidate 1 --timeout 7200 --max-attempts 1
python3 tools/run_comfy_phase.py ./examples/ad2184 extended_clips --candidate 1 --timeout 7200 --max-attempts 1
./scene_factory.py rough-cut ./examples/ad2184 --candidate 1 --duration 5
```

Do not use `--allow-missing` for a completion claim.

## Failure and ownership rules

- Missing `full_visual_graph_manifest.json`: rerun `prepare`, `comfy-build`, and `comfy-preflight`.
- Missing node type: inspect `/object_info` and startup logs; do not submit a guessed graph.
- Explicit failure: fix the recorded cause before a deliberate retry.
- Timeout: never submit a duplicate automatically.
- Missing staged keyframe: finish and approve its storyboard dependency.
- Completed outputs are skipped unless missing or `--force` is explicitly used.
- Voice and image/video agents must not independently restart or own the same Comfy process.

Preserve `build/comfyui/full_visual_graph_manifest.json`, `build/execution/comfy_state.json`, `build/identity_fidelity/selected_reference_manifest.json`, review records, and `/Users/voxels/ComfyUI-Shared/output/ad2184_v3_identity_fidelity/`.

## Local-agent assignment

> Follow `docs/22_KOLEKA_AD2184_LOCAL_AGENT_HANDOFF.md`. Run compile, preflight, dry-run, and the one-job identity milestone in order. Preserve resumable state, never duplicate a timeout, never fabricate user approval, and stop at every human review gate with artifact paths and the exact next command.
