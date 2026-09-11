#!/bin/zsh
set -euo pipefail
COMFY_ROOT="${COMFY_ROOT:-/Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI}"
SHARED_INPUT="${SHARED_INPUT:-/Users/voxels/ComfyUI-Shared/input}"
SHARED_MODELS="${SHARED_MODELS:-/Users/voxels/ComfyUI-Shared/models}"
ROOT="$(cd "$(dirname "$0")" && pwd)"

base_model="$ROOT/models/qwen3_tts/Qwen3-TTS-12Hz-1.7B-Base/model.safetensors"
speech_tokenizer_model="$ROOT/models/qwen3_tts/Qwen3-TTS-12Hz-1.7B-Base/speech_tokenizer/model.safetensors"
tokenizer_model="$ROOT/models/qwen3_tts/Qwen3-TTS-Tokenizer-12Hz/model.safetensors"
reference_wav="$ROOT/voices/on_camera.wav"
transcript_file="$ROOT/voices/on_camera.reference.txt"
workflow_template="$ROOT/workflows/qwen3_base_clone_f5_ab.json"
ready_workflow="$ROOT/workflows/qwen3_base_clone_f5_ab.ready.json"
for required_file in "$base_model" "$speech_tokenizer_model" "$tokenizer_model" "$reference_wav" "$transcript_file" "$workflow_template"; do
  if [[ ! -s "$required_file" ]]; then
    echo "Refusing to stage incomplete voice-clone assets; missing: $required_file" >&2
    exit 2
  fi
done

transcript="$(sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$transcript_file" | awk 'NF' | paste -sd ' ' -)"
if [[ -z "$transcript" ]] || print -r -- "$transcript" | grep -Eqi 'paste .*words|exact transcript|todo|placeholder|__REFERENCE_TRANSCRIPT_REQUIRED__'; then
  echo "Refusing to stage an empty or placeholder reference transcript: $transcript_file" >&2
  exit 2
fi

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "Refusing to stage without ffprobe; reference duration and format cannot be validated" >&2
  exit 2
fi
reference_fields="$(ffprobe -v error -select_streams a:0 \
  -show_entries stream=codec_name,sample_rate,channels \
  -show_entries format=duration -of default=noprint_wrappers=1 \
  "$reference_wav" 2>/dev/null || true)"
reference_codec="$(print -r -- "$reference_fields" | awk -F= '$1=="codec_name" {print $2}')"
reference_rate="$(print -r -- "$reference_fields" | awk -F= '$1=="sample_rate" {print $2}')"
reference_channels="$(print -r -- "$reference_fields" | awk -F= '$1=="channels" {print $2}')"
reference_duration="$(print -r -- "$reference_fields" | awk -F= '$1=="duration" {print $2}')"
if [[ "$reference_codec" != "pcm_s16le" || "$reference_rate" != "22050" || "$reference_channels" != "1" ]]; then
  echo "Refusing to stage invalid reference format: expected pcm_s16le/22050 Hz/mono, got $reference_codec/$reference_rate/$reference_channels" >&2
  exit 2
fi
if [[ -z "$reference_duration" ]] || ! awk -v d="$reference_duration" 'BEGIN { exit !(d >= 6 && d <= 15) }'; then
  echo "Refusing to stage reference duration ${reference_duration:-unknown}s; Qwen3 ICL requires 6-15s" >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Refusing to stage without jq; it is required to embed the verified transcript" >&2
  exit 2
fi

mkdir -p "$SHARED_INPUT/voice_clone" "$COMFY_ROOT/models/TTS" "$SHARED_MODELS/TTS"
staged_reference="$SHARED_INPUT/voice_clone/reference.wav"
reference_tmp="$SHARED_INPUT/voice_clone/.reference.wav.$$"
workflow_tmp="$ROOT/workflows/.qwen3_ready.$$"
trap 'rm -f "$reference_tmp" "$workflow_tmp"' EXIT
cp -f "$reference_wav" "$reference_tmp"
mv -f "$reference_tmp" "$staged_reference"

jq --arg transcript "$transcript" '
  (.nodes[] | select(.id == 3 and .type == "CharacterVoicesNode") | .widgets_values[1]) = $transcript
' "$workflow_template" > "$workflow_tmp"
mv -f "$workflow_tmp" "$ready_workflow"

if ! cmp -s "$reference_wav" "$staged_reference"; then
  echo "Staged reference does not match canonical reference: $staged_reference" >&2
  exit 2
fi
# Prefer the Comfy install models tree; also copy to shared TTS if that folder exists.
if [[ -d "$COMFY_ROOT/models" ]]; then
  mkdir -p "$COMFY_ROOT/models/TTS"
  rsync -a "$ROOT/models/qwen3_tts/" "$COMFY_ROOT/models/TTS/qwen3_tts/"
fi
if [[ -d "$SHARED_MODELS" ]]; then
  mkdir -p "$SHARED_MODELS/TTS"
  rsync -a "$ROOT/models/qwen3_tts/" "$SHARED_MODELS/TTS/qwen3_tts/"
fi
echo "Staged canonical reference WAV and Qwen3 weights."
echo "Generated ready workflow with verified transcript: $ready_workflow"
echo "Restart Comfy only after its queue is empty."
