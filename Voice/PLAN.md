# Gage TTS production and manual-takeover guide

This folder is the complete handoff package for producing the supplied script.
It is self-contained except for the installed ComfyUI models and
TTS-Audio-Suite runtime.

## Current outcome

There is no approved final master yet.

- `examples/clean_short_reference_preview.flac` had the cleanest microphone
  character and acceptable pronunciation, but later short-reference production
  renders were judged less similar to the preferred pass.
- `examples/preferred_max_data_preview.flac` was judged closer overall, but its
  middle section sounded muffled. A long composite reference can transfer
  inconsistent microphone acoustics between generated chunks.
- `renders/paragraph_01.flac` belongs to the rejected short-reference run. It is
  retained for comparison and must not be treated as approved.
- Create `output/gage_final_master.flac` only after reviewing all six renders.

## How the system works

The graph uses Qwen3-TTS 12 Hz 1.7B Base in zero-shot clone mode. It does not
fine-tune weights. Qwen receives reference audio, its exact transcript, the new
paragraph, and sampling/delivery settings. The reference controls identity,
pronunciation, cadence, vocal weight, and some microphone character. More audio
is not automatically better when the recordings are inconsistent.

The requested script is rendered as six independent paragraphs. A weak section
can therefore be replaced without regenerating the complete performance.
`scripts/assemble_final.sh` inserts five exact 1.2-second pauses and creates a
loudness-normalized FLAC master.

## Folder map

```text
inputs/                 Clean short reference, transcript, and complete script
reference_profiles/     Long composite and cleaned extended source
examples/               The two important listening comparisons
workflows/              Base graph, preferred preview, and six paragraph graphs
renders/                Reviewed paragraph FLAC files
output/                 Final assembled master
scripts/                Staging, generation, collection, assembly, validation
```

## Local prerequisites

```text
ComfyUI: /Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI
Shared input: /Users/voxels/ComfyUI-Shared/input
Shared output: /Users/voxels/ComfyUI-Shared/output
API: http://127.0.0.1:8188
```

Required nodes are `LoadAudio`, `CharacterVoicesNode`, `Qwen3TTSEngineNode`,
`UnifiedTTSTextNode`, and `SaveAudio`. Use Base 1.7B, MPS `auto`, float32,
SDPA, Shared Runtime, and `x_vector_only_mode=false`.

## Manual production procedure

```sh
cd /Users/voxels/SceneFactory/Voice
```

Choose `max_data` for the voice closest to the preferred pass or `short_clean`
when microphone clarity is more important:

```sh
PROFILE=max_data ./scripts/stage_reference.sh
PROFILE=max_data ./scripts/prepare_workflows.sh
```

Confirm Comfy is running and empty:

```sh
curl -fsS http://127.0.0.1:8188/queue | jq .
```

Submit, wait for the queue to empty, and collect:

```sh
./scripts/submit_all.sh
./scripts/collect_outputs.sh
```

Listen to every file in `renders/`. If one is muffled or poorly inflected,
change only that paragraph's seed or profile and resubmit it. Once all six are
approved:

```sh
./scripts/assemble_final.sh
./scripts/validate_final.sh
```

## Manual source cleanup

Keep originals immutable. Make one file per clean utterance, ideally 5–15
seconds, with a matching exact `.txt` transcript.

- Mono PCM WAV; original rate or 48 kHz; 24-bit preferred.
- Peaks below -3 dBFS and approximately -20 LUFS.
- Use 50–100 ms edge fades.
- Remove other speakers, music, handling noise, and long silences.
- Apply gentle noise reduction separately for each recording.
- Avoid pitch correction, strong gating, heavy de-reverb, aggressive low-pass
  filtering, and "voice enhancer" effects.

Never combine clips until their transcripts are exact. Transcript mismatch
weakens pronunciation and identity conditioning.

## Improving one paragraph

The safest controls are:

- `seed`: test 41–45.
- `temperature`: 0.70–0.82; higher values add variation and drift.
- `max_chars_per_chunk`: 180 for sentence control, 400 for fewer transitions.
- `max_data` for similarity, `short_clean` for capture clarity.

Change one variable at a time. Do not pitch-shift until identity, pronunciation,
and microphone character are already acceptable.

## Fine-tuning takeover

The current Comfy graph is inference-only and provides no LoRA training graph.
Do not train on the present 50 seconds or generated audio; it would likely
memorize noise, phrases, and microphone coloration.

Before using the 3090 Ti for an adapter, build at least 10–20 minutes of clean,
speaker-pure, exactly transcribed speech; 30–60 minutes is preferable. Keep a
held-out evaluation set, exclude Ryan/overlap/music/synthetic output, and use a
framework that explicitly supports this exact Qwen3-TTS Base checkpoint and
adapter format. Keep the base checkpoint immutable and record dataset/config
hashes. More GPU power cannot repair contaminated training data.

## Final approval

Technical validation only proves that the master is decodable, mono, 24 kHz,
and non-empty. Human listening must approve identity, pronunciation, inflection,
microphone clarity, continuity, and absence of other speakers.
