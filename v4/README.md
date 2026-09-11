# Scene Factory v4

Scene Factory v4 starts with multimodal identity evidence. A character identity is
not reduced to a folder of LoRA images: photographs, video, archived web pages,
voice performances, transcripts, and 3D captures retain separate provenance and
separate authority over the characteristics they can actually support.

The first example is [`examples/modeling_interview`](examples/modeling_interview).
It references the original assets in `v3/examples/modeling_interview/Gage` so the
large source set remains single-copy.

The complete cross-modality map is [`docs/SPACE_MAP.md`](docs/SPACE_MAP.md).
It is the authoritative status view for built artifacts, live connections,
prepared-but-unconsumed inputs, blockers, and finishing outputs.

Run the stable v4 identity harness with no review gates (the default):

```bash
./scene-factory-v4 process-identity --project examples/modeling_interview
```

The automatic harness inventories every source type, extracts web images, samples video
frames, exposes native USDZ geometry and textures, analyzes visual quality,
clusters duplicates, creates leakage-safe provisional train/validation splits,
and pairs generated audio with the TTS transcript when present. Missing optional
modalities are reported as warnings and do not prevent completion; final-delivery
requirements such as the authoritative waveform remain explicit blockers. Outputs stay beneath
`examples/modeling_interview/build/identity/`; source assets are never changed.

Once local trainer/runtime prerequisites are present, the complete automatic
orchestrator is:

```bash
./scene-factory-v4 run --project examples/modeling_interview
```

It records each stage in `build/pipeline/automatic_run.json` and records the
first genuine blocker instead of claiming a placeholder success. Completed and
blocked ledgers are resumable: stages are skipped only when their source/config/code
signature and output hashes still match, and dependency blocks preserve intact work.
Final-delivery prerequisites such as the supplied waveform are recorded as
deferred blockers, allowing runnable ingest and identity-preparation stages to
advance while still preventing a false `complete` result.

Use fine-tuning mode only when explicit consent, asset review, required audio,
conditioning approvals, and split approvals should gate completion:

```bash
python3 training_harness.py run examples/modeling_interview --mode fine_tuning
```

Record a human decision with the selected asset ID:

```bash
python3 training_harness.py decide examples/modeling_interview ASSET_ID approved --reviewer NAME
python3 training_harness.py decide examples/modeling_interview ASSET_ID rejected --reviewer NAME --note "reason"
```

Export the default automatic run as a hash-verified package with:

```bash
python3 training_harness.py export examples/modeling_interview /path/to/training-package
```

Add `--mode fine_tuning` to export when the optional review gates are desired.

Compile the image API graphs and stage hashed original/mask-derived references:

```bash
./scene-factory-v4 benchmark-image-controls --project examples/modeling_interview
```

Execute a compiled image route only when a compatible ComfyUI server and model
files are available; the command fails closed otherwise:

```bash
./scene-factory-v4 execute-image-workflow --project examples/modeling_interview --route native_reference
```

Create the deterministic held-out image plan and run its connected bakeoff using
only the already-installed local models (no download step):

```bash
./scene-factory-v4 plan-image-evaluation --project examples/modeling_interview
./scene-factory-v4 evaluate-image-identity --project examples/modeling_interview
```

The held-out evaluator is single-run locked and resumable: an interrupted or
blocked report retains completed case hashes and retries only missing cases.

Prepare the role-separated LTX inputs and audio contract:

```bash
./scene-factory-v4 prepare-video-audio --project examples/modeling_interview
```

Inspect the additive Voice handoff directly:

```bash
./scene-factory-v4 inspect-voice-flow --project examples/modeling_interview
```

This command writes scene-split visual-identity clips/frames separately from
motion guides and fails closed when the supplied TTS waveform or official LTX
trainer is absent. The canonical Voice package is `/Users/voxels/SceneFactory/Voice`:
`inputs/tts_script.txt` is the target script, reference recordings remain a
separate conditioning channel, and the final waveform must be assembled at
`Voice/output/gage_final_master.flac`. Nothing in the Voice package is replaced
or silently promoted by a merge; source hashes and provenance are preserved.

Compile the native ComfyUI LTX 2.5 identity/motion graph without waiting for
generation:

```bash
./scene-factory-v4 compile-video-workflow --project examples/modeling_interview
```

This emits `build/workflows/video_runtime/ltx25_identity_motion.json`, binding
the selected visual-identity keyframe and an independent motion-reference video
with the installed local motion-control LoRA. Compilation does not promote an
identity adapter or bypass the audio/training gates.

For a resumable handoff while blocked dependencies are being repaired, emit
explicit non-production contracts:

```bash
./scene-factory-v4 emit-stubs --project examples/modeling_interview
```

This writes `build/stubs/` with one stub per unavailable trainer/control/audio/
Unreal stage. Stubs are marked `production_ready=false` and never satisfy
consumption, promotion, packaging, or final-run completion.

## Intended finished output

The completed automatic run produces a self-contained `identity_bundle/` for the
configured character. It is the delivery artifact that downstream tools consume,
not a training log. It contains:

- a promoted, loadable image-identity LoRA and a promoted, loadable video-identity
  LoRA, each with exact model/config/source hashes and model cards;
- a provenance-aware reference bank with original and masked images, captions,
  embeddings, quality scores, and split/group records;
- executable image and video workflow graphs with real loaders, reference inputs,
  identity adapters, structural controls, and explicit optional-adapter bypasses;
- USDZ geometry plus canonical RGB, alpha, depth, normal, silhouette, and pose
  controls, along with motion skeletons/tracks;
- a rig-ready avatar deliverable: a mesh talking-head USDZ with preserved
  geometry, skeleton, blend shapes, UV textures, material maps, normals, and
  animation/voice hooks, plus a matching Gaussian-splat head for splat-capable
  playback and post-production comparison;
- the supplied voice waveform unchanged, transcript/phoneme/viseme alignment, and
  mux metadata;
- held-out ablation metrics, generated image/video samples, runtime contracts,
  modality-consumption evidence, and a README describing licenses and limitations.

From that bundle, documented commands can generate a new identity-consistent image
and video without reading undeclared source paths (apart from the declared base
model installations). The current build is intentionally not called finished
until real image/video promotion and the authoritative audio are present.

Package the final identity bundle only after both image and video adapters have
been genuinely promoted:

```bash
./scene-factory-v4 package-identity-bundle \
  --project examples/modeling_interview \
  --destination examples/modeling_interview/build/identity_bundle
```

The command fails closed if either adapter, the supplied waveform, or the
Koleka-exclusion audit is incomplete.

Audit actual modality consumption (not just manifest presence) with:

```bash
./scene-factory-v4 validate --project examples/modeling_interview
```

Audit every numbered completion criterion in the August goal with:

```bash
./scene-factory-v4 audit-goal --project examples/modeling_interview
```

The report is written to `build/validation/goal_completion_audit.json` and is
fail-closed: plans, stubs, and prepared manifests cannot satisfy criteria that
require real training or runtime execution.

Run the self-contained test suite with:

```bash
python3 -m unittest discover -s tests -v
```
