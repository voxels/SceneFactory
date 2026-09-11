# Remaining implementation walkthrough

Prepared 2026-09-06. This is an implementation sequence for the engineer taking
over Scene Factory v4. The companion
[handoff](/Users/voxels/SceneFactory/v4/docs/PRINCIPAL_ENGINEER_HANDOFF.md)
contains the evidence inventory and defect register D01–D20. This document explains
where to edit and how to connect the remaining pieces. Source line links are
accurate at preparation time; function names remain useful after edits move lines.

The steps below are proposed work, not claims that these repairs have been made.
Names explicitly described as new modules/artifacts are recommendations and do
not denote existing files.

## Execution order

Complete the foundation in steps 1–3. Image work in 4–5 and Voice/video work in
6–10 can then advance independently where their inputs permit. Connect the
orchestrator while those interfaces settle, rather than waiting for all generations.
Complete delivery in 11–13. Avatar work in 14 remains part of the final scope but
should not block implementation of the image/video path.

| Steps | Outcome | Dependency |
|---|---|---|
| 1–3 | Stable source records, selection and execution states | Existing sources/config |
| 4–5 | Evaluated image identity and exercised structural control | Stable selected dataset; compatible local model/control files |
| 6–7 | Complete Voice performance and actual timing | Selected voice reference; local synthesis/alignment runtime |
| 8–10 | Correct LTX graph, video identity training, full-duration video | Image keyframes, timing, compatible local trainer and controls |
| 11–13 | Automatic execution, portable bundle and real acceptance | Implemented stage interfaces; actual generation evidence for final acceptance |
| 14 | Rigged mesh and reconstructed Gaussian avatar playback | USDZ/camera data, timing, usable target runtime |

Keep original files, previous runs and rejected takes. Create versioned derived
artifacts and record explicit selection decisions. A new run should reuse valid
work; it should not silently overwrite or promote older results.

## 1. Reconcile the source registry before regenerating anything

Start at [identity_pipeline.build](/Users/voxels/SceneFactory/v4/identity_pipeline.py:382)
and [prepare_video_audio](/Users/voxels/SceneFactory/v4/video_audio_pipeline.py:313).
Video preparation currently calls ingestion with web extraction disabled and
rewrites the shared asset manifest. This loses extracted-web entries from the
current view even though downstream datasets still reference them.

Implement the repair in this order:

1. Separate source inventory, derivative records and selected consumer views.
   Loading a source inventory without extraction must retain existing derivative
   lineage rather than replacing it with an empty list.
2. Give each processing run an immutable manifest keyed by source/config/tool
   hashes. Keep the familiar current-manifest path as a pointer or derived view.
3. Replace the extraction-folder cleanup inside `build` with explicit accounting
   of historical/unreferenced derivatives. Do not delete prior work during ingest.
4. Make video preparation consume the current registry and add its own derivatives.
   Reconcile existing hashes and source-group IDs before refreshing downstream views.

Suggested new records: source ID/hash/origin, derivative parent IDs, source
timecode/member, processor/config/model hashes, intended role, run ID and decision
history. Filesystem birth/modified dates are observations, not proof of when the
original recording was made.

Extend [test_identity_pipeline.py](/Users/voxels/SceneFactory/v4/tests/test_identity_pipeline.py).
Acceptance: extract a web image, annotate/select it, prepare video, and prove its
lineage and bytes remain available. Repeating the operation must not create
duplicates or lose prior records. Addresses D08.

## 2. Unify Voice input resolution and purpose-aware selection

Edit [voice_flow.build_voice_manifest](/Users/voxels/SceneFactory/v4/voice_flow.py:86),
[voice classification](/Users/voxels/SceneFactory/v4/voice_flow.py:47),
[bundle audio discovery](/Users/voxels/SceneFactory/v4/identity_bundle.py:23),
[preflight](/Users/voxels/SceneFactory/v4/scene_factory_v4.py:236), and
[audio preparation](/Users/voxels/SceneFactory/v4/video_audio_pipeline.py:313).

Create one resolver that returns explicit selected references, target transcript,
performance master and retained alternatives. Every consumer should use that
result. Maintain both canonical Voice and legacy source records, even when one is
selected for the current run. Same filenames must not determine equivalence.

Pair reference audio with its exact transcript and documented profile. Mark the
known rejected paragraph as rejected; draft transcripts/custom edits need their
actual evidence state. Do not mark all files in `reference_profiles` eligible
merely because of directory membership. Record which takes produced a final
master instead of treating the expected filename as approval.

Use [schema](/Users/voxels/SceneFactory/v4/schemas/identity.schema.json) and
[example config](/Users/voxels/SceneFactory/v4/examples/modeling_interview/identity.json)
for explicit selected-input settings. Generalize the hardcoded Gage master name
for future characters while retaining this example's intended output path.

Connect selected Voice records into `identity_pipeline.build` and the exported
voice channel, preserving reference/performance separation. Add a new focused
Voice resolver test module. Acceptance: same-name different-content files remain
distinct; rejected/generated material cannot enter reference training; preflight,
alignment and packaging all select the same performance hash. Addresses D09–D10.

## 3. Establish honest stage states and correct resume dependencies

Edit [_source_fingerprint](/Users/voxels/SceneFactory/v4/scene_factory_v4.py:418),
[_stage_signature](/Users/voxels/SceneFactory/v4/scene_factory_v4.py:431),
[_raise_for_blocked_stage](/Users/voxels/SceneFactory/v4/scene_factory_v4.py:451), and
[CLI status handling](/Users/voxels/SceneFactory/v4/scene_factory_v4.py:650).

Define explicit states for preparation, execution, pending quality evaluation,
validated completion and dependency failure. Preserve `rendered_pending_validation`
as such through the CLI. Evaluate nested stage outcomes deliberately: a successful
annotation call cannot hide blocked video/audio work inside a composite result.

Replace the global fingerprint with stage-specific dependency signatures. Include
used Voice files, stage implementation modules, model/adapter hashes, selected
inputs and upstream output hashes. Track actual terminal outputs, not merely a
plan file. Changing the voice script should invalidate timing/video delivery,
not automatically retrain unchanged photographic identity.

Extend [orchestrator tests](/Users/voxels/SceneFactory/v4/tests/test_scene_factory_v4.py).
Acceptance: missing/changed outputs invalidate their consumers; unchanged stages
resume; nested failures and pending quality never become final completion.
Addresses D06–D07 and D18.

## 4. Finish selected-data coverage and image evaluation

Trace [annotations](/Users/voxels/SceneFactory/v4/identity_annotations.py:46)
through [caption generation](/Users/voxels/SceneFactory/v4/identity_captions.py:140),
[coverage selection](/Users/voxels/SceneFactory/v4/training_harness.py:350),
[group splits](/Users/voxels/SceneFactory/v4/training_harness.py:419),
[select](/Users/voxels/SceneFactory/v4/training_harness.py:498) and
[reference-bank construction](/Users/voxels/SceneFactory/v4/reference_bank.py:25).

First reconcile the main candidate dataset with the separate scene-split visual
video frames. Ensure every selected frame has the required masks, annotations,
caption, quality scores, timestamp and source group. Add segment-role overrides
at [video role resolution](/Users/voxels/SceneFactory/v4/identity_pipeline.py:357)
and [video partitioning](/Users/voxels/SceneFactory/v4/video_audio_pipeline.py:41).
Motion-only frames must remain excluded from identity training.

Add script/shot relevance to coverage selection while retaining identity quality
and view/body/expression diversity. Keep all derivatives of a source scene or
perceptual cluster in one split. Verify representative masks and poses visually.

Then inspect [completed training candidates](/Users/voxels/SceneFactory/v4/image_training.py:233)
and [evaluation-plan construction](/Users/voxels/SceneFactory/v4/image_evaluation.py:206).
Reconcile compatible prior cases by plan/model/data hashes before rendering more.
Do not retrain all three existing adapters simply because evaluation is incomplete.

Extend [_score_outputs](/Users/voxels/SceneFactory/v4/image_evaluation.py:313),
[_candidate_summary](/Users/voxels/SceneFactory/v4/image_evaluation.py:362), and
[_promotion_eligibility](/Users/voxels/SceneFactory/v4/image_evaluation.py:378)
with actual face-recognition, foreground/body, prompt adherence, pose, anatomy,
diversity/copying and resource metrics required by the goal. Verify availability
of the needed local metric models. Do not silently replace missing metrics with
feature-print distance or fabricated values.

Acceptance: a bounded, comparable held-out experiment selects a loadable image
adapter and reference route under explicit quality criteria; the resulting
promotion manifest and runtime contract refer to the same hashes. Extend
[evaluation tests](/Users/voxels/SceneFactory/v4/tests/test_image_evaluation.py)
and [selection tests](/Users/voxels/SceneFactory/v4/tests/test_training_harness.py).
Addresses D13–D14.

## 5. Connect USDZ controls to a real image consumer

Start with [USDZ ingestion](/Users/voxels/SceneFactory/v4/usdz_ingestion.py:37),
[control rendering](/Users/voxels/SceneFactory/v4/usdz_controls.py:17), and
[image workflow compilation](/Users/voxels/SceneFactory/v4/image_workflows.py:245).

Audit the existing 168 controls for shared camera, units, depth normalization,
normal coordinate space, dimensions and source hash. Repair mismatched passes
before adding a model consumer. Select a control checkpoint compatible with the
actual image model and present locally; inventory alone is not compatibility.

Extend the compiled graph with the real loader/preprocessor/control application
nodes. Reuse the subject adapter and selected references, and implement exact
optional-control bypass. Enhance [graph validation](/Users/voxels/SceneFactory/v4/image_workflows.py:39)
to check actual installed socket types/required fields, not only link IDs.

Acceptance: a fixed-seed control-on/control-off comparison proves the USDZ-derived
map reached the intended node and improved structural adherence without destroying
identity. Persist control/model/source hashes in execution evidence. If no compatible
local checkpoint exists, record that exact dependency and continue independent
image/Voice work. Addresses D15; do not fetch or change model families silently.

## 6. Finish voice synthesis as a resumable input-producing stage

The current implementation is the standalone
[Voice scripts](/Users/voxels/SceneFactory/Voice/scripts), especially
[workflow preparation](/Users/voxels/SceneFactory/Voice/scripts/prepare_workflows.sh),
[submission](/Users/voxels/SceneFactory/Voice/scripts/submit_all.sh),
[collection](/Users/voxels/SceneFactory/Voice/scripts/collect_outputs.sh), and
[assembly](/Users/voxels/SceneFactory/Voice/scripts/assemble_final.sh).
Read [Voice operating guide](/Users/voxels/SceneFactory/Voice/PLAN.md) first.

Introduce run-specific take paths and durable paragraph prompt IDs before wrapping
these scripts in v4. Existing fixed paths/truncated submission logs and `-y` assembly
must not overwrite the rejected take or an existing master. Use the selected
reference/profile from step 2 consistently for all paragraph workflows.

Add a v4 stage adapter that stages, submits, observes, collects, selects and assembles
the six paragraphs. Keep `Voice/output/gage_final_master.flac` as this example's
final destination with versioned lineage behind it. Existing generated previews
are comparison evidence, never new training references.

Implement automatic technical/quality handling in default mode, with listening
review optional in fine-tuning mode. The manual engineer can review takes during
takeover without encoding a mandatory production-mode pause. Test interrupted
submission, selective rerender, take selection and master provenance.

Acceptance: full intended text and pauses, valid audio, known selected takes,
canonical master hash supplied to the shared resolver. This step produces audio;
it does not yet establish video lip synchronization. Addresses D09–D10/D17.

## 7. Implement real word, phoneme and viseme alignment

Integration point:
[audio/transcript preparation](/Users/voxels/SceneFactory/v4/video_audio_pipeline.py:313)
currently reports `blocked_aligner_not_configured` after audio appears.
[Transcript parsing](/Users/voxels/SceneFactory/v4/video_audio_pipeline.py:238)
counts words/pauses but is not an aligner.

Add a dedicated alignment module using a verified local runtime. Record waveform
and transcript hashes, timing origin/sample rate, word and phoneme intervals,
phoneme-to-viseme mapping version, confidence and unaligned spans. Estimated
word duration must not be labelled forced alignment.

Pass this contract to the video conditioning/retiming stage and avatar animation
binding. Preserve original waveform bytes. Acceptance: timing within audio bounds,
monotonic segments, pause handling, transcript-change invalidation and measured
alignment on a known speech fixture plus the actual Gage performance.

## 8. Correct LTX graph semantics against installed nodes

Primary edit: [compile_workflow](/Users/voxels/SceneFactory/v4/video_workflows.py:130).
The specific fixes are:

1. Remove the unrelated pose checkpoint from text loading. The local combined
   Gemma4 file contains LTX projections. Check the installed
   [CLIPLoader](/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI/nodes.py:1007)
   and [Gemma4 LTX detection](/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI/comfy/sd.py:1808)
   for a verified single-file load, then test actual text encoding.
2. Correct audio node binding. The installed
   [DecodeAndSaveVideo](/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI/custom_nodes/comfyui-kjnodes/nodes/image_nodes.py:4960)
   requires an audio VAE when receiving audio latents. Preserve the final master
   through mux; do not interpret output audio decoding as mouth-motion conditioning.
3. Replace raw motion footage as an image guide with the correctly formatted
   control required by the installed compatible adapter. Resolve any latent/image
   socket mismatch. Feed normalized tracks from
   [motion_tracking.track](/Users/voxels/SceneFactory/v4/motion_tracking.py:66).
4. Add an actual promoted subject-LoRA loader to the sampled model. Execution
   eligibility must be derived from verified bindings, never toggled manually.
5. Replace [_first_visual_frame](/Users/voxels/SceneFactory/v4/video_workflows.py:51)
   with an explicit generated image-keyframe input from the promoted image runtime.
6. Correct [_local_node_contract](/Users/voxels/SceneFactory/v4/video_workflows.py:100)
   and verify full schemas, shapes and model compatibility against the installation.

Potential reusable code, not an existing v4 connection:
[v3 pose-to-motion conversion](/Users/voxels/SceneFactory/v3/render_pipeline.py:221)
and [v3 motion workflow configuration](/Users/voxels/SceneFactory/v3/render_pipeline.py:315).
Review their assumptions and identity defaults before adapting them for Gage.

Acceptance: real minimal graph executes with intended models, correct tensor types,
separate identity/motion roles and explicit audio-conditioning semantics. Extend
[video workflow tests](/Users/voxels/SceneFactory/v4/tests/test_video_workflows.py)
with installed-schema checks as well as graph structure tests. Addresses D01–D04/D15.

## 9. Implement the LTX identity trainer and promotion

Edit [_ltx_runtime_contract](/Users/voxels/SceneFactory/v4/video_audio_pipeline.py:266)
and [train_video_identity](/Users/voxels/SceneFactory/v4/video_audio_pipeline.py:454).
The latter currently always raises, including when a trainer is discovered.

Locate suitable existing local trainer code and pin its actual invocation. If none
exists, stop this branch at the explicit missing dependency; do not fetch under
the current instruction or guess a trainer CLI. Other implementation continues.

Separate visual-video training prerequisites from final audio/alignment delivery
requirements. Export selected stills/clips with captions, split groups, temporal
buckets and first-frame conditioning. Record the exact checkpoint/encoder pair
for latent/text caches. Persist commands/configuration, optimizer checkpoints,
resume state, logs, held-out samples and adapter hashes.

Use [image_training.prepare](/Users/voxels/SceneFactory/v4/image_training.py:58)
and [image_training.train](/Users/voxels/SceneFactory/v4/image_training.py:141)
as orchestration patterns, not as a compatible video training implementation.
Promotion must test real loading and held-out identity/temporal behavior.

Acceptance: loadable video adapter, immutable promotion manifest, exact consumer
binding in step 8, and repeatable validation video. Addresses D03/D05.

## 10. Build full-duration video and durable execution

Edit [video_executor.execute](/Users/voxels/SceneFactory/v4/video_executor.py:104)
and [validate_execution_contract](/Users/voxels/SceneFactory/v4/video_executor.py:65).
The current graph's 49 frames at 24 fps cannot cover the speech script.

Add a shot/timeline planner with paragraph/time ranges, frame counts, keyframes,
motion intervals, control strengths/masks and continuity requirements. Expose
needed settings through [run_command](/Users/voxels/SceneFactory/v4/scene_factory_v4.py:569)
and the CLI. Generate/retime all segments using actual alignment; verify continuity
and lipsync before concatenation and final mux.

Persist server URL, prompt ID, graph hash and input hashes immediately after
submission. Reobserve that prompt after interruption or timeout. Record an uncertain
submission state when a response is lost and reconcile it before resubmitting.
Select actual video outputs from history and probe them. Do not mark failed downloads
as complete or infer model consumption from filenames.

Reuse [finalize_delivery](/Users/voxels/SceneFactory/v4/video_executor.py:167)
and [mux_original_audio](/Users/voxels/SceneFactory/v4/video_audio_pipeline.py:473),
which already check input hashes, reject overwrites and refuse short video. Add
output-stream equivalence checks where needed; unchanged source bytes alone do
not prove complete speech survived in the delivery.

Add video quality evaluation for identity drift, pose, flicker and lipsync. Publish
verified evidence into the canonical video runtime contract only after those checks.
Extend [executor tests](/Users/voxels/SceneFactory/v4/tests/test_video_executor.py)
for interruption/resume, ambiguous submission, output selection, full timeline and
failure-to-success transitions. Addresses D16–D18.

## 11. Wire all consuming stages into the automatic runner

Edit [_automatic_run](/Users/voxels/SceneFactory/v4/scene_factory_v4.py:458).
Its current stage list omits generation, alignment, video evaluation and avatar work.

Add explicit stages for selected image proof/keyframes, Voice production or supplied
master resolution, alignment, video graph/training/promotion, segment execution,
video evaluation, final mux, runtime publication and packaging. Bind the appropriate
real artifact dependencies using step 3. Integrate stage interfaces now; missing
runtime dependencies should appear as explicit stage outcomes.

Keep independent branches runnable when another dependency is absent. Define
delivery dependencies separately from optional experiments and deferred avatar
runtime tests; full-goal status must still show unfinished required scope. Persist
one run ledger linking all branch/run IDs and final artifacts.

Acceptance: default run produces a real image/video delivery with no human gate;
interruption resumes only unfinished work; an intentionally missing prerequisite
does not hide independent progress or yield a false complete result. Extend
[orchestrator tests](/Users/voxels/SceneFactory/v4/tests/test_scene_factory_v4.py)
with real local artifact integrations in addition to mocks. Addresses D06–D07/D18.

## 12. Package and connect the finished bundle to scene production

Edit [build_bundle](/Users/voxels/SceneFactory/v4/identity_bundle.py:134),
[_bundle_path](/Users/voxels/SceneFactory/v4/identity_bundle.py:94), and
[_copy_runtime_contract](/Users/voxels/SceneFactory/v4/identity_bundle.py:122).

Require actual promotion/execution/quality evidence before packaging. Copy the full
goal layout: models, selected datasets/references, controls/cameras, tracks, voice
master/alignment, workflows, runtime contracts, validation, samples and instructions.
Rewrite all consumer paths through an explicit source-to-bundle mapping; retain
original paths as provenance only. Validate every referenced copied path/hash.

Add a scene-consumer adapter that accepts the bundle plus shot/script requests and
returns generated clips, timing and edit metadata. Candidate older integration
points are [scene manifest compilation](/Users/voxels/SceneFactory/v3/scene_factory.py:877),
[post-production manifest](/Users/voxels/SceneFactory/v3/scene_factory.py:720), and
[rough-cut assembly](/Users/voxels/SceneFactory/v3/rough_cut.py:52).
Do not assume those functions already accept v4 bundles or import identity-specific
defaults from older examples.

Acceptance: relocate the bundle and generate a new image and video with original
project/Voice paths unavailable to the consumer. Only declared model installations
remain external. Demonstrate the scene consumer using the resulting performance
and timeline. Addresses D11/D20.

## 13. Replace weak completion checks with evidence verification

Edit [modality consumption](/Users/voxels/SceneFactory/v4/modality_audit.py:61)
and [goal audit](/Users/voxels/SceneFactory/v4/goal_audit.py:76).

Replace file-existence and status-flag checks with artifact rehashing, validated
promotion lineage, real model loading, connected consumer execution, quality
results and portable-bundle proof. Resolve the active evaluation by its plan hash,
not directory-name ordering. Voice presence must not count as aligned/muxed use.
Validate the masks/captions/skeletons/splits themselves rather than only manifests.

Map every numbered completion criterion and named deliverable in the original goal
to an evidence verifier. Explicitly handle any documented allowed exception without
fabricating its missing artifact or weakening unrelated requirements.

Acceptance: deleted/changed output, fake adapter, stale metric, disconnected control,
unapproved comparison take, or broken bundle path each produces a truthful failure.
A full real run, rather than fabricated fixtures, proves final acceptance. Addresses D12.

## 14. Finish the avatar branch without blocking earlier core implementation

Review [add_rig](/Users/voxels/SceneFactory/v4/tools/rig_avatar_blender.py:65),
[add_blend_shapes](/Users/voxels/SceneFactory/v4/tools/rig_avatar_blender.py:108),
[write_gaussian_ply](/Users/voxels/SceneFactory/v4/tools/rig_avatar_blender.py:140),
and [avatar validation](/Users/voxels/SceneFactory/v4/avatar_validation.py:68).

Retain current exports as prototypes. Replace estimated mouth offsets with fitted
facial deformation and validated skinning/viseme shapes. Verify texture sampling,
UV/material/normal fidelity, skeleton scale/orientation and animation export.

Implement actual calibrated Gaussian reconstruction and the required deformation or
playback mechanism; a PLY with Gaussian field names and one record per mesh vertex
does not establish reconstructed appearance. Verify the viewer's coefficient,
opacity, scale and rotation conventions.

Bind the alignment/visemes from step 7 into mesh and splat playback or explicitly
document representation limits. Use [Metal probe](/Users/voxels/SceneFactory/v4/scene_factory_v4.py:172)
and [Unreal preflight](/Users/voxels/SceneFactory/v4/scene_factory_v4.py:118)
to establish the usable runtime. Implement UE import/animation/playback tests once
available; plugin presence and null-renderer checks do not prove render fidelity.

Acceptance: prerecorded speaking avatar with editable timing/expressions, validated
mesh and Gaussian rendering, matching identity, and demonstrated supported playback.
Document actual visionOS/SharePlay support without claiming native Persona equivalence.
Addresses D19–D20.

## Working checklist and verification cadence

Use the step numbers as implementation batches and record the resulting artifact
and test evidence in
[IMPLEMENTATION_TASKS.md](/Users/voxels/SceneFactory/v4/docs/IMPLEMENTATION_TASKS.md).
After each batch, run its affected tests; broaden to the full suite after integration
changes. Use a short real model proof before spending hours on another matrix.

```sh
cd /Users/voxels/SceneFactory
PYTHONPATH=v4:v4/tests python3 -m unittest discover -s v4/tests -p 'test_*.py'
```

The final completion check is the repaired automatic run plus independent inspection
of its portable delivery, metrics and avatar scope. Green unit tests or completion
of this implementation walkthrough are not a substitute for that product evidence.
