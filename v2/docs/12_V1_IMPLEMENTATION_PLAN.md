# V1 Reference Reconstruction Implementation Plan

This checked task list implements the authoritative decisions in [Ad2184 Semantic Resource Review Manual](11_SEMANTIC_RESOURCE_REVIEW.md).

An item is complete only when its acceptance condition is demonstrated by code, generated records, or automated tests. Documentation alone does not count as implementation.

## Definition of done

Starting from a clean v1 build, Scene Factory can ingest the declared reference video, derive source-grounded contracts and tracking tasks, compile a reference-faithful master plus approximately three-times-duration optional coverage, produce separable visual-only layer plans, and admit material to the post-production pool only through explicit user approval.

## Phase 1: authoritative configuration

- [x] Add `reference_reconstruction` to the project schema.
- [x] Encode the source-authority matrix for K, workers, enforcers, hammer, environments, camera, and story beats.
- [x] Configure `coverage_multiplier: 3.0`.
- [x] Configure `audio_policy: strip_and_ignore`.
- [x] Configure `approval_authority: user_only`.
- [x] Configure master coverage and automatic narrative-bounded alternate POV coverage.
- [x] Validate contradictory authority, audio, coverage, and approval settings as errors.

Acceptance: valid Ad2184 configuration passes; deliberate policy contradictions fail with specific errors.

## Phase 2: reference ingestion

- [x] Resolve the external reference without modifying or duplicating it.
- [x] Record SHA-256, duration, dimensions, frame rate, and stream inventory.
- [x] Map narrative shots to approximate ordered source ranges.
- [x] Extract deterministic start, action, and end frames for each master shot.
- [x] Record timestamps, hashes, shot IDs, and resource tags.
- [x] Write `build/reference/reference_manifest.json`.
- [x] Write frames under `build/reference/frames/`.
- [x] Emit no audio artifact.

Acceptance: a clean build produces the same reference manifest and frame hashes for the same source.

## Phase 3: automatic visual contracts

- [x] Create vision-analysis tasks for extracted reference frames.
- [x] Derive contracts for wardrobe, workers, enforcers, hammer, environments, camera, lighting, blocking, and screen state.
- [x] Keep K identity/body/hair separate from reference-performer identity/body/hair.
- [ ] Merge only reference wardrobe, pose, and movement into K's production contract.
- [x] Attach source-frame and timestamp provenance to every derived field.
- [x] Compare derived and written contracts.
- [x] Block generation on unresolved disagreement or a stale disagreement audit.

The 21 current tasks were completed by an interactive multimodal review of all seven
three-frame contact sheets, not by the configured local Qwen runtime. The task results
identify that provider and explicitly record `local_qwen_executed: false`; the configured
Qwen snapshot directories were absent on 2026-08-26. Future local execution is available
through `reference-contract-run` when those weights are restored.

Acceptance: no production field lacks source authority and no cross-subject flattened attribute list exists.

## Phase 4: tracking

- [ ] Extract the reference performer's body-pose track.
- [ ] Retarget it to K's proportions.
- [ ] Preserve timing, balance, joint intent, and screen-space trajectory.
- [ ] Create direct video-guidance tasks for worker and enforcer groups.
- [ ] Produce one hammer rigid-body track across held, release, flight, and impact.
- [ ] Record the hammer ownership-transfer frame.
- [ ] Track the speaker screen's four planar corners.
- [ ] Record the screen-destruction boundary.

Acceptance: normalized tracking records cover every required master range and contain no audio dependency.

## Phase 5: master and alternate coverage

- [x] Compile one reference-faithful master task per source shot.
- [x] Preserve story-beat order and relative rhythm.
- [x] Permit approximate cut points.
- [x] Compile automatic alternate POV tasks within the existing narrative.
- [x] Mark alternate POVs as optional creative coverage, never repair material.
- [x] Allocate approximately 60 seconds to master coverage.
- [x] Allocate approximately 120 seconds to alternate coverage.
- [x] Report approximately 180 seconds total planned coverage.

Acceptance: the 60-second project compiles distinct master and alternate budgets totaling approximately 180 seconds.

## Phase 6: render-layer compilation

- [x] Compile environment plates.
- [x] Compile workers as group layers where visible.
- [x] Compile enforcers as coordinated group layers separate from K.
- [x] Compile K with K identity/hair, reference wardrobe, and retargeted-motion authority.
- [x] Keep held hammer inside K's layer.
- [x] Compile released hammer as its own layer.
- [x] Compile only necessary convenience-occluder layers.
- [x] Require mattes or alpha for foreground layers.
- [x] Record layer ownership, z-order, source range, and planned output path.
- [x] Require foreground lighting, lens, grain, and motion blur to match the plate.
- [x] Do not require separate shadow or reflection passes.

Acceptance: no task contains both K and enforcer appearance conditioning; hammer ownership changes exactly once.

## Phase 7: green insert and post graphics

- [ ] Emit a tracked chroma-green planar insert for the projected speaker screen.
- [ ] Match perspective, movement, and occlusion.
- [ ] Prevent generated imagery, reflections, and external green spill.
- [ ] Shatter and remove the insert with the screen.
- [ ] Reserve final title and logo for post only.

Acceptance: the insert has valid corners until impact and no plane after destruction; no prompt requests final text or logo.

## Phase 8: visual-only generation

- [x] Remove audio inputs and audio latents from generated LTX API graphs.
- [x] Remove audio VAE/model requirements.
- [x] Strip audio from reference proxies.
- [x] Keep rough-cut generation video-only.
- [x] Fail tests when a generated workflow contains an audio node or stream.

Acceptance: generated workflows and outputs require and contain no audio.

## Phase 9: post-production manifest

- [x] Emit planned layer paths, mattes, transforms, z-order, and source ranges.
- [x] Emit K skeleton and hammer track references.
- [x] Emit convenience-occluder metadata.
- [x] Emit green-insert corner-track references and destruction lifetime.
- [x] Emit master/alternate classification and duration budgets.
- [x] Emit dependency hashes for invalidation.

Acceptance: an editor can reconstruct a shot without inferring layer ownership or timing.

## Phase 10: user-only approval

- [x] Require `approved_by: user` for post-production admission.
- [x] Reject missing, automated, or non-user approval values.
- [x] Keep still, motion-proof, extension, and composite decisions separate.
- [x] Invalidate descendants when a source frame, contract, track, layer, or selected artifact changes.

Acceptance: no artifact enters the post-production pool without an explicit user approval record.

## Phase 11: regression and end-to-end verification

- [ ] Test source-authority validation.
- [x] Test deterministic frame-manifest generation.
- [x] Test K/reference identity exclusions in reference-analysis tasks.
- [x] Test K/enforcer layer separation.
- [x] Test held/released hammer ownership.
- [x] Test three-times coverage allocation.
- [x] Test green-insert lifetime.
- [x] Test absence of audio nodes and reference audio artifacts.
- [x] Test user-only approval.
- [x] Run the complete test suite (41 tests passing on 2026-08-25).
- [x] Compile Ad2184 and inspect the generated reference, generation, and post-production manifests.

Acceptance: every phase acceptance condition passes and no unchecked blocker remains.

## Production tracking and control stack

The Swift/Vision tools in `tools/` are bounded fallbacks and QC utilities. They do not, by themselves, satisfy the production skeleton-retargeting or four-corner planar-tracking requirements.

| Need | Production choice | Required action | Role of local Swift tool |
|---|---|---|---|
| K whole-body skeleton | Core Comfy `SDPoseKeypointExtractor` with `sdpose_wholebody_fp16.safetensors`; RT-DETR person boxes for difficult/multi-person frames | Acquire the two missing weights, persist joint confidence/timestamp JSON, associate and smooth K's track | Fallback pose evidence and independent QC |
| K motion transfer | Official Lightricks LTX motion-track IC-LoRA | Repair the official LTX custom-node checkout, acquire the motion-track IC-LoRA, convert selected joints to reviewed sparse tracks | No replacement; can compare source joints |
| Worker/enforcer motion | Direct reference-video guidance, with SDPose/depth evidence only where useful | Use group-level guides; do not rig every background person | None |
| Hammer | Core SAM3.1 video tracking followed by project-owned rigid centroid/rotation fitting | Acquire SAM3.1 checkpoint; review the object seed around release/impact | Bounding-box fallback only |
| Screen insert | Dedicated four-corner planar homography tracking in post | Export per-frame quad, confidence, and destruction boundary | Current box tracker is initialization/QC only, not final corners |
| Occlusion/depth | Core Depth Anything 3 and SAM3.1 masks | Acquire tested weights; treat mono depth as relative, not measured scale | None |
| Temporal QC | Core RAFT optical flow, optional | Use for drift/edge metrics, never as object identity | None |

### Comfy Manager policy

- Prefer current Comfy core for SDPose, SAM3.1, Depth Anything 3, BiRefNet, RAFT, masks, and compositing.
- Repair and pin only the official `Lightricks/ComfyUI-LTXVideo` package before using IC-LoRA controls.
- Disable or remove `comfyui-ltxvideo-registry-mattabyte`; it currently fails against the installed core API.
- Do not add `ComfyUI-LTXTricks` or a broad preprocessor megapack.
- Keep KJNodes and VideoHelperSuite as optional I/O helpers, not API-workflow dependencies.
- Add weights capability-by-capability and record filename, source, checksum, license, tested workflow, and rollback commit.

## Progress summary

| Phase | Status | Blocking evidence |
|---|---|---|
| 1. Configuration | Implemented | Add a deliberate contradiction regression test before closing acceptance. |
| 2. Reference ingestion | Implemented and run | Actual source: 60.04s, 1280×720, 25 fps, SHA-256 `d6d3014b…`; 21 PNG evidence frames, no audio artifacts. |
| 3. Visual contracts | Implemented with reviewed fallback | 21/21 tasks complete; 14 aggregate contract types carry field-level frame/hash/timestamp provenance. The local Qwen snapshots are absent, so the recorded provider is interactive multimodal review rather than local Qwen. K production-contract merge remains. |
| 4. Tracking | In progress | Swift fallback tools compile; production SDPose/LTX/SAM3/homography stack still needs weights and workflow wiring. |
| 5. Coverage | Implemented | 7 master tasks/60s plus 21 alternate tasks/120s = 180s planned. |
| 6. Render layers | Implemented at plan level | Actual rendered mattes/composites remain generation work. |
| 7. Green insert | Planned | Layer lifetime/shatter policy and track paths exist; actual corner tracks/composite remain. |
| 8. Visual-only | Implemented | Native LTX graph, requirements, reference extraction, and assembly are video-only. |
| 9. Post manifest | Implemented at plan level | Planned paths and dependencies are explicit; generated assets/tracks remain pending. |
| 10. Approval | Implemented | Runtime fingerprints now invalidate transitive contract, track, layer, and artifact descendants; user approvals remain intentionally pending. |
| 11. Verification | In progress | 55 tests pass; production render and user-approval proofs are not yet complete. |
