#!/bin/zsh
set -euo pipefail

# Verify that a running ComfyUI instance can accept this workflow without
# starting, restarting, or submitting any job.

COMFY_URL="${COMFY_URL:-http://127.0.0.1:8188}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
READY_WORKFLOW="$ROOT/workflows/qwen3_base_clone_f5_ab.ready.json"

for command_name in curl jq; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "FAIL: $command_name is required for runtime preflight" >&2
    exit 2
  fi
done

if [[ ! -s "$READY_WORKFLOW" ]]; then
  echo "FAIL: generated workflow missing; run ./stage_into_comfy.sh first" >&2
  exit 2
fi

queue_json="$(curl -fsS --max-time 5 "$COMFY_URL/queue" 2>/dev/null)" || {
  echo "FAIL: ComfyUI is not reachable at $COMFY_URL; start it through the normal operator workflow, then rerun this check" >&2
  exit 3
}

running="$(print -r -- "$queue_json" | jq -r '.queue_running | length')"
pending="$(print -r -- "$queue_json" | jq -r '.queue_pending | length')"
if (( running > 0 || pending > 0 )); then
  echo "FAIL: ComfyUI queue is occupied (running=$running, pending=$pending); do not submit or restart" >&2
  exit 4
fi
echo "PASS: ComfyUI is reachable and its queue is empty"

object_info="$(curl -fsS --max-time 10 "$COMFY_URL/object_info" 2>/dev/null)" || {
  echo "FAIL: could not read ComfyUI node registration from $COMFY_URL/object_info" >&2
  exit 3
}

missing=0
for node_name in Qwen3TTSEngineNode CharacterVoicesNode UnifiedTTSTextNode SaveAudio LoadAudio; do
  if print -r -- "$object_info" | jq -e --arg node "$node_name" 'has($node)' >/dev/null; then
    echo "PASS: node registered: $node_name"
  else
    echo "FAIL: node not registered: $node_name" >&2
    missing=$((missing + 1))
  fi
done
if (( missing > 0 )); then
  echo "Runtime preflight failed with $missing missing node(s). Restart only when the queue remains empty." >&2
  exit 2
fi

vendor_suite="$ROOT/vendor/TTS-Audio-Suite"
installed_suite="${COMFY_ROOT:-/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI}/custom_nodes/TTS-Audio-Suite"
if command -v git >/dev/null 2>&1 && [[ -d "$vendor_suite/.git" && -d "$installed_suite/.git" ]]; then
  vendor_revision="$(git -C "$vendor_suite" rev-parse HEAD)"
  installed_revision="$(git -C "$installed_suite" rev-parse HEAD)"
  if [[ "$vendor_revision" == "$installed_revision" ]]; then
    echo "PASS: installed TTS-Audio-Suite matches staged revision $vendor_revision"
  else
    echo "FAIL: installed suite revision $installed_revision differs from staged revision $vendor_revision" >&2
    exit 2
  fi
fi

echo "Voice-clone runtime preflight passed. Load $READY_WORKFLOW for the smoke test."
