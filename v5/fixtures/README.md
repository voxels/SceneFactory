# v5 test fixtures (self-contained)

These fixtures let `test_v5.sh` run anywhere with zero setup.

- `workflows/` — archived ComfyUI API graphs A (identity proof),
  B (environment reference), C (event-take template) + the 138-shot
  manifest. Override with `CEZAR_WORKFLOWS_DIR`.
- `face_id/` — `cezar_id_impression.npy` + `.json`: the user-validated
  identity impression (trimmed mean of 18 user-confirmed faces).
  Override with `CEZAR_FACE_ID_V3`.
