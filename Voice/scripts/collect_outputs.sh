#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMFY_OUTPUT=${COMFY_OUTPUT:-/Users/voxels/ComfyUI-Shared/output}
SOURCE_DIR="$COMFY_OUTPUT/voice_clone"
DEST="$ROOT/renders"
mkdir -p "$DEST"

for n in 01 02 03 04 05 06; do
  latest=$(ls -t "$SOURCE_DIR/gage_final_p${n}_"*.flac 2>/dev/null | head -n 1 || true)
  test -n "$latest" || { echo "No output found for paragraph $n" >&2; exit 1; }
  cp "$latest" "$DEST/paragraph_$n.flac"
  echo "paragraph_$n <- $latest"
done

echo "Collected six renders into $DEST"
