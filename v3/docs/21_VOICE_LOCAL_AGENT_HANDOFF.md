# Voice clone local-agent handoff

This runbook completes the local Qwen3-TTS process in `/Users/voxels/SceneFactory/v3/voice_clone`. It is suitable for the operator or a local coding agent.

## Current state and required input

`TTS-Audio-Suite`, Qwen3-TTS 1.7B Base, its speech tokenizer, and the separate 12 Hz tokenizer are installed and staged. `voice_clone/workflows/qwen3_base_clone_f5_ab.json` is the template; staging generates the operator-ready `.ready.json` workflow.

Two operator inputs still block execution:

1. Replace the current 1.35-second reference with clean, single-speaker audio lasting 6–15 seconds.
2. Put the exact spoken transcript in `voice_clone/voices/on_camera.reference.txt`.

The pip conflict report concerns optional TTS engines sharing one environment. Do not globally downgrade or upgrade Transformers, Gradio, protobuf, or Hugging Face packages to silence it. Qwen uses the suite's Shared Runtime isolation.

Findings:
- voice_clone/input/tts_text.txt is the target synthesis script, not the reference transcript.
- IMG_0474.MOV is 10.666292 seconds, but contains multiple speakers.
- The documented on-camera speaker window is only 2.75–4.10 seconds.
- The extracted reference is valid PCM16/22050 Hz/mono, but only 1.350023 seconds.
- voice_clone/voices/on_camera.reference.txt is empty.
- Local Whisper produced only an unverified draft; I did not present it as an exact transcript.
- Models, tokenizer, workflow, and TTS-Audio-Suite all passed validation.

## Exact commands

Choose the correct source, start time, and duration:

```sh
cd /Users/voxels/SceneFactory/v3/voice_clone
chmod +x extract_reference.sh preflight.sh stage_into_comfy.sh
./extract_reference.sh /absolute/path/to/source-video.mp4 ./voices/on_camera.wav 0 12
```

Use a text editor to put the verbatim transcript of only that selection in:

```text
/Users/voxels/SceneFactory/v3/voice_clone/voices/on_camera.reference.txt
```

Then stage and validate. Staging atomically replaces Comfy's copy of the WAV,
verifies that it is byte-identical, and generates a ready workflow containing
the verified transcript:

```sh
cd /Users/voxels/SceneFactory/v3/voice_clone
export COMFY_ROOT=/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI
export COMFY_PYTHON=/Users/voxels/ComfyUI-Installs/ComfyUI/standalone-env/bin/python3
./stage_into_comfy.sh
./preflight.sh
```

Success ends with `Voice-clone assets pass static preflight`. The workflow to
load is then:

```text
/Users/voxels/SceneFactory/v3/voice_clone/workflows/qwen3_base_clone_f5_ab.ready.json
```

Do not load the `.json` template: it deliberately contains
`__REFERENCE_TRANSCRIPT_REQUIRED__`. If weights ever need recovery, run
`./download_models.sh` with the same environment variables. It uses the current
`hf` command or a Python fallback and verifies completed weights.

## Run in ComfyUI

1. Run `./runtime_preflight.sh`. It performs read-only checks that Comfy is reachable, both queue lists are empty, all required nodes are registered, and the installed suite revision matches this kit.
2. If Comfy is unreachable, start it through the normal operator workflow. Restart only if nodes are missing and the queue remains empty.
3. Load `/Users/voxels/SceneFactory/v3/voice_clone/workflows/qwen3_base_clone_f5_ab.ready.json`.
4. Confirm Character Voices exactly matches `voices/on_camera.reference.txt`; do not retype or paraphrase it.
5. Keep Qwen3 Base 1.7B on `auto`, `float32`, `sdpa`, Shared Runtime, with `x_vector_only_mode=false`.
6. For the first smoke test, use the short sentence already in TTS Text, keep seed 42, leave F5 muted, record `date +%s`, and queue Qwen.

Expected output: `/Users/voxels/ComfyUI-Shared/output/voice_clone/qwen3_base_clone_*.wav`.

Validate the exact newly created file, passing the epoch recorded immediately
before queueing so an old WAV cannot count as success:

```sh
./validate_output.sh /absolute/path/to/new-output.wav RUN_STARTED_EPOCH
```

Technical success requires a completed Comfy history entry and a new,
decodable, non-silent WAV. Human success additionally requires the operator to
confirm the requested words, intelligibility, speaker similarity, clean audio,
and no second-speaker bleed.

## Failure and approval rules

- Preflight exit 2: fix its named input/model/node problem; do not queue.
- Runtime preflight exit 3: Comfy is unavailable; start it normally and rerun. Exit 4: its queue is occupied; wait without restarting or submitting.
- MPS `inf/nan`: Base must use `float32`, not fp16/bfloat16.
- Missing nodes: restart only after the Comfy queue is empty.
- First Shared Runtime initialization may take several minutes.
- Do not mutate the working Qwen environment to satisfy warnings from unused engines.
- Record output path, output creation time, source and staged hashes, reference transcript, target text, settings, seed, prompt ID, and Comfy history status.
- A local agent may prepare and run the job, but only the operator may listen and approve it.

## Local-agent assignment

> Follow `docs/21_VOICE_LOCAL_AGENT_HANDOFF.md`. Run every safe preflight and staging step. Never invent a transcript, approve audio for the user, or restart/submit to ComfyUI while another process owns its queue. At a human gate, report the artifact and exact next command.
