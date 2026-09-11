#!/bin/sh
set -eu

# Extract an audition copy from an original audio-only candidate while keeping
# the selected source channel intact. This never edits or replaces source data.
if [ "$#" -ne 6 ]; then
  echo "usage: $0 SOURCE START DURATION CHANNEL OUTPUT SAMPLE_RATE" >&2
  exit 2
fi

source_audio=$1
start=$2
duration=$3
channel=$4
output=$5
sample_rate=$6

case "$channel" in
  left) pan='pan=mono|c0=FL' ;;
  right) pan='pan=mono|c0=FR' ;;
  *) echo "CHANNEL must be left or right" >&2; exit 2 ;;
esac

mkdir -p "$(dirname "$output")"
ffmpeg -hide_banner -loglevel error -y \
  -ss "$start" -t "$duration" -i "$source_audio" -vn \
  -af "$pan,highpass=f=70,lowpass=f=11000,loudnorm=I=-18:LRA=11:TP=-1.5" \
  -ar "$sample_rate" -c:a pcm_s24le "$output"
