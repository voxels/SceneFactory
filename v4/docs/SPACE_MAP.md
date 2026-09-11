# Scene Factory v4 space map

Manual takeover update, 2026-09-06: read
[PRINCIPAL_ENGINEER_HANDOFF.md](/Users/voxels/SceneFactory/v4/docs/PRINCIPAL_ENGINEER_HANDOFF.md)
for the current defect/connection audit and acceptance plan. Its D01–D20 findings
supersede stronger readiness claims below: the LTX graph has concrete loader and
control defects, Voice integration is partial, and the Gaussian export is a
mesh-derived prototype. Neither compiled graphs nor the existing goal audit
establish finished functionality.

Status snapshot: 2026-09-06. This is the authoritative map of the current
`v4/examples/modeling_interview` run. It separates source material, derived
artifacts, executable connections, and finishing blockers. A merge in this
system is additive: it creates an indexed/derived view and never replaces a
source file, a prior run, or a rejected comparison.

## 1. Intended finished product

One self-contained identity bundle for Gage that can:

1. generate still images from a promoted subject identity model, reference
   images, and structural controls;
2. generate identity-preserving video from a promoted video identity model,
   a visual-identity keyframe, and separate motion controls;
3. preserve and mux the supplied TTS performance with word/phoneme/viseme
   timing;
4. deliver a rigged talking-head mesh and a matching Gaussian splat with
   geometry, skeleton, blend shapes/visemes, textures, normals, UVs, and
   timing metadata; and
5. package provenance, hashes, workflows, samples, and validation evidence.

The system is not finished until the final bundle is executable and its
completion audit is green. Prepared manifests and stubs do not count as
consumption or completion.

## 2. Source spaces and authority

| Space | What it contains | How it is used | Current connection |
|---|---|---|---|
| `v3/examples/modeling_interview/Gage` | original images, videos, webarchives, USDZ, source transcript | immutable source-of-truth for visual, motion, web, and geometry ingestion | connected to `identity_pipeline.build` |
| `Voice/inputs` | clean reference audio and `tts_script.txt` | voice reference and authoritative target script | package exists; bridge manifest now records it; final waveform absent |
| `Voice/reference_profiles` | longer cleaned/profile audio | optional voice identity/prosody reference | package exists; reference-only, not final performance |
| `Voice/examples` | listening comparisons | comparison evidence only | explicitly excluded from training/runtime inputs |
| `Voice/renders` | generated paragraph attempts | pending/rejected human-review material | explicitly excluded from training/runtime inputs |
| `Voice/output` | final destination for `gage_final_master.flac` | finishing output only | destination exists; approved master absent |
| local installed model/runtime files | FLUX.2 Klein, PuLID node, LTX 2.5 weights/nodes, UE 5.8 | execution/training dependencies | present in part; availability is recorded in preflight |

Koleka-named paths are excluded case-insensitively at ingest, derivative,
bundle, and workflow boundaries. No Koleka media is part of this example.

## 3. Connected pipeline graph

```text
Gage source tree ──> ingest manifest ──> annotations/masks/captions/selection
        │                                  ├──> image dataset ──> FLUX LoRA training
        │                                  ├──> reference bank ──> image workflows
        │                                  ├──> visual-video frames/clips ──> LTX video training (not connected)
        │                                  ├──> motion frames/poses/tracks ──> LTX motion control (not executed)
        │                                  └──> USDZ audit/geometry controls ──> structural route (not executed)
        │
Voice package ──> additive voice input manifest ──> transcript + reference channels
        │                                  └──> final performance waveform ──> align ──> mux (waveform missing)
        │
promoted image route + controls ──> image generation ──> image evidence (promotion not selected)
promoted video route + keyframe + motion + audio ──> video generation ──> final video (not connected)
USDZ + rig metadata ──> UE/USD import/runtime ──> Persona-oriented delivery (Metal blocked)
all promoted outputs ──> identity_bundle ──> finished deliverable (blocked)
```

## 4. What is built and evidenced

| Area | Evidence | State |
|---|---|---|
| v4 root/CLI/config | `v4/scene_factory_v4.py`, example `identity.json` | built |
| source ingest/provenance/Koleka exclusion | `build/identity/asset_manifest.json` | built; 278 source assets indexed |
| image masks/landmarks/poses/identity filtering | `build/identity/annotation_manifest.json` | built; 320 records, 75 passes, 245 rejects |
| semantic captions | `build/identity/caption_manifest.json` | built; 75 records |
| group-safe image splits | `build/identity/selection_manifest.json` | built; 64 selected (43 train/9 validation/6 calibration/6 final test) |
| reference bank | `build/identity/reference_bank/reference_bank.json` | built; six-category bank, pending optimization |
| image LoRA experiments | `build/training/image_identity/experiments/*` | built; three adapters structurally audited |
| image workflow graph | `build/workflows/image_ablation/manifest.json` | compiled; base/native/PuLID/LoRA routes described |
| image runtime executor | `v4/comfy_executor.py` | built; requires promoted route and live backend |
| visual-video split/frame extraction | `build/identity/video/visual_identity_manifest.json` | built; 11 clips/158 frames |
| motion/skeleton extraction | `build/identity/motion/skeleton_manifest.json` | built; 994 frames/558 poses/99 tracks |
| native LTX 2.5 graph | `build/workflows/video_runtime/ltx25_identity_motion.json` | compiled; identity guide and motion guide are separate |
| USDZ ingestion/geometry controls | `build/identity/geometry/usdz_ingestion_manifest.json` | built; 3 sources/168 controls audited |
| static rig/splat prototype | `build/avatar/gage_portrait/avatar_manifest.json` | built prototype; final UE/runtime validation open |
| explicit blocked-stage stubs | `build/stubs/stub_manifest.json` | built; non-production and excluded from consumption |
| 79-test contract suite | `v4/tests` | passing at last verification |

## 5. What is not connected or not complete

| Missing connection | Why it matters | Exact completion evidence |
|---|---|---|
| held-out image evaluation → promotion | no production image route may be selected by guess | terminal report comparing base/native/PuLID/LoRA, then `promoted/promotion_manifest.json` |
| promoted image route → connected generation | compiled JSON is not execution | hash-verified outputs under `build/workflows/image_ablation/executions` for the promoted route |
| visual-video clips → LTX identity trainer | no official local LTX trainer is installed | real adapter, completion marker, validation, and promotion manifest |
| motion tracks → LTX control execution | poses/tracks are prepared but not consumed | runtime evidence with `motion_control_consumed=true` |
| USDZ controls → generation | geometry is audited/rendered but not used in a successful route | execution record with `geometry_control_consumed=true` |
| Voice transcript/reference → final performance waveform | Voice package has no approved `output/gage_final_master.flac` | six reviewed paragraph renders, assembled master, validation report |
| waveform → alignment/mux | lipsync must use original bytes, not an estimate/substitute | phoneme/viseme alignment plus stream-copy mux hash proof |
| LTX audio/video runtime → final video | `generate-video` dispatches to the executor and original-audio mux; adapter/control binding, alignment, full-duration timeline and runtime proof remain incomplete | generated video containing both video and original audio streams |
| USDZ/rig → Unreal runtime | UE 5.8 is installed but Metal toolchain probe fails | successful commandlet/import and supported runtime proof |
| promoted artifacts → identity bundle | packager correctly refuses incomplete inputs | `build/identity_bundle/bundle.json` with all runtime and provenance records |

## 6. Current truth in one line

The project is substantially prepared, but not finished: image training is
complete only through checkpoint creation; video, motion, USDZ execution, Voice
finishing, promotion, and final packaging remain unconsumed or blocked. The
automatic ledger is blocked after six stages, and the held-out evaluator was
stopped before a terminal report.

## 7. Finish order that preserves all prior work

1. Keep every source and prior run immutable; update only additive manifests.
2. Complete the Voice render/review/assembly in `Voice/output` and bind its
   hashes into the v4 audio contract.
3. Finish the short, bounded image held-out matrix and promote one route.
4. Obtain/verify a compatible local LTX trainer or record that video training
   is externally supplied; then promote a real video adapter.
5. Execute motion and USDZ structural routes and record consumer evidence.
6. Run alignment/mux and the connected video path.
7. Complete UE-independent import checks, then runtime checks when the Metal
   toolchain is available.
8. Package the final bundle and rerun `audit-goal`; only a green ten-criterion
   audit is called finished.
