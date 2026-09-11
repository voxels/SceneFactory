# v4 completion goal prompt (execution contract)

Work in `/Users/voxels/SceneFactory` and complete the identity example at
`v4/examples/modeling_interview`. Treat existing v4 code as an ingest foundation,
not proof of completion. Continue until a fresh automatic run produces validated
image and video outputs and a reusable `identity_bundle/`.

The ultimate delivery target is an Unreal Engine-authorable, pre-recordable avatar
that can be retimed and tweaked in post-production. Prefer Unreal Engine 5.8 for
rigging, Control Rig, animation, material, playback, and delivery integration once it
is installed; use Blender only as a documented fallback for USD/USDZ conversion or
canonical control rendering. Record the exact UE build/plugins and do not claim
native visionOS Persona/SharePlay support without a runtime validation.

The existing stable CLI, fail-closed validation, Koleka exclusion, provenance,
mask/pose/caption extraction, coverage selection, immutable splits, reference bank,
motion-frame extraction, USDZ rendering, dataset export, MPS preflight, consent
record, and contract tests are part of the required foundation. Preserve them and
re-run their evidence after architectural changes; do not replace them with a
manifest-only shortcut.

## Hard requirements

- Exclude Koleka media and every derivative, with a negative test.
- Automatic mode is fully unattended; review gates exist only in `fine_tuning` mode.
- Verify contractual consent before any training or generation and fail closed if it
  is missing, revoked, or mismatched.
- Preserve immutable sources and record SHA-256, provenance, processing/model versions,
  timestamps or USDZ member paths, and derivative lineage for every consumed artifact.
- A modality is consumed only when a hashed derived artifact reaches a real trainer or
  executing inference node. Manifests alone do not count.
- Account for every configured source class explicitly: still images, web archives,
  visual-identity video, motion-reference video, voice/TTS audio, and USDZ assets.
- PuLID is never the sole or assumed identity solution. The primary identity harness is
  a trained subject adapter fused with native multi-reference conditioning and tested
  structural controls; PuLID may remain only as a separately measured face-anchor
  ablation and may not be required for production promotion.

## Required implementation

1. Finish and resume-safe the bounded FLUX.2 bakeoff: Klein 4B subject LoRA, native
   multi-reference, compatible RefControl depth, optional PuLID, and eligible 9B/dev
   ControlNet branches. Record license/hardware eligibility and select a winner using
   fixed prompts/seeds and held-out identity metrics. Every trained adapter must have
   a loadability check, SHA-256, configuration, trainer commit/model hashes, logs,
   completion marker, and model card.
2. Keep video roles separate: visual-identity frames feed image identity; motion clips
   feed motion/control training; voice-performance media feeds audio only. Scene-split
   and group derivatives to prevent leakage. Persist the extracted image frames and
   retain short clips only for temporal/video training.
3. Process still images and web-archive media through the same provenance-aware
   annotation path. Validate masks, alpha cutouts, face crops/landmarks, skeleton
   tracks, captions, clean-shot relevance against the configured input script, and
   coverage-constrained selection. Emit auditable pass/reject reasons and ensure
   selected annotations—not just their source files—are consumed by training or
   inference. Use masks in filtering, references, metrics, and spatial controls;
   implement a tested foreground loss only if the chosen trainer actually supports it.
4. Process USDZ files into verified geometry-derived controls (depth, normals,
   silhouette, and camera metadata as available). Connect those controls to a
   compatible RefControl/ControlNet or other structural inference/training node, or
   record an explicit compatibility failure with no silent fallback. USDZ presence in
   a manifest alone is not sufficient.
5. Compile real API workflows whose graph connectivity is machine-checked for base,
   reference, LoRA, RefControl/ControlNet, PuLID, LTX Ingredients/Union/Motion,
   masks, and multi-keyframe routes. Unavailable routes must fail explicitly.
6. Train/validate/promote a real LTX 2.5 identity LoRA, generate an authoritative
   identity keyframe, and produce a motion-controlled video with per-frame identity,
   drift, pose, flicker, and lip-sync measurements.
   Pin the official trainer commit/release and matching text/vision encoders, and
   record their hashes and licenses in preflight.
7. If `voice/` contains supplied TTS audio, use that exact waveform (hash before/after),
   align phonemes/visemes, and mux it into the final video; never synthesize a substitute.
8. Produce Persona-oriented avatar deliverables for each character: (a) a rigged
   talking-head mesh in a validated USDZ package containing geometry, skeleton/skin
   weights, facial blend shapes and visemes, UVs, textures, normals, materials, camera
   calibration, and voice/viseme timing references; and (b) a matching Gaussian-splat
   head with calibrated scale/origin/cameras and a documented visionOS-compatible
   delivery path where supported. Both representations must be traceable to the same
   identity evidence and independently checked for identity, expression coverage,
   texture/normal fidelity, and lip-sync timing. Support pre-recorded playback and
   post-production retiming/tweaks. Do not claim native visionOS 27 Persona or
   SharePlay equivalence without an Apple-supported runtime validation; document any
   integration boundary explicitly.
   Author and validate these assets through the preferred Unreal path when available,
   including Control Rig-compatible skeletons, animation curves, blend-shape/viseme
   channels, material instances, and deterministic import settings. If Unreal is not
   installed, fail the avatar-delivery stage with an actionable dependency report;
   do not silently mark a Blender-only render as the final runtime deliverable.

## Acceptance tests

`scene-factory-v4 run --project v4/examples/modeling_interview` must succeed without
review and emit loadable adapters, connected workflow JSON, image/video outputs,
metrics, logs, and a self-contained identity bundle. Tests must cover checkpoint
loadability, exact adapter bypass, graph links/model filenames, modality consumption,
Koleka exclusion, split isolation, restart/resume, audio byte preservation, and a
full automatic-run smoke. Image evaluation must report identity similarity and
detection rate, foreground similarity, pose/silhouette adherence, prompt alignment,
anatomy, diversity, copying, runtime, and peak memory. Documentation must map every source modality—including
web archives and USDZ-derived controls—to its exact derived artifact, trainer or
inference consumer, and evidence file; clearly list any intentionally unavailable
route and prove that it did not silently degrade to text-only generation. The final
bundle must include the rigged USDZ and Gaussian-splat avatar artifacts, rig/blend-shape
and viseme manifests, calibration metadata, playback/post-production instructions,
and an explicit report of what was and was not validated against visionOS 27
Persona/SharePlay.
