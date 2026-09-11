# 2. Quick Start

## Summary

This procedure checks the installed Ad2184 example without starting image, LoRA, or video generation.

## 1. Open the project folder

```sh
cd /Users/voxels/SceneFactory
```

Confirm it:

```sh
pwd
```

Expected path:

```text
/Users/voxels/SceneFactory
```

## 2. Validate

```sh
./scene_factory.py validate ./examples/ad2184
```

Expected result:

```text
Valid project: ad2184
Scenes: 7
Duration: 60.000 seconds
```

This command checks IDs, durations, references, shot formations, concepts, and LoRA stack rules. [S1]

## 3. Index

```sh
./scene_factory.py index ./examples/ad2184
```

Expected result:

```text
Characters: 3
Environments: 3
```

The independent application contains no copied source material. Its Ad2184 path default points to the existing production folder. The index should see 45 `k0l3k4` photos and the motion-reference video there. [S2]

## 4. Compile

```sh
./scene_factory.py compile ./examples/ad2184
```

Expected counts:

```text
scenes: 7
shots: 7
training_tasks: 1
keyframe_tasks: 21
video_tasks: 21
timeline_seconds: 60.0
```

These counts come from the generated manifest. [S3]

## 5. Read status

```sh
./scene_factory.py status ./examples/ad2184
```

Expected current state:

```text
Validation errors: 0
Warnings: 0
Compiled key frames: 21
Compiled clips: 21
Key-frame tasks ready: 0 of 21
LoRA training tasks ready: 0 of 1
```

Zero ready tasks is correct. The identity LoRA is not validated, and the reference-based group concepts have no media. [S2][S3]

## Pass criteria

- Validation reports seven scenes and 60 seconds.
- Indexing sees 45 foreground source photos through the default external pointer.
- Indexing sees the external motion-reference video.
- Compilation makes 21 key-frame tasks and 21 video tasks.
- The assembly timeline is 60 seconds.
- Missing identity and group inputs keep the related tasks blocked.
- No ComfyUI job starts.

## Failure rule

Stop if a command prints `Error:` or a Python traceback. Do not continue to media execution from a failed project definition.

## Related pages

- [Operator manual](06_OPERATOR_MANUAL.md)
- [Ad2184 example](05_AD2184_EXAMPLE.md)
- [Status and roadmap](07_STATUS_AND_ROADMAP.md)

[S1]: ../scene_factory.py#L145 "Validator implementation"
[S2]: ../examples/ad2184/build/asset_index.json "Current indexed sources"
[S3]: ../examples/ad2184/build/generation_manifest.json "Current compiled tasks"
