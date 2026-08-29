# 6. Operator Manual

> For current manual ComfyUI operation, asset/script swaps, and feature-length episodic production, use the canonical [Feature-Episode Production Handbook](17_FEATURE_EPISODE_PRODUCTION_HANDBOOK.md). This page remains the compact compiler-oriented procedure.

## Summary

This page gives the complete operator sequence. Use it to inspect the installed example, create a project, map an existing hierarchy, and interpret failures.

## A. Inspect the installed example

1. Open Terminal.
2. Go to the workspace:

```sh
cd /Users/voxels/SceneFactory
```

3. Confirm the program and example inputs:

```sh
ls -l scene_factory.py
ls -l examples/ad2184/project.json
ls -l examples/ad2184/concepts.json
ls -l examples/ad2184/script.json
```

4. Run the four safe checks:

```sh
./scene_factory.py validate ./examples/ad2184
./scene_factory.py index ./examples/ad2184
./scene_factory.py compile ./examples/ad2184
./scene_factory.py status ./examples/ad2184
```

5. Compare the result with [Ad2184 expected evidence](05_AD2184_EXAMPLE.md). The independent application does not contain production media. Its default pointer reads the existing external Ad2184 folder.

## B. Inspect the generated files

Asset evidence:

```sh
jq '{characters: [.assets.characters[] | {id, count: (.files | length)}], concepts: .assets.concepts, motion: .assets.motion_references}' examples/ad2184/build/asset_index.json
```

Task counts:

```sh
jq '.counts' examples/ad2184/build/generation_manifest.json
```

Blockers by shot:

```sh
jq '[.keyframe_tasks | group_by(.shot_id)[] | {shot_id: .[0].shot_id, blockers: ([.[].blockers[]] | unique)}]' examples/ad2184/build/generation_manifest.json
```

Shot 2 path:

```sh
jq '{keyframes: [.keyframe_tasks[] | select(.shot_id == "shot_02")], videos: [.video_tasks[] | select(.shot_id == "shot_02")], edit: [.assembly[] | select(.shot_id == "shot_02")]}' examples/ad2184/build/generation_manifest.json
```

## C. Create a new project

Choose an empty folder:

```sh
./scene_factory.py new "$HOME/Desktop/scene_factory_test" --id scene_factory_test --title "Scene Factory Test"
```

The new project contains `project.json`, `concepts.json`, a model profile, a script, and asset drop folders. The `new` command copies these from the template. [S1]

## D. Add sources

Use the created folders or point the records to existing folders:

```text
assets/foreground_characters/<id>/source/
assets/background_characters/<id>/source/
assets/environments/<id>/reference/
assets/motion_references/
```

Keep IDs identical across `project.json`, `concepts.json`, and the script.

## E. Map an existing hierarchy

Set the common parent folder and recursive script pattern:

```json
"hierarchy": {
  "content_root": "/absolute/path/to/existing/root",
  "script_sources": [
    {
      "glob": "series/*/episodes/*/scripts/*.json",
      "adapter": "scene_factory_v1"
    }
  ]
}
```

See [Architecture: hierarchy overlay](03_ARCHITECTURE.md#hierarchy-overlay).

To override a named path without editing JSON:

```sh
export SCENE_FACTORY_SOURCE_ROOT="/new/source/root"
export SCENE_FACTORY_COMFYUI_MODELS_ROOT="/new/comfyui/models"
export SCENE_FACTORY_OUTPUT_ROOT="/new/output/root"
```

The environment variable name is `SCENE_FACTORY_` followed by the key from `path_defaults`.

## F. Validate the new project

```sh
./scene_factory.py validate "$HOME/Desktop/scene_factory_test"
./scene_factory.py index "$HOME/Desktop/scene_factory_test"
./scene_factory.py compile "$HOME/Desktop/scene_factory_test"
./scene_factory.py status "$HOME/Desktop/scene_factory_test"
```

## G. Verify structured captions

Prepare the production records and run the configured caption model:

```sh
./scene_factory.py prepare ./examples/ad2184
./scene_factory.py caption-run ./examples/ad2184
./scene_factory.py caption-audit ./examples/ad2184
```

Open `examples/ad2184/build/captions/MANUAL_REVIEW.md`. For each row, compare the source image, raw response, and validated result. Confirm the correct foreground woman, face visibility, age-range label, framing, variable attributes, and training caption. A record with multiple people must be isolated with a subject mask or rejected before identity training.

Do not approve captions automatically. Use `caption-review` only after this visual check. Keep at least one approved validation image separate from the training images. After review, run `dataset-build` and inspect the dataset manifest before LoRA training.

## Failure interpretation

| Result | Meaning | Action |
|---|---|---|
| `Error:` | Project relationship or input is invalid | Correct it before compilation |
| Python traceback | Program defect or unsupported input | Stop and retain the complete output |
| Warning | Project can continue, but a source or policy needs review | Review before execution |
| `ready: false` | A declared gate is not satisfied | Read the task `blockers` list |
| Zero indexed media | Folder exists but contains no supported media | Add media or change conditioning strategy |
| Wrong duration | Shot total and project duration differ | Correct script durations |
| Unknown concept | Script and concept IDs do not match | Use one stable ID |
| Unvalidated LoRA combination | Two LoRAs have no approved compatibility record | Validate or remove the combination |

## Acceptance checklist

- [ ] `validate` reports no errors.
- [ ] Indexed source counts match the folders.
- [ ] Motion references exist and have fingerprints.
- [ ] Scene and shot counts match the script.
- [ ] Formation count matches the project rule.
- [ ] Compiled duration matches the project duration.
- [ ] LoRA training is blocked without approved training and validation sources.
- [ ] Reference conditioning is blocked without reference media.
- [ ] Each key-frame task has a matching video and assembly record.
- [ ] No generation starts from these compiler commands.
- [ ] `caption-audit` reports 45 valid caption records and no missing raw responses for Ad2184.
- [ ] Multi-person identity images are isolated or rejected before approval.

## Related pages

- [Quick start](02_QUICK_START.md)
- [Reference](08_REFERENCE.md)
- [Legacy detailed test guide](../USER_TEST_GUIDE.md)

[S1]: ../scene_factory.py#L518 "New project implementation"
