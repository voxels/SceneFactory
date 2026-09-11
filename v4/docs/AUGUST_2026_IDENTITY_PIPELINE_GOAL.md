# Scene Factory v4 identity pipeline: August 2026 research and goal prompt

Research cutoff: 2026-08-31

## Research conclusion

The original v4 prototype was not a complete identity pipeline: it only inventoried,
extracted, scored, and selected evidence. The current implementation has advanced
beyond that baseline: it trains and audits three local FLUX.2 Klein image LoRA
candidates, compiles executable base/native-reference/PuLID and LoRA graphs, and
produces hash-verified image evaluation artifacts. It is still not a finished
identity delivery because held-out promotion, the LTX video trainer/output path,
authoritative audio alignment, and final bundle validation remain open.

PuLID should not be the foundation of this identity. The August 2026 FLUX.2 PuLID
port is an inference-time face adapter using InsightFace and EVA-CLIP. It is useful
as an optional facial anchor, but its own project reports that training scripts were
removed because of instability and lists body consistency as future work. This does
not match a corpus containing many photographs, visual-identity videos, full-body
evidence, web archives, USDZ geometry, motion footage, and audio.

The recommended identity stack is:

1. A subject-specific FLUX.2 Klein DreamBooth LoRA trained on the undistilled Base
   checkpoint, using the official Diffusers FLUX.2 Klein trainer.
2. Native FLUX.2 multi-reference conditioning from a deliberately selected reference
   bank. All official FLUX.2 Klein variants support multi-reference editing.
3. A separately evaluated structural-control path:
   - FLUX.2 Klein 9B RefControl LoRAs currently cover reference + pose, depth,
     canny, lineart, and normals.
   - FLUX.2 Klein 4B RefControl currently covers reference + depth only.
   - Alibaba's FLUX.2 Fun ControlNet Union is a true ControlNet side model supporting
     pose, depth, canny, HED, MLSD, scribble, and gray controls, but it targets
     FLUX.2 dev rather than Klein. JLC provides a recent ComfyUI implementation with
     up to four control branches and up to ten native FLUX.2 reference images.
4. PuLID only as an optional, separately scored face-lock adapter. It must be kept
   only if it improves held-out identity without harming prompt adherence, body
   identity, expression, or image quality.
5. An LTX 2.5 standard identity LoRA trained from visual-identity clips, combined
   at inference with official LTX IC-LoRAs:
   - Ingredients for character/body/costume reference sheets;
   - Union Control for depth, canny, and pose;
   - Motion Control for sparse trajectories;
   - spatial or spatiotemporal attention masks so control applies to the person
     rather than unnecessarily constraining the background.

The preferred image-model decision is conditional:

- Retain Klein 4B when Apache 2.0 licensing, consumer-hardware operation, and local
  deployment dominate. Use subject LoRA + native multi-reference + RefControl depth,
  and train or validate an additional 4B control adapter before claiming pose or
  normal control.
- Use Klein 9B when its non-commercial license is acceptable and hardware permits.
  It is the best match within the Klein family for the existing USDZ depth/normal
  renders and skeleton data because the current RefControl suite is much broader.
- Evaluate FLUX.2 dev + Alibaba Fun ControlNet Union only as a higher-compute branch.
  Do not silently substitute it for Klein: it changes hardware, license, model,
  trainer, and runtime requirements.

Important implementation facts:

- Train Klein LoRAs against a Base checkpoint, not the four-step distilled runtime
  checkpoint. Use the matching distilled checkpoint only after verifying adapter
  compatibility and quality.
- The official Diffusers Klein trainer supports per-image captions, prior
  preservation, LoRA rank/alpha/dropout, caption dropout, aspect-ratio buckets,
  checkpointing, and resume. The standard text-to-image trainer does not accept a
  mask column. Masks therefore cannot be declared as training inputs unless the
  trainer is extended with a tested foreground-weighted loss; otherwise they are
  still required for filtering, crops, annotations, reference sheets, metrics, and
  spatial control.
- The official Diffusers Klein image-to-image DreamBooth trainer accepts paired
  target and conditioning-image columns. It should be benchmarked only when real,
  defensible pairs can be constructed; do not manufacture semantically false pairs.
- The official LTX trainer supports LTX 2.5, standard LoRA, I2V conditioning, mixed
  still/video datasets, IC-LoRA paired references, trigger words, validation samples,
  checkpoint/resume, and production inference pipelines.
- A standard video LoRA and an IC-LoRA solve different problems. The subject LoRA
  learns the person; Ingredients/Union/Motion IC-LoRAs apply reference, structural,
  and temporal control. They should be calibrated together, not conflated.

Primary sources:

- Black Forest Labs FLUX.2 repository:
  https://github.com/black-forest-labs/flux2
- Official Diffusers FLUX.2 Klein DreamBooth LoRA trainer:
  https://github.com/huggingface/diffusers/blob/main/examples/dreambooth/train_dreambooth_lora_flux2_klein.py
- Official Diffusers FLUX.2 Klein image-to-image LoRA trainer:
  https://github.com/huggingface/diffusers/blob/main/examples/dreambooth/train_dreambooth_lora_flux2_klein_img2img.py
- FLUX.2 Klein RefControl project:
  https://github.com/thedeoxen/refcontrol
- Alibaba FLUX.2 dev Fun ControlNet Union:
  https://huggingface.co/alibaba-pai/FLUX.2-dev-Fun-Controlnet-Union
- JLC FLUX.2 ControlNet implementation:
  https://github.com/Damkohler/JLC-Flux2-ControlNet
- FLUX.2 PuLID port and stated limitations:
  https://github.com/iFayens/ComfyUI-PuLID-Flux2
- Official LTX-2 trainer and inference repository:
  https://github.com/Lightricks/LTX-2
- LTX IC-LoRA documentation:
  https://docs.ltx.io/open-source-model/usage-guides/ic-lo-ra
- LTX IC-LoRA adapter catalog:
  https://docs.ltx.io/open-source-model/integration-tools/ic-lo-ra-adapters

## Paste-ready goal prompt

You are working in `/Users/voxels/SceneFactory`. Complete a production-capable
Scene Factory v4 identity pipeline for the example under
`/Users/voxels/SceneFactory/v4/examples/modeling_interview`.

Do not stop at research, a plan, manifests, workflow stubs, or dataset export. The
goal is complete only when the pipeline has processed every authorized source
modality, trained and promoted usable identity adapters, compiled executable image
and video workflows that bind those artifacts to real model nodes, run representative
generations, validated the results, and packaged a reusable identity bundle with
documented commands.

### Non-negotiable scope

- Exclude all Koleka media, derivatives, embeddings, captions, checkpoints, and
  cached artifacts from this version. Add automated negative tests proving it cannot
  enter the dataset or identity bundle.
- Treat the current v4 as an incomplete ingest prototype. Preserve useful provenance,
  hashing, immutable-source handling, configuration validation, and tests, but replace
  its architecture wherever required. Do not preserve a flawed interface merely for
  compatibility.
- Default mode is `automatic`. It must run from ingest through final validated image
  and video outputs without review gates.
- `fine_tuning` mode may add optional human review and checkpoint-promotion gates.
  Gates must never be mandatory in automatic mode.
- Never claim that a data type was incorporated because it appears in a manifest.
  A modality counts as consumed only when a concrete derived artifact is connected
  to a trainer or executing inference node, with hashes, logs, and output evidence.
- Preserve source files. All derived artifacts must be deterministic where practical,
  content-addressed, and traceable to source path, hash, video timecode or USDZ member,
  processing version, configuration, and model version.
- Confirm the existing consent contract before training. Fail closed if consent is
  revoked or the configured subject does not match the authorized identity.

### Phase 1: audit and dependency contract

Audit the repository, existing v3 capabilities, current v4, source media, local
ComfyUI installation, installed custom nodes, model files, trainer repositories,
GPU/VRAM/RAM/disk, Python environments, licenses, and checkpoint hashes.

Produce a machine-readable preflight report. Pin exact upstream commits or releases,
model filenames, hashes, licenses, and compatibility. Distinguish stable, experimental,
and unavailable paths. Missing dependencies must fail preflight with actionable
instructions; they must not cause silent fallback to text-only generation.

The chosen image model is currently FLUX.2 Klein 4B Base for training and Klein 4B
distilled for inference. Do not assume that remains optimal. Implement a bounded
model/control bakeoff covering:

1. Klein 4B Base subject LoRA + distilled inference + native multi-reference.
2. Klein 4B plus the current reference-depth RefControl adapter.
3. Klein 9B Base subject LoRA + distilled inference + reference pose/depth/normal
   RefControl adapters, if its non-commercial license and hardware are acceptable.
4. FLUX.2 dev + Alibaba Fun ControlNet Union through a validated implementation such
   as JLC, only if the hardware/license preflight permits.
5. PuLID-FLUX.2 as an optional ablation, never as a presumed requirement.

Record the selected production route and why it won. If licensing prevents a route,
mark it ineligible rather than treating it as a quality failure.

### Phase 2: semantic ingest and video-role separation

Extend the identity schema so every video and video segment can have explicit roles:

- `visual_identity`
- `motion_reference`
- `voice_performance`
- `both` only when independently eligible for each downstream dataset
- `exclude`

Allow roles to be assigned by path rules and per-source overrides. Scene-split long
videos before classification. Materialize deterministic image frames for visual
identity and retain short temporal clips for LTX training. Motion-only frames must
not enter FLUX or LTX identity training. Visual-identity clips must not automatically
be treated as desired motion.

Prevent dataset leakage by grouping all derivatives of the same original photo,
video, scene, burst, perceptual cluster, web archive item, or USDZ render sequence.
No group may cross train, validation, calibration, or final test splits.

### Phase 3: masking, annotation, tracking, and captions

For every image and eligible video frame, produce and validate:

- person instance mask and alpha cutout;
- face crop and face mask where reliable;
- face landmarks and face-detection confidence;
- body keypoints/skeleton and confidence;
- shot size, viewpoint/yaw bucket, visible body regions, expression, occlusion,
  blur, exposure, compression, other-person detection, and background leakage;
- identity embedding and distance from the subject cluster;
- semantic caption with the unique identity token, stable subject class, pose,
  expression, framing, lighting, wardrobe, and scene described in separable fields;
- clean-shot score and relevance to the supplied script;
- source path, source hash, frame timestamp, extractor version, and all derived hashes.

Reuse or supersede the existing Apple Vision person-mask and body-pose tools from v3.
Visually verify representative masks and skeletons. Reject masks that cut off identity-
critical features or include unrelated people. Do not use synthetic or web-extracted
images as equivalent to direct photos without provenance-aware weights.

Use masks honestly. If the selected trainer has no mask input, use masks for quality
filtering, crop construction, reference sheets, foreground metrics, and spatial
control. If foreground-weighted training loss is desired, implement it explicitly
in a maintained trainer adapter, test the tensor alignment and loss behavior, and
document the divergence from upstream.

### Phase 4: data selection and identity reference bank

Replace global top-N sharpness selection with coverage-constrained selection. Balance:

- frontal, three-quarter, and profile views;
- close-up, medium, three-quarter, and full-body shots;
- neutral and expressive faces;
- hairline, ears, jaw, hands, and body-proportion visibility;
- lighting and background diversity;
- still photographs and high-quality visual-identity video frames;
- direct evidence versus archived-web evidence.

Reject perceptual duplicates, identity outliers, excessive occlusion, anatomy
distortion, low effective resolution, unrelated people, and frames whose background
or wardrobe would dominate the corpus. Create immutable train, validation,
calibration, and final-test manifests.

Build a separate multi-reference bank for inference. Include a canonical frontal
portrait, left/right three-quarter views, useful profiles, expression references,
and full-body references. Store aligned face crops, original frames, masks, embeddings,
quality scores, intended use, and provenance. Optimize the bank through held-out
generation tests; do not merely pick the sharpest image.

### Phase 5: USDZ geometry as real conditioning

Validate each USDZ package, mesh hierarchy, units, transforms, topology, UVs,
materials, textures, skeletons, blend shapes, and cameras. Record missing or suspect
components.

Using a reproducible renderer, create canonical multi-view passes at the generation
aspect ratios:

- beauty/RGB or albedo reference;
- alpha/person mask;
- metric and normalized depth;
- camera-space and world-space normals;
- silhouette/canny/lineart;
- projected landmarks or skeleton where possible;
- camera intrinsics, extrinsics, focal length, framing, unit scale, and source hash.

Validate alignment across passes and visibly inspect sample grids. Route these assets
to actual consumers:

- depth/normal/pose RefControl or ControlNet inputs for FLUX.2;
- Union Control or other compatible IC-LoRA inputs for LTX;
- silhouette, landmark, and morphology evaluation.

Do not train photographic appearance directly from synthetic USDZ renders unless an
ablation proves it helps. Geometry renders should primarily constrain structure;
real images remain authoritative for skin, hair, and photographic surface appearance.

### Phase 6: train and promote the image identity model

Generalize the existing hardcoded v3 training wrapper for the configured identity.
Use the official Diffusers `train_dreambooth_lora_flux2_klein.py` against the selected
undistilled Klein Base model. Export a Hugging Face image dataset with per-image
captions and stable split/group identifiers.

Implement reproducible experiment configurations for LoRA rank, alpha, dropout,
learning rate, steps, caption dropout, prior preservation, aspect-ratio buckets,
precision, quantization, gradient checkpointing, seed, checkpoint interval, and
resume state. Start with conservative subject-LoRA recipes and run a bounded search;
do not hardcode one unvalidated rank or step count.

Train multiple checkpoints and evaluate them on held-out prompts and fixed seeds.
Reject checkpoints showing source-background memorization, wardrobe leakage, trigger
leakage, facial overfitting, age drift, body drift, poor expression editability,
prompt collapse, or reduced output diversity. Promote a real `.safetensors` adapter
with its exact config, source manifest hash, base-model hash, logs, and model card.

Benchmark the official paired image-to-image trainer only if the data supports valid
conditioning-target pairs. A same-image reconstruction shortcut or arbitrary pairing
is not acceptable evidence of identity generalization.

### Phase 7: evaluate identity and structural-control alternatives

Compile executable, fixed-seed image workflows for these ablations where compatible:

- base model only;
- native multi-reference only;
- subject LoRA only;
- subject LoRA + native multi-reference;
- PuLID only;
- subject LoRA + PuLID;
- subject LoRA + reference-depth control;
- subject LoRA + reference-pose control;
- subject LoRA + reference-normal control;
- subject LoRA + true ControlNet Union on FLUX.2 dev;
- combinations of identity references and structural controls.

Evaluate close-up, medium, full-body, profile, difficult expression, difficult
lighting, new wardrobe, new background, seated, walking, and occluded prompts.
Include script-derived prompts and negative controls.

Measure at minimum:

- face identity similarity using a pinned face-recognition model;
- face detection success and identity variance across seeds;
- foreground/full-body similarity using masked visual embeddings;
- pose keypoint error or PCK;
- silhouette IoU and body-proportion error;
- depth agreement for geometry-controlled shots;
- prompt/text alignment;
- image quality and anatomy failure rate;
- diversity and source-image copy/memorization;
- runtime, peak VRAM, and disk footprint.

Use blind contact sheets in `fine_tuning` mode and automatic metric-based promotion
in default mode. A candidate must improve identity over the base/native-reference
baseline without materially degrading prompt adherence, anatomy, or diversity.
Store all scores and generated outputs. PuLID remains only if the results justify it.

### Phase 8: train and assemble the video identity stack

Use the official LTX-2 trainer with the exact LTX 2.5 checkpoint and matching
LTX-tuned Gemma 4 encoder. Re-precompute latents and text embeddings whenever the
checkpoint/encoder pair changes.

Train a standard LTX identity LoRA from eligible visual-identity clips and selected
stills. Scene-split, caption, normalize frame rate, and use appropriate spatial and
temporal buckets. Use I2V first-frame conditioning during training so the promoted
FLUX identity keyframe remains authoritative. Preserve validation clips and generate
validation videos during training. Save checkpoint weights, training state, config,
logs, samples, hashes, and model card.

Do not use motion-reference footage as identity footage unless it independently
passes the visual-identity selection policy. Extract pose sequences, body tracks,
and sparse trajectories from motion references. Normalize them to target resolution,
frame rate, and duration, while preserving the source-to-guide mapping.

At inference, evaluate and calibrate combinations of:

- identity-locked FLUX keyframe;
- LTX identity LoRA;
- LTX Ingredients IC-LoRA using an automatically composed black-background
  reference sheet of face, body, wardrobe, props, and location as appropriate;
- LTX Union Control using pose/depth/canny guides;
- LTX Motion Control using sparse tracks;
- spatial/spatiotemporal person masks and control strengths;
- multiple keyframes where they improve long-clip identity.

The supplied TTS audio and text are authoritative performance inputs. Align words,
phonemes, and visemes; preserve the supplied waveform unless an explicitly configured
audio-generation stage is requested. Generate or retime lip motion using a compatible,
validated path, then mux the original supplied audio. Do not claim LTX 2.5 Dub-It
support while the upstream adapter remains validated only for LTX 2.3.

Evaluate per-frame face similarity, face-detection rate, masked foreground similarity,
landmark/body drift, pose-guide adherence, flicker, temporal consistency, lip/audio
alignment, and start/end identity drift. Produce short proofs before final clips in
automatic mode, but automatically continue when proofs pass; do not create a review
gate.

### Phase 9: runtime workflows and final identity bundle

Provide stable command-line entry points equivalent to:

```text
scene-factory-v4 preflight
scene-factory-v4 ingest
scene-factory-v4 process-identity
scene-factory-v4 render-usdz-controls
scene-factory-v4 train-image-identity
scene-factory-v4 benchmark-image-controls
scene-factory-v4 train-video-identity
scene-factory-v4 generate-image
scene-factory-v4 generate-video
scene-factory-v4 validate
scene-factory-v4 run
```

`run` in automatic mode must orchestrate the complete pipeline and resume safely.
Heavy stages should be content-addressed and skipped only when their complete input,
configuration, model, code, and output hashes match.

Package a self-contained identity bundle containing at least:

```text
identity_bundle/
  bundle.json
  provenance/
  datasets/
  models/image_identity_lora.safetensors
  models/video_identity_lora.safetensors
  references/images/
  references/reference_bank.json
  geometry/usdz/
  geometry/renders/{rgb,alpha,depth,normals,silhouette,pose}/
  geometry/cameras.json
  motion/skeletons/
  motion/tracks/
  avatar/mesh_talking_head.usdz
  avatar/mesh_talking_head_manifest.json
  avatar/gaussian_splat/
  avatar/rig/{skeleton,blend_shapes,materials,animation_hooks}/
  voice/dialogue.*
  voice/alignment.json
  workflows/generate_image_api.json
  workflows/generate_video_api.json
  runtime/image_runtime.json
  runtime/video_runtime.json
  validation/image_ablation_report.json
  validation/video_identity_drift_report.json
  validation/modality_consumption_report.json
  samples/images/
  samples/videos/
  README.md
```

Workflow graphs must contain real model loaders and connections for every enabled
component. Verify at runtime that the promoted LoRAs are loaded, reference images are
encoded, control maps reach the intended control nodes, and output files were produced.

### Phase 10: tests and completion criteria

Add unit, integration, contract, negative, restart/resume, and end-to-end tests.
Tests must cover:

- Koleka exclusion, including derived/cached data;
- explicit video roles and segment overrides;
- deterministic frame extraction and source timecodes;
- mask, caption, skeleton, embedding, and USDZ render schemas;
- group-safe split leakage prevention;
- trainer command/config generation and checkpoint resume;
- non-placeholder checkpoint existence and loadability;
- ComfyUI workflow node types, model paths, inputs, and graph connectivity;
- exact bypass behavior when an optional adapter is disabled;
- identity/control ablation generation;
- audio preservation and final mux;
- modality-consumption evidence;
- a clean automatic run with no review state;
- optional review gates only in `fine_tuning` mode.

Completion requires all of the following:

1. A fresh automatic run succeeds or resumes to completion on the available execution
   environment.
2. At least one promoted, loadable FLUX.2 identity LoRA exists.
3. At least one promoted, loadable LTX identity LoRA exists, unless a documented
   hardware/license blocker makes training genuinely impossible; a manifest is not
   an acceptable substitute.
4. The selected image runtime demonstrably uses the promoted identity model, selected
   reference bank, and enabled structural-control path.
5. The selected video runtime demonstrably uses the identity keyframe/model and the
   intended Ingredients, Union, or Motion controls.
6. USDZ-derived depth/normal/pose/silhouette artifacts are generated and at least one
   compatible geometry control is exercised in a successful generation.
7. Masks, captions, embeddings, skeletons, split groups, and source provenance exist
   and pass validation.
8. Representative held-out image and video outputs exist with comparative metrics and
   ablations, including a PuLID alternative rather than an assumption.
9. The final identity bundle can generate a new image and a new video from documented
   commands without reading undeclared paths outside the bundle and declared base
   model installation.
10. Documentation accurately states limitations, licenses, hardware requirements,
    selected model/control route, and rejected alternatives.

Do not mark the work complete while any required stage is represented only by a plan,
TODO, blocked placeholder, fabricated metric, unexecuted workflow, or manifest entry.
When a real external blocker is encountered, exhaust safe local alternatives, preserve
resume state, and report the exact command, error, missing artifact, and minimal action
needed to continue.
