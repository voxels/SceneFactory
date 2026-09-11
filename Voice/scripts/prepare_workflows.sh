#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BASE="$ROOT/workflows/base.api.json"
SCRIPT="$ROOT/inputs/tts_script.txt"
OUT="$ROOT/workflows"
PROFILE=${PROFILE:-max_data}

test -s "$BASE"
test -s "$SCRIPT"

case "$PROFILE" in
  max_data)
    REF_TEXT_FILE="$ROOT/reference_profiles/gage_reference_max.txt"
    TEMPERATURE=0.72
    MAX_CHARS=180
    COMBINATION=silence_padding
    SILENCE_MS=140
    ;;
  short_clean)
    REF_TEXT_FILE="$ROOT/inputs/gage_reference.txt"
    TEMPERATURE=0.78
    MAX_CHARS=400
    COMBINATION=crossfade
    SILENCE_MS=100
    ;;
  *) echo "PROFILE must be max_data or short_clean" >&2; exit 2 ;;
esac

test -s "$REF_TEXT_FILE"
REF_TEXT=$(tr '\n' ' ' < "$REF_TEXT_FILE")

awk 'BEGIN { RS="\\[pause:1\\.2\\]" }
     { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0); if (length($0)) print $0 }' \
    "$SCRIPT" > "$OUT/paragraphs.txt"

count=$(wc -l < "$OUT/paragraphs.txt" | tr -d ' ')
test "$count" -eq 6 || {
  echo "Expected 6 paragraphs, found $count" >&2
  exit 1
}

i=1
while IFS= read -r paragraph; do
  n=$(printf '%02d' "$i")
  jq --arg text "$paragraph" --arg prefix "voice_clone/gage_final_p$n" \
    --arg reference_text "$REF_TEXT" --argjson temperature "$TEMPERATURE" \
    --argjson max_chars "$MAX_CHARS" --arg combination "$COMBINATION" \
    --argjson silence_ms "$SILENCE_MS" \
    '.["2"].inputs.audio = "voice_clone/gage_final_reference.wav"
     | .["3"].inputs.reference_text = $reference_text
     | .["4"].inputs.instruct = "Closely match the reference speaker’s natural pronunciation, cadence, rhythm, vocal weight, and relaxed conversational delivery. Use varied sentence-level intonation and natural emphasis. Avoid broadcast or corporate-presenter diction."
     | .["4"].inputs.temperature = $temperature
     | .["4"].inputs.top_p = 0.95
     | .["5"].inputs.text = $text
     | .["5"].inputs.seed = 43
     | .["5"].inputs.max_chars_per_chunk = $max_chars
     | .["5"].inputs.chunk_combination_method = $combination
     | .["5"].inputs.silence_between_chunks_ms = $silence_ms
     | .["7"].inputs.filename_prefix = $prefix' \
    "$BASE" > "$OUT/paragraph_$n.api.json"
  i=$((i + 1))
done < "$OUT/paragraphs.txt"

echo "Prepared 6 paragraph workflows in $OUT using PROFILE=$PROFILE"
