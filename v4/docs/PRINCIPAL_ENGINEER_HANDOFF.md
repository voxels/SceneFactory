# Scene Factory v4 — principal engineer handoff

Prepared 2026-09-06 from local source, artifacts, installed node implementations,
process inspection, and tests. Purpose: take over the existing work, reconcile
its evidence, finish the missing connections, and deliver the requested system.
This is a handoff of an incomplete implementation, not a production acceptance.

## 1. Executive assessment

There is useful implemented work: source indexing, image preprocessing,
role-separated video preparation, three trained image LoRA candidates, image
execution records, geometry renders, voice tools, and a CLI. There is no verified
end-to-end product or portable production identity bundle.

The major problem is integration and overstated readiness. Compiled graphs,
prototype exports, and file-presence checks have sometimes been described as
completed functionality. Several components cannot meet their stated contract
even after missing input files are supplied. Treat this document's defect register
as corrections to earlier status summaries and checked task items.

The saved automatic ledger records six completed stages and a failure at
`evaluate_image_identity`. Its error is `compiled candidate route is missing:
subject_lora_rank16_lr0.0001_steps500`. That is historical ledger state, not proof
that the current graph still lacks the route. Current image runtime has
`selected_route: null`. Image adapters have not been promoted. No promoted LTX
identity adapter or approved Voice master is present in the inspected paths.

The existing goal audit reports 2/10 checks passed, but those two checks mostly
test whether files exist. This is neither a completion percentage nor a sufficient
acceptance test. The audit itself needs strengthening.

## 2. Product contract and decisions to preserve

The goal is a reusable identity system for the modeling-interview Gage example,
with image and video generation and an editable avatar delivery. It must process
photographs, archived web evidence, visual-identity video, independent motion
video, USDZ captures, voice reference data, and the requested speech performance.

Required outputs are a selected image identity model, video identity model,
reference bank, structural/motion controls, working generation commands,
original-performance audio with word/phoneme/viseme timing, generated image/video
proofs, and a portable bundle. Avatar scope includes geometry, a skinned skeleton,
facial blend shapes, textures, UVs, normals/materials, voice timing, and a matching
Gaussian head representation suitable for prerecorded playback and post editing.
VisionOS Persona/SharePlay fidelity is a design target; no equivalence or supported
native integration has been demonstrated.

Preserve these explicit user decisions:

- No Koleka media or derivatives in this version.
- Use models already on disk; do not fetch models, trainers, or tools silently.
- Default `automatic` mode completes without human review gates. Optional human
  review belongs in `fine_tuning` mode. Technical failures must still be honest.
- PuLID is an optional scored face adapter, not the identity foundation. The
  intended system is trained subject identity plus native references and
  compatible structure/motion controls.
- Voice work belongs at `/Users/voxels/SceneFactory/Voice`, and flows into Scene
  Factory as an input. Reference recordings and generated performance have
  different purposes.
- Preserve previous work and reconcile by origin, time, purpose, and evidence.
  Do not merge by overwriting files or selecting the newest filename alone.
- Finish the core image/video integration without waiting on the broken rig.
  Unreal is the preferred eventual destination; Blender is optional.
- Do not restart the long evaluation merely to produce another status report.
  The previous evaluator was stopped at the user's request.

The governing specification is
[AUGUST_2026_IDENTITY_PIPELINE_GOAL.md](/Users/voxels/SceneFactory/v4/docs/AUGUST_2026_IDENTITY_PIPELINE_GOAL.md).
Its completion criterion 3 allows a documented hardware/license exception to
video training when genuinely impossible. Missing local code alone does not
establish that exception; do not use it to rename a stub as a finished adapter.

## 3. Where everything lives

| Absolute location | Purpose and authority |
|---|---|
| `/Users/voxels/SceneFactory/v4` | Current Python implementation and CLI |
| `/Users/voxels/SceneFactory/v4/examples/modeling_interview/identity.json` | Example config: automatic mode, Gage, source path, Voice path, consent attestation, role rules, exclusions |
| `/Users/voxels/SceneFactory/v3/examples/modeling_interview/Gage` | Original visual/motion/web/USDZ sources; preserve |
| `/Users/voxels/SceneFactory/Voice` | Current standalone Qwen TTS package and intended voice destination |
| `/Users/voxels/SceneFactory/v4/examples/modeling_interview/build` | All principal v4 derived artifacts discussed below |
| `/Users/voxels/SceneFactory/v3` | Older broader scene tools; inspect for reusable functionality, not proof of v4 integration |
| `/Users/voxels/SceneFactory/archive` | Historical material; do not bulk-import |
| `/Users/voxels/SceneFactory/v4/docs/IMPLEMENTATION_TASKS.md` | Existing detailed checklist; corrections in this document take precedence over older completion claims |
| `/Users/voxels/SceneFactory/v4/docs/SPACE_MAP.md` | Earlier overview, less detailed than this review |

The SceneFactory root is not a Git repository (`git status` failed there).
Establish an engineer-controlled snapshot/version history before broad changes.
Do not assume prior work can be recovered with Git. Do not duplicate large model
trees merely to create a checkpoint of the code.

In the following tables, `build/...` means a path beneath
`/Users/voxels/SceneFactory/v4/examples/modeling_interview` and module names mean
files beneath `/Users/voxels/SceneFactory/v4`.

## 4. Architecture and connection map

```text
Original Gage images/webarchives
  -> identity_pipeline -> annotations/captions/selection/reference_bank
  -> image_training -> 3 FLUX candidate LoRAs
  -> image_workflows + comfy_executor -> partial generated image corpus
  -> image_evaluation -> [no promotion] -> generate-image -> [no production proof]

Visual-identity videos -> video_audio_pipeline -> 11 clips / 158 frames
  -> [no executing LTX trainer] -> [no video identity adapter]

Motion-only videos -> motion_tracking -> frames / body poses / tracks
  -> [no validated trajectory/control adapter connection]

USDZ -> usdz_ingestion + usdz_controls -> audited members / 168 controls
  -> [no successful geometry-controlled generation]
  -> rig_avatar_blender -> heuristic mesh rig + mesh-derived Gaussian PLY
  -> [no verified Unreal or visionOS playback]

Voice package -> voice_flow -> transcript/reference index + expected final path
  Voice scripts -> [final performance not produced]
  -> [aligner absent] -> video_executor -> original-audio mux -> delivery record
     (mux tested using fixtures; no actual Gage video delivery)

All branches -> [incomplete orchestration/validation/packaging]
  -> [no portable bundle that generates new image and video]
  -> [no verified v4 bundle consumer in the older scene-production pipeline]
```

## 5. Implemented artifacts and strength of evidence

| Area | Implementation and artifact | What the evidence proves / does not prove |
|---|---|---|
| Inventory | `identity_pipeline.py`; `build/identity/asset_manifest.json` | 278 source entries: 247 photos, 10 videos, 15 webarchives, 3 geometry files, 1 contact image, 1 HTML document, 1 transcript. 257 unique source hashes, 21 exact-duplicate groups. Current inventory has no source audio and zero extracted candidates; see provenance overwrite defect below. |
| Masks/annotations | `identity_annotations.py`, `tools/analyze_visual_frames.swift`; `build/identity/annotation_manifest.json` | 320 candidate records, 75 identity passes, 245 rejects. These counts do not prove quality of every mask/landmark or coverage of the separate 158-frame video dataset. |
| Captions | `identity_captions.py`; `build/identity/caption_manifest.json` | 75 caption records using pinned Florence processing. Check content quality and field separation. |
| Selection | `training_harness.py`; `build/identity/selection_manifest.json` | 64 selected records: 43 train, 9 validation, 6 calibration, 6 final test; coverage/deduplication code exists. Script-specific clean-shot relevance still needs evidence. |
| References | `reference_bank.py`; `build/identity/reference_bank/reference_bank.json` | Six reference categories; status remains `candidate_pending_heldout_generation_optimization`. |
| FLUX training | `image_training.py`, `adapter_validation.py`; `build/training/image_identity` | Three completed candidate adapters and structural audits; no production promotion. Structural tensor checks are not full base-model loading/fidelity proof. |
| Image generation | `image_workflows.py`, `comfy_executor.py`; `build/workflows/image_ablation` | Compiled route files and real downloaded image records exist. Some runs are partial/failed and cannot be combined without plan-hash reconciliation. |
| Visual video | `video_audio_pipeline.py`; `build/identity/video/visual_identity_manifest.json` | 11 clips, 158 extracted frames from identity-role sources. No trainer consumption. |
| Motion | `motion_tracking.py`; `build/identity/motion/skeleton_manifest.json` | 7 sources, 994 frames, 558 with poses, 99 tracks. These are image-space tracking artifacts, not a solved 3D facial rig. |
| Geometry | `usdz_ingestion.py`, `usdz_controls.py`; `build/identity/geometry` | 3 source records, 168 bound controls. No successful control-conditioned runtime proof. |
| Voice bridge | `voice_flow.py`; `build/identity/voice/voice_input_manifest.json` | Paths, hashes, filesystem dates, roles and transcript discovered. Does not render speech, verify speaker purity, or establish approval. |
| Video execution | `video_workflows.py`, `video_executor.py` | CLI dispatch, input/hash checks, download probing and original-audio mux exist. Graph has defects below; execution deliberately disabled. |
| Delivery mux | `video_audio_pipeline.mux_original_audio`, `video_executor.finalize_delivery` | Local FFmpeg test writes MKV with original audio stream, rejects overwrite and short video. Does not establish lipsync or identity. Intended output: `build/identity/video/deliveries/<run-id>/performance.mkv` and `delivery.json`. |
| Avatar | `tools/rig_avatar_blender.py`, `avatar_validation.py`; `build/avatar/gage_portrait` | Mesh USDZ and PLY prototype exist. Rig and splat construction are heuristic, not finished Persona-fidelity reconstruction. |
| Orchestrator | `scene_factory_v4.py`; `build/pipeline/automatic_run.json` | Resumable ledger and ten stage entries exist; generation/alignment/avatar stages are absent. |
| Packaging/audits | `identity_bundle.py`, `modality_audit.py`, `goal_audit.py` | Initial copying and reporting mechanisms; insufficient acceptance checks and incomplete portable layout. |
| Stubs | `stage_stubs.py`; `build/stubs/stub_manifest.json` | Explicit non-production handoff contracts only. Never train or generate from them as substitutes. |

Trained image candidate directories, each containing
`pytorch_lora_weights.safetensors`, `experiment_complete.json`, a validation JSON,
and model card:

- `build/training/image_identity/experiments/rank8_lr0.0001_steps300`
- `build/training/image_identity/experiments/rank16_lr0.0001_steps500`
- `build/training/image_identity/experiments/rank16_lr5e-05_steps700`

The one-step smoke under `build/training/image_identity/smoke` is not a substitute
for any of those candidates. `build/test-package-current` is the intended current
dataset export; `build/test-package` is retained historical diagnostic material.

## 6. Process and evaluation takeover

At handoff inspection, ComfyUI PID 38509 was running. An unsandboxed read of
`http://127.0.0.1:8188/queue` returned empty running and pending arrays. Process
inspection found no matching active image evaluator, DreamBooth trainer, or Voice
submission script. Recheck immediately before submission; these are snapshots.

Earlier sandboxed probes returned no MPS and an unreachable local API. Do not
conclude hardware is absent from those results: the live process and unrestricted
queue query establish that ComfyUI is running. Inspect the actual Comfy environment
before accepting preflight's accelerator diagnosis.

Persisted reports under `build/training/image_identity/heldout_runs`:

| Run prefix | Saved status | Saved case counts by route |
|---|---|---|
| `3efd415c68c736ee` | running | base 0 |
| `4f64ab0d1fa1c678` | blocked | rank16/500 subject 8; corresponding reference route 0 |
| `a5dccc2d80d26032` | blocked | base 8, native 8, PuLID 8, rank16/500 subject 3 |
| `be6db453eca3a7ea` | running | base 2 |
| `f460b00ee1af5f2f` | running | base 8, native 5 |

`running` in these JSON files is not live process evidence. Never pick the
lexicographically greatest folder as the authoritative run. Resolve the intended
plan SHA and compare graph, adapter, data, seed and metric-version hashes. Preserve
all runs and reuse only compatible case evidence. Do not reset counters or delete
locks based only on report state. The saved automatic ledger's six stage entries
are history, not proof that current regenerated manifests still match them.

## 7. Confirmed defects and unfinished engineering

Priority means order to unblock a reliable product, not a claim that only these
items are in scope. Each row names code and a concrete acceptance condition.

| ID | Priority / location | Finding and required repair | Acceptance |
|---|---|---|---|
| D01 | P0 `video_workflows.py` node 3 | `LTXAVTextEncoderLoader.ckpt_name` is `sdpose_wholebody_fp16.safetensors`, an unrelated pose checkpoint. Installed loader passes that checkpoint into `load_clip`. The installed combined Gemma file already has LTX projection keys; installed `comfy/sd.py` has a single-file Gemma4 LTX branch. Test `CLIPLoader(type=ltxv)` against this exact file or choose another locally verified loader. | Real text encoding using intended model, no unrelated checkpoint, model hashes recorded. |
| D02 | P0 `video_workflows.py` audio branch | Audio latent is connected to `DecodeAndSaveVideo` without its `audio_vae`; installed implementation explicitly raises in that case. Audio is only encoded for output, not shown to condition generated mouth motion. Use original stream mux for preservation and implement an actual validated audio/viseme conditioning path. | Node-schema-valid execution and measured lipsync; no claim that encoding/decoding alone supplies lipsync. |
| D03 | P0 video graph/model path | No node loads a subject video LoRA. Compiler sets `identity_lora_bound=false`, `execution_allowed=false`. Executor checks the boolean but does not independently prove adapter promotion/hash/binding. Supplying a master or editing flags will not fix this. | Real adapter promotion, hash-checked loader connected to sampled model, bypass test and generation proof. |
| D04 | P0 motion graph | Raw motion-reference video is sent through an image guide with a motion-track LoRA. Extracted skeletons/trajectories are not bound to the appropriate track-control input. `VHS_LoadVideoFFmpegPath` with a VAE may output latents where the next guide expects images; inspect installed node schema. LTX 2.3-named control weight compatibility with 2.5 is unproven. | Explicit compatible control contract, normalized trajectories/masks, correct tensor types, motion adherence test. |
| D05 | P0 `video_audio_pipeline.train_video_identity` | Always raises even if trainer discovery succeeds because invocation contract is not pinned. Trainer absence and missing audio also block preparation. Audio should not unnecessarily block independent visual identity training. | Executing locally verified trainer command, dataset/config hashes, resume, actual adapter and validation video. |
| D06 | P0 `scene_factory_v4._automatic_run` | Stage list contains no `generate-image`, `generate-video`, speech rendering, alignment, mux, video evaluation or avatar stage. Nested blocked results from `process_identity` are not propagated by the top-level status checker. | Real automatic run reaches actual image/video deliveries and truthful terminal state, with optional manual gates only in fine-tuning mode. |
| D07 | P0 resume signatures | Source fingerprint scans original Gage root, not canonical Voice inputs. Code signature hashes the orchestrator file rather than all stage code. Evaluation output tracking uses a plan file rather than terminal report/adapters/output corpus. | Changing a used source/module/model invalidates affected consumers; unrelated history does not retrain everything; valid completed work resumes. |
| D08 | P0 provenance rebuild | `prepare_video_audio` calls `identity.build(extract_web_media=False)`, rewriting the shared inventory without extracted web candidates. Current inventory reports zero, while earlier annotations/train data include web derivatives. Extraction code also deletes unrecognized files from its derivative folder. | Immutable source/derivative registry plus versioned consumer views; downstream preparation cannot erase lineage; preserve prior artifacts before regeneration. |
| D09 | P0 Voice semantics | `voice_flow` marks every reference-profile audio file consumable without curated status, exact transcript pairing or speaker validation; extended transcript is explicitly a draft. Known rejected paragraph 01 is labelled pending. Final master existence is treated as sufficient performance selection while its record still says unapproved. | Explicit reference selection/profile/transcript hashes and take status, rejected evidence preserved, target performance identified independently of reference recordings. |
| D10 | P0 Voice integration/merging | Config connects canonical Voice to preflight/audio preparation/bundle lookup, but not the main ingest/training registry. Audio preparation selects canonical transcript over legacy records and may fall back to legacy audio; bundle lookup will not. Legacy same-name precedence is still replacement selection. | One role-aware resolver shared by all consumers, preserving both origins and intentional selection; same-name conflicts retained; consistent performance identity across stages. |
| D11 | P0 packaging | Packager primarily checks two adapter filenames and audio existence. Does not establish required evaluation/promotion/lipsync evidence. Required datasets/references/samples/documentation are not fully copied. Runtime path rewrite leaves external paths and may map to files never copied. | Relocated bundle generates new image and video with original project tree unavailable; only declared base-model installations remain external. |
| D12 | P0 goal/consumption audits | Criterion 3 checks video file existence; 7 and 10 mostly check file presence; 9 accepts a bundle status flag. Runtime checks can accept recorded hashes without rehashing outputs. Voice consumption becomes true merely because an audio entry exists. | Missing, stale, forged, mismatched or unconsumed artifacts fail; each acceptance requirement backed by actual content and current runtime results. |
| D13 | P1 image evaluation | Current minimum metrics are feature-print distance, face detection and output hash; plan explicitly lacks prompt alignment, foreground similarity and pose adherence. Generic Apple Vision feature prints are not automatically a pinned face-recognition metric. | Full required identity/body/pose/prompt/anatomy/diversity/copying and resource metrics, representative script/negative prompts, comparable baselines, calibrated promotion. |
| D14 | P1 frame selection/coverage | Main annotations and separate visual-video manifest are different datasets. Existence of both does not show every eligible video frame has masks/captions/embeddings and split-safe selection. Script-aware ranking and segment-level overrides need audit. | Every selected still/clip/frame has required fields and lineage; no motion-only identity leakage; verified group splits and script relevance. |
| D15 | P1 controls/dependencies | USDZ renders have no compatible exercised FLUX structural route. Ingredients/Union/mask/multi-keyframe paths are incomplete. Installed node-file detection maps many classes to `nodes_lt.py` even when defined elsewhere. | Verify installed schema, actual model binding and enabled control behavior; disabled optional controls bypass exactly. No silent download. |
| D16 | P1 video executor/resume | No durable prompt handle is written immediately after submission; timeout can lose observation and permit duplicate work. Upload endpoint/schema needs live verification; generic output scanning can choose an image. Live runtime result is not reconciled into the canonical audited `video_runtime.json`. | Persist prompt/server/graph state before polling, resume same prompt, select actual video output, validate and publish canonical evidence without overwriting previous runs. |
| D17 | P1 full performance | Default graph is 49 frames at 24 fps, about two seconds. Keyframe is first source frame, not a promoted FLUX result. Cannot cover six-paragraph speech. | Script/shot timeline, generated identity keyframes, duration-aware segments, continuity/retiming and original-audio delivery of the full performance. |
| D18 | P1 CLI status | CLI converts many statuses other than blocked/incomplete/error/stubbed into outer `complete`; executor now returns `rendered_pending_validation`. | Explicit state vocabulary; pending quality evidence cannot appear as fully complete delivery. |
| D19 | P2 avatar prototype | Blend shapes are analytic offsets around an estimated mouth location; many visemes share crude displacement. PLY places a Gaussian-format record at each mesh vertex with constant scale/rotation and material fallback color. It is not trained multiview Gaussian reconstruction. | Validate facial anatomy/deformation, UV texture fidelity, calibrated cameras, correct splat conventions, reconstruction/render fidelity, animation/voice binding and playback. |
| D20 | P2 Unreal/scene consumer | UE installed; Metal compiler fails. A `.uproject` and plugin manifests do not prove asset import. No verified v4-bundle consumer was found in the inspected v3 Python code. | Supported UE import/playback and explicit Scene Factory adapter consuming bundle, shot timeline and Voice output; prerecorded editable take works. |

The workflow's generic graph validator checks link existence and nonnegative output
indices. It does not validate Comfy socket types, required parameters, cycles,
model-family compatibility or successful inference. Do not equate “compiled” with
“executable and compatible.” Current automatic promotion thresholds likewise do
not replace the full acceptance metrics required in the goal.

## 8. Voice manual completion and the review-policy conflict

Read [Voice/PLAN.md](/Users/voxels/SceneFactory/Voice/PLAN.md),
[Voice/CURRENT_STATE.md](/Users/voxels/SceneFactory/Voice/CURRENT_STATE.md), and
[Voice/AGENTS.md](/Users/voxels/SceneFactory/Voice/AGENTS.md) before editing that
package. These describe the existing manual procedure, not a completed automatic
Scene Factory voice stage.

Current reference choices are `max_data` (default, approximately 50-second
composite) and `short_clean`. The preferred max-data preview has a muffled middle.
The short-reference paragraph at `renders/paragraph_01.flac` is rejected. Preserve
it as comparison, never include it in a new final assembly by filename alone.
The `.aup3` edit and custom WAV are source/editor history and need explicit review
before substituting for the documented profile. Do not train on generated speech.

The package performs zero-shot Qwen3-TTS inference; it does not train voice weights.
The existing package advises against fine-tuning with this limited audio. Any
future voice training needs adequate clean, exactly transcribed speaker data and
a verified compatible training framework, separately from performance generation.

Manual takeover sequence, after preserving existing outputs and choosing the
intended profile consistently:

1. Inspect `scripts/stage_reference.sh`, `prepare_workflows.sh`, `submit_all.sh`,
   `collect_outputs.sh`, `assemble_final.sh`, and `validate_final.sh`.
2. Make run-specific output/collection paths before executing. Existing scripts
   have fixed names and overwrite behavior: submission truncates prompt IDs;
   assembly uses FFmpeg `-y`. They are not safe additive-merge tools as written.
3. Stage the chosen reference and its exact transcript; prepare six paragraph
   workflows from `inputs/tts_script.txt`; verify their model/settings and hashes.
4. Check queue, submit once, retain all six prompt IDs, collect matching outputs.
5. As a manual engineer, listen and replace only weak takes using versioned names.
   Verify wording, identity, clarity, continuity and absence of other speakers.
6. Assemble the selected takes with intended pauses, normalize as specified, and
   validate the master at `Voice/output/gage_final_master.flac`. Preserve takes and
   record which ones produced it. This authoring step may normalize audio; the
   subsequent Scene Factory consumer must preserve the resulting supplied master.
7. Repair the Voice resolver so the master, transcript and reference selection
   share hashes across preflight, ingestion, alignment and bundle packaging.
8. Implement an actual local word/phoneme/viseme aligner and bind timing into video
   and avatar consumers. No configured aligner currently exists in v4.

Policy conflict to resolve in code/docs: Voice package instructions require human
listening before final master creation, while the user's overarching default is
automatic completion without review. Manual review is appropriate for this manual
handoff; it must not become a permanent mandatory automatic-mode gate. Implement
mode-aware quality/promotion behavior and preserve user review decisions as evidence.

## 9. Local execution environment

| Component | Inspected location / condition |
|---|---|
| FLUX trainer | `/Users/voxels/ComfyUI-Installs/FLUX2-Trainer/diffusers/examples/dreambooth/train_dreambooth_lora_flux2_klein.py`; recorded commit `58eb52c0803ea9af3abec60841c2a093bdf1f951` |
| Trainer Python | `/Users/voxels/ComfyUI-Installs/FLUX2-Trainer/.venv/bin/python` |
| FLUX Base | `/Users/voxels/.cache/huggingface/hub/models--black-forest-labs--FLUX.2-klein-base-4B/snapshots/a3b4f4849157f664bdbc776fd7453c2783562f4d` |
| Comfy code | `/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI` |
| Live Comfy Python | Process used `/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI/.venv/bin/python3`; preflight separately probes `standalone-env/bin/python`, so reconcile environments |
| Shared models/input/output | `/Users/voxels/ComfyUI-Shared/models`, `/Users/voxels/ComfyUI-Shared/input`, `/Users/voxels/ComfyUI-Shared/output` |
| LTX weights | `/Users/voxels/Library/Application Support/LTXDesktop/models/ltx-2.5` contains transformer, video VAE, audio VAE |
| Combined encoder | `/Users/voxels/ComfyUI-Shared/models/text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors`; header confirms LTX video/audio aggregate projections |
| Motion adapter | `/Users/voxels/ComfyUI-Shared/models/loras/ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors`; compatibility still needs proof |
| Native LTX | Comfy `comfy_extras/nodes_lt.py` and `nodes_lt_audio.py`; KJNodes supplies advanced LoRA loader and video decoder |
| LTX trainer | Not found by current discovery. `SCENE_FACTORY_LTX_TRAINER_ROOT` can point to local code, but current wrapper still lacks a pinned invocation |
| UE | `/Users/Shared/Epic Games/UE_5.8`, recorded 5.8.2 / changelist 56702186 |
| Unreal project | `/Users/voxels/SceneFactory/v4/examples/modeling_interview/SceneFactoryV4.uproject` |
| Metal | `/Applications/Xcode-beta.app/Contents/Developer`; prior compiler probe says missing Metal Toolchain. Suggested Apple repair command is `xcodebuild -downloadComponent MetalToolchain`; this downloads a component and was not run for this handoff |
| Blender fallback | `/Applications/Blender.app/Contents/MacOS/blender`; user reported crashes; do not make it prerequisite for A/B completion |

No new dependencies were fetched for this handoff. The August document contains
historical research/license claims; independently verify the exact local artifacts'
licenses and compatibility before selecting another route. Do not infer a usable
LTX trainer or ControlNet from installed inference weights alone.

## 10. Recommended engineering order and exit criteria

1. **Freeze and reconcile evidence.** Snapshot code/config and small manifests;
   index model/data paths without moving originals. Resolve stale run status,
   authoritative plan hashes and known rejected takes. Add D01–D20 to the active
   backlog. Exit: each artifact has a purpose and evidence class, and reproduction
   cannot overwrite the history needed to judge it.
2. **Repair the runnable image path.** Reconcile existing graphs/checkpoints;
   reuse compatible completed cases. Add the missing acceptance metrics and
   bounded script-relevant proofs, then select a production route automatically
   under the declared quality criteria. Exit: new image from promoted LoRA and
   selected references, with comparative evidence. Do not retrain all three
   candidates unless results show it is necessary.
3. **Complete Voice and timing independently.** Use the manual procedure above,
   then implement consistent input selection and alignment. Exit: complete
   performance master, exact transcript and real timing, consumed by a tested
   downstream adapter. This work should not wait on geometry/UE.
4. **Repair LTX graph and trainer.** Fix loader/tensor/control semantics using
   installed code. Locate any suitable local trainer outside the narrow discovery
   list before concluding it is absent; if unavailable, record the exact external
   prerequisite without fetching it. Train/promote with real validation. Exit:
   short identity+motion+audio proof using the intended controls.
5. **Build full timeline and structural consumers.** Generate the authoritative
   identity keyframes, normalize trajectories and USDZ controls, add masks and
   compatible control combinations, segment to cover all dialogue. Exit: complete
   video with original audio and measured identity/motion/lipsync across segments.
6. **Complete the delivery integration.** Add missing stages and signatures to
   the orchestrator, publish verified runtime evidence, finish packaging and a
   Scene Factory consumer. Exit: relocated bundle creates a new image and video
   and the default run resumes correctly with no review interaction.
7. **Finish avatar track when runtime permits.** Correctly author/validate rig,
   textures and splat reconstruction; bind speech/expressions and verify UE import
   and editable prerecorded playback. Exit: demonstrated avatar fidelity and
   documented visionOS/SharePlay limitations. Preserve this scope while keeping
   it off the critical path for earlier A/B integration.

## 11. Verification and runbook

Handoff verification: full discovery completed with **85 collected tests passing
in 35.085 seconds**. This includes two compiler tests collected again through an
import in `test_video_executor.py`; 85 is the collection count, not 85 independent
acceptance requirements. No real Gage generation, training, model fetch or Voice
assembly was started for this handoff. Live queue was read without modification.
New loader/control findings were documented for takeover, not silently fixed.

Run from `/Users/voxels/SceneFactory`. Commands below are existing interfaces,
not a claim that production generation currently succeeds.

Read/test without starting generation:

```sh
cd /Users/voxels/SceneFactory
PYTHONPATH=v4:v4/tests python3 -m unittest discover -s v4/tests -p 'test_*.py'
PYTHONPATH=v4 python3 -m compileall -q v4
curl --max-time 10 -fsS http://127.0.0.1:8188/queue
```

Diagnostic CLI commands write derived reports; preserve the previous evidence
snapshot first. Exit 2 commonly means a reported blocker, not interpreter failure.

```sh
./v4/scene-factory-v4 preflight --project v4/examples/modeling_interview
./v4/scene-factory-v4 inspect-voice-flow --project v4/examples/modeling_interview
./v4/scene-factory-v4 validate --project v4/examples/modeling_interview
./v4/scene-factory-v4 audit-goal --project v4/examples/modeling_interview
```

Commands that rebuild/execute work: run only after repairing the relevant defects
and reconciling prior artifacts. Do not run this block as a blind checklist.

```sh
./v4/scene-factory-v4 benchmark-image-controls --project v4/examples/modeling_interview
./v4/scene-factory-v4 plan-image-evaluation --project v4/examples/modeling_interview
./v4/scene-factory-v4 evaluate-image-identity --project v4/examples/modeling_interview
./v4/scene-factory-v4 generate-image --project v4/examples/modeling_interview --prompt 'gage_identity, studio portrait' --seed 260801
./v4/scene-factory-v4 prepare-video-audio --project v4/examples/modeling_interview
./v4/scene-factory-v4 compile-video-workflow --project v4/examples/modeling_interview
./v4/scene-factory-v4 train-video-identity --project v4/examples/modeling_interview
./v4/scene-factory-v4 generate-video --project v4/examples/modeling_interview
./v4/scene-factory-v4 package-identity-bundle --project v4/examples/modeling_interview --destination /Users/voxels/SceneFactory/v4/examples/modeling_interview/build/identity_bundle
./v4/scene-factory-v4 run --project v4/examples/modeling_interview
```

Do not delete a lock, kill ComfyUI or submit a replacement job solely because a
poll timed out. Reobserve the same prompt/process. Add durable video prompt state
before relying on unattended execution. Tests using mocks and tiny fixture media
do not prove real model compatibility or fidelity; keep those proof layers separate.

## 12. Final acceptance checklist for the engineer

- [ ] Reconciled source registry retains original and derived provenance and all
  historical/rejected versions; excludes Koleka from every actual consumer.
- [ ] Every eligible selected image/video frame has verified masks, captions,
  landmarks/poses, identity features, script relevance and leakage-safe groups.
- [ ] Promoted image adapter is loadable against its pinned base/runtime model;
  references and a compatible geometry control are exercised in real generation.
- [ ] Real video adapter/training evidence or the goal's narrowly applicable,
  documented hardware/license exception; no stub/file-name substitution.
- [ ] Intended Ingredients/Union/Motion path actually consumes correct controls;
  identity keyframes and person masks reach the generation nodes.
- [ ] Complete Voice performance in the canonical destination, exact transcript,
  selected reference provenance and real word/phoneme/viseme timing.
- [ ] Full-duration generated video preserves the original performance stream;
  identity, motion, flicker, anatomy and lipsync meet recorded quality criteria.
- [ ] Independent representative held-out image/video evidence includes baselines,
  optional PuLID comparison, structural ablations and all required metrics.
- [ ] Rigged mesh and actual validated Gaussian representation, textures/normals,
  deformation, voice hooks and supported prerecorded/post-edit playback proven.
- [ ] Automatic orchestrator includes every required consuming stage, has no
  mandatory human-review gate, and resumes without duplicate jobs or stale reuse.
- [ ] Bundle matches the goal's full directory contract; relocated image/video
  generation works without undeclared paths into the original project or Voice.
- [ ] Scene Factory consumes that bundle and performance through a documented
  interface; exact model licenses, hardware and platform limitations are recorded.
- [ ] Strengthened completion audit rehashes/revalidates actual artifacts and
  agrees with this requirement-by-requirement review.

Only then should the overarching goal be closed. Finishing this handoff document
does not finish the identity pipeline.
