# Voice directory agent guide

## Scope

This file applies to `/Users/voxels/SceneFactory/Voice` and every directory
beneath it.

This directory is a self-contained manual handoff package for producing a
six-paragraph Gage TTS performance with local ComfyUI and Qwen3-TTS. It contains
reference audio, transcripts, comparison renders, API workflows, and scripts
for staging, rendering, collecting, assembling, and validating output.

Read `CURRENT_STATE.md`, `README.md`, and `PLAN.md` before changing or running
anything. `PLAN.md` is the authoritative operating guide.

## Current truth

- The package is prepared, but there is no approved final master.
- The default packaged profile is `max_data`.
- `examples/preferred_max_data_preview.flac` is the closest identity comparison
  so far, but its middle section sounds muffled.
- `examples/clean_short_reference_preview.flac` has cleaner capture character
  but was less preferred overall.
- `renders/paragraph_01.flac` belongs to a rejected short-reference run. It is
  retained only for comparison and must not be presented as approved.
- A final master may be created only after all six paragraph renders have been
  reviewed by listening.

## Directory map

- `inputs/`: clean short reference, exact transcript, and requested TTS script.
- `reference_profiles/`: longer composite and cleaned extended reference data.
- `examples/`: listening comparisons; these are not training data.
- `workflows/`: ComfyUI API JSON graphs and generated paragraph workflows.
- `renders/`: paragraph outputs awaiting or carrying human review.
- `output/`: destination for `gage_final_master.flac`.
- `scripts/`: reproducible staging, submission, collection, assembly, and
  validation commands.
- `MANIFEST.sha256`: checksums for package files. Regenerate it after material
  package changes, excluding the manifest itself.

## Path and portability rules

Scripts derive the package root from their own location. Keep internal package
paths relative to that root.

External defaults are configurable:

- `COMFY_INPUT`, default `/Users/voxels/ComfyUI-Shared/input`
- `COMFY_OUTPUT`, default `/Users/voxels/ComfyUI-Shared/output`
- `COMFY_URL`, default `http://127.0.0.1:8188`

Comfy workflow audio paths are relative to Comfy's input directory, such as
`voice_clone/gage_final_reference.wav`. Do not embed this package's absolute
filesystem location into workflow JSON.

## Safe operating procedure

1. Inspect the Comfy queue before submitting work. Do not restart, interrupt,
   clear, or replace another user's active job without explicit authorization.
2. Select a profile consistently for staging and workflow generation:

   ```sh
   PROFILE=max_data ./scripts/stage_reference.sh
   PROFILE=max_data ./scripts/prepare_workflows.sh
   ```

3. Submit only when the queue is empty:

   ```sh
   ./scripts/submit_all.sh
   ```

4. After completion, collect outputs with `scripts/collect_outputs.sh`.
5. Treat each paragraph as a separate listening gate. Regenerate only weak
   paragraphs and change one variable at a time.
6. Assemble and validate only after six paragraph files are approved:

   ```sh
   ./scripts/assemble_final.sh
   ./scripts/validate_final.sh
   ```

Technical validation is not human approval.

## Audio and identity rules

- Preserve raw and manually edited source audio. Never overwrite it in place.
- Exclude Ryan, overlapping speakers, music, machine-selected candidates, and
  synthetic Gage output from reference or training datasets.
- Keep reference transcripts exact. Mark uncertain words instead of inventing
  them.
- Prefer several clean 5–15 second utterances over one noisy composite.
- Use gentle per-recording noise reduction. Avoid aggressive gating,
  low-passing, pitch correction, de-reverb, compression, and generic "voice
  enhancement" that removes consonants or harmonics.
- Do not use race, birthplace, or age stereotypes as prompt controls. Match
  pronunciation and cadence from verified recordings.
- Do not train on generated speech.

## Reference profiles

`max_data` uses the 50.46-second composite and settings closest to the preferred
preview: temperature `0.72`, `max_chars_per_chunk=180`, and silence padding.
It favors identity but may inherit inconsistent microphone acoustics.

`short_clean` uses the verified clean TikTok excerpt: temperature `0.78`,
`max_chars_per_chunk=400`, and crossfade. It favors capture clarity but was less
preferred in later production renders.

Do not silently mix settings from the two profiles. Document intentional
experiments and preserve comparison outputs with unambiguous filenames.

## Fine-tuning boundary

The supplied Comfy workflow performs zero-shot inference only; it does not
train a LoRA or modify Qwen weights.

Do not attempt fine-tuning with the current approximately 50 seconds of usable
audio. A credible experiment needs at least 10–20 minutes of clean,
speaker-pure, exactly transcribed audio, preferably 30–60 minutes, plus a held-
out evaluation set. Use only a framework explicitly compatible with the exact
Qwen3-TTS Base checkpoint and adapter format. Keep base weights immutable and
record dataset, configuration, and output hashes.

## Editing and verification

- Use `apply_patch` for text and script edits.
- Keep scripts POSIX `sh` unless an existing script explicitly uses another
  shell.
- After script changes, run `sh -n scripts/*.sh` and exercise both
  `PROFILE=max_data` and `PROFILE=short_clean` workflow generation.
- After material changes, regenerate `MANIFEST.sha256` from the SceneFactory
  root:

  ```sh
  find Voice -type f ! -name MANIFEST.sha256 -print0 | sort -z \
    | xargs -0 shasum -a 256 > Voice/MANIFEST.sha256
  ```

- Do not delete rejected comparisons unless the user explicitly requests it;
  their status must remain documented so they cannot be mistaken for final
  material.
