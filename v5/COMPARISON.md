# v4 vs v5 — plain head-to-head

> NOTE: the user's ACID-diff instructions were searched for across the repo
> and not found. This is a plain comparison written without inventing that
> format. It is explicitly **not** the user's ACID diff.

## One-line

- **v4** = the multimodal identity pipeline: builds a provenance-aware
  `identity_bundle/` (LoRAs, reference bank, workflow graphs, USDZ/avatar,
  voice alignment) via `./scene-factory-v4` + `training_harness.py`.
- **v5** = the stabilized compile→execute API, clean-installed: CLI command
  surface, intake pipeline, stable ComfyUI adapter interface, read-only
  execution status. No identity branch, no voice, no legacy.

## Head-to-head

| Dimension | v4 | v5 |
|---|---|---|
| Lineage / purpose | Identity-evidence pipeline (`v4/README.md`): "a character identity is not reduced to a folder of LoRA images" | Stabilized API clean install (this folder's `README.md`) |
| Entry points | `./scene-factory-v4` (`scene_factory_v4.py`), `training_harness.py` | `./scene_factory.py` (`new/validate/index/compile/.../pipeline-status/execution-status`) |
| Core modules | `identity_pipeline.py`, `identity_bundle.py`, `identity_captions.py`, `identity_annotations.py`, `reference_bank.py`, `modality_audit.py`, `goal_audit.py`, `image_training.py`, `image_evaluation.py`, `video_executor.py`, `video_audio_pipeline.py`, `voice_flow.py`, `usdz_ingestion.py`, `comfy_executor.py`, `adapter_validation.py`, `stage_stubs.py`, `training_harness.py` | `scene_factory.py`, `pipeline.py`, `prompt_plan.py`, `execution_adapter.py`, `execution_status.py`, `schemas/` |
| Execution interface | `comfy_executor.py` + per-route compiled graphs (`execute-image-workflow`, `compile-video-workflow`); fail-closed without local models | Stable adapter interface v1: `execution_adapter.py` (`INTERFACE_ID="scene_factory.comfyui_api_workflow"`, one compiled task → one versioned API workflow, `validate_job`/`validate_manifest`) |
| Status truth | `docs/SPACE_MAP.md` as "authoritative status view"; `build/pipeline/automatic_run.json` records stages; resumable ledgers; fail-closed (stubs never satisfy completion) | `docs/19_EXECUTION_STATUS.md` authority order (user review → plans/graph manifest → runner job log → named output files → live queue overlay); `pipeline_state.json` = intake stages only; `execution-status` read-only derived view; `pipeline-status` never rewrites state |
| Hardcoded generation rows | n/a (different architecture) | **Absent in v5 by construction.** Present-but-blocked in v3 (fixed in this clone's `v3/pipeline.py` by the ported patch) |
| Identity model | Multimodal: photos, video, web pages, voice, transcripts, 3D captures keep separate provenance/authority; leakage-safe splits; held-out ablation | Intake-stage `identity_isolation` (caption-level person masks/face anchors); execution identity via PuLID-Flux2 Tier 1 / K LoRA Tier 2 per v3 docs |
| Voice | First-class: `voice_flow.py`, `Voice/` package handoff, TTS waveform as explicit blocker | Not included |
| Human gating | `training_harness.py decide` (approve/reject per asset); fine-tuning mode gates | Only user review JSON may mark output approved/rejected; `approve_all_gates.py` tooling in v3 (not carried into v5) |
| Tests | `v4/tests/` (adapter/avatar/identity/caption/image/motion suites) | `v5/tests/test_pipeline_state.py` (2 truth-fix regression tests, passing) |
| Docs | `v4/docs/` (identity pipeline goals, SPACE_MAP, USDZ, walkthrough) | This `README.md` + `COMPARISON.md` (this file) |

## v3 vs v5

v5 is v3's stabilized core, cleaned. File-for-file, the only code delta is
`pipeline.py::refresh_state` (five hardcoded blocked generation rows removed;
intake-stages-only, with the explanatory comment). Everything else —
`scene_factory.py`, `prompt_plan.py`, `execution_status.py`,
`execution_adapter.py`, `schemas/` — is verbatim from v3 at `df2d6cc`.
Dropped from v3's surface: `tools/`, `profiles/`, `template/`,
`review_console/`, `voice_clone/`, `comfy_adapter.py`, `lora_validation.py`,
`production_tracking.py`, `reference_contracts.py`, `reference_pipeline.py`,
`render_pipeline.py`, `rough_cut.py`, `ltx_server_wrapper.py`.

## What v5 does not claim

- No live ComfyUI verification exists for this machine; the `--live` overlay
  is unit-covered only.
- v5 was not run end-to-end against a real project here (no fixture run was
  performed in this pass beyond the unit tests).
- The v4 column describes v4's documented intent (from its README/docs), not a
  verified runtime.
