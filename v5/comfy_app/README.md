# SceneFactory ComfyUI app — `v5/comfy_app/`

A ComfyUI custom-node pack implementing the A→B→C→D Cezar teaser pipeline
as an app surface, with voice capture as a first-class input and the
cross-media review UI the user directed (16:02: "a ui for folliw up review
to fine tune references across media types maybe just as an app in comfy").

Install (his Mac): copy `comfy_app/` into
`ComfyUI/custom_nodes/scenefactory_app/` (rename on copy; the pack reads its
`NODE_CLASS_MAPPINGS` from `__init__.py`) and restart ComfyUI. No pip
dependencies — pure stdlib at import time.

## Node list

### SceneFactory/Workflow (archived-workflow coverage)

| Node | Covers | What it does |
|---|---|---|
| SF_IdentityReferenceIntake | workflow_A_identity_proof.json | Bundles the face-visible held-pose still + v3 impression contract (.npy + .json); tensor passes through to the Mac graph |
| SF_IdentityGatePrefilter | A gate | Automated pre-filter over candidate distances: NO MATCH rejected before his eyes, DRIFTS flagged, HOLDS proceed. Diagnostic only — never approves. `user_confirmed_ids` bypass the model |
| SF_EnvironmentReference | workflow_B_env_reference.json | Validates separated env PLY + camera trajectory JSON; emits the conditioning bundle for RenderSplat/DepthEstimatorNode on the Mac |
| SF_EventTakeParams | workflow_C_event_take_template.json | Resolves event/shot from manifest_shots.json, snaps duration to LTX frame multiple, emits the EVENT_* token mapping + per-take values (noise seed, LoRA version) |
| SF_AssemblyHandoff | assemble_reel.sh | Builds the EDL from accepted takes. A missing take is a hard, named failure — never a silent skip. Only clean user approvals are eligible |

### SceneFactory/Voice (the separate voice-capture work, first-class)

| Node | Voice/ source | What it does |
|---|---|---|
| SF_VoiceReferenceProfile | AGENTS.md + PLAN.md profiles | Intake + validation of a reference profile (`max_data` / `short_clean`): mono PCM WAV 6–15 s checked via header, exact transcript required. Profile settings are never silently mixed |
| SF_VoiceParagraphRender | workflows/paragraph_XX.api.json | Builds the Qwen3-TTS 12Hz 1.7B Base zero-shot API graph for one paragraph (LoadAudio → CharacterVoicesNode → Qwen3TTSEngineNode → UnifiedTTSTextNode → SaveAudio). Inference only — no fine-tuning path exposed |
| SF_VoiceListeningGate | PLAN.md listening gates | Technical validation of the rendered paragraph (exists, non-empty, readable). Technical validation is NOT human approval — the bundle goes to SF_UserAttribution |

### SceneFactory/Review (his eyes = final approval)

| Node | Direction | What it does |
|---|---|---|
| SF_ReviewCandidateBrowser | 16:02 review UI | Browses cross-media candidates (image / audio / text); gate band attached as diagnostic-only label. Sidecar web UI renders the previews |
| SF_UserAttribution | USER ATTRIBUTION OVERRULES THE MODEL | THE write path (OUTPUT_NODE): approve / reject / user-confirmed. `user_confirmed=True` forces a clean user approval regardless of gate band. Writes the review JSON — the only thing that can mark approved |
| SF_RefusalRedirect | refusal-with-redirection (spec §5) | Implements the adjustment ladder (rephrase → swap reference → lower LoRA → reduce denoise → drop conditioning → split shot), bounded at 3 attempts, then escalates with the full debug log. Never stalls |

### SceneFactory/Manifests (Scene Factory owns these)

| Node | Rule | What it does |
|---|---|---|
| SF_TakeManifestWriter | docs/22 | OUTPUT_NODE: writes the take manifest (gate verdict, review, refusal history). Rejected takes are kept as negative training data, never deleted |
| SF_GraphManifestBuilder | INTERFACE_ID scene_factory.comfyui_api_workflow v1 | Stamps one compiled task → one versioned API workflow after structural validation |

## Interface assumptions for the spec crew (sibling comfy_pipeline)

- **A1:** `HOLDS_MAX=0.45` / `DRIFTS_MAX=0.65` are duplicated here from
  sibling `identity_gate.py` (canonical). Nodes prefer the sibling's
  `gate_band`/`prefilter` when importable, else the local fallback.
- **A2:** take/review record shapes mirror sibling `manifests.py`
  (`build_take_record` / `build_review_record` / `is_approved`).
- **A3:** the refusal-record shape is defined in `nodes_review.py` per spec
  §5 (sibling `redirection.py` did not exist when this was written):
  `{kind, refusal_kind, refusal_signal, attempt, adjustment,
  adjustment_action, request_as_sent, escalated, escalation?}`.
- **A4:** the `SF_VOICE` profile bundle shape is defined in `nodes_voice.py`;
  the spec crew should adopt it for any voice conditioning in graphs.
- **A5:** custom socket types are in-process Python dicts with a `kind`
  field. They do NOT serialize inside API-format graphs; on export, bundles
  travel as JSON sidecars next to the graph.

## Review UI (web/)

`web/js/scenefactory_review.js` — ComfyUI frontend extension scaffold:
gate-band badges (diagnostic-only) on the pre-filter node, a review-surface
entry point on the candidate browser, and an escalation banner on the
refusal-redirect node. Full candidate-grid rendering and media previews are
Mac-side work against the live ComfyUI frontend.

## Tests

`tests/test_node_schemas.py` — 97 checks, all green (no ComfyUI, torch, or
numpy required): interface schema validation for all 13 nodes, OUTPUT_NODE
placement, gate-band mapping + boundaries, pre-filter routing incl. the
user-confirmed override, the attribution write path incl. forced approval,
refusal-ladder bounds + escalation, EDL hard failure on missing takes,
synthetic WAV validation, voice graph structure, take-manifest negative-data
retention. Run: `python3 tests/test_node_schemas.py`.

## What needs the live ComfyUI on his Mac

- Installing the pack into `custom_nodes/` and confirming all 13 nodes load
  (node names verified against this pack only — third-party nodes
  LTXV*/LoadPlySplat/Qwen3TTSEngineNode come from their own packs per
  node_shopping_list.md).
- Queueing the A/B/C graphs the nodes build; the identity proof run (A)
  and the user-eye gate happen there.
- Rendering the six voice paragraphs and the listening approvals.
- The full review-surface frontend (candidate grid, media previews).
- `assemble_reel.sh` execution against the EDL this pack emits.
