# comfy_pipeline — v5 execution-layer implementation (metadata layer)

Implements `DESIGN_SPEC_COMFY_PIPELINE.md`. Nothing here generates video;
his Mac executes the graphs in ComfyUI. Everything is verifiable here.

## Modules

| Module | Role |
|---|---|
| `graphs.py` | Load/validate the archived A/B/C API workflows; instantiate the C event-take template per event (token substitution with leftover-token guard); frame-count snapping |
| `manifests.py` | Shot-manifest validation (138 shots, 4 events); take records; review records — only `approved_by: user` + empty issues counts as approved |
| `identity_gate.py` | Automated pre-filter wired to the v3 impression contract (`cezar_id_impression.npy` + `.json`); bands HOLDS d<0.45 / DRIFTS <0.65 / NO MATCH; diagnostic only — user attribution overrules |
| `redirection.py` | Refusal-with-redirection loop (the 05:31 lesson): record → debug along the adjustment ladder → bounded retry (3) → escalate with full debug log, never silence |
| `edl.py` | Assembly EDL from shot + take manifests; missing/unapproved takes block with named reasons |

## Run the tests

```sh
cd ~/workspace/scenefactory-real/v5
python3 -m unittest discover -s comfy_pipeline/tests
```

24 tests, all against the real archived artifacts
(`your_files/cezar-comfy-workflows/`, `teaser_kit/face_id/v3/`).

## Where things run

This machine: graph validation, manifest checks, pre-filter, redirection
logic, EDL. His Mac: ComfyUI queue/execution, LoRA training, identity proof
run, user-eye gate, `assemble_reel.sh`.
