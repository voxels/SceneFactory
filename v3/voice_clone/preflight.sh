#!/bin/zsh
set -euo pipefail

# Validate the local Qwen3 Base voice-clone inputs without starting ComfyUI or
# submitting a prompt. This is safe to run while another workflow owns Comfy.

ROOT="$(cd "$(dirname "$0")" && pwd)"
COMFY_ROOT="${COMFY_ROOT:-/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI}"
MODEL_ROOT="${Qwen3_TTS_DIR:-$COMFY_ROOT/models/TTS/qwen3_tts}"
SHARED_INPUT="${SHARED_INPUT:-/Users/voxels/ComfyUI-Shared/input}"
REFERENCE_WAV="${VOICE_REFERENCE_WAV:-$ROOT/voices/on_camera.wav}"
TRANSCRIPT_FILE="${VOICE_TRANSCRIPT_FILE:-$ROOT/voices/on_camera.reference.txt}"
STAGED_REFERENCE="$SHARED_INPUT/voice_clone/reference.wav"
WORKFLOW_TEMPLATE="$ROOT/workflows/qwen3_base_clone_f5_ab.json"
READY_WORKFLOW="$ROOT/workflows/qwen3_base_clone_f5_ab.ready.json"
MIN_REFERENCE_SECONDS="${MIN_REFERENCE_SECONDS:-6}"
MAX_REFERENCE_SECONDS="${MAX_REFERENCE_SECONDS:-15}"

failures=0
fail() {
  print -u2 -- "FAIL: $*"
  failures=$((failures + 1))
}
pass() {
  print -- "PASS: $*"
}

require_file() {
  local file_path="$1"
  local label="$2"
  local min_bytes="${3:-1}"
  if [[ ! -f "$file_path" ]]; then
    fail "$label missing: $file_path"
    return
  fi
  local size
  size="$(stat -f %z "$file_path")"
  if (( size < min_bytes )); then
    fail "$label is incomplete ($size bytes; need at least $min_bytes): $file_path"
    return
  fi
  pass "$label present ($size bytes)"
}

require_file "$MODEL_ROOT/Qwen3-TTS-12Hz-1.7B-Base/model.safetensors" "Qwen3 Base model" 3000000000
require_file "$MODEL_ROOT/Qwen3-TTS-12Hz-1.7B-Base/speech_tokenizer/model.safetensors" "Base speech tokenizer" 500000000
require_file "$MODEL_ROOT/Qwen3-TTS-Tokenizer-12Hz/model.safetensors" "Qwen3 tokenizer" 500000000
require_file "$WORKFLOW_TEMPLATE" "Comfy workflow template"
require_file "$READY_WORKFLOW" "generated ready workflow"

if [[ -d "$COMFY_ROOT/custom_nodes/TTS-Audio-Suite" ]]; then
  pass "TTS-Audio-Suite installed"
else
  fail "TTS-Audio-Suite missing: $COMFY_ROOT/custom_nodes/TTS-Audio-Suite"
fi

if ! command -v ffprobe >/dev/null 2>&1; then
  fail "ffprobe is required to validate the reference WAV"
elif [[ ! -s "$REFERENCE_WAV" ]]; then
  fail "reference WAV missing or empty: $REFERENCE_WAV"
else
  audio_fields="$(ffprobe -v error -select_streams a:0 \
    -show_entries stream=codec_name,sample_rate,channels \
    -show_entries format=duration \
    -of default=noprint_wrappers=1 "$REFERENCE_WAV" 2>/dev/null || true)"
  codec="$(print -r -- "$audio_fields" | awk -F= '$1=="codec_name" {print $2}')"
  sample_rate="$(print -r -- "$audio_fields" | awk -F= '$1=="sample_rate" {print $2}')"
  channels="$(print -r -- "$audio_fields" | awk -F= '$1=="channels" {print $2}')"
  duration="$(print -r -- "$audio_fields" | awk -F= '$1=="duration" {print $2}')"

  if [[ "$codec" == "pcm_s16le" && "$sample_rate" == "22050" && "$channels" == "1" ]]; then
    pass "reference format is PCM16 mono at 22050 Hz"
  else
    fail "reference format must be pcm_s16le/22050 Hz/mono (got $codec/$sample_rate/$channels)"
  fi

  if [[ -z "$duration" ]]; then
    fail "could not determine reference duration: $REFERENCE_WAV"
  elif awk -v d="$duration" -v lo="$MIN_REFERENCE_SECONDS" -v hi="$MAX_REFERENCE_SECONDS" \
    'BEGIN { exit !(d >= lo && d <= hi) }'; then
    pass "reference duration ${duration}s is within ${MIN_REFERENCE_SECONDS}-${MAX_REFERENCE_SECONDS}s"
  else
    fail "reference duration ${duration}s is outside ${MIN_REFERENCE_SECONDS}-${MAX_REFERENCE_SECONDS}s"
  fi
fi

if [[ ! -s "$TRANSCRIPT_FILE" ]]; then
  fail "exact reference transcript missing or empty: $TRANSCRIPT_FILE"
else
  transcript="$(sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$TRANSCRIPT_FILE" | awk 'NF' | paste -sd ' ' -)"
  if [[ -z "$transcript" ]]; then
    fail "exact reference transcript contains no text: $TRANSCRIPT_FILE"
  elif print -r -- "$transcript" | grep -Eqi 'paste .*words|exact transcript|todo|placeholder'; then
    fail "reference transcript still contains placeholder instructions: $TRANSCRIPT_FILE"
  else
    pass "exact reference transcript present (${#transcript} characters)"
  fi
fi

if [[ -s "$STAGED_REFERENCE" ]]; then
  if cmp -s "$REFERENCE_WAV" "$STAGED_REFERENCE"; then
    pass "staged Comfy reference matches canonical reference"
  else
    fail "staged Comfy reference is stale or different: $STAGED_REFERENCE"
  fi
else
  fail "staged Comfy reference missing: $STAGED_REFERENCE"
fi

if ! command -v jq >/dev/null 2>&1; then
  fail "jq is required to validate the generated workflow"
elif [[ -s "$READY_WORKFLOW" && -n "${transcript:-}" ]]; then
  workflow_transcript="$(jq -r '.nodes[] | select(.id == 3 and .type == "CharacterVoicesNode") | .widgets_values[1]' "$READY_WORKFLOW" 2>/dev/null || true)"
  if [[ "$workflow_transcript" == "$transcript" ]]; then
    pass "ready workflow embeds the verified reference transcript"
  else
    fail "ready workflow transcript differs from $TRANSCRIPT_FILE; rerun stage_into_comfy.sh"
  fi

  if jq -e '
    (.nodes[] | select(.id == 4 and .type == "Qwen3TTSEngineNode") | .widgets_values) as $w |
    $w[0] == "TTS - Base 1.7B (Voice Clone)" and
    $w[1] == "auto" and $w[10] == "float32" and $w[11] == "sdpa" and
    $w[12] == false and $w[13] == false and $w[14] == false and
    $w[19] == "⚠️ Shared Runtime"
  ' "$READY_WORKFLOW" >/dev/null 2>&1; then
    pass "ready workflow has safe Qwen MPS settings"
  else
    fail "ready workflow Qwen settings are not the required Base/auto/float32/sdpa/Shared Runtime configuration"
  fi

  if jq -e '(.nodes[] | select(.id == 11 and .type == "UnifiedTTSTextNode") | .mode) == 4' "$READY_WORKFLOW" >/dev/null 2>&1; then
    pass "F5 synthesis remains muted for the smoke test"
  else
    fail "F5 synthesis node must remain muted (mode 4) for the smoke test"
  fi
fi

if (( failures > 0 )); then
  print -u2 -- "Voice-clone preflight failed with $failures issue(s). Do not queue the workflow."
  exit 2
fi

print -- "Voice-clone assets pass static preflight. Confirm Comfy's queue is empty before submitting TTS."
