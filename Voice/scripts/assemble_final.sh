#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RENDERS="$ROOT/renders"
OUTPUT="$ROOT/output/gage_final_master.flac"
LIST="$ROOT/output/concat.txt"
SILENCE="$ROOT/output/pause_1_2s.flac"

for n in 01 02 03 04 05 06; do
  test -s "$RENDERS/paragraph_$n.flac" || {
    echo "Missing render: $RENDERS/paragraph_$n.flac" >&2
    exit 1
  }
done

ffmpeg -hide_banner -loglevel error -y -f lavfi -i anullsrc=r=24000:cl=mono \
  -t 1.2 -c:a flac "$SILENCE"

: > "$LIST"
for n in 01 02 03 04 05 06; do
  printf "file '%s'\n" "$RENDERS/paragraph_$n.flac" >> "$LIST"
  test "$n" = 06 || printf "file '%s'\n" "$SILENCE" >> "$LIST"
done

ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$LIST" \
  -af 'loudnorm=I=-18:LRA=11:TP=-1.5' -ar 24000 -ac 1 -c:a flac "$OUTPUT"

echo "$OUTPUT"

