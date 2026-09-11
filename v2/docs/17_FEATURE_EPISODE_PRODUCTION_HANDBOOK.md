# Feature-Episode Production Handbook

This is the canonical manual for operating Scene Factory as a long-term episodic production system. AD2184 is the first test episode and working example. The intended future workflow is to retain stable series-level assets and production rules while swapping episode scripts, guest characters, locations, props, references, and editorial decisions.

This handbook covers both the Scene Factory compiler and manual ComfyUI work. It distinguishes editable UI workflows from API execution graphs and never treats a generated file as approved merely because it exists.

## 1. Production model

Use three scopes:

| Scope | Lifespan | Examples | Change effect |
|---|---|---|---|
| Series | Entire series | visual bible, recurring-character identities, color pipeline, delivery specification, issue codes | Deliberate versioned migration across episodes |
| Episode | One feature-length episode | script, guest cast, episode locations, shot list, reference contracts, approvals | Recompile only that episode |
| Shot/candidate | Minutes to days | prompt, seed, pose track, mask, key frame, clip, matte | Invalidate only descendants of that artifact |

Create one Scene Factory project per episode. Do not put an entire series into one `project.json`. Point every episode at a shared read-only series asset library using `path_defaults`.

Recommended hierarchy:

```text
series_root/
├── series_bible/
│   ├── SERIES_BIBLE.md
│   ├── series_context.json
│   └── delivery/
├── shared_assets/
│   ├── characters/<character_id>/
│   ├── environments/<environment_id>/
│   ├── props/<prop_id>/
│   ├── styles/<style_id>/
│   └── motion_references/<reference_id>/
├── episodes/
│   ├── s01e01_test/
│   ├── s01e02_.../
│   └── ...
└── editorial/
    ├── shared_graphics/
    ├── sound/
    └── delivery_presets/
```

Each episode remains portable:

```text
episode/
├── project.json
├── concepts.json
├── scripts/script.json
├── SERIES_EPISODE_WORKSHEET.md
├── assets/
├── reviews/
├── build/                 # regenerated evidence and workflows
└── outputs/               # media outputs; do not use as source truth
```

## 2. What is authoritative

For every field, choose exactly one source of authority before generation.

| Resource | Typical authority | AD2184 example |
|---|---|---|
| Recurring face/body identity | approved series character sources and promoted identity model | K source images |
| Hair or makeup | series bible unless explicitly episode-variable | K sources plus approved post styling |
| Wardrobe | episode wardrobe sheet or declared motion reference | Apple reference video |
| Character motion | shot motion reference, mocap, or reviewed track | SDPose extraction from the Apple reference |
| Prop geometry | series/episode prop contract | one single-headed sledgehammer |
| Environment | approved location contract and references | processing tunnel, corridor, ideology hall |
| Camera and blocking | episode shot record | reference-derived camera and formations |
| Screen replacement | post-production contract | tracked green plane through 46.04 s |
| Dialogue, music, final graphics | post-production | all source audio ignored by generation |

If two written sources disagree, resolve the contract before rendering. Do not ask the image or video model to arbitrate.

## 3. First installation and runtime check

The current tested runtime is:

```text
Scene Factory: /Users/voxels/SceneFactory/v1
ComfyUI: /Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI
Python: /Users/voxels/comfy/.venv/bin/python
Shared models: /Users/voxels/ComfyUI-Shared/models
ComfyUI URL: http://127.0.0.1:8188
```

Start ComfyUI:

```bash
cd /Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI
/Users/voxels/comfy/.venv/bin/python main.py \
  --listen 127.0.0.1 \
  --port 8188 \
  --disable-auto-launch \
  --extra-model-paths-config /Users/voxels/SceneFactory/v1/examples/ad2184/build/comfyui/extra_model_paths.yaml
```

Open `http://127.0.0.1:8188`. A macOS Triton warning from optional KJNodes is expected and does not block the tested workflows.

Run the LTX audit:

```bash
cd /Users/voxels/SceneFactory/v1
python3 render_pipeline.py audit-ltx \
  --comfy-root /Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI \
  --models-root /Users/voxels/ComfyUI-Shared/models \
  --runtime-python /Users/voxels/comfy/.venv/bin/python \
  --object-info examples/ad2184/build/comfyui/object_info_live.json \
  --output examples/ad2184/build/comfyui/ltx_runtime_audit.json
```

Continue only when `ready` is `true` and `blockers` is empty.

## 4. Create a new episode

From the Scene Factory root:

```bash
python3 scene_factory.py new \
  /absolute/path/to/series_root/episodes/s01e02_episode_slug \
  --id s01e02_episode_slug \
  --title "Episode Title"
```

The command copies the episode template, including the production worksheet and review forms.

Immediately edit:

1. `SERIES_EPISODE_WORKSHEET.md`
2. `project.json`
3. `concepts.json`
4. `scripts/script.json`
5. `series_context.json`

Use stable lowercase IDs. Never reuse an ID for a different person, place, prop, or concept.

## 5. Point an episode at shared assets

Example `path_defaults`:

```json
{
  "SERIES_ROOT": "/absolute/path/to/series_root",
  "SHARED_ASSETS": "${SERIES_ROOT}/shared_assets",
  "EPISODE_ASSETS": "${PROJECT_ROOT}/assets",
  "COMFYUI_MODELS_ROOT": "/Users/voxels/ComfyUI-Shared/models",
  "OUTPUT_ROOT": "${PROJECT_ROOT}/outputs"
}
```

Recurring character example:

```json
{
  "id": "series_lead",
  "role": "foreground",
  "identity_tag": "series_lead_identity",
  "concept_id": "series_lead_identity",
  "source_folder": "${SHARED_ASSETS}/characters/series_lead/approved",
  "attribute_tags": ["adult person"],
  "continuity": ["same approved face", "same body proportions"],
  "training": {"enabled": true, "minimum_approved_images": 24}
}
```

Guest character example:

```json
{
  "id": "episode_guest_01",
  "role": "foreground",
  "identity_tag": "episode_guest_01_identity",
  "concept_id": "episode_guest_01_identity",
  "source_folder": "${EPISODE_ASSETS}/foreground_characters/episode_guest_01/source",
  "attribute_tags": ["adult person"],
  "continuity": ["same face throughout this episode"],
  "training": {"enabled": true, "minimum_approved_images": 24}
}
```

## 6. Swap resources safely

An asset swap is not a filename replacement. Update the contract, provenance, dependencies, and review state.

### Character swap

1. Assign a new character ID and identity tag.
2. Point `source_folder` to the approved source set.
3. Add or replace the identity concept in `concepts.json`.
4. Replace cast IDs and active concepts in the script.
5. Re-index and rebuild captions/dataset evidence.
6. Generate an identity grid before any episode key frame.
7. Reject inherited wardrobe, hair, or props that are not part of the new character contract.

Do not reuse another character's LoRA merely because the role is similar.

### Wardrobe swap

Keep identity unchanged. Change only the wardrobe contract/reference and its concept or prompt block. Validate front, back, seated, running, and hand/prop interaction views. Wardrobe must never migrate onto a face or become anatomy.

### Environment swap

Add a new environment ID, reference folder, stable geometry, entrances/exits, light rules, and continuity rules. Replace `environment_id` only in intended scenes. Rebuild all dependent key frames; do not reuse old mattes or screen tracks.

### Prop swap

Give the prop a unique ID and explicit geometry. Include count, ownership, attachment/release events, material, dimensions, forbidden variants, and layer ownership. Rebuild masks and rigid tracks for the new prop.

### Script swap

Treat a new script as a new episode or a versioned episode revision. Preserve stable recurring-resource IDs. Every shot must declare duration, cast, action, formations, and any active concepts, props, motion reference, continuity, and negative constraints.

Complete the copyable [Asset Swap Manifest](../template/reviews/asset_swap_manifest.json) before recompiling.

## 7. Script and shot design

One episode script may contain many scenes and shots. Keep each shot small enough to have one readable action and one ownership state.

Example:

```json
{
  "id": "shot_042",
  "duration_seconds": 6.5,
  "cast": ["series_lead", "episode_guard_group"],
  "props": ["episode_key_prop"],
  "active_concepts": ["series_lead_identity", "episode_guard_group"],
  "motion_reference_id": "shot_042_reference",
  "action": "The lead crosses the gantry and transfers the key prop to the guest.",
  "audio": ["editorial reference only; generation ignores audio"],
  "continuity": ["lead enters frame left", "prop transfers exactly once"],
  "negative": ["duplicate prop", "identity drift", "extra limbs"],
  "formations": [
    {
      "id": "master_wide",
      "framing": "wide",
      "camera": "Track parallel to the gantry.",
      "lens": "32mm",
      "subject_priority": "complete action and screen direction"
    },
    {
      "id": "lead_medium",
      "framing": "medium",
      "camera": "Track with the lead before the transfer.",
      "lens": "50mm",
      "subject_priority": "identity, hands, and prop ownership"
    },
    {
      "id": "transfer_detail",
      "framing": "close",
      "camera": "Hold on both hands during the transfer.",
      "lens": "85mm",
      "subject_priority": "one coherent prop and readable hand contact"
    }
  ]
}
```

For a feature-length episode, compile and approve in sequences or reels. Do not wait for the complete episode before testing the first representative dialogue, action, crowd, effects, and low-light shots.

## 8. Compile an episode

```bash
cd /Users/voxels/SceneFactory/v1
python3 scene_factory.py validate /absolute/path/to/episode
python3 scene_factory.py index /absolute/path/to/episode
python3 scene_factory.py compile /absolute/path/to/episode
python3 scene_factory.py comfy-build /absolute/path/to/episode
python3 scene_factory.py status /absolute/path/to/episode
```

If the episode declares an authoritative reconstruction reference, run these before `compile`:

```bash
python3 scene_factory.py reference-prepare /absolute/path/to/episode
python3 scene_factory.py reference-contract-run /absolute/path/to/episode
python3 scene_factory.py reference-contract-audit /absolute/path/to/episode
```

`compile` and `comfy-build` must stop when reference contracts disagree or are stale. Generated manifests are plans, not approvals.

## 9. ComfyUI workflow file types

| Suffix | Purpose | Edit manually? |
|---|---|---|
| `.ui.json` | Full visual graph with positions, notes, groups, and widgets | Yes—load through the ComfyUI UI |
| `.api.json` or `_api.json` | Minimal server execution graph | Edit only when you understand node IDs and typed connections |
| `workflow_api.json` | Saved API request, often wrapped in `{"prompt": ...}` | Normally run through the API; use the UI equivalent for visual editing |

AD2184 editable LTX graph:

```text
/Users/voxels/SceneFactory/v1/examples/ad2184/build/proofs/ltx_motion_control/configured_official_workflow.ui.json
```

AD2184 visual-only API graph:

```text
/Users/voxels/SceneFactory/v1/examples/ad2184/build/proofs/ltx_motion_control/configured_visual_only.api.json
```

The API graph is authoritative for the no-audio execution constraint. The editable official UI graph may retain upstream audio-related nodes or notes; disconnect/bypass/remove all audio nodes before using an edited UI graph for this production.

## 10. Manually load and edit the LTX motion workflow

1. Start ComfyUI and open `http://127.0.0.1:8188`.
2. Drag `configured_official_workflow.ui.json` onto the canvas, or choose **Workflow → Open**.
3. Confirm these model selections:
   - diffusion model: `ltx-2.5-22b-distilled-transformer-bf16.safetensors`;
   - motion IC-LoRA: `ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors`;
   - video VAE: `ltx-2.5-video-vae-bf16.safetensors` or the approved convolutional VAE;
   - text encoder: `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors`.
4. Set the start image/key frame.
5. Set width, height, fps, and duration. Legal frame counts satisfy `1 + 8n`. At 24 fps, a nominal 3-second proof uses 73 frames.
6. In **LTX Sparse Track Editor**, place only reviewed points on stable body/prop landmarks. Avoid points that jump between people or cross editorial cuts.
7. Preview the drawn guide before sampling.
8. Keep the reference downscale factor at the official tested value unless a separate test proves another value.
9. Change one variable per proof: track, seed, prompt, LoRA strength, or key frame—not all at once.
10. Remove or bypass audio VAE, audio latent, audio decoder, and audio mux nodes. Save video only.
11. Queue a short proof.
12. Inspect identity, anatomy, track following, background motion, and temporal artifacts.
13. Save a new workflow version; never overwrite the approved baseline.

Suggested names:

```text
workflows/shot_042/shot_042_motion_v001.ui.json
workflows/shot_042/shot_042_motion_v002_trackfix.ui.json
workflows/shot_042/shot_042_motion_v003_approved.ui.json
```

## 11. Edit an LTX motion track

Track editing is appropriate for subject translation and selected landmarks. It is not a replacement for skeleton retargeting or object masks.

For K in AD2184:

- source observations: `build/tracking/k_body_pose_raw.json`;
- associated/smoothed/retargeted controls: `build/tracking/shot_03_to_05/k_body_pose.json`;
- real interval: 36.48–39.48 seconds at 24 fps;
- 73 samples, 39 with usable root-relative controls.

When filling a gap:

1. Confirm the character is actually visible in the source.
2. Use neighboring confident frames.
3. Interpolate only across continuous action, never across a cut.
4. Preserve left/right joint identity.
5. Preview the guide at full duration.
6. Mark interpolated samples separately from observed samples.

## 12. Manually run SDPose

The executed API workflow is:

```text
examples/ad2184/build/tracking/sdpose_workflow_api.json
```

Its important inputs are:

- `VHS_LoadVideoPath`: video, frame rate, size, frame cap, and starting-frame offset;
- `CheckpointLoaderSimple`: `sdpose_wholebody_fp16.safetensors`;
- `SDPoseKeypointExtractor`: model, VAE, image batch, batch size;
- `SceneFactorySavePoseKeypoints`: workspace output path, source start time, fps.

For another shot, copy the workflow, replace the video path, calculate `skip_first_frames`, set `frame_load_cap`, and change the output path. Do not write two shots to the same raw file.

## 13. Manually run and correct SAM3 masks

AD2184 contains three reproducible examples:

| Workflow | Use | Result |
|---|---|---|
| `sam3_hammer_workflow_api.json` | one initial mask, temporal memory track | lost the object after 3/59 frames |
| `sam3_hammer_box_refine_workflow_api.json` | independent per-frame proxy boxes | 21/59 nonempty frames |
| `sam3_hammer_text_box_workflow_api.json` | text plus padded proxy boxes | 59/59 nonempty, but false positives after the cut |

All are under:

```text
examples/ad2184/build/tracking/shot_06/
```

Manual correction procedure:

1. Split work at every editorial cut.
2. Mark the exact first and last frame where the object is visible.
3. Draw or correct a tight box on visible key frames.
4. Run SAM refinement inside each box.
5. Add key frames when scale, rotation, occlusion, or blur changes materially.
6. Emit an empty mask when the object is off-screen or not visible.
7. Inspect overlays, not masks alone.
8. Reject masks that capture faces, screens, hands, or background edges.
9. Record observed, interpolated, and manually painted frames distinctly.

AD2184 QC evidence:

```text
examples/ad2184/build/tracking/shot_06/sam3_attempt_report.json
examples/ad2184/build/tracking/shot_06/hammer_masks_sam3_text_box/overlay_contact_sheet.png
```

## 14. Green-screen insert and screen destruction

For a replaceable screen:

1. Track all four corners per continuous camera segment.
2. Composite a pure `#00FF00` plane through the last intact frame.
3. Apply perspective with the four-corner homography.
4. Apply foreground occlusion after the screen insert.
5. Prevent green spill and do not generate speaker imagery.
6. End the insert at the destruction boundary.
7. Add the final MP4 and exact graphics in post.

AD2184 authority:

```text
examples/ad2184/build/tracking/shot_06/speaker_screen_corners.json
last intact: 46.04 seconds
first destroyed: 46.08 seconds
```

## 15. Layered rendering and compositing

Render separately when possible:

- hero character plus held props;
- coordinated background group;
- antagonist/enforcer group;
- released prop after ownership transfer;
- environment/plate;
- convenience occluders;
- tracked green insert;
- destruction/effects elements.

Each layer delivery must include:

- media file;
- alpha or matte where applicable;
- transform/track reference;
- source and workflow hashes;
- time range and frame rate;
- ownership state;
- approval record;
- explicit audio-stream inventory of zero.

Never infer layer ownership in post. Declare transfers in the shot contract.

## 16. Overshooting and alternates

For each narrative shot, produce:

- one reference-faithful master candidate;
- at least three useful alternate POV/formations when declared;
- more generated duration than the final edit requires;
- no invented event outside the existing narrative boundary.

Alternates provide editorial variety. They are not attempts to conceal a broken master.

For feature episodes, budget by sequence:

```text
required edit duration × coverage multiplier = planned generated duration
```

AD2184 uses a 3× multiplier: 60 seconds master plus approximately 120 seconds of alternates.

## 17. Review and approval

Only the user can approve a production artifact. A valid approval is:

```json
{
  "decision": "approved",
  "approved_by": "user",
  "issues": []
}
```

Review in this order:

1. contract and provenance;
2. character identity;
3. wardrobe and hair;
4. anatomy;
5. prop geometry/count/ownership;
6. blocking and screen direction;
7. motion fidelity;
8. masks and occlusion;
9. environment/camera/light continuity;
10. composite and post reconstruction;
11. editorial usefulness.

Use issue codes instead of prose-only rejection notes. Preserve rejected candidates and their metadata so recurring failure modes can be measured.

## 18. Versioning and invalidation

Use immutable source files and versioned derived artifacts.

```text
source → contract → track/mask → key frame → clip/layer → composite → edit
```

When an upstream hash changes, invalidate every descendant. Do not manually copy an old approval onto a new hash.

Recommended states:

```text
planned → generated → machine_checked → user_reviewed → approved → superseded
                                  └──────→ rejected
```

## 19. Feature-length operating cadence

### Series setup

- approve the series bible and delivery specification;
- establish recurring character and environment contracts;
- validate reusable models and LoRA combinations;
- create issue-code taxonomy and naming rules.

### Episode development

- lock script version;
- inventory new and recurring resources;
- write source-authority matrix;
- compile shot/formation records;
- select representative risk shots.

### Episode production

- generate identity/wardrobe/environment validation grids;
- approve storyboards and key frames sequence by sequence;
- generate three-second motion proofs;
- extend only approved proofs;
- render layers and alternates;
- reconstruct in post.

### Episode turnover

- verify no generated audio;
- verify media and matte dimensions/frame rates;
- package approved assets only;
- retain provenance, workflows, seeds, prompts, tracks, masks, and rejection history;
- mark the episode manifest immutable at delivery.

## 20. Recovery and common failures

| Failure | Meaning | Response |
|---|---|---|
| Helmet/equipment appears on hero face | subject/attribute binding failure | strengthen character and group separation; render layers separately |
| Extra or fused arms | pose/anatomy failure | improve key frame and skeleton controls; shorten proof; reject frame |
| Double-ended or duplicate prop | prop geometry/ownership failure | isolate prop contract; enforce count and layer transfer |
| Motion track jumps | association or cut-boundary failure | split at cut; correct identities; add confident key frames |
| SAM mask follows background | seed/detector failure | tighten boxes, add key frames, lower reliance on text detection |
| Workflow contains audio nodes | invalid production graph | remove audio model, latent, decoder, and mux; rebuild API graph |
| Output exists but is unapproved | expected review state | do not admit it to the edit pool |

## 21. AD2184 working index

- Semantic authority: [11_SEMANTIC_RESOURCE_REVIEW.md](11_SEMANTIC_RESOURCE_REVIEW.md)
- Implementation gates: [12_V1_IMPLEMENTATION_PLAN.md](12_V1_IMPLEMENTATION_PLAN.md)
- LTX runtime and compositor: [14_RENDER_PIPELINE_STATUS_2026-08-26.md](14_RENDER_PIPELINE_STATUS_2026-08-26.md)
- Tracking execution: [15_TRACKING_EXECUTION_REPORT_2026-08-26.md](15_TRACKING_EXECUTION_REPORT_2026-08-26.md)
- Current closure: [16_BURNDOWN_CLOSURE_2026-08-26.md](16_BURNDOWN_CLOSURE_2026-08-26.md)
- Episode worksheet template: [SERIES_EPISODE_WORKSHEET.md](../template/SERIES_EPISODE_WORKSHEET.md)
- Series bible template: [SERIES_BIBLE_TEMPLATE.md](templates/SERIES_BIBLE_TEMPLATE.md)
