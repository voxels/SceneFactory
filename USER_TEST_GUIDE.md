# Scene Factory User Test Guide

> Documentation entry point: [Scene Factory Documentation](docs/README.md). Canonical operator procedure: [Operator Manual](docs/06_OPERATOR_MANUAL.md).

Use this guide to inspect Scene Factory and run it yourself. These steps do not start ComfyUI generation. They validate and compile the production plan.

## Part 1: Open Terminal in the correct folder

1. Open Terminal.
2. Run:

```sh
cd /Users/voxels/SceneFactory
```

3. Confirm the location:

```sh
pwd
```

Expected result:

```text
/Users/voxels/SceneFactory
```

Stop if Terminal shows a different folder.

## Part 2: Confirm that the software is present

Run:

```sh
ls -l scene_factory.py
ls -l examples/ad2184/project.json
ls -l examples/ad2184/script.json
ls -l examples/ad2184/concepts.json
```

Expected result: Terminal shows all four files. A `No such file or directory` message is a failure.

## Part 3: Read the three Ad2184 inputs

Open these files in your preferred text editor:

```text
examples/ad2184/project.json
examples/ad2184/script.json
examples/ad2184/concepts.json
```

Check these facts:

- `project.json` has project ID `ad2184`.
- The project duration is 60 seconds.
- The frame rate is 24 fps.
- The image generator is FLUX.2 Klein.
- The video generator is LTX 2.5.
- The hierarchy content root is `../../..`.
- `script.json` has seven scenes.
- Each shot has three formations.
- `concepts.json` has `k0l3k4_identity`.
- The `k0l3k4` inference strategy is `lora`.
- The `k0l3k4` LoRA status is `planned`.
- The masses and enforcers use `prompt_reference`.

Do not change these files during the first test.

## Part 4: Run the project validator

Run:

```sh
./scene_factory.py validate ./examples/ad2184
```

Expected result:

```text
Valid project: ad2184
Scenes: 7
Duration: 60.000 seconds
```

The validator checks:

- JSON structure
- Unique scene, shot, character, environment, and concept IDs
- Character and environment references
- Shot duration
- Total project duration
- Three formations per shot
- Known concept names
- LoRA stack limits
- Blocked or unvalidated LoRA combinations

Any line that starts with `Error:` is a failure. Correct the reported file or ID before you continue.

## Part 5: Build the asset index

Run:

```sh
./scene_factory.py index ./examples/ad2184
```

Expected result:

```text
Characters: 3
Environments: 3
```

The asset index is here:

```text
examples/ad2184/build/asset_index.json
```

Inspect the important counts:

```sh
jq '{characters: [.assets.characters[] | {id, count: (.files | length)}], concepts: .assets.concepts, motion: .assets.motion_references}' examples/ad2184/build/asset_index.json
```

Expected current facts:

- The independent app sees 45 external `k0l3k4` source files through its default pointer.
- `dystopian_masses` has 0 reference files.
- `enforcers` has 0 reference files.
- `k0l3k4_identity` has 0 approved training files.
- `k0l3k4_identity` has 0 validation files.
- The independent app sees the external Apple 1984 motion reference through its default pointer.

These zero counts are current workflow blockers. They are not index failures.

## Part 6: Compile the generation manifest

Run:

```sh
./scene_factory.py compile ./examples/ad2184
```

Expected result:

```text
scenes: 7
shots: 7
training_tasks: 1
keyframe_tasks: 21
video_tasks: 21
timeline_seconds: 60.0
```

The compiled file is here:

```text
examples/ad2184/build/generation_manifest.json
```

This command does not call ComfyUI. It creates a complete list of future training, key-frame, video, and edit tasks.

## Part 7: Read the workflow status

Run:

```sh
./scene_factory.py status ./examples/ad2184
```

Expected current result:

```text
Validation errors: 0
Warnings: 0
Compiled key frames: 21
Compiled clips: 21
Key-frame tasks ready: 0 of 21
LoRA training tasks ready: 0 of 1
```

The zero ready counts are correct at this stage. They show that the safety gates work.

## Part 8: Check the blocker for every shot

Run:

```sh
jq '[.keyframe_tasks | group_by(.shot_id)[] | {shot_id: .[0].shot_id, blockers: ([.[].blockers[]] | unique)}]' examples/ad2184/build/generation_manifest.json
```

Expected blockers:

- Shots 1, 3, 5, 6, and 7 need masses reference media.
- Shot 2 needs the k0l3k4 LoRA and enforcer reference media.
- Shot 4 needs the k0l3k4 LoRA, masses references, and enforcer references.

If a task with one of these missing inputs says `ready: true`, the gate has failed.

## Part 9: Inspect one complete shot

Run:

```sh
jq '{keyframes: [.keyframe_tasks[] | select(.shot_id == "shot_02")], videos: [.video_tasks[] | select(.shot_id == "shot_02")], edit: [.assembly[] | select(.shot_id == "shot_02")]}' examples/ad2184/build/generation_manifest.json
```

Confirm that Shot 2 contains:

- Three key-frame formations: `corridor_wide`, `frontal_chase`, and `hammer_close`.
- The identity tag `k0l3k4`.
- The enforcer tag `enforcer_anchor`.
- One planned k0l3k4 LoRA in the LoRA stack.
- The `apple_1984_motion` motion reference.
- Three video tasks with 81 frames each.
- Three edit segments of approximately 3.333 seconds each.
- A total Shot 2 edit duration of 10 seconds.

## Part 10: Create a new test project

Choose an empty destination folder. This example uses your Desktop:

```sh
./scene_factory.py new "$HOME/Desktop/scene_factory_test" --id scene_factory_test --title "Scene Factory Test"
```

Expected result:

```text
Project created: /Users/voxels/Desktop/scene_factory_test
```

The new folder contains:

```text
project.json
concepts.json
profiles/
scripts/script.json
assets/foreground_characters/
assets/background_characters/
assets/environments/
assets/motion_references/
```

If the destination already contains files, the command stops. Choose another empty folder.

## Part 11: Drop files into the new project

Put files in these example folders:

```text
assets/foreground_characters/lead/source/
assets/background_characters/background_group/source/
assets/environments/main_environment/reference/
assets/motion_references/
```

Then edit:

```text
project.json
concepts.json
scripts/script.json
```

Keep each ID identical in all three files. For example, `lead` must not become `Lead` or `lead_character` in only one file.

## Part 12: Test the new project

Run:

```sh
./scene_factory.py validate "$HOME/Desktop/scene_factory_test"
./scene_factory.py index "$HOME/Desktop/scene_factory_test"
./scene_factory.py compile "$HOME/Desktop/scene_factory_test"
./scene_factory.py status "$HOME/Desktop/scene_factory_test"
```

Correct all validation errors before you connect generation tools.

## Part 13: Connect an existing folder hierarchy

In the project `project.json`, set the common parent folder:

```json
"hierarchy": {
  "content_root": "/absolute/path/to/your/existing/production/root",
  "script_sources": [
    {
      "glob": "series/*/episodes/*/scripts/*.json",
      "adapter": "scene_factory_v1"
    }
  ]
}
```

Use `scene_factory_v1` when the script follows `schemas/script.schema.json`.

The software reads matched child scripts recursively. It does not move or rename them.

## Part 14: Understand the current software boundary

These parts work now:

- Project validation
- Existing hierarchy discovery
- Asset indexing
- File fingerprints
- Concept and LoRA registry checks
- Shot-formation compilation
- Key-frame task compilation
- Video direction compilation
- Frame-count calculation
- 60-second assembly planning
- Review and readiness gates

These parts are not implemented yet:

- Sending compiled key-frame tasks to ComfyUI
- Running generic LoRA training tasks
- Sending compiled video tasks to LTX 2.5
- Monitoring ComfyUI jobs
- Reviewing and approving outputs in an app interface
- Final video assembly

Do not expect `compile` to generate media. The next software component is the ComfyUI execution adapter.

## Test acceptance checklist

- [ ] `validate` reports seven scenes and 60 seconds.
- [ ] `index` sees 45 external k0l3k4 source photos.
- [ ] `index` sees the external motion-reference video.
- [ ] `compile` makes 21 key-frame tasks.
- [ ] `compile` makes 21 video tasks.
- [ ] The assembly duration is 60 seconds.
- [ ] The k0l3k4 LoRA is not ready before approval and validation.
- [ ] Missing prompt-reference media blocks affected tasks.
- [ ] Shot 2 has three correct formations.
- [ ] Shot 2 uses only one LoRA slot.
- [ ] No ComfyUI generation starts during this test.
