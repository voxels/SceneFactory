# Scene Factory

Scene Factory is a reusable local production kit for consistent image and video generation. You put source files in named folders. You describe the project and script with JSON. The compiler makes one generation manifest for identity work, key frames, clips, environments, audio, graphics, and final assembly.

Start with the [Scene Factory documentation](docs/README.md). It contains the ordered reading path, status dashboard, architecture, LoRA system, Ad2184 example, operator manual, roadmap, and reference index.

For a complete user-operated test, follow the [operator manual](docs/06_OPERATOR_MANUAL.md). The older [user test guide](USER_TEST_GUIDE.md) remains available for detailed command output.

Scene Factory does not copy model files. It points to the models that ComfyUI Desktop can already see.

The Ad2184 caption stage points to the installed Qwen3.5-9B vision weights and a compatible local Qwen3.8 processor. The installed example has 45 raw responses and 45 validated caption results. Run `./scene_factory.py caption-audit ./examples/ad2184` to refresh the manual review report. The caption command selects the configured vision Python environment and prints progress while it runs.

## Start a project

```sh
./scene_factory.py new ./my_project --id my_project --title "My Project"
```

Put files in these folders:

```text
my_project/
  assets/
    foreground_characters/<character-id>/source/
    background_characters/<group-id>/source/
    environments/<environment-id>/reference/
    motion_references/
  scripts/script.json
  project.json
```

Then run:

```sh
./scene_factory.py validate ./my_project
./scene_factory.py index ./my_project
./scene_factory.py compile ./my_project
./scene_factory.py status ./my_project
```

The compiled file is `build/generation_manifest.json`.

Prepare the complete production process:

```sh
./scene_factory.py prepare ./my_project
./scene_factory.py pipeline-status ./my_project
```

See `docs/09_PRODUCTION_PROCESS.md` for structured captions, dataset approval, character sheets, storyboards, clips, and sequences.

## Use an existing parent and child hierarchy

You do not have to move existing files. Set `hierarchy.content_root` to the common parent folder. Add one or more recursive patterns to `hierarchy.script_sources`. Each pattern also names an adapter for the JSON format.

```json
"hierarchy": {
  "content_root": "../existing-production-root",
  "script_sources": [
    {"glob": "series/*/episodes/*/scripts/*.json", "adapter": "scene_factory_v1"}
  ]
}
```

Character, group, environment, and concept source folders can also point to child folders under that root. Scene Factory records the relationships. It does not copy or rename the source files.

## Flexible path pointers

`project.json` can declare named `path_defaults`. Any path can use `${NAME}`. An environment variable named `SCENE_FACTORY_NAME` overrides the default without a JSON edit.

The Ad2184 example defaults to the existing production folder. To move it later, set:

```sh
export SCENE_FACTORY_AD2184_SOURCE_ROOT="/new/path/to/ad2184"
```

Built-in pointers include `${PROJECT_ROOT}` and `${CONTENT_ROOT}`. The example also defines `${COMFYUI_MODELS_ROOT}` and `${OUTPUT_ROOT}`.

## Repeating concept LoRAs

`concepts.json` is the LoRA registry. A concept can be a character identity, background group, environment, wardrobe, prop, or style.

See `LORA_CONCEPT_POLICY.md` for dataset isolation, stack validation, model profiles, and promotion rules.

Use a LoRA only when a visual concept repeats and prompt or reference conditioning does not keep it stable. Use these rules:

- Train one identity LoRA for each important repeating foreground character.
- Train a background-group LoRA only when that group has a distinct and repeating design.
- Train an environment LoRA only when the same location must remain stable across many shots.
- Train wardrobe or prop LoRAs only for unique designs that repeat often.
- Use no more than one style LoRA in a stack. Test it with every identity LoRA that it can meet.
- Do not make separate LoRAs for simple age, mood, color, camera, or lighting attributes.
- Keep training and validation sources separate. Keep near-duplicate photos in only one split.
- Use real approved sources by default. Generated sources require a separate provenance and identity review.
- Keep the trigger token and class token stable. Caption only the attributes that are visible.
- Validate each LoRA alone and in every allowed LoRA combination.
- Keep the active LoRA count within `stack_policy.maximum_active_loras`.

## Main rules

- Each character has one stable ID and one stable identity tag.
- Attribute tags stay with the character across all shots.
- Each scene points to one declared environment.
- Each shot contains three or more shot formations by default.
- Each formation becomes one key-frame task and one video task.
- The video frame count follows the configured model rule.
- A stage cannot start until its input review gate passes.
- Exact text and logos stay in the graphics stage.
- Motion-reference video controls timing and movement. It does not control identity.

## Ad2184 example

The example in `examples/ad2184/` shows seven scenes, one foreground character, one background group, one enforcer group, three formations per shot, and the Ridley Scott motion reference.

```sh
./scene_factory.py validate ./examples/ad2184
./scene_factory.py compile ./examples/ad2184
```

## What the compiler connects

```text
photos -> identity review -> approved dataset -> identity model
script + characters + environments + shot formations -> key-frame tasks
key frames + motion reference + motion direction -> clip tasks
approved clips + audio + graphics -> final assembly plan
```

The compiler makes plans and checks. ComfyUI workflow adapters execute those plans. Model-specific adapters can be added without changing the project or script schema.
