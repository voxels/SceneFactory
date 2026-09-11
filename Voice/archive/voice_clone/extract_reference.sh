#!/bin/zsh
set -euo pipefail

usage() {
  cat <<'EOF'
Extract a 6-15s mono 22050 Hz PCM16 WAV from a local video for Qwen3/F5 voice cloning.

Usage:
  ./extract_reference.sh INPUT.mp4 [OUT.wav] [START_SECONDS] [DURATION_SECONDS]

Examples:
  ./extract_reference.sh clip.mp4
  ./extract_reference.sh clip.mp4 ./input/reference.wav 12.5 10

Defaults:
  OUT      = ./input/reference.wav
  START    = 0
  DURATION = 12

Requires ffmpeg. Does not call any network API.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || $# -lt 1 ]]; then
  usage
  exit 0
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found" >&2
  exit 1
fi

input="$1"
out="${2:-./input/reference.wav}"
start="${3:-0}"
duration="${4:-12}"

if ! [[ -f "$input" ]]; then
  echo "Input not found: $input" >&2
  exit 1
fi

python3 - <<PY
duration = float("$duration")
if duration < 6 or duration > 15:
    raise SystemExit("Duration must be between 6 and 15 seconds (got $duration)")
PY

mkdir -p "$(dirname "$out")"
ffmpeg -y -ss "$start" -t "$duration" -i "$input" \
  -vn -acodec pcm_s16le -ar 22050 -ac 1 \
  "$out"

echo "Wrote $out"
echo "Next: put this WAV in ComfyUI input as voice_clone/reference.wav"
echo "      and paste the exact spoken transcript into Character Voices."
