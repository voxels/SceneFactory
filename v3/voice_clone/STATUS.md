# Voice-clone setup status (historical snapshot: 2026-08-29)

This file records an earlier installation state and is superseded by
`../docs/21_VOICE_LOCAL_AGENT_HANDOFF.md` plus the current preflight output. Do
not use the statements below as current readiness checks.

Live Ad2184 Comfy/LTX jobs were still running. This session did **not** restart ComfyUI, POST to `/prompt`, or edit Ad2184 graphs.

## In progress (2026-08-29 evening)

- On-camera reference WAV is `input/reference.wav` (1.35s).
- Qwen3-TTS 1.7B Base **configs** are on disk under `models/qwen3_tts/Qwen3-TTS-12Hz-1.7B-Base/`.
- Weight download (`speech_tokenizer/model.safetensors` then `model.safetensors`, ~4.5 GB) is running via curl into that folder. ComfyUI still cannot be written from this sandbox; after the download, run `./stage_into_comfy.sh` from Terminal.
- LTX runner is still live. Do not restart Comfy until it exits.

## Done in this workspace

- Vendored [TTS-Audio-Suite](https://github.com/diodiogod/TTS-Audio-Suite) at `vendor/TTS-Audio-Suite` (gitignored, ~185 MB) for `install.py`.
- Loadable workflow: `workflows/qwen3_base_clone_f5_ab.json`
- `extract_reference.sh`, `install.sh`, `download_models.sh`, `README.md`

## Blocked from this sandbox (TCC / path ACL)

| Target | Result |
|---|---|
| `/Users/voxels/ComfyUI-Installs/ComfyUI/` | Operation not permitted — cannot copy custom_nodes |
| `/Users/voxels/ComfyUI-Shared/` | Operation not permitted — cannot drop models or input WAV |
| `python3 -m pip install huggingface_hub` | PermissionError on `/opt/local/USD/lib/python` |
| `python3 -m venv voice_clone/.venv` | ensurepip failed |

So nodes are **not** registered in the live Comfy process yet, and Qwen3-TTS-12Hz-1.7B-Base is **not** on disk yet.

## Operator next (Terminal, after LTX finishes)

```sh
cd /Users/voxels/SceneFactory/v3/voice_clone
chmod +x extract_reference.sh install.sh download_models.sh
export COMFY_ROOT=/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI
export COMFY_PYTHON="$COMFY_ROOT/.venv/bin/python"
"$COMFY_PYTHON" -c 'import platform; assert platform.machine()=="arm64"'
./install.sh
./download_models.sh
```

Then restart Comfy Desktop, load the workflow, copy `reference.wav` into Shared input, queue the Qwen group only.

## MPS notes verified in suite source

- `utils/device/torch_device_resolver.py`: `auto` prefers MPS on Apple Silicon.
- Qwen3 engine UI device list is `auto`/`cuda`/`cpu` only. Use `auto` + `dtype=float32` + `attn=sdpa`.
- F5 engine UI includes `mps`; the A/B group is set to `mps` and muted by default.
