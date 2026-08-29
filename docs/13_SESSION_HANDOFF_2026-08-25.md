# SceneFactory v1 Session Handoff

Date: 2026-08-25  
Workspace: `/Users/voxels/SceneFactory`  
Active implementation: `/Users/voxels/SceneFactory/v1`  
Archived baseline: `/Users/voxels/SceneFactory/v0`

This historical handoff is superseded by [16_BURNDOWN_CLOSURE_2026-08-26.md](16_BURNDOWN_CLOSURE_2026-08-26.md). Use that document as the current restart point; statements below describe the earlier 2026-08-25 state.

## 1. Governing production decisions

- The declared Apple 1984 reference video is authoritative for wardrobe, worker/enforcer design, hammer design and movement, environments, camera, blocking, action, beat order, and relative rhythm.
- K's face, body identity, and hair come from K's approved source material.
- K's wardrobe, pose, and movement come from the reference video. Pose and movement must be skeleton-tracked and retargeted to K's proportions.
- K and the enforcers should be rendered separately whenever possible.
- Enforcers remain one coordinated group layer. Workers are also treated as a group layer.
- A held hammer belongs to K's layer. At release, ownership transfers once to a separate hammer layer through flight and impact.
- Produce only necessary convenience occluders. They may be simplified but must remain visually invisible in the composite.
- Replace the projected speaker with a tracked `#00FF00` plane for later MP4 replacement. It must obey perspective and occlusion, produce no green spill or generated speaker imagery, and shatter with the screen.
- Final title and logo are post-production only.
- Story order and relative rhythm are invariant. Exact cut frames are only approximately matched.
- Produce a 60-second reference-faithful master plus about 120 seconds of narrative-bounded alternate POV coverage: approximately 180 seconds total.
- Alternates provide creative coverage, not repairs, and cannot invent story events outside the existing narrative.
- Strip and ignore every audio stream. Do not generate audio.
- Only the user may approve material into the post-production pool.

The authoritative semantic manual is [11_SEMANTIC_RESOURCE_REVIEW.md](11_SEMANTIC_RESOURCE_REVIEW.md). The acceptance-based engineering checklist is [12_V1_IMPLEMENTATION_PLAN.md](12_V1_IMPLEMENTATION_PLAN.md).

## 2. Verified state at handoff

The following checks passed immediately before this handoff:

```text
Valid project: ad2184
Scenes: 7
Script duration: 60.000 seconds
Tests: 41 passed
```

Reference ingestion has been run against the real source:

| Field | Verified value |
|---|---|
| Source | `/Users/voxels/SovereignSurvivalKit/media/characters/k0l3k4/shots/choreography_reference/apple_1984_ridley_scott_reference.mp4` |
| SHA-256 | `d6d3014bc4f4f5239129958db90692e1a833d3cb4268e4dc42c6ec5492fe08fe` |
| Duration | 60.04 seconds |
| Video | 1280×720, 25 fps, H.264 |
| Source audio | One AAC stereo stream, identified and ignored |
| Visual evidence | 21 hashed PNGs: start/action/end for seven shots |
| Audio artifacts | None |

Coverage compilation currently reports:

| Coverage | Tasks | Planned duration |
|---|---:|---:|
| Reference-faithful master | 7 | 60 seconds |
| Alternate POV | 21 | 120 seconds |
| Total | 28 | 180 seconds |

Generated evidence:

- [Reference manifest](../examples/ad2184/build/reference/reference_manifest.json)
- [Reference evidence frames](../examples/ad2184/build/reference/frames)
- [Generation manifest](../examples/ad2184/build/generation_manifest.json)
- [Post-production manifest](../examples/ad2184/build/post_production_manifest.json)

The post-production manifest intentionally reports `planned_assets_pending_generation_tracking_and_user_approval`. It describes expected assets and ownership; it does not claim that tracked or rendered assets exist.

## 3. Implemented code

### Reference ingestion

[reference_pipeline.py](../reference_pipeline.py) now:

- resolves the configured external source without copying or modifying it;
- fingerprints and probes it with `ffprobe`;
- maps the seven narrative shots to ordered approximate ranges;
- extracts deterministic visual-only PNG evidence with `ffmpeg -map 0:v:0 -an`;
- records timestamps, resource tags, frame hashes, and vision-contract task stubs;
- explicitly records that source audio is ignored and no audio artifact is emitted.

CLI command:

```bash
cd /Users/voxels/SceneFactory/v1
python3 scene_factory.py reference-prepare examples/ad2184
```

Do not use `--no-extract-frames` for the production build: that mode writes task stubs with null frame paths and can replace the full reference manifest. It exists for dry integration/testing only. If it is used accidentally, rerun the command above without the flag.

### Compiler and manifests

[scene_factory.py](../scene_factory.py) now validates the reconstruction policy and compiles:

- master and alternate coverage budgets;
- environment, worker, enforcer, K, hammer, green-insert, and convenience-occluder layers;
- K/enforcer separation;
- held-to-released hammer ownership transfer;
- visual-only assembly records;
- planned media, matte, transform, skeleton, hammer, and screen-track paths;
- dependency hashes and user-only approval requirements.

### Visual-only Comfy workflow

[comfy_adapter.py](../comfy_adapter.py) now uses a video-only native LTX graph. Audio model, audio VAE, audio latent, audio decoder, and audio concatenation requirements were removed. Approval records require all of:

```json
{
  "decision": "approved",
  "approved_by": "user",
  "issues": []
}
```

### Tracking utilities

- [track_body_pose.swift](../tools/track_body_pose.swift): bounded Apple Vision body-pose extraction.
- [track_planar_object.swift](../tools/track_planar_object.swift): bounded Apple Vision object bounding-box tracking.

These compile and have synthetic smoke coverage. They are fallback/QC tools—not the production tracking solution. The planar tool emits boxes, not four-corner homographies.

### Tests

- [Reference ingestion tests](../tests/test_reference_pipeline.py)
- [Reconstruction/layer tests](../tests/test_reference_reconstruction.py)
- [Tracking tool tests](../tests/test_tracking_tools.py)
- [Comfy graph and approval tests](../tests/test_comfy_adapter.py)

## 4. Work that is not complete

Do not describe these as implemented until their acceptance conditions in the plan pass:

Completed on 2026-08-26:

- All 21 reference tasks are populated from direct multimodal review of the 21 hashed frames.
  The records honestly identify `codex_interactive_multimodal_review`; local Qwen did not run
  because both configured snapshot directories are absent.
- Wardrobe, group, hammer, environment, camera, lighting, blocking, and screen-state contracts
  are emitted with provenance on every observed field.
- Written claims are classified per evidence frame. Compile and Comfy build reject incomplete,
  contradictory, or stale audits. The current 25-claim audit has zero unresolved contradictions.
- Runtime fingerprint changes now invalidate every transitive contract/track/layer/artifact descendant.

Still incomplete:

1. Production K skeleton extraction, smoothing, person-track association, and retargeting are not wired.
2. LTX motion-track IC-LoRA control is not operational because the official extension is broken locally and the control weights are absent.
3. Hammer temporal masks and rigid centroid/rotation tracks have not been produced.
4. Four-corner screen homographies and the exact destruction boundary have not been produced.
5. No reference-faithful master or alternate clip has been rendered under the new constraints.
6. No real alpha/matte, layered composite, green-insert composite, or post-production reconstruction proof exists.
7. User approvals have not been supplied for production artifacts.

## 5. Production tracking/model decision

The production stack should use narrow, current capabilities rather than adding a general custom-node pack.

| Requirement | Selected production approach | Current local state |
|---|---|---|
| K whole-body pose | Core Comfy SDPose whole-body extraction plus RT-DETR person boxes | Core nodes present; model weights missing |
| K motion transfer | Official LTX motion-track IC-LoRA using selected, smoothed joint tracks | Official extension broken; IC-LoRA missing |
| Worker/enforcer motion | Direct video guidance, optionally supported by pose/depth evidence | Core guide nodes available |
| Hammer | Core SAM3.1 video tracking followed by rigid centroid/rotation fitting | Core nodes present; checkpoint missing |
| Screen | Dedicated four-corner homography tracker in post | Not implemented; current Swift box tracker is insufficient |
| Occlusion/depth | Core Depth Anything 3 plus SAM3.1 masks | Core nodes present; weights missing |
| Temporal QC | Core RAFT optical flow | Core node present; optional weight missing |
| Foreground still matte | Core BiRefNet background removal, subject-reviewed | Core node present; weight missing |

Candidate filenames recorded during the local capability audit:

- `sdpose_wholebody_fp16.safetensors`
- `rt_detr_v4-x-hgnet_fp16.safetensors`
- `sam3.1_multiplex_fp16.safetensors`
- `depth_anything_3_mono_large.safetensors`
- `birefnet.safetensors`
- `raft_large_C_T_SKHT_V2-ff5fadd5.safetensors` (optional)
- `ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors`
- `ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors`

Before downloading, confirm filenames and licenses against the current official workflow/model source. Record source URL, checksum, license, tested Comfy core commit, custom-node commit, and rollback point.

## 6. Local Comfy findings

Local core was inspected at ComfyUI v0.33.4 / commit `7a131a3` dated 2026-08-24. Core already contains SAM3.1 tracking, SDPose, Depth Anything 3, BiRefNet, RAFT loading, LTX guide/I2V nodes, masks, and compositing.

Package policy:

- Repair or reinstall only the official `Lightricks/ComfyUI-LTXVideo`, pinned to a tested commit.
- Its local tree currently fails because it is incomplete and lacks `nodes_registry.py` plus other tracked files.
- Disable/remove `comfyui-ltxvideo-registry-mattabyte`; it is incompatible with the installed core and fails on `precompute_freqs_cis`.
- Do not install `ComfyUI-LTXTricks`.
- Do not add `comfyui_controlnet_aux` merely for pose/depth/SAM capability already present in core.
- KJNodes and VideoHelperSuite may remain optional UI/I/O helpers, but API workflows must not depend on them.
- Do not make Radiance a hard dependency; use it only for reviewed optional finishing operations.

No new nodes or large weights were installed during this session.

## 7. Recommended continuation order

### Step A — restore and prove LTX control capability

- [ ] Record the current Comfy core commit and custom-node directories before mutation.
- [ ] Disable the incompatible Mattabyte package.
- [ ] Repair/reinstall the official Lightricks extension at a tested commit.
- [ ] Restart Comfy and confirm a clean import log.
- [ ] Load the official motion-track workflow before acquiring weights.
- [ ] Confirm exact required filenames and locations from that workflow.
- [ ] Acquire only the required SDPose, detector, SAM3.1, depth, and LTX control weights.
- [ ] Record checksums/licenses/commits in a local dependency manifest.

Do not begin full generation until the production tracker/control graph imports cleanly.

### Step B — derive the reference contracts

- [x] Populate all 21 `vision_contract_tasks` in the reference manifest through the recorded interactive multimodal fallback.
- [x] Save structured contracts under `examples/ad2184/build/reference/contracts/`.
- [x] Attach frame path, frame SHA-256, timestamp, shot ID, and authority to every derived field.
- [x] Preserve the explicit exclusions for reference-performer face, body identity, and hair.
- [ ] Replace provisional K wardrobe text with the reference-derived wardrobe contract.
- [x] Reconcile workers, enforcers, hammer, environments, camera, lighting, blocking, and screen state.
- [x] Implement disagreement reports and block affected generation while conflicts remain or the audit is stale.

### Step C — create tracking records

- [ ] Extract and associate K's whole-body pose across K-visible reference ranges.
- [ ] Smooth joints without changing action timing or trajectory.
- [ ] Retarget to K's approved proportions.
- [ ] Convert selected stable joints into an LTX motion-track guide and preview it.
- [ ] Generate and review hammer masks around grip, release, flight, and impact.
- [ ] Fit the hammer's center, angle, scale, and ownership-transfer frame.
- [ ] Track the screen separately for every edit/camera range; do not track through cuts as one box.
- [ ] Export four corners, homography, confidence, and destruction boundary.

### Step D — run small proofs before full coverage

- [ ] One K identity/wardrobe still with no enforcer conditioning.
- [ ] One enforcer-group still in a separate layer.
- [ ] One three-second K skeleton-controlled motion proof.
- [ ] One held-hammer grip proof.
- [ ] One release/flight hammer proof.
- [ ] One green-insert perspective/occlusion/shatter proof.
- [ ] One layered composite with mattes and matching blur/grain.
- [ ] Verify the output contains no audio stream.
- [ ] Present each proof for explicit user review; do not self-approve.

### Step E — expand only after proof acceptance

- [ ] Render the seven-shot master pool.
- [ ] Render narrative-bounded alternate POV coverage.
- [ ] Maintain separate layer ownership and post paths.
- [ ] Update actual artifact hashes and paths in the post-production manifest.
- [ ] Admit only user-approved artifacts to the edit pool.

## 8. Restart commands

Run from `/Users/voxels/SceneFactory/v1`:

```bash
python3 scene_factory.py validate examples/ad2184
python3 -m unittest discover -s tests -v
python3 scene_factory.py reference-prepare examples/ad2184
python3 scene_factory.py compile examples/ad2184
python3 scene_factory.py status examples/ad2184
```

Quick manifest checks:

```bash
jq '.source, .audio, (.shot_ranges | length), (.vision_contract_tasks | length)' examples/ad2184/build/reference/reference_manifest.json
jq '.reference_coverage.summary' examples/ad2184/build/generation_manifest.json
jq '{status, audio_policy, coverage_summary, shot_count: (.shots | length)}' examples/ad2184/build/post_production_manifest.json
```

Expected results:

- validation: seven scenes, 60 seconds;
- tests: 41 passing at this handoff;
- reference tasks: 21;
- audio artifacts emitted: false;
- coverage: 60 master + 120 alternate = 180 seconds;
- post manifest status remains pending until real assets, tracks, and approvals exist.

## 9. Important traps

- Do not modify `/Users/voxels/SceneFactory/v0`; it is the archived baseline.
- The workspace root is not currently a Git repository. Do not assume Git provides rollback.
- Preserve external source material; v1 references it by path rather than duplicating it.
- Do not return to flattened prompts. Keep identity, wardrobe, equipment, anatomy, and prop attributes attached to named owners.
- Do not describe a planned layer path as a rendered asset.
- Do not treat Apple Vision body pose as the requested production skeleton system.
- Do not treat a tracked rectangle, SAM mask, or optical flow as a screen homography.
- Do not run one object tracker through editorial cuts.
- Do not make K inherit the reference performer's face, body identity, or hair.
- Do not reintroduce the old fixed tank-top/shorts wardrobe text; wardrobe authority is the reference video.
- Do not permit audio nodes, latents, model requirements, extracted proxies, or assembly streams.
- Do not install broad Comfy packs to solve capabilities already available in core.
- Do not mark user approval automatically.

## 10. Separate WAN weights discussion

The side task is `01a03ac7-e992-7d50-83c4-193f9254ea03` (“WAN3 weights discussion”). Its initial research found no verified open WAN3 checkpoint release as of this handoff. The recent concrete release it identified was Wan2.2-Animate-2-14B. Keep that investigation separate from v1 implementation unless a verified model, license, workflow, and hardware fit justify a deliberate pipeline change.

## 11. Definition of the next meaningful milestone

The next milestone is not a full render. It is a verified, visual-only three-second K motion proof that simultaneously demonstrates:

1. K identity and hair come only from K sources;
2. wardrobe comes from a cited reference contract;
3. motion comes from a reviewed SDPose-derived and retargeted K skeleton guide;
4. K and enforcers are separate layers;
5. anatomy and hammer grip are coherent;
6. the result has a usable matte and matches the plate;
7. no audio stream exists;
8. the user—not automation—makes the approval decision.

Once that proof passes, extend the same verified graph to the master and alternate coverage pools.
