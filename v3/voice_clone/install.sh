#!/bin/zsh
set -euo pipefail

# Install diodiogod/TTS-Audio-Suite into a local ComfyUI tree.
# Does not restart ComfyUI. Do not run this while you still need the live
# Ad2184 LTX queue; the nodes only load after a Comfy restart.

ROOT="$(cd "$(dirname "$0")" && pwd)"
COMFY_ROOT="${COMFY_ROOT:-/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI}"
CUSTOM_NODES="$COMFY_ROOT/custom_nodes"
TARGET="$CUSTOM_NODES/TTS-Audio-Suite"
VENDOR="$ROOT/vendor/TTS-Audio-Suite"

if [[ ! -d "$COMFY_ROOT" ]]; then
  echo "ComfyUI root not found: $COMFY_ROOT" >&2
  echo "Set COMFY_ROOT to the folder that contains main.py" >&2
  exit 1
fi

mkdir -p "$CUSTOM_NODES"

if [[ -d "$TARGET/.git" ]]; then
  echo "Updating existing TTS-Audio-Suite at $TARGET"
  git -C "$TARGET" pull --ff-only
elif [[ -d "$VENDOR/.git" ]]; then
  echo "Copying vendored TTS-Audio-Suite to $TARGET"
  rm -rf "$TARGET"
  cp -R "$VENDOR" "$TARGET"
else
  echo "Cloning TTS-Audio-Suite into $TARGET"
  git clone --depth 1 https://github.com/diodiogod/TTS-Audio-Suite.git "$TARGET"
fi

COMFY_PYTHON="${COMFY_PYTHON:-}"
if [[ -z "$COMFY_PYTHON" ]]; then
  for candidate in \
    "$COMFY_ROOT/.venv/bin/python" \
    "$COMFY_ROOT/../.venv/bin/python" \
    "$COMFY_ROOT/.venv/bin/python3"
  do
    if [[ -x "$candidate" ]]; then
      COMFY_PYTHON="$candidate"
      break
    fi
  done
fi

if [[ -z "${COMFY_PYTHON:-}" ]]; then
  echo "Could not find ComfyUI Python. Set COMFY_PYTHON." >&2
  exit 1
fi

arch="$("$COMFY_PYTHON" -c 'import platform; print(platform.machine())')"
if [[ "$arch" != "arm64" ]]; then
  echo "Refusing to install with non-arm64 Python ($arch). Use native Apple Silicon Python, not Rosetta." >&2
  exit 1
fi

echo "Running TTS-Audio-Suite install.py with $COMFY_PYTHON"
cd "$TARGET"
"$COMFY_PYTHON" install.py

mkdir -p "$COMFY_ROOT/models/TTS/qwen3_tts"
mkdir -p "$COMFY_ROOT/models/TTS/F5-TTS"
mkdir -p "$COMFY_ROOT/models/voices"
mkdir -p "${COMFY_INPUT_ROOT:-/Users/voxels/ComfyUI-Shared/input}/voice_clone"

echo "Installed. Restart ComfyUI after the Ad2184 jobs finish."
echo "Then run ./download_models.sh"
