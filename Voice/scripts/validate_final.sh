#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FINAL="$ROOT/output/gage_final_master.flac"

test -s "$FINAL" || { echo "FAIL: missing final master" >&2; exit 1; }
codec=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$FINAL")
rate=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$FINAL")
channels=$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$FINAL")
duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$FINAL")
peak=$(ffmpeg -hide_banner -i "$FINAL" -af volumedetect -f null - 2>&1 | awk '/max_volume/ {print $5; exit}')

test "$codec" = flac
test "$rate" = 24000
test "$channels" = 1
awk -v d="$duration" 'BEGIN { exit !(d > 30) }'
test -n "$peak"

echo "PASS: $FINAL"
echo "duration=$duration codec=$codec rate=$rate channels=$channels max_volume_db=$peak"
shasum -a 256 "$FINAL"
