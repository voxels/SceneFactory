# SceneFactory v5 — clean install

One zip, one test command, one node-pack copy. No pip installs, no network.

## 1. Unzip

Unzip `scene-factory-v5.zip` at your SceneFactory repo root. It creates `v5/`:

```
v5/
  test_v5.sh               # single-step test runner
  fixtures/                # bundled test data (workflows + identity impression)
  comfy_pipeline/          # metadata pipeline (graphs, manifests, gates, EDL)
  comfy_app/               # ComfyUI custom-node pack (13 nodes + review UI)
  DESIGN_SPEC_COMFY_PIPELINE.md
  CHATLOG_CORRELATION.md
```

## 2. Verify (one step)

```bash
./v5/test_v5.sh
```

Expect `V5 ALL GREEN` (2 + 24 + 97 checks). Pure stdlib Python — no ComfyUI,
no torch, no GPU. Exit code is non-zero on any failure.

## 3. Install the ComfyUI node pack

```bash
cp -r v5/comfy_app /path/to/ComfyUI/custom_nodes/scenefactory_app
```

Restart ComfyUI. Confirm 13 nodes load under `SceneFactory/Workflow`,
`SceneFactory/Voice`, `SceneFactory/Review`, `SceneFactory/Manifests`.

## 4. Run order

1. **A — identity proof.** `SF_IdentityReferenceIntake` + `SF_IdentityGatePrefilter`.
   Gate bands are diagnostic only; nothing proceeds without your eyes.
2. **Your approval.** `SF_ReviewCandidateBrowser` → `SF_UserAttribution`.
   Your attribution overrules the model, no exceptions.
3. **B — environment.** `SF_EnvironmentReference` (separated env PLY + trajectory).
4. **C — event takes.** `SF_EventTakeParams` per shot in `manifest_shots.json`.
5. **Voice.** `SF_VoiceReferenceProfile` → `SF_VoiceParagraphRender` →
   `SF_VoiceListeningGate` → your listening approval. Voice is a first-class
   stream, not an add-on.
6. **D — assembly.** `SF_AssemblyHandoff` builds the EDL. A missing take is a
   hard, named failure — never a silent skip. Rejected takes stay as negative
   training data; nothing is deleted without your approval.

## 5. Rules that don't bend

- Refusals debug through the adjustment ladder (max 3 attempts), then escalate
  with the full log. A refusal without redirection is a failure.
- No PC LoRA phase before the Mac identity proof passes.
- Clean structural assemblies only — no color grading, no photo editing.

## 6. Overrides (optional)

Tests are self-contained, but you can point at your own data:

```bash
CEZAR_WORKFLOWS_DIR=/path/to/workflows CEZAR_FACE_ID_V3=/path/to/face_id ./v5/test_v5.sh
```
