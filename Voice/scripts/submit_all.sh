#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMFY_URL=${COMFY_URL:-http://127.0.0.1:8188}
RUN="$ROOT/run"
mkdir -p "$RUN"

queue=$(curl -fsS "$COMFY_URL/queue")
running=$(printf '%s' "$queue" | jq '.queue_running | length')
pending=$(printf '%s' "$queue" | jq '.queue_pending | length')
test "$running" -eq 0 && test "$pending" -eq 0 || {
  echo "Comfy queue is not empty: running=$running pending=$pending" >&2
  exit 1
}

: > "$RUN/prompt_ids.tsv"
for n in 01 02 03 04 05 06; do
  workflow="$ROOT/workflows/paragraph_$n.api.json"
  test -s "$workflow"
  request=$(mktemp /tmp/gage-final-request.XXXXXX)
  jq -n --slurpfile prompt "$workflow" --arg client_id "gage-final-p$n" \
    '{prompt:$prompt[0],client_id:$client_id}' > "$request"
  response=$(curl -fsS -H 'Content-Type: application/json' \
    --data-binary "@$request" "$COMFY_URL/prompt")
  id=$(printf '%s' "$response" | jq -r '.prompt_id // empty')
  test -n "$id" || { echo "$response" >&2; exit 1; }
  printf 'paragraph_%s\t%s\n' "$n" "$id" | tee -a "$RUN/prompt_ids.tsv"
done

echo "Submitted six paragraphs. Monitor: curl -fsS $COMFY_URL/queue | jq ."

