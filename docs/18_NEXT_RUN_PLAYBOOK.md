# Next Run Playbook

Verified against Scene Factory v3 on 2026-08-29.

This is the restart document for a new script, project, or character set. Scene Factory owns production truth and gates. ComfyUI executes generated graphs; it is not the script, asset, or approval database.

A successful process exit is not visual approval. Only a user approval record admits an artifact to the next stage.

## UI ownership

| Work | Use now | Do not use as authority |
|---|---|---|
| Discuss changes, inspect folders, run commands, review contact sheets and clips | This Grok session or a terminal | Chat history alone |
| Edit `project.json`, scripts, concepts, character policies, and review JSON | A JSON-aware editor | ComfyUI prompts |
| Inspect or debug generation graphs and view the live queue | ComfyUI | ComfyUI workflow filenames as production state |
| Record approvals and rejections | Scene Factory JSON manifests and `reviews/` records | Finder labels or verbal approval only |

The recommended future UI is a local **Scene Factory Review Console** in the browser. It should read and write the existing manifests, not introduce a second database. Required screens are Project Setup, Script/Shot Review, Character Assets, Identity Seed and Similarity Review, Generation Queue, and Gate Approvals. That console does not exist yet.

## Current execution boundary

These commands work for a new project:

`new`, `validate`, `index`, `compile`, `status`, `prepare`, `pipeline-status`, caption and isolation review, `dataset-build`, and identity-reference audit.

These stages compile plans but have no generic execution adapter yet. `pipeline-status` will report them blocked:

- `concept_training`
- `character_sheets`
- `storyboards`
- `scripted_clips`
- `extended_sequences`
- `final_assembly`

`comfy-build` and `comfy-preflight` emit API graphs. The current adapter still hard-codes Ad2184 identity references, LoRA names, and output namespaces. Do not treat it as a generic new-character generator.

`--identity-id` and `--character-id` on isolation, isolation-caption, and `character-balance` commands default to `k0l3k4`. Pass the new character's IDs explicitly.

## 1. Create the project

```sh
cd /Users/voxels/SceneFactory/v3
./scene_factory.py new ./projects/PROJECT_ID --id PROJECT_ID --title "PROJECT TITLE"
```

`--id` is stored as `stable_id`: lowercase, spaces to underscores. Destination must be empty or missing.

`new` copies the v3 template and `profiles/`. It does **not** create asset drop folders or `characters/`. The new project contains:

```text
project.json
concepts.json
scripts/script.json
series_context.json
SERIES_EPISODE_WORKSHEET.md
reviews/asset_swap_manifest.json
reviews/episode_artifact_review.json
profiles/flux2_klein_identity_lora.json
```

Replace the template placeholders before generation. The template lead is `lead` / `lead_identity`; the environment is `main_environment`; `series_context.json` still says Scene Factory does not validate that file.

Create source folders to match `project.json`:

```text
projects/PROJECT_ID/assets/foreground_characters/CHARACTER_ID/source/
projects/PROJECT_ID/assets/background_characters/GROUP_ID/source/
projects/PROJECT_ID/assets/environments/ENVIRONMENT_ID/reference/
```

Put each foreground character's original images in that character's `source/` folder. Keep generated images, prior builds, screenshots, and output clips out of source folders.

Concept training globs in the template point at `approved/` and `validation/` under the character folder. Those folders are filled later from reviewed captions, not from identity-audit face crops.

## 2. Declare the production

Edit these files:

- `SERIES_EPISODE_WORKSHEET.md`: episode intent, authority, and gates. Complete this before generating media.
- `series_context.json`: series id, episode id, bible path, shared asset root.
- `project.json`: characters, environments, models, `path_defaults`, and script discovery. The copied path defaults are machine-local; point them at this machine.
- `concepts.json`: identity, wardrobe, prop, environment, and style concepts. Keep them as separate conditioning layers.
- `scripts/*.json`: scenes, shots, cast, actions, timing, formations, and continuity.
- `reviews/*.json`: per-swap and per-artifact review records when those events happen.

Use one stable character ID and one identity tag throughout `project.json`, `concepts.json`, the script `cast` / `active_concepts` lists, and the identity-selection file. `identity_id` must equal the character's `identity_tag`.

If the episode has an authoritative motion or reconstruction video, declare it under `motion_references` and ingest it with `reference-prepare` before compiling generation work. That path is documented in the reconstruction plan; skip it for a script-only intake.

## 3. Validate intake before generation

```sh
./scene_factory.py validate ./projects/PROJECT_ID
./scene_factory.py index ./projects/PROJECT_ID
./scene_factory.py compile ./projects/PROJECT_ID
./scene_factory.py prepare ./projects/PROJECT_ID
./scene_factory.py pipeline-status ./projects/PROJECT_ID
```

`prepare` writes planning records, not media:

| File | Purpose |
|---|---|
| `build/asset_index.json` | Fingerprinted sources |
| `build/generation_manifest.json` | Compiled tasks |
| `build/source_catalog.json` | Source ownership and provenance |
| `build/caption_tasks.json` | One caption task per source image |
| `build/character_sheet_plan.json` | Planned identity sheets |
| `build/storyboard_plan.json` | Planned formation frames |
| `build/scripted_clip_plan.json` | Planned clips |
| `build/sequence_plan.json` | Planned sequences |
| `build/pipeline_state.json` | Stage status and blockers |

Do not generate while validation reports unknown characters, missing sources, unresolved pointers, or unmatched script files.

## 4. Configure each foreground character

Create `characters/CHARACTER_ID.identity-selection.json` inside the project. This file is not part of the template.

```json
{
  "schema_version": 1,
  "character_id": "CHARACTER_ID",
  "identity_id": "IDENTITY_TAG",
  "canonical_seed": "chosen-seed.jpg",
  "maximum_matches": 12,
  "thresholds": {
    "maximum_seed_distance": 0.75,
    "minimum_face_area_fraction": 0.06,
    "minimum_edge_variance": 45.0,
    "minimum_multi_face_identity_margin": 0.08
  }
}
```

Optional keys the audit actually reads:

- `output_folder` — default `build/identity/CHARACTER_ID`
- `source_folder` — otherwise the character's `source_folder` from `project.json`
- `manual_face_overrides`, `manual_person_overrides`, `reject_person_isolation`

The canonical seed must be one of that character's original source images. Thresholds may be changed per character; never add generated candidates as identity truth.

## 5. Build the character reference set

The audit needs Pillow and `bin/k-identity-isolator`. `bin/` is local and gitignored. Compile the isolator from source if it is missing:

```sh
mkdir -p bin
swiftc tools/k_identity_isolator.swift \
  -framework AppKit -framework CoreImage -framework Vision \
  -o bin/k-identity-isolator
```

Run with a Python that has Pillow:

```sh
/Users/voxels/ComfyUI-Installs/Identity-Tools/.venv/bin/python \
  tools/run_identity_reference_audit.py ./projects/PROJECT_ID \
  --character-id CHARACTER_ID
```

The selector derives the source folder from `project.json` or the identity-selection file, reads the per-character policy, runs the isolator, ranks every remaining source against the seed's normalized face crop, applies quality and multi-face ambiguity gates, and writes:

```text
build/identity/CHARACTER_ID/
  approved_references/
  anchor_candidates/
  isolation/
  isolation_config.json
  identity_reference_audit.json
  selected_reference_manifest.json
```

`approved_references/` and `anchor_candidates/` are automatic face-crop copies of the seed plus eligible matches. They are not the concept training globs.

The project-wide discovery record is always `build/identity/selection_registry.json`, even when a character overrides `output_folder`.

## 6. Review before training or generation

Verify:

- The seed depicts the intended identity and life-stage presentation.
- Every accepted face is the same person.
- No mask, sunglasses, severe blur, photo-of-photo, or unrelated person was accepted.
- Expression, makeup, hair, and wardrobe are not being mistaken for identity.
- Rejected sources remain traceable in `identity_reference_audit.json`.
- Identity, wardrobe, cultural direction, visual style, props, and environments remain separate conditioning layers.

If the accepted cluster is wrong, change the seed or thresholds and rerun the audit. Do not hand-copy images into `approved_references/`.

## 7. Caption, split, and generate in order

Work the pipeline in this order. Approve the actual artifact and its manifest entry at every gate.

1. Identity reference set from steps 4–6.
2. Structured captions and human split.
3. Identity model or reference-conditioning proof.
4. Character sheets.
5. Storyboards and key frames.
6. Three-second representative motion proofs.
7. Full clips.
8. Sequence assembly and final output.

### Captions and dataset split (implemented)

```sh
./scene_factory.py caption-run ./projects/PROJECT_ID
./scene_factory.py caption-audit ./projects/PROJECT_ID
```

For a multi-person identity source, approve the isolation and the isolated-subject caption before approving the original caption. Always pass `--identity-id`:

```sh
./scene_factory.py identity-isolation-review ./projects/PROJECT_ID SOURCE_SHA256 \
  --identity-id IDENTITY_TAG --decision approved
./scene_factory.py isolation-caption-run ./projects/PROJECT_ID \
  --identity-id IDENTITY_TAG
./scene_factory.py isolation-caption-review ./projects/PROJECT_ID ASSET_ID \
  --identity-id IDENTITY_TAG --decision approved
```

Then review each caption into a split:

```sh
./scene_factory.py caption-review ./projects/PROJECT_ID ASSET_ID \
  --decision approved --split train
./scene_factory.py dataset-build ./projects/PROJECT_ID
```

Approved captions, not identity-audit face crops, feed `dataset-build`. The template identity concept still requires a separate validation set and at least 24 approved training images.

Optional coverage check (defaults to `k0l3k4` unless overridden):

```sh
./scene_factory.py character-balance ./projects/PROJECT_ID --character-id CHARACTER_ID
```

### Generation stages (planned records only)

`prepare` already wrote character-sheet, storyboard, clip, and sequence plans. Do not claim those stages complete until an execution adapter produces media and a user approval record exists.

When graphs are needed for an Ad2184-shaped project:

```sh
./scene_factory.py comfy-preflight ./projects/PROJECT_ID
./scene_factory.py comfy-build ./projects/PROJECT_ID
```

`rough-cut` concatenates completed ComfyUI clips in script order. It is visual-only and will fail closed if required clips are missing unless `--allow-missing` is set.

## 8. Progress checks

Use Scene Factory for durable status:

```sh
./scene_factory.py pipeline-status ./projects/PROJECT_ID
./scene_factory.py status ./projects/PROJECT_ID
```

`pipeline-status` is read-only and combines the intake summary with generation rollups. For the detailed per-job view, including runner records, output hashes, approvals, and optional live queue data, run:

```sh
./scene_factory.py execution-status ./projects/PROJECT_ID
./scene_factory.py execution-status ./projects/PROJECT_ID --live
```

The reporter is read-only. Do not treat `OUTPUT_ROOT` or file mtimes as proof.

Use ComfyUI only for the live queue and graph diagnostics.

User approval records require `decision: approved`, `approved_by: user`, and an empty `issues` list. `tools/approve_all_gates.py` exists for mechanical tests; do not use it as production approval.

## Koleka reference example

If the local Ad2184 tree is present, the reusable policy is [Koleka identity selection](../examples/ad2184/characters/k0l3k4.identity-selection.json). That file sets `output_folder` to `build/identity_fidelity` instead of the default `build/identity/k0l3k4`. Its approved seed and filtered matches are recorded in `examples/ad2184/build/identity_fidelity/selected_reference_manifest.json`.

`examples/` is gitignored. A clean clone will not contain that tree.

## Related pages

- [Feature-episode production handbook](17_FEATURE_EPISODE_PRODUCTION_HANDBOOK.md)
- [Operator manual](06_OPERATOR_MANUAL.md)
- [Complete production process](09_PRODUCTION_PROCESS.md)
- [Reference](08_REFERENCE.md)
- [Status and roadmap](07_STATUS_AND_ROADMAP.md)
