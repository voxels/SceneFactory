# SceneFactory Comfy pipeline — chat-log / git correlation

Forensic reconstruction of what the Comfy pipeline is supposed to do, built by
correlating the real repo's git history (`github.com/voxels/SceneFactory`)
with the agent-side conversation substrate. There was never a formal spec; the
spec lives in chat logs. Newest first.

Method: `git fetch --deepen` (repo has only 4 real commits — it is a snapshot
archive, not a worked history), then grep of `~/workspace/transcripts/`,
`~/memory/2026-09-*.md`, `~/workspace/video_project/CHANGELOG.md`,
`~/workspace/context_cache/`. Where no log matches a commit, that is stated.

## Git history (all real commits)

| commit | date (EDT) | msg | what it did |
|---|---|---|---|
| 1680f1a | 2026-08-29 17:48 | first commit | flat repo: docs 01–10, pipeline.py, comfy_adapter.py, schemas, tests |
| f102900 | 2026-08-29 17:50 | gitignore | .gitignore |
| 1a974e9 | 2026-09-10 20:47 | udpates | **the Comfy execution-layer commit** (see below) |
| df2d6cc | 2026-09-11 16:01 | archive | reorg flat → `v0/`, `v1_pre_fresh_run_2026-08-29/`, `v2/`, `v3/`, `v4/`, `Voice/`; v4 = multimodal identity pipeline |
| a9013ec | 2026-09-11 16:16 | (crew) | status-truth fix ported to v3/pipeline.py + 2 regression tests |
| e6a6b08 | 2026-09-11 16:16 | (crew) | v5 clean version on stabilized API |

### 1a974e9 "udpates" — file-level (the execution layer)

New files: `execution_adapter.py` (INTERFACE_ID
`scene_factory.comfyui_api_workflow` v1 — one compiled task → one versioned
ComfyUI API workflow), `execution_status.py` (495 lines — read-only derived
execution status, authority order), `docs/19_EXECUTION_STATUS.md`,
`docs/20_COMPLETION_PLAN.md`, `docs/21_VOICE_LOCAL_AGENT_HANDOFF.md`
(Qwen3-TTS voice-clone runbook: 6–15 s clean reference, verbatim transcript,
stage into Comfy), `docs/22_KOLEKA_AD2184_LOCAL_AGENT_HANDOFF.md`
(Koleka-first AD2184: compile → validate → comfy-build → comfy-preflight →
one PuLID proof → **human review gate**), `review_console/` (full Next.js
review/approval app), `lora_validation.py`, `prompt_plan.py`,
`reference_contracts.py`.

Changed: `comfy_adapter.py` (new PuLID-Flux2 identity graph — ApplyPuLIDFlux2
at strength 1.4; LTX graph fixes: fp8 UNET, cfg 3.25, LTXVScheduler),
`pipeline.py`, `docs/08_REFERENCE.md`, `docs/18_NEXT_RUN_PLAYBOOK.md`.

Standing rule visible in docs/22: **"Scene Factory owns manifests and
approvals; ComfyUI executes generated API graphs."** "A file on disk is not an
approval. Only the operator may approve identity or production media."

## Newest substantive chat logs about the Comfy pipeline (newest first)

1. **2026-09-11 ~16:02 EDT** — `~/workspace/transcripts/main/2026-09-11.jsonl`
   — user verbatim: "automated with a ui for folliw up review to fine tune
   references across media types maybe just as an app in comfy".
   Gate model: automated identity pre-filter, user's eyes give final approval,
   review UI for cross-media reference fine-tuning, possibly a ComfyUI app.

2. **2026-09-11 ~15:57 EDT** — `~/memory/2026-09-11.md` (Identity ruling 1)
   — automated pre-filter (v3 impression, HOLDS d<0.45) + user final approval;
   follow-up review UI as ComfyUI app; user attribution overrules the model.

3. **2026-09-11 ~02:53 EDT** — `~/memory/2026-09-11.md`
   — `teaser_kit/IDD_CONTRACTS_ROUGHCUT.md`: Interface-Driven Development
   contracts, 8 stages S0 (ingest) → S7 (assemble), each with input/output
   schemas; Impl A = agent Python, **Impl B = his Comfy graph**; compare +
   mix procedures and gates. Companion to the run spec.

4. **2026-09-11 ~02:49–02:52 EDT** — `~/memory/2026-09-11.md`
   — `teaser_kit/COMFY_RUN_SPEC_ROUGHCUT.md`: 9:16 output, four simultaneous
   events, 27 vocal-phrase splice map, four-lobe camera path, Braitenberg
   camera system, **identity LoRA gate**, skeleton-take slot, PLY/USDZ
   environment conditioning, staged generation/assembly order. PLY correction:
   subject/environment splats mixed in files → Stage B0 separation via
   SceneFactory SAM3 text-prompted segmentation before conditioning.
   Pipeline order: ingest → cache → downstream reads cache.

5. **2026-09-11 ~01:58 EDT** — `~/memory/2026-09-11.md`
   — user quotes: "ltx desktop 2.5"; "there is an unfinished piece around post
   training identity in comfy esp with ecisting usdz inputs"; "also we are
   supposed to be creating both mesh and splats for layering"; "Both character
   and environment". Mac-first proof, then remote-control the 3080 Ti PC.

6. **2026-09-11 10:57 EDT** — `~/memory/2026-09-11.md`
   — ComfyUI handoff package `~/workspace/your_files/cezar-comfy-workflows.zip`:
   A) identity proof + user-eye gate → B) environment-only splat
   trajectory/depth reference → C) four event-specific identity-locked
   held-pose take workflows → D) ffmpeg assembly from accepted takes.
   LoRA training, skeleton takes, USDZ→GLB remain user-side.

7. **2026-09-11 (morning)** — `~/memory/2026-09-11.md`
   — conditioning wiring: USDZ beach meshes → scene conditioning (GLB first),
   PLY splats → appearance/depth, Cezar identity → LoRA + skeleton takes.
   LTX-2 is the official line (Python inference + ltx-trainer).

8. **2026-09-11** — `~/workspace/video_project/CHANGELOG.md`
   — identity gate ruling (his labels overrule the model); LoRA set = 37
   images (user authority); USDZ = environment data (beach), not character;
   four-Cezar fiction; skeleton requirement (strictly tracked, no invented
   motion); real-footage re-cut rejected — identity-locked generated scenes.

9. **2026-09-10** — `~/memory/2026-09-10.md` lines 51–52, 60, 87
   — repo cloned from GitHub; Mac completion runbook (install
   ComfyUI-PuLID-Flux2 node + weights, validate LTX 2.5, one PuLID-conditioned
   keyframe for human approval); SAM3 ComfyUI node package built at user
   direction ("SAM3 belong in the Comfy code").

## Commit ↔ log correlation

- **1a974e9 (2026-09-10 20:47)** — authored directly by the user on their Mac.
  **No chat log in the agent substrate documents the session that produced
  it.** Topic-adjacent logs from the same day: memory 2026-09-10 lines 51–60
  (repo clone, PuLID/LTX Mac runbook — same PuLID-proof milestone as
  docs/22). The commit's own handoff docs (21/22) are the primary record of
  the conversation behind it.
- **df2d6cc (2026-09-11 16:01)** — the v0–v4/Voice reorganization. **No chat
  log discusses the versioning scheme**; it appears to be the user's own
  archival structure. v4's `docs/SPACE_MAP.md` is dated 2026-09-06
  (modeling_interview / Gage identity bundle — a different subject from
  Cezar; Koleka media explicitly excluded).
- **All 2026-09-11 Cezar/Comfy logs (items 1–8 above)** — produced in the
  agent workspace (`teaser_kit/`, `your_files/`, memory). **None committed to
  the repo.** The repo's execution layer predates them and does not yet
  reflect the Cezar identity-gate, review-UI-as-Comfy-app, or
  four-event/IDD-contract direction.

## Gaps

- Commits with no matching log: 1a974e9 (authoring conversation not in
  substrate), df2d6cc (no log of the versioning decision).
- Logs with no matching commit: everything from 2026-09-11 about Cezar in
  Comfy (run spec, IDD contracts, workflow handoff, identity rulings) —
  workspace-only, uncommitted.
- The user's ACID-diff instructions were not found anywhere in the repo or
  the workspace substrate (searched 2026-09-11 16:16 EDT). Still missing.
- `review_console/` (from 1a974e9) vs the 2026-09-11 "review UI as a ComfyUI
  app" direction: two review surfaces now exist in concept; no log reconciles
  them.
