#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FINAL="$ROOT/.speaker_analysis/final"
MANIFEST="$FINAL/speaker_manifest.jsonl"

test -s "$MANIFEST" || { echo "FAIL: missing final speaker manifest" >&2; exit 1; }

gage_count=$(find "$FINAL/accepted/gage" -maxdepth 1 -type f -name '*.wav' | wc -l | tr -d ' ')
ryan_count=$(find "$FINAL/accepted/ryan" -maxdepth 1 -type f -name '*.wav' | wc -l | tr -d ' ')
gage_review_count=$(find "$FINAL/review/gage_channel_recovery" -maxdepth 1 -type f -name '*.wav' 2>/dev/null | wc -l | tr -d ' ')
rejected_count=$(find "$FINAL/quarantine/rejected_by_user" -maxdepth 1 -type f -name 'Hidden*.wav' | wc -l | tr -d ' ')
bad_count=$(find "$FINAL/quarantine/bad_data" -maxdepth 1 -type f -name '*.wav' | wc -l | tr -d ' ')

test "$gage_count" -eq 0 || { echo "FAIL: expected no accepted Gage candidates, found $gage_count" >&2; exit 1; }
test "$ryan_count" -eq 10 || { echo "FAIL: expected 10 accepted Ryan candidates, found $ryan_count" >&2; exit 1; }
test "$gage_review_count" -eq 0 || { echo "FAIL: rejected channel-recovery files remain in review, found $gage_review_count" >&2; exit 1; }
test "$rejected_count" -eq 4 || { echo "FAIL: expected 4 user-rejected candidates, found $rejected_count" >&2; exit 1; }
test "$bad_count" -eq 271 || { echo "FAIL: expected 271 quarantined clips, found $bad_count" >&2; exit 1; }

# These two independently sourced recordings are definitive Gage enrollment
# references. They must never be moved into candidate quarantine.
test -s "$ROOT/voices/on_camera_mov.wav" || { echo "FAIL: missing Gage MOV reference" >&2; exit 1; }
test -s "$ROOT/voices/archive/on_camera_tiktok_7553986048305401143.wav" || {
  echo "FAIL: missing Gage TikTok reference" >&2
  exit 1
}

find "$FINAL/accepted/ryan" -type f -name '*.wav' -print0 |
while IFS= read -r -d '' wav; do
  codec=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$wav")
  rate=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$wav")
  channels=$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$wav")
  video=$(ffprobe -v error -select_streams v -show_entries stream=index -of csv=p=0 "$wav")
  test "$codec" = pcm_s16le && test "$rate" = 24000 && test "$channels" = 1 && test -z "$video" || {
    echo "FAIL: invalid audio-only format: $wav" >&2
    exit 1
  }
done

missing=0
while IFS= read -r clip; do
  if test ! -f "$clip"; then
    echo "FAIL: manifest target missing: $clip" >&2
    missing=$((missing + 1))
  fi
done <<EOF
$(jq -r '.clip' "$MANIFEST")
EOF
test "$missing" -eq 0 || exit 1

echo "PASS: audio-only speaker selection is internally consistent"
echo "PASS: 10 confirmed Ryan clips; rejected channel-recovery audio is excluded from review and training"
echo "NOTICE: definitive MOV/TikTok Gage references are the only Gage enrollment data"
