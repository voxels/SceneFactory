#!/bin/zsh
set -euo pipefail

# Offline-after-cache download of the required Qwen3-TTS Base 1.7B cloner
# plus the shared 12Hz tokenizer. Optional variants are flags.

ROOT="$(cd "$(dirname "$0")" && pwd)"
COMFY_ROOT="${COMFY_ROOT:-/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI}"
DEST="${Qwen3_TTS_DIR:-$COMFY_ROOT/models/TTS/qwen3_tts}"
STAGING="$ROOT/models/qwen3_tts"
HUB_PYTHON="${COMFY_PYTHON:-python3}"

if [[ ! -d "$COMFY_ROOT" ]]; then
  echo "ComfyUI root not writable/present; staging into $STAGING"
  DEST="$STAGING"
fi

mkdir -p "$DEST"

if ! command -v hf >/dev/null 2>&1 && ! "$HUB_PYTHON" -c 'import huggingface_hub' >/dev/null 2>&1; then
  echo "Need huggingface_hub. Install with the ComfyUI Python:" >&2
  echo "  \"\$COMFY_PYTHON\" -m pip install -U 'huggingface_hub[cli]'" >&2
  exit 1
fi

download() {
  local repo="$1"
  local dir="$2"
  mkdir -p "$dir"
  if command -v hf >/dev/null 2>&1; then
    hf download "$repo" --local-dir "$dir"
  else
    "$HUB_PYTHON" - <<PY
from huggingface_hub import snapshot_download
snapshot_download(repo_id="$repo", local_dir="$dir", local_dir_use_symlinks=False)
PY
  fi
}

echo "Downloading required cloner to $DEST/Qwen3-TTS-12Hz-1.7B-Base"
download "Qwen/Qwen3-TTS-12Hz-1.7B-Base" "$DEST/Qwen3-TTS-12Hz-1.7B-Base"

echo "Downloading tokenizer to $DEST/Qwen3-TTS-Tokenizer-12Hz"
download "Qwen/Qwen3-TTS-Tokenizer-12Hz" "$DEST/Qwen3-TTS-Tokenizer-12Hz"

if [[ ! -s "$DEST/Qwen3-TTS-12Hz-1.7B-Base/model.safetensors" ]]; then
  echo "Base model download is incomplete: $DEST/Qwen3-TTS-12Hz-1.7B-Base/model.safetensors" >&2
  exit 2
fi
if [[ ! -s "$DEST/Qwen3-TTS-Tokenizer-12Hz/model.safetensors" ]]; then
  echo "Tokenizer download is incomplete: $DEST/Qwen3-TTS-Tokenizer-12Hz/model.safetensors" >&2
  exit 2
fi

if [[ "${DOWNLOAD_OPTIONAL:-0}" == "1" ]]; then
  download "Qwen/Qwen3-TTS-12Hz-0.6B-Base" "$DEST/Qwen3-TTS-12Hz-0.6B-Base"
  download "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign" "$DEST/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
  download "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice" "$DEST/Qwen3-TTS-12Hz-1.7B-CustomVoice"
fi

echo "Done. After cache, this machine can run offline."
echo "F5-TTS v1 Base auto-downloads on first F5 engine run into models/TTS/F5-TTS/F5TTS_v1_Base/"
