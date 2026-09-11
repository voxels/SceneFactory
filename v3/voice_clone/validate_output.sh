#!/bin/zsh
set -euo pipefail

if (( $# < 1 || $# > 2 )); then
  echo "Usage: ./validate_output.sh OUTPUT_AUDIO [NOT_BEFORE_EPOCH]" >&2
  exit 2
fi

output="$1"
not_before="${2:-0}"
if [[ ! -s "$output" ]]; then
  echo "FAIL: output audio is missing or empty: $output" >&2
  exit 2
fi
if ! command -v ffprobe >/dev/null 2>&1 || ! command -v ffmpeg >/dev/null 2>&1; then
  echo "FAIL: ffprobe and ffmpeg are required" >&2
  exit 2
fi

modified="$(stat -f %m "$output")"
if (( modified < not_before )); then
  echo "FAIL: output predates this test run ($modified < $not_before): $output" >&2
  exit 2
fi

duration="$(ffprobe -v error -select_streams a:0 -show_entries format=duration -of default=nw=1:nk=1 "$output" 2>/dev/null || true)"
if [[ -z "$duration" ]] || ! awk -v d="$duration" 'BEGIN { exit !(d >= 0.25) }'; then
  echo "FAIL: output has no decodable audio or is too short (${duration:-unknown}s): $output" >&2
  exit 2
fi

max_volume="$(ffmpeg -hide_banner -nostats -i "$output" -af volumedetect -f null - 2>&1 | awk '/max_volume:/ {print $5}' | tail -1)"
if [[ -z "$max_volume" || "$max_volume" == "-inf" ]]; then
  echo "FAIL: output appears silent: $output" >&2
  exit 2
fi

echo "PASS: new output is decodable, ${duration}s long, and non-silent (max ${max_volume} dB): $output"
echo "Human approval is still required for words, speaker similarity, cleanliness, and absence of speaker bleed."
