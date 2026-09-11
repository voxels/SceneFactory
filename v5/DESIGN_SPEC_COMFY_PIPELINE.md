# Comfy Pipeline — Design Spec (Cezar teaser, v5 execution layer)

**Status:** design + metadata-layer implementation. Nothing here generates video.
**Stop point it resumes from:** 2026-09-11 05:31 EDT — the parallel web-generation
path died on `policy_denied` / HTTP 403 with no retry or redirection attempted.
That stall is the failure this spec is built to never repeat.

## 1. Source of truth

- Archived workflows: `~/workspace/your_files/cezar-comfy-workflows/`
  (A identity proof, B env reference, C event-take template ×4, D assembly).
- Run spec: `teaser_kit/COMFY_RUN_SPEC_ROUGHCUT.md`. IDD contracts:
  `teaser_kit/IDD_CONTRACTS_ROUGHCUT.md` (8 stages S0→S7; Impl A = agent Python,
  Impl B = his Comfy graph; compare + mix).
- Repo execution-layer rule (docs/22): **Scene Factory owns manifests and
  approvals; ComfyUI executes generated API graphs.** A file on disk is not an
  approval. Only the operator may approve identity or production media.
- Status truth (docs/19): authority order — user review JSON → compiled
  plans/graph manifest → runner job log → files named in the log → optional
  live Comfy queue overlay. Status is derived on read, read-only.

## 2. The pipeline A → B → C → D

### A — Identity proof (Mac, ComfyUI + LTX-2, GPU)
One face-visible held-pose still → ~4 s clip with the trained Cezar LoRA
(`workflow_A_identity_proof.json`). **Gate: his eye on the identity output.**
Nothing proceeds until this passes. Automated pre-filter (see §4) may screen,
but only his review JSON (`decision`, `approved_by: user`, `issues: []`) can
mark it approved.

### B — Environment reference (Mac, camera-comfyUI pack)
Separated environment splats (Stage B0: SAM3 text-prompted subject/environment
separation — manual, before B) rendered along the 4-lobe camera loop →
depth/mask/camera sequences (`workflow_B_env_reference.json`). Output is
conditioning data for every C take. Label all output PREVIZ.

### C — Event takes ×4 (Mac, LTX-2 + LoRA + depth/pose conditioning)
One template instantiated per event (`workflow_C_event_take_template.json`),
`EVENT_TOKEN`/`EVENT_FOLDER`/`EVENT_PROMPT`/`SHOT_FRAMES` substituted from
`manifest_shots.json` (138 shots, 4 events). Per-shot frame counts from the
manifest; `noise_seed` varies per take. **Every take is identity-gated before
acceptance; failures are discarded, never fixed in post.** Held poses only
until skeleton takes land — no invented motion, ever.

### D — Assembly (Mac, ffmpeg)
`assemble_reel.sh`: cut accepted takes to shot durations, concatenate in shot
order, scale 768×1344, mux the 424 s Thin White Duke soundtrack. No color
treatment of any kind. Blocked until every shot has an accepted take; a
missing take is a hard, named failure, not a silent skip.

## 3. Conditioning wiring

| Stream | Source | Path into generation |
|---|---|---|
| Environment geometry | 7 PLY splats (66.1 MB each, on his Mac) | B0 SAM3 separation → `LoadPlySplat` → `RenderSplat` along loop → depth/mask/camera sequences |
| Environment mesh | USDZ beach meshes | USDZ → GLB → scene conditioning (his side) |
| Character identity | v3 identity impression + trained Cezar LoRA (37-image set, his authority) | `LoraLoader` (strength 0.8–0.9) + reference still |
| Character motion | Skeleton takes (future) | Motion driver slot in C when they land; held poses until then |
| Camera | `camera_path_4cezar_loop.npy` (1200 samples) | `convert_trajectory.py` → trajectory JSON → `CameraTrajectoryNode` |

## 4. Approval gates

Two layers, in order:

1. **Automated identity pre-filter** (metadata layer, here or Mac):
   v3 impression `cezar_id_impression.npy` + `.json`. Cosine distance bands:
   HOLDS `d < 0.45`, DRIFTS `d < 0.65`, NO MATCH `d >= 0.65`.
   NO MATCH takes are rejected before they reach his eyes. DRIFTS are flagged
   for his attention. The pre-filter is **diagnostic**: it may reject, never
   approve.
2. **User-eye gate** (his Mac, review surface): only a user review JSON with
   `decision: approved`, `approved_by: user`, empty `issues` moves a take to
   approved. **USER ATTRIBUTION OVERRULES THE MODEL, no exceptions** — the
   action footage is Cezar by his authority; rejected media is kept as
   negative training data, never deleted.

The follow-up review UI (his 16:02 ruling): a ComfyUI app for fine-tuning
references across media types. Input contract: impression `.npy` + manifest
`.json`, gate bands, read-only rules (see `face_id/v4_rebuild/REVIEW_UI_CONTRACT.md`).

## 5. Refusal-with-redirection loop (the 05:31 lesson)

Standing rule: **a refusal must come with redirection.** The 05:31 web-generation
attempt died on `policy_denied` with no retry and no debug — that is the failure
mode this loop exists to kill.

When a generation is refused (policy filter) or fails the identity gate:

1. **Record** a refusal entry: kind (`policy` / `identity_gate` / `execution`),
   the request as sent (prompt, conditioning, reference), the refusal signal,
   attempt number.
2. **Debug the content into an acceptable request.** Adjustment ladder, in order:
   - Strip or rephrase flagged prompt terms (keep `same man as reference`
     phrasing; identity comes from LoRA + reference, not words).
   - Swap the reference still (face-visible held pose; sunset silhouettes fail
     identity — pick a face-visible frame).
   - Lower LoRA strength (0.85 → 0.7) if the face drifts; raise if identity
     is weak.
   - Reduce denoise (< 1.0 preserves reference structure).
   - Drop optional conditioning (pose/canny) and retry depth-only.
   - Split the shot: shorter take, reframe the camera move.
3. **Retry** the adjusted request. Bounded: max 3 debug attempts per take.
4. **Never stall.** If the ladder is exhausted, escalate: hand him the full
   debug log (every attempt, every adjustment, every refusal signal) and the
   recommended next manual move. Silence is not an option.

The refusal log is part of the take manifest — rejected media stays as
negative training data with its refusal record attached.

## 6. Manifests (Scene Factory owns these)

- **Shot manifest** (`manifest_shots.json`): 138 shots, per shot start/duration/
  event/frustum support/risk flag/POV. Honest split noted: event_01 0/40
  supported, event_03 5/40, event_04 16/42, event_02 14/16. Rebalancing toward
  SUPPORTED is his decision.
- **Take manifest** (per accepted take): event, shot index, start_sec,
  duration_sec, camera sample range, LoRA version, skeleton_take (null until
  they land), gate verdict, review record, refusal history if any.
- **Graph manifest** (`build/comfyui/full_visual_graph_manifest.json` per
  docs/19): compiled A/B/C graphs, versioned, one compiled task → one
  ComfyUI API workflow (`scene_factory.comfyui_api_workflow` v1).
- **Review JSON**: `decision`, `approved_by: user`, `issues: []` — the only
  thing that can mark approved.

## 7. Assembly EDL

Generated from shot manifest + accepted take manifests: ordered cut list,
source take file per shot, in/out durations, gate state. A missing take for
any shot blocks assembly with the shot named — matching `assemble_reel.sh`.

## 8. Where things run

| Here (metadata layer, this machine) | His Mac (ComfyUI, GPU) |
|---|---|
| Graph builders/validators (A/B/C vs archived JSONs) | Queue + execute all graphs |
| Manifest schemas + validation | LoRA training (or the 3080 Ti PC after the Mac proof) |
| Identity pre-filter (embeddings vs v3 impression) | Identity proof run + user-eye gate |
| Refusal-redirection loop logic + refusal log | Manual debug steps the loop escalates |
| Assembly EDL generation | `assemble_reel.sh` execution |
| Status derivation (docs/19 authority order) | Live Comfy queue (optional overlay) |

## 9. Blocked on his side (unchanged)

- Identity proof run on the Mac (then PC LoRA training).
- Skeleton takes (motion driver for C; held poses until then).
- USDZ inputs for environment conditioning (post-training identity with
  existing USDZ inputs is the known unfinished piece).
- Push of v5 commits to GitHub (his step).
- Live ComfyUI verification of everything here.

## 10. Non-goals

- No video generation here — validated graphs, manifests, gates, EDLs only.
- No color treatment, ever.
- No invented motion — strictly skeleton-tracked, held poses until takes land.
- No fourth database; status derived on read per the authority order.
