#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROFILE=${PROFILE:-max_data}
COMFY_INPUT=${COMFY_INPUT:-/Users/voxels/ComfyUI-Shared/input}
DEST="$COMFY_INPUT/voice_clone/gage_final_reference.wav"

case "$PROFILE" in
  max_data) SOURCE="$ROOT/reference_profiles/gage_reference_max.wav" ;;
  short_clean) SOURCE="$ROOT/inputs/gage_reference.wav" ;;
  *) echo "PROFILE must be max_data or short_clean" >&2; exit 2 ;;
esac

test -s "$SOURCE"
mkdir -p "$(dirname "$DEST")"
cp "$SOURCE" "$DEST"
cmp -s "$SOURCE" "$DEST"
echo "Staged PROFILE=$PROFILE: $DEST"
shasum -a 256 "$SOURCE" "$DEST"

