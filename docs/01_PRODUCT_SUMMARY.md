# 1. Product Summary

## Summary

Scene Factory is a folder-overlay compiler. It lets an existing production hierarchy supply foreground characters, background characters, environments, motion references, and generated scripts. It converts these sources into one checked production manifest. [S1][S2]

Scene Factory currently plans work. It does not yet execute ComfyUI, LoRA training, LTX 2.5, or final assembly. [S3]

## Problem

A multi-scene generation project must keep these relationships stable:

- One character ID across many scenes and camera formations.
- One identity tag across training captions and prompts.
- One environment ID across related shots.
- One shot duration across key frames, generated clips, and final edit placement.
- One repeating concept policy across LoRA training and inference.
- One review gate between each production stage.

A loose collection of ComfyUI graphs does not define these relationships. Scene Factory puts them in project, concept, and script records before generation begins. [S1][S2]

## Inputs

| Input | Purpose | Definition |
|---|---|---|
| `project.json` | Project format, models, characters, environments, hierarchy, and defaults | [Project schema][S1] |
| `concepts.json` | Repeating concepts, LoRA training, inference strategy, status, and stack policy | [Concept schema][S2] |
| Script JSON | Scenes, shots, cast, action, active concepts, motion reference, and formations | [Script schema][S4] |
| Source media | Character, group, environment, and motion-reference files | [Indexer][S5] |

## Outputs

| Output | Purpose | Evidence |
|---|---|---|
| `asset_index.json` | Resolved source paths, file counts, and SHA-256 fingerprints | [Ad2184 asset index][S6] |
| `generation_manifest.json` | Training, key-frame, video, and assembly tasks | [Ad2184 manifest][S7] |

## Commands

Scene Factory supplies five commands: `new`, `validate`, `index`, `compile`, and `status`. [S8]

## Product boundary

The compiler can say that a task is ready or blocked. It cannot prove that an image has correct identity, that a video has good motion, or that a model file is usable. Those facts need execution adapters and human review evidence. [S3]

## Related pages

- [Quick start](02_QUICK_START.md)
- [Architecture](03_ARCHITECTURE.md)
- [Status and roadmap](07_STATUS_AND_ROADMAP.md)

[S1]: ../schemas/project.schema.json "Project schema"
[S2]: ../schemas/concepts.schema.json "Concept and LoRA schema"
[S3]: 07_STATUS_AND_ROADMAP.md "Current implementation boundary"
[S4]: ../schemas/script.schema.json "Script schema"
[S5]: ../scene_factory.py#L297 "Asset index implementation"
[S6]: ../examples/ad2184/build/asset_index.json "Generated Ad2184 asset evidence"
[S7]: ../examples/ad2184/build/generation_manifest.json "Generated Ad2184 task evidence"
[S8]: ../scene_factory.py#L518 "Command implementations"
