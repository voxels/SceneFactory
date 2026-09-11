#!/bin/bash
# test_v5.sh — single-step test for SceneFactory v5.
# Usage: ./test_v5.sh   (run from anywhere; it finds its own directory)
# Exit 0 = all suites green. No ComfyUI, no GPU, no network needed.
set -uo pipefail
V5="$(cd "$(dirname "$0")" && pwd)"
cd "$V5" || exit 1
export PYTHONPATH="$V5${PYTHONPATH:+:$PYTHONPATH}"
command -v python3 >/dev/null || { echo "FAIL: python3 not found"; exit 1; }

pass=0; fail=0
run_suite() {
  local name="$1"; shift
  echo "=== $name ==="
  if python3 "$@" 2>&1 | tail -5; then
    echo "--> $name: PASS"; pass=$((pass+1))
  else
    echo "--> $name: FAIL"; fail=$((fail+1))
  fi
  echo
}

run_suite "v5 pipeline state (2 tests)"            tests/test_pipeline_state.py
run_suite "comfy_pipeline metadata (24 tests)"     comfy_pipeline/tests/test_comfy_pipeline.py
run_suite "comfy_app node schemas (97 checks)"    comfy_app/tests/test_node_schemas.py

echo "==============================="
echo "suites passed: $pass, failed: $fail"
[ "$fail" -eq 0 ] && echo "V5 ALL GREEN" || echo "V5 HAS FAILURES"
exit "$fail"
