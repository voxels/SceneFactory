# Next Run Playbook

This is the restart document for a new script, project, or character set. Scene Factory owns production truth and gates. ComfyUI executes generated graphs; it is not the script, asset, or approval database.

## UI ownership

| Work | Use now | Do not use as authority |
|---|---|---|
| Discuss changes, inspect folders, run commands, review contact sheets and clips | Codex desktop | Chat history alone |
| Edit `project.json`, scripts, concepts, and character policies | Codex editor or a JSON-aware code editor | ComfyUI prompts |
| Inspect or debug generation graphs and view the live queue | ComfyUI | ComfyUI workflow filenames as production state |
| Record approvals and rejections | Scene Factory JSON manifests and review records | Finder labels or verbal approval only |

The recommended future UI is a local **Scene Factory Review Console** in the browser. It should read and write the existing manifests, not introduce a second database. Required screens are Project Setup, Script/Shot Review, Character Assets, Identity Seed and Similarity Review, Generation Queue, and Gate Approvals. Until that console exists, Codex desktop is the best operator surface and ComfyUI is the execution/debug surface.

## 1. Create the project

```sh
cd /Users/voxels/SceneFactory/v3
./scene_factory.py new ./projects/PROJECT_ID --id PROJECT_ID --title "PROJECT TITLE"
```

Put the script in `projects/PROJECT_ID/scripts/`. Put each foreground character's original images in:

```text
projects/PROJECT_ID/assets/foreground_characters/CHARACTER_ID/source/
```

Keep generated images, prior builds, screenshots, and output clips out of source folders.

## 2. Declare the production

Edit these files:

- `project.json`: characters, environments, models, output root, and script discovery.
- `concepts.json`: identity, wardrobe, prop, environment, and style concepts.
- `scripts/*.json`: scenes, shots, cast, actions, timing, formations, and continuity.

Use one stable character ID and identity tag throughout the project.

## 3. Validate intake before generation

```sh
./scene_factory.py validate ./projects/PROJECT_ID
./scene_factory.py index ./projects/PROJECT_ID
./scene_factory.py compile ./projects/PROJECT_ID
./scene_factory.py prepare ./projects/PROJECT_ID
./scene_factory.py pipeline-status ./projects/PROJECT_ID
```

Do not generate while validation reports unknown characters, missing sources, unresolved pointers, or unmatched script files.

## 4. Configure each foreground character

Create `characters/CHARACTER_ID.identity-selection.json` inside the project:

```json
{
  "schema_version": 1,
  "character_id": "CHARACTER_ID",
  "identity_id": "CHARACTER_ID_identity",
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

The canonical seed must be one of that character's original source images. Thresholds may be changed per character; never add generated candidates as identity truth.

## 5. Build the character reference set

Run with the Python environment containing Pillow:

```sh
/Users/voxels/ComfyUI-Installs/Identity-Tools/.venv/bin/python \
  tools/run_identity_reference_audit.py ./projects/PROJECT_ID \
  --character-id CHARACTER_ID
```

The reusable selector derives the source folder from `project.json`, reads the per-character policy, normalizes detected face crops, ranks every remaining source against the seed, applies quality and multi-face ambiguity gates, and writes:

```text
build/identity/CHARACTER_ID/
  approved_references/
  review_candidates/
  identity_reference_audit.json
  selected_reference_manifest.json
  isolation/
```

The project-wide discovery record is `build/identity/selection_registry.json`.

## 6. Review before training or generation

Verify:

- The seed depicts the intended identity and life-stage presentation.
- Every accepted face is the same person.
- No mask, sunglasses, severe blur, photo-of-photo, or unrelated person was accepted.
- Expression, makeup, hair, and wardrobe are not being mistaken for identity.
- Rejected sources remain traceable in the audit.
- Identity, wardrobe, cultural direction, visual style, props, and environments remain separate conditioning layers.

If the accepted cluster is wrong, change the seed or thresholds and rerun. Do not manually copy questionable images into `approved_references`.

## 7. Generate and review in order

1. Identity reference set.
2. Captions and dataset split.
3. Identity model or reference-conditioning proof.
4. Character sheets.
5. Storyboards and key frames.
6. Three-second representative motion proofs.
7. Full clips.
8. Sequence assembly and final output.

At every gate, approve the actual artifact and its manifest entry. A successful process exit is not visual approval.

## 8. Progress checks

Use Scene Factory for durable status:

```sh
./scene_factory.py pipeline-status ./projects/PROJECT_ID
./scene_factory.py status ./projects/PROJECT_ID
```

Use ComfyUI only for the live queue and graph diagnostics. Check final assets under the project's configured `OUTPUT_ROOT`, not by file modification date alone.

## Koleka reference example

The reusable policy is [Koleka identity selection](../examples/ad2184/characters/k0l3k4.identity-selection.json). Its approved seed and six filtered matches are recorded in [the selection manifest](../examples/ad2184/build/identity_fidelity/selected_reference_manifest.json).
