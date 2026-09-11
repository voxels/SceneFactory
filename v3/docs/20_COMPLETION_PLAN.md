# 20. Completion Plan

Specified 2026-08-30 (revised). Ordered plan to take Scene Factory v3 from "compiles correctly" to "generates and reviews real media." Consolidates the next-implementation order (07), the master checklist (10), the execution-status spec (19), **PuLID-Flux2 as the identity backbone**, and hardware-optimized model precision configs for Apple Silicon (96GB Unified Memory).

---

## Where we are (verified)

* **Definition + compilation layer works:** Python parses; `new` creates/validates/indexes/compiles a project; Ad2184 validates (7 scenes, 60s); compilation emits 21 keyframe + 21 video tasks on the 60s timeline; gates block tasks on missing media; full process planning + caption lifecycle pass.
* **Evidence:** 45 source images indexed; 45/45 structured captions valid (0 human-reviewed); 36 character-sheet graphs, 84 storyboard graphs, 168 portrait video tasks compiled; **0 completed native LTX clips; 0 completed full generation cycles.**
* **The read-only execution-status layer is implemented.** Generation remains incomplete until a real PuLID graph runs and a user approves its output.

---

## The core gap

Scene Factory plans and compiles perfectly but cannot prove it generates. Three surfaces already disagree on the same machine:

| Surface | Reports | Writer |
| --- | --- | --- |
| `build/pipeline_state.json` | everything blocked (`no source images`) | `prepare` |
| `run_comfy_phase.py` | posts graphs to ComfyUI | runner |
| ComfyUI `/queue` | a running LTX I2V job | ComfyUI |

Root cause: three writers answer the same question with different data. The fix is a single owned execution view derived from Scene Factory records + on-disk outputs, with **explicit human approval as the only thing that marks a stage complete.**

---

## Phase 0 — Safety: satisfied (no work item remains)

No live Comfy/LTX jobs are running, so the "wait for jobs to exit" gate is clear. Procedure for future sessions before a Comfy mutation (node install, restart, graph edit): confirm the `/queue` is empty, then record the Comfy core commit + custom-node dirs.

---

## Hardware & Environment Architecture Strategy

To prevent Unified Memory swapping and execution thrashing on Apple Silicon (96GB RAM), model loading and environment parameters are strictly constrained:

### Environment Variables & Process Offloading

* **ComfyUI RAM Flags:** Launch ComfyUI with `export COMFYUI_FLAGS="--highvram --disable-smart-memory"` to pin FLUX.2 Klein, Gemma 4, and LTX 2.5 in memory simultaneously.
* **Prompt & Vision Offloading:** Set `export PROMPT_PLANNER_URL="[http://127.0.0.1:8080/v1](http://127.0.0.1:8080/v1)"` to route vision captioning and prompt expansion to an external local `mlx-serve` instance running `Huihui-Qwen3.8-27B-abliterated-oQ4e-mtp`. This keeps LLM processing off ComfyUI VRAM and bypasses safety refusals on dystopian imagery.

### Quantization & Precision Profile

* **Captioning & Prompting:** Standardize `QWEN_VISION_MODEL_PATH` and `QWEN_VISION_PROCESSOR_PATH` to point to the unified 27B vision snapshot directory (`Qwen3.8-27B`) to resolve tokenizer path divergence.
* **Keyframe Generator:** FLUX.2 Klein 4B distilled executed in `fp16` or `Q8_0` (GGUF) to preserve fine facial geometry and skin details.
* **Video Generator:** LTX 2.5 DiT loaded in `fp8_e4m3fn` precision.
* **Video Text Encoder:** Gemma 4 12B loaded in `Q8_0` precision.
* **Frame Target Math (`mod8_plus1`):**
* Motion proofs (3s @ 24 fps): 73 frames (24 * 3 + 1)
* Extended clips (5s @ 24 fps): 121 frames (24 * 5 + 1)



---

## Identity strategy — PuLID-Flux2 (new)

PuLID-Flux2 gives native, ID-preserving generation for FLUX.2 from a **single reference face** without training. It extracts a face embedding (InsightFace) + visual features (EVA-CLIP) and injects them into FLUX.2 transformer blocks via `Apply PuLID ✦ Flux.2` using **Klein** weights (`pulid_flux2_klein_v2.safetensors`) at **strength 1.4**.

This turns identity from a hard prerequisite into a **tiered** capability:

| Tier | Method | Input | Use | Status |
| --- | --- | --- | --- | --- |
| 1 (immediate) | PuLID-Flux2 | one approved reference face | ID-faithful keyframes, character sheets, clip first-frames | source adapter implemented; runtime dependency absent |
| 2 (when ready) | K identity LoRA (FLUX.2 Klein) | ≥24 approved training imgs + validation set | full-body + finest fidelity, cross-shot consistency | planned (WS-B) |

* **Scope:** The human protagonist **K** uses PuLID for keyframe generation, character sheets, and first-frame video anchoring. Non-human subjects (masses, environments) retain standard conditioning.
* **Conditioning Masking:** LoRA and PuLID identity nodes apply exclusively to K's spatial/conditioning masks to prevent attribute transfer (e.g., preventing `BINDING_HELMET_ON_K` or enforcer armor bleeding).
* **Setup:** Install `ComfyUI-PuLID-Flux2` in `custom_nodes`; place `pulid_flux2_klein_v2.safetensors` in `ComfyUI/models/pulid/`; select one approved K reference face.

---

## Acceptance boundary (the milestone)

Do not call Scene Factory a media-generation app until **at least one compiled task completes through ComfyUI and produces a reviewed (human-approved) output.**

> **Milestone:** one PuLID-conditioned K keyframe → ComfyUI → human-approved output.

Current runtime blocker (verified 2026-08-31): the configured ComfyUI installation does not contain `ComfyUI-PuLID-Flux2`, and `models/pulid/pulid_flux2_klein_v2.safetensors` is absent. Installing third-party executable code requires explicit operator approval. The compiler and API graph are implemented and tested, but the milestone has not run.

---

## Workstreams

### WS-A — Execution layer (critical path)

#### Phase 1 — Execution core

* [x] Define the stable **adapter interface**: one compiled task → one versioned ComfyUI API workflow; validate it before runner execution.
* [x] Wire `execution_status.py` into `scene_factory.py` as read-only `execution-status <project>` with optional `--live`; resolve ComfyUI from `project.json` and report queue → execution records → on-disk outputs.
* [x] Add `schemas/execution.schema.json` with status enum: `not_started | ready | active | complete | blocked | failed | needs_approval`. Do **not** reuse `pipeline.schema.json`'s status.
* [x] Add `build/execution/comfy_state.json` (runner job log), written by `run_comfy_phase.py` only.
* [x] Add output records + human approval states: `build/review/storyboard_selections.json`, `build/review/motion_proof_reviews.json`, `reviews/episode_artifact_review.json`.
* [x] Fix the `refresh_state` bug: `pipeline-status` no longer rewrites `pipeline_state.json`.
* [x] Reconcile surfaces: `pipeline_state.json` = persisted preparation state; `execution-status` = generation view; `pipeline-status` = read-only intake + generation rollup.
* [x] Register project runtime defaults (`--highvram`, `--disable-smart-memory`, `PROMPT_PLANNER_URL`) for new projects.
* [x] Inject the exact issue codes from `project.json`'s `production_constraints` block into the Qwen system-prompt contract and strict JSON response schema; reject invented codes before keyframe graph generation.

#### Phase 2 — Generation adapters (PuLID-led & hardware-optimized)

* [x] **PuLID-Flux2 identity adapter:** map character-sheet and keyframe tasks to the upstream `ApplyPuLIDFlux2` API graph (Klein model + approved K reference + prompt, strength 1.4); approved results become clip first frames.
* [x] **FLUX.2 Klein key-frame adapter:** PuLID-conditioned for K with owner-only prompt/negative-attribute scoping.
* [x] **FLUX.2 Klein LoRA training adapter:** Tier 2 script fails closed until the full reviewed training and validation sets are ready.
* [x] Fixed LoRA **validation grids** + user-only promotion records via `lora-validation-build`.
* [ ] Repair + validate local **LTX 2.5** install — compatible nodes, `fp8_e4m3fn` DiT weights, `Q8_0` Gemma 4 text encoder.
* [x] **LTX image-to-video adapter:** first frame = approved PuLID keyframe; 24 steps; CFG 3.25; `fp8_e4m3fn` DiT loading; enforce `mod8_plus1` frames (73 frames for 3s proof, 121 frames for 5s clip).
* [x] Job **monitoring, explicit-failure retry rules, retained per-attempt logs**; timeouts fail closed and are never automatically duplicated.
* [x] Ship a per-project runtime dependency manifest listing ComfyUI-PuLID-Flux2, ComfyUI-LTXVideo, and ComfyUI-Impact-Pack, and require `--exclude "transformer_full/*"` when downloading LTX-2.5-Diffusers.
#### Phase 3 — Assembly + interface

* [x] Final **assembly** + post-production records: `build/rough_cut/*.mp4` + `*.json`, with user approval required for completion.
* [ ] **Non-technical local interface** over project files.

---

### WS-B — K identity & Vision Pipeline (human-gated, parallel)

**Immediate (PuLID Tier 1):**

1. [x] Align `QWEN_VISION_MODEL_PATH` and `QWEN_VISION_PROCESSOR_PATH` in the Ad2184 project and new-project template to the same 27B model snapshot directory.
2. [x] Bind PuLID to K's existing issue-free, user-approved canonical seed and stage that exact source into the Comfy input namespace during preflight.

**Tier 2 — full K LoRA (12-step content plan):**

1. Face-detection, K face-match, full-subject-mask, isolated-derivative stage.
2. Remove forced `mid-20s` caption text; add reviewed apparent-life-stage metadata.
3. Controlled K character-label contract + balance report.
4. Isolate or reject the 32 group images.
5. Select the final adult reference cluster for K.
6. Approve ≥24 training images + a separate validation set.
7. Train + validate the K FLUX.2 Klein LoRA.
8. Generate + approve the complete K character sheet.
9. Generate + approve storyboard + production key frames for all formations.
10. Run one 5s + one 10s LTX 2.5 portrait clip.
11. Assemble one complete scene sequence.
12. Update all guides + run clean manual verification procedure.

---

### WS-C — Voice clone (sandbox-blocked)

* [ ] Finish Qwen3-TTS 1.7B Base weight download (~4.5GB).
* [ ] Run `./stage_into_comfy.sh` from Terminal (bypasses sandbox write restrictions on `custom_nodes` / `ComfyUI-Shared`).
* [ ] Register nodes in the live Comfy process; verify `qwen3_base_clone_f5_ab` workflow loads.

---

## Recommended order (critical path to the milestone)

1. **Phase 1 Execution Core:** Adapter interface + `execution-status` + execution schema + approval records + `refresh_state` fix + environment export flags.
2. **PuLID Setup:** Install `ComfyUI-PuLID-Flux2`, place `pulid_flux2_klein_v2.safetensors` in `models/pulid/`, select one approved K reference face, align Qwen 27B paths.
3. **Phase 2 First Item:** PuLID-Flux2 identity adapter (keyframe, PuLID-conditioned, `fp16`/`Q8_0` Klein).
4. **Run One Keyframe:** Pass K keyframe through ComfyUI (PuLID) → human reviews → approval record. (**Milestone achieved**).
5. **Parallel Expansion:** Proceed with Phase 2 LTX adapters (`fp8_e4m3fn` + `mod8_plus1`), WS-B Tier-2 LoRA training, and WS-C voice clone.

---

## Risks / caveats

* **Human review is the gate:** Every `complete` status and WS-B approval requires a human. The agent prepares artifacts + records but cannot self-approve.
* **PuLID is face-focused:** It locks facial identity from one reference; full-body/wardrobe/pose consistency across multi-shot sequences still requires the Tier-2 LoRA. Maintain strength at 1.4.
* **Prop Geometry Guardrails:** FLUX models can duplicate hammer heads. Implement depth-guided ControlNet or rigid-body pass on the hammer prop.
* **Sandbox limits:** Voice clone staging, pip/venv, and writes outside the project directory are TCC/ACL-blocked; operator must execute these in Terminal.
* **Stale build files:** Build outputs go stale after source edits; re-run index + compile.
* **Schema drift:** The program uses its own semantic validator; keep schemas synchronized.
* **ad2184_v1 adapter:** Uses fixed duration mapping for current 7-shot shape; generalize before reusing for external scripts.

---

## Definition of done (v3)

Scene Factory v3 is complete when one full Ad2184 scene sequence is generated (PuLID-identity keyframes → LTX 2.5 clips → sequence assembly) with every stage carrying an explicit human approval record, a rough cut assembles from approved clips, `execution-status` is the single trusted view, and memory flags keep multi-model inference stable within the 96GB Unified Memory buffer.
