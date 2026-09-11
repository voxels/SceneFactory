# Scene Factory v4 implementation task list

Last verified: 2026-09-06 (manual handoff review; 85 collected tests passing;
ComfyUI running with empty queue; production delivery still incomplete).

Principal engineer takeover:
[PRINCIPAL_ENGINEER_HANDOFF.md](/Users/voxels/SceneFactory/v4/docs/PRINCIPAL_ENGINEER_HANDOFF.md).
Its D01–D20 register records current defects, locations, repair requirements and
acceptance tests. It corrects older completion claims in this checklist:

- [ ] D01–D05: repair LTX loader/audio/control semantics and implement actual
  subject-adapter training/binding. Graph compilation has not established runtime compatibility.
- [ ] D06–D08: complete automatic generation stages and repair resume signatures
  and derivative-provenance overwrite behavior.
- [ ] D09–D10: complete Voice selection/status semantics and shared input resolution;
  the current bridge is partial and does not establish curated training eligibility.
- [ ] D11–D12: complete portable bundle contents and strengthen consumption/goal
  checks beyond file presence or status flags.
- [ ] D13–D18: finish acceptance metrics, eligible-frame coverage, structural
  consumers, durable video execution, full performance timeline and status propagation.
- [ ] D19–D20: complete actual rig/splat fidelity and Unreal/Scene Factory consumption.
  Existing mesh-derived Gaussian PLY and procedural blend shapes remain prototypes.

These are unresolved engineering items, not merely missing validation of finished code.

Authoritative status map: `v4/docs/SPACE_MAP.md`. This map is the single
cross-modality view of what is built, connected, prepared, blocked, and still
required for finishing.

Merge policy: additive and provenance-preserving. No source, prior run,
comparison, or rejected render is replaced. Derived manifests may combine
records for a consumer view, but retain origin path, hash, creation time,
purpose, and approval state. A merged view never counts as consumed unless a
real downstream trainer/runtime produces hash-verified evidence.

2026-09-06 integration update: `generate-video` now dispatches to
`video_executor.execute` using the existing compiled inputs. Audio presence
cannot enable a graph missing the identity adapter. Graph/input hashes,
alignment completion, server node availability, queue occupancy, and downloaded
video decodability are checked. Targeted executor/compiler tests pass. This is
an integrated entry point, not a completed video path: adapter binding,
validated motion control, original-audio mux integration, resumable submission,
and execution evidence still remain.

2026-09-06 delivery integration: the video executor now calls the original-audio
mux after downloading a decodable render and writes a separate
`build/identity/video/deliveries/<run-id>/performance.mkv` plus `delivery.json`.
It verifies the generated-video and original-audio hashes, refuses destination
overwrites, and rejects video shorter than the performance instead of cutting
speech with `-shortest`. A real local FFmpeg integration test covers successful
delivery, unchanged source bytes, overwrite rejection, and short-video rejection.
Runtime output remains `rendered_pending_validation`; motion, identity and lip
sync are not certified by a successful mux. Thirteen targeted tests pass.

Loose-end handoff stubs (2026-09-06): `./v4/scene-factory-v4 emit-stubs --project v4/examples/modeling_interview`
now emits `build/stubs/stub_manifest.json` plus one contract per blocked stage. These
are explicitly non-production (`production_ready=false` and
`does_not_count_as_consumed=true`); they document exact inputs, expected outputs,
and resume commands without fabricating trainer, control, audio, or Unreal proof.

This checklist tracks execution of `AUGUST_2026_IDENTITY_PIPELINE_GOAL.md`.
An item is checked only when an implementation and corresponding artifact or test
exists. A plan or placeholder does not count as completion.

Execution policy: use only model/trainer/runtime files already present on disk;
do not fetch or silently substitute external models. Any missing local dependency
remains an explicit blocker.

## Completed

- [x] Create the independent v4 root and modeling-interview example.
- [x] Implement stable CLI command names and fail-closed errors.
- [x] Exclude Koleka source and derived assets case-insensitively.
- [x] Assert the Koleka exclusion at the executable workflow boundary as well as
  ingest and bundle boundaries; compiled route JSON contains no Koleka identifiers.
- [x] Prove the automatic-run source fingerprint ignores Koleka-named derived
  cache paths while still changing for authorized derivatives.
- [x] Separate visual-identity videos from motion-reference videos.
- [x] Preserve hashes, provenance, derivative lineage, and source group IDs.
- [x] Make manual review gates exclusive to `fine_tuning` mode.
- [x] Implement automatic image-quality filtering and perceptual deduplication.
- [x] Generate masks, alpha cutouts, face crops, identity distances, landmarks,
  and body poses for 320 candidates.
- [x] Record 75 identity passes and 245 explicit rejections.
- [x] Generate pinned Florence-2 semantic captions for all 75 identity passes.
- [x] Build group-safe immutable splits: 43 train, 9 validation,
  6 calibration, and 6 final test.
- [x] Build a six-category training-split-only identity reference bank.
- [x] Extract 994 frames from seven motion-reference videos at 6 fps.
- [x] Generate poses on 558 motion frames and associate 99 temporal tracks.
- [x] Render three USDZ sources into 168 canonical geometry controls.
- [x] Audit every USDZ member with hashes and bind each source to its rendered
  structural controls (`build/identity/geometry/usdz_ingestion_manifest.json`).
- [x] Export the Hugging Face image dataset and three bounded FLUX experiments.
- [x] Verify MPS access in the FLUX trainer and ComfyUI runtimes outside the sandbox.
- [x] Record contractual consent from the user's explicit attestation.
- [x] Stage and hash mask-derived alpha-cutout references into the executable
  native-reference/PuLID graph inputs (`build/workflows/image_ablation/`).
- [x] Add a fail-closed ComfyUI API executor with staged-input, model, node,
  queue, timeout, output, and hash checks (`v4/comfy_executor.py`).
- [x] Add LoRA safetensors tensor-pair/rank/metadata/hash audits before adapter
  promotion (`v4/adapter_validation.py`); full base-model runtime loading remains
  a post-training check.
- [x] Complete provenance-aware model cards for all three trained FLUX candidates;
  each records the pinned trainer commit, exact rank/learning-rate/step recipe,
  trigger token, runtime route, validation-manifest hash authority, and explicit
  non-promotion status.
- [x] Implement the production `generate-image` entry point: it requires an
  explicitly promoted runtime route, rejects unpromoted routes, and forwards
  prompt/negative-prompt/seed/output-prefix overrides to the immutable executor.
- [x] Let automatic mode continue through ingest and runnable A/B preparation
  when only final-delivery audio is missing; preflight records that prerequisite
  as deferred and still refuses to call the run complete.
- [x] Make preflight status fail closed at the CLI boundary: partial readiness
  is reported as `blocked`, never as a successful complete run.
- [x] Force all trainer subprocesses into offline mode (`HF_HUB_OFFLINE`,
  `TRANSFORMERS_OFFLINE`, and `DIFFUSERS_OFFLINE`) so local model files are never
  implicitly fetched.
- [x] Refresh stale local ComfyUI adapter staging copies atomically by hash and
  include the image training plan in the benchmark-stage resume signature.
- [x] Refuse to resume a held-out evaluator when the persisted report plan hash
  differs from the current workflow/model/selection plan, preventing mixed-run
  metrics and provenance.
- [x] Verify workflow and promotable adapter hashes immediately before each
  evaluation candidate, so a plan cannot score changed artifacts.
- [x] Ensure blocked candidate staging propagates through the automatic stage
  ledger instead of being recorded as successful workflow compilation.
- [x] Add a project-wide evaluator lock spanning plan-hash directories, so
  changed workflow plans cannot start a parallel matrix during an active run.
- [x] Pass the current 79-test unit and contract suite (`PYTHONPATH=v4
  python3 -m unittest discover -s v4/tests -p 'test_*.py'`).
- [x] Implement a fail-closed identity-bundle packager with hash-verified copies,
  Koleka negative audit, and the declared bundle layout. Final packaging remains
  blocked until real video promotion, audio, and image-evaluation evidence exist.
- [x] Implement the modality-consumption audit and `validate` CLI. The current
  real-example report distinguishes photographic trainer consumption from
  prepared-but-unconsumed visual-video, motion, and USDZ controls; voice is
  blocked by the missing waveform and image runtime awaits held-out promotion.
- [x] Regenerate the automatic training package from the current role-separated
  selection (`build/test-package-current`): 64 visual identity records, 3 USDZ
  conditioning records, and 1 transcript; no motion-reference/TikTok frame is
  exported into the visual channel. The older `build/test-package` directory is
  retained as a legacy diagnostic only and is excluded from current consumers.
- [x] Document the intended finished delivery contract in `v4/README.md`: a
  self-contained identity bundle with promoted image/video adapters, executable
  workflows, provenance/reference data, controls, audio alignment, samples, and
  validation evidence.
- [x] Emit explicit image/video runtime contracts with route/control references,
  promotion requirements, and declared invocation paths for bundle packaging.
- [x] Rewrite packaged runtime contracts to bundle-relative paths and package
  the referenced video manifests, preventing dependency on the original project tree.
- [x] Re-verify every export in `build/test-package-current/training_package.json`:
  all 68 visual/conditioning files exist and match their recorded SHA-256 values.
- [x] Exercise the successful bundle path with promoted image/video artifacts,
  fallback voice inputs, runtime contracts, alignment, and a Koleka-negative audit.
- [x] Emit explicit non-production stubs for every currently blocked downstream
  handoff; stubs remain excluded from consumption, promotion, and packaging.
- [x] Add a machine-readable ten-criterion completion audit at
  `build/validation/goal_completion_audit.json`; it remains fail-closed until
  real training, execution, promotion, and packaging evidence exists.
- [x] Add the canonical Voice bridge at `voice_root=/Users/voxels/SceneFactory/Voice`.
  `build/identity/voice/voice_input_manifest.json` records every Voice file
  with origin, hash, creation/modification time, purpose, and approval state;
  `inputs/tts_script.txt` is the target script, `inputs/` and
  `reference_profiles/` are reference channels, `examples/` and `renders/`
  remain comparison/review-only, and `output/gage_final_master.flac` remains
  the explicit finishing destination. No Voice source bytes are replaced.

## In progress

- [x] Complete the one-step official FLUX.2 Klein trainer smoke test.
  - Evidence: `build/training/image_identity/smoke/smoke_complete.json` and loadable
    `pytorch_lora_weights.safetensors` (MPS, fp16, one optimizer step).
- [x] Train the rank/learning-rate/step experiment matrix (resume-safe).
  - All three bounded experiments completed on MPS: `rank8_lr0.0001_steps300`,
    `rank16_lr0.0001_steps500`, and `rank16_lr5e-05_steps700`. Each final adapter
  has a completion marker, SHA-256, and structural LoRA audit. Held-out
  validation and promotion remain separate unchecked stages.
- [x] Build a deterministic held-out evaluation plan: 8 prompt/seed cases across
  3 adapters plus base/native/PuLID baselines (9 scheduled routes), with source/group/hash checks. Evidence:
  `build/training/image_identity/heldout_evaluation_plan.json`. The plan now also
  schedules base, native-reference, and the locally available PuLID ablation;
  the currently running older plan remains resumable.
- [ ] Evaluate all checkpoints on fixed held-out prompts and seeds.
- [ ] Promote one loadable image identity LoRA with hashes, config, logs, and model card.
  Promotion now requires a unique candidate that beats both base and native-reference
  identity baselines on the held-out metrics; an absolute threshold alone is not enough.

## Parallel execution tracks (2026-09-05)

- [ ] Track A — image evaluation: fixed-seed held-out scoring for the three FLUX
  adapters, route ablations, and automatic winner promotion (fail closed when the
  ComfyUI backend cannot complete a sample). The base baseline is now complete:
  all 8 fixed-seed cases produced hash-verified images with 100% face and person
  mask detection; its measured identity distance is 0.876128. The evaluator has
  moved to native-reference and continues resumably. The refreshed plan includes base/native-reference/PuLID
  baselines plus three adapters (subject and LoRA-reference routes), for 9 routes
  and 72 fixed route/case generations. The prior adapter-only run is retained as a
  blocked diagnostic after exposing a wrapped-conditioning override bug; the
  corrected plan is active at `build/training/image_identity/heldout_runs/a5dccc2d80d26032/`.
- [ ] Track B — video/audio: LTX 2.5 trainer/runtime contract, visual-identity versus
  motion clip preparation, supplied-waveform preservation, alignment, and mux tests.
- [ ] Track C — Unreal/avatar: diagnose the macOS 27 Metal-toolchain crash and prove
  USDZ/Control Rig import through a crash-free commandlet or supported runtime path.
- [ ] Integration — package the promoted artifacts, modality-consumption report, and
  automatic end-to-end run; this remains dependent on the three tracks' evidence.

Architecture decision: PuLID is not the identity foundation. The production identity
system is the trained subject LoRA plus native multi-reference and compatible
structural controls; PuLID is retained only as an optional, separately scored face
anchor ablation.

## Remaining image runtime work

- [x] Compile executable base-model and native-reference baselines. Runtime
  execution is tracked separately and remains blocked by the installed backend.
- [x] Compile subject-LoRA and LoRA-plus-reference routes for all three completed
  adapters. Runtime execution and held-out scoring remain open.
- [x] Compile the installed PuLID Flux.2 Klein alternative as an optional ablation;
  execution/scoring remains open and it is not required for promotion.
- [ ] Compile compatible depth, pose, normal, and silhouette-control routes.
- [ ] Install/enable true FLUX.2 ControlNet Union only if model/runtime compatibility is proven.
- [ ] Generate the full fixed-seed ablation corpus.
- [ ] Measure identity, detection rate, foreground similarity, pose, silhouette,
  prompt alignment, anatomy, diversity, copying, runtime, and memory.
- [ ] Automatically promote the winning connected image workflow.

## Remaining video and audio work

- [ ] Install and pin the official LTX 2.5 trainer and matching encoder.
  The matching LTX-tuned Gemma encoder is already present at
  `/Users/voxels/ComfyUI-Shared/models/text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors`;
  only the official trainer repository remains unavailable. The real
  `train-video-identity` command fails closed on that dependency and the missing
  supplied waveform.
- [x] Prepare scene-split visual-identity clips separately from motion guides.
  Evidence: `build/identity/video/video_roles_manifest.json`,
  `visual_identity_manifest.json` (11 clips/158 frames), and
  `motion_reference_manifest.json` (994 pose frames/99 tracks); motion-only
  sources are excluded from the visual-identity frame/clip set.
- [x] Emit an audio/transcript preservation contract and fail-closed lipsync/mux
  preconditions. Evidence: `build/identity/video/audio_alignment_manifest.json`;
  no waveform is substituted for the still-missing supplied TTS audio.
- [x] Keep bundle voice discovery aligned with the declared input contract:
  local `v4/voice` takes precedence over the configured source-root fallback,
  and packaging includes the authoritative transcript and alignment manifest.
- [x] Compile the native ComfyUI LTX 2.5 identity/motion workflow against the
  installed in-tree LTX nodes and local motion-control LoRA. Evidence:
  `build/workflows/video_runtime/ltx25_identity_motion.json` and
  `video_runtime_contract.json`; the graph binds an identity keyframe and a
  separate motion-reference video. Compilation is not execution or adapter
  promotion.
- [x] Detect native ComfyUI LTX video/audio nodes in preflight even when the
  historical standalone `ComfyUI-LTXVideo` plugin directory is absent.
- [ ] Train, validate, and promote a real LTX identity LoRA.
- [ ] Compile Ingredients, Union, Motion Control, mask, and multi-keyframe ablations.
- [ ] Generate the authoritative FLUX identity keyframe for I2V.
- [ ] Add the user-supplied TTS audio when it is placed in `voice/` (still absent).
- [ ] Finish Voice handoff: render and review all six paragraphs, assemble and
  validate `Voice/output/gage_final_master.flac`, then bind its hash into the
  v4 audio/mux contract. Reference audio must not be substituted for this
  performance waveform.
- [ ] Align words, phonemes, and visemes without replacing the supplied waveform.
- [ ] Generate video, retime/validate lip motion, and mux the original audio.
- [ ] Measure per-frame identity, drift, pose adherence, flicker, and lip sync.

## Persona-oriented avatar outputs (Unreal preferred)

- [x] Fetch/install Unreal Engine 5.8 and record it in preflight: `/Users/Shared/Epic Games/UE_5.8`,
  build `5.8.2` (changelist `56702186`), with Control Rig, Live Link, Rig Logic,
  USD Importer, MetaHuman Animator, Apple ARKit, and Apple ARKit Face Support
  plugin manifests present.
- [ ] Install and verify the Xcode Metal Toolchain required by the UE macOS
  renderer. On macOS 27 the current read-only probe fails closed with Apple's
  explicit diagnostic `missing Metal Toolchain`; the documented repair is
  `xcodebuild -downloadComponent MetalToolchain`. Do not launch the editor or
  claim UE render/import validation until this probe passes.
- [x] Keep Blender optional in preflight; it remains a USD conversion fallback
  and is not required for the preferred Unreal/image/video tracks.
- [ ] Run an editor-independent Unreal commandlet smoke test with
  `UnrealEditor-Cmd -nullrhi -unattended -nop4 -nosplash -nosound`, then validate
  the USD import/Control Rig/asset path once the toolchain is available. A
  minimal target now exists at `SceneFactoryV4.uproject`; the bounded invocation
  timed out without a success signal, so commandlet/import validation remains
  unchecked. A commandlet result is not a substitute for a rendered Metal runtime
  test.
- [x] Export a deterministic static rig prototype and matching Gaussian point cloud
  from the high-resolution portrait USDZ; validate archive contents, hashes, and PLY
  fields with `scene-factory-v4 validate-avatar`.

- [ ] Build a rigged talking-head mesh per character and export a validated USDZ
  package with geometry, skeleton/skin weights, blend shapes (facial expressions and
  visemes), textures, normals, materials, UVs, camera metadata, and voice/viseme timing
  references. Static rig export evidence exists at
  `build/avatar/gage_portrait/avatar_manifest.json` and the USD token audit
  (Skeleton, BlendShape, jawOpen, viseme, normals, textures); final voice/viseme
  binding and runtime validation remain open.
- [x] Build a matching Gaussian-splat representation of the same head, retain its
  calibrated scale/origin/camera metadata, and export the native splat asset plus a
  documented visionOS-compatible delivery path where supported. Evidence: the
  `gage_head_gaussian.ply` artifact and avatar manifest.
- [ ] Verify mesh and splat identity against the held-out reference bank and compare
  facial motion, expression coverage, texture/normal fidelity, and lip-sync timing.
- [ ] Package both representations for pre-recorded playback and post-production
  retiming/tweaks. Record any visionOS 27 Persona/SharePlay integration limitations;
  do not claim native Persona equivalence without an Apple-supported runtime test.
  Prefer Unreal's import/Control Rig/MetaHuman-compatible path for authoring and
  playback; retain Blender only as a fallback for USDZ conversion and canonical
  control rendering if UE cannot complete a required export.

## Remaining packaging and verification

- [ ] Execute the connected image API workflows against the live ComfyUI server;
  server and FLUX.2 Klein files are present, and the live API reports an MPS
  device. A base-route smoke and several LoRA cases have produced downloaded
  output bytes and hashes; the held-out matrix remains in progress and has also
  exposed intermittent KSampler/server timeouts.
- [ ] Build real connected video API workflows.
- [x] Verify every enabled model and reference reaches its consumer node before
  queueing; unavailable control routes remain explicitly disabled/blocked and
  are not treated as enabled consumers.
- [ ] Package the self-contained `identity_bundle/` tree with
  `package-identity-bundle`. The real command is implemented and currently
  fails closed because image/video promotion and the supplied waveform are not
  complete.
- [x] Add checkpoint-loadability and exact adapter-bypass tests.
- [x] Add workflow graph-connectivity and modality-consumption tests.
- [x] Require every declared ComfyUI model to be bound to a concrete graph
  loader/control node before queueing; coverage exercises the real base route.
- [x] Add audio-preservation and mux precondition tests.
- [x] Provide an executable stream-copy mux helper that verifies the supplied
  waveform hash is unchanged and the output contains both video and audio streams.
- [x] Reject unsafe ComfyUI output filenames/subfolder traversal and reject
  non-image payloads before accepting runtime artifacts.
- [x] Add restart/resume and negative-path tests for held-out evaluation.
- [x] Add automatic-run preflight-block and no-placeholder smoke test.
- [x] Add deterministic integration and automatic-run success/resume contract tests.
- [x] Propagate blocked/incomplete stage status through the CLI wrapper with a
  nonzero exit code; blocked preparation can no longer print success.
  The test drives all ten stages through the real orchestrator, verifies a complete
  ledger, then verifies a second invocation skips every intact stage; a changed
  signature/output is separately covered by the invalidation test.
- [ ] Run `scene-factory-v4 run` to successful image and video outputs without review.
- [ ] Complete the requirement-by-requirement audit and accurate final documentation.

## Current execution order

1. Evaluate the three completed FLUX adapters on fixed held-out prompts and seeds,
   then promote the winner.
2. Compile/validate image ablation graphs (base, native reference, LoRA, RefControl,
   PuLID) and run fixed-seed comparisons.
3. Install/pin the LTX trainer and complete the video identity and control path.
4. Ingest the supplied TTS waveform, preserve it byte-for-byte, and validate mux/lipsync.
5. Build and validate the rigged USDZ and matching Gaussian-splat talking-head outputs.
6. Package, run the automatic end-to-end command, and execute the full audit suite.

Current focus override: Unreal/rig runtime work is deferred. Until the Metal
toolchain is repaired, work is limited to image evaluation/promotion, local
video-role and control preparation, audio contracts, tests, and packaging
preconditions; no rig task is treated as a prerequisite for those advances.

## Live execution note (2026-09-05)

Integration policy for this run: do not wait synchronously for the complete
generation matrix. The evaluator runs resumably against local ComfyUI while
preparation, audits, tests, and documentation continue independently; only
hash-verified outputs may advance promotion.

The three FLUX trainer experiments are complete and resumable checkpoints are
audited. The corrected connected ComfyUI run has now verified multiple base-route
PNGs and is continuing through the fixed-seed matrix; every downloaded output is
hash-recorded and the report is resumable after a backend failure.
The refreshed preflight confirms ComfyUI 0.34.5 on MPS, the three local FLUX
adapters, and the local FLUX/PuLID nodes; no compatible local FLUX ControlNet
checkpoint or JLC node is installed, so that structural branch remains
explicitly unavailable rather than fetched or substituted.

Earlier live observations recorded a 5/8 native-reference baseline and an
interleaved historical queue. Those measurements belong to the superseded
adapter-only run and are retained only as historical evidence; they must not be
used as current promotion evidence. The refreshed candidate graphs are
hash-consistent with all three retrained adapters.
The current deterministic evaluation plan is
`f460b00ee1af5f2f63ece163af2e8e152b3c0846d7fb8852845e7063059d6738` (8 held-out
cases, 4 candidate routes including PuLID). The active queue may contain
historical prompts interleaved with current-plan prompts; historical artifacts
are retained as evidence only. The current-plan evaluator owns the project lock,
and its report is resumable and remains separate from the historical directory.
The historical evaluator was created under the prior plan hash; its report is
retained as historical evidence. The current evaluator owns the project lock and
will write only the current-plan report, so the two matrices cannot be mixed.

Verification update (2026-09-06): the current-plan held-out evaluator remains
running under plan hash
`f460b00ee1af5f2f63ece163af2e8e152b3c0846d7fb8852845e7063059d6738`.
Its base route is complete (8/8 hash-verified cases, 100% face/person-mask
detection); native-reference has begun and is resumable. A separate historical
PuLID job is still interleaved in the local ComfyUI queue and is not merged into
the current report. The image audit was re-run and all three FLUX adapters remain
structurally loadable; no adapter is promoted until it beats both base and
native-reference on the fixed held-out matrix.

The non-rig preparation pass was also re-run successfully: visual identity is
still isolated to 11 clips/158 frames, motion is isolated to 7 sources/99 tracks
(994 pose frames), and the supplied-audio contract still preserves the
transcript/hash requirement without inventing a waveform. `validate` correctly
remains blocked because these prepared artifacts have not yet reached a real LTX
trainer/control consumer, the authoritative TTS waveform is absent, and image
promotion evidence is pending. No Unreal/Blender work was started.

Avatar validation is independently green for the existing deterministic prototype:
`validate-avatar` found a 1,321,745-vertex USDZ mesh and matching 3DGS PLY with
geometry, skeleton, skin weights, blend shapes, visemes, UVs, textures, normals,
and materials. Voice/viseme timing remains pending the supplied waveform, and
native visionOS Persona/SharePlay equivalence is intentionally not claimed.

The non-generation verification pass is green: all 79 unit/contract tests pass.
Python sources compile successfully; all three completed image adapters are structurally
loadable, base-route adapter bypass is covered, and the real-example modality audit
now refuses to call visual-video, motion, or USDZ preparation “consumed” without
downstream execution evidence.
The real video/audio preparation stage was rerun and produced the same hashed
role/frame/audio manifests (11 visual-identity clips, 158 frames, 7 motion
sources), confirming deterministic preparation; it exits blocked until the
supplied waveform and official LTX trainer are available.
The evaluator now holds a per-run kernel lock to prevent duplicate matrix
submissions; the lock behavior is covered by the image-evaluation contract tests.
Its blocked-report resume path is also covered: completed cases are retained and
only missing route/case generations are retried after an interruption.
Connected image executions now retain elapsed runtime in each execution record,
and the candidate summary exposes median runtime and true median identity distance
for performance and promotion comparison.
The `run` command now records a resumable `build/pipeline/automatic_run.json`
stage ledger and invokes the real ingest, USDZ, identity, image, video, validate,
and bundle stages once preflight dependencies are satisfied; it records the first
blocked stage rather than emitting placeholder success. Completed stages are
skipped only when their source/config/code signature and recorded output hashes
still match; changed inputs invalidate that stage and downstream work resumes.
Preflight dependency blocks preserve the same-identity completed ledger so a
retry after audio/toolchain repair can resume from intact stages.
The latest escalated automatic invocation completed ingest, USDZ rendering and
ingestion, identity processing, all three image experiments, and workflow
compilation; it stopped before evaluation when stale adapter staging was detected.
Staging has since been atomically refreshed and the evaluator is continuing under
its existing locked run; the automatic ledger is intentionally left resumable.

The latest `scene-factory-v4 run` failed closed as designed. With the local API
probe enabled, the actionable blockers are the missing supplied TTS waveform and
the unusable Xcode Metal Toolchain for Unreal rendering; image training remains
separately constrained by the trainer environment even though live ComfyUI
inference exposes MPS.

## External input still required

- [ ] Supply the generated TTS audio file in
  `v4/examples/modeling_interview/voice/` (the configured source-root
  `v3/.../Gage/voice/` remains supported as a fallback).
  Existing voice-reference samples elsewhere under `Voice/` are not treated as
  this waveform: they are enrollment/reference audio, not an authoritative
  rendering of `tts_text.txt`, and substituting them would violate the byte-
  preservation and lipsync contract.
