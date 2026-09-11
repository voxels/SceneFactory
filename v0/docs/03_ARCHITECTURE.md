# 3. Architecture

## Summary

Scene Factory is an overlay on an existing folder hierarchy. It separates project definition, repeating visual concepts, generated script content, indexed evidence, and executable work records. [S1][S2][S3]

## Components

| Component | Responsibility | Source |
|---|---|---|
| Project record | Format, model names, asset definitions, hierarchy root, and script patterns | [Project schema][S1] |
| Concept registry | Conditioning strategy, LoRA sources, validation set, weights, compatibility, and state | [Concept schema][S2] |
| Script records | Scenes, shots, cast, action, formations, audio, motion, continuity, and exclusions | [Script schema][S3] |
| Validator | Finds broken relationships before compilation | [Validator][S4] |
| Asset indexer | Resolves media and records fingerprints | [Indexer][S5] |
| Compiler | Makes training, key-frame, video, and assembly tasks | [Compiler][S6] |
| Future adapters | Convert compiled tasks into model-specific jobs | [Roadmap][S7] |

## Hierarchy overlay

`hierarchy.content_root` points to the common parent folder. `hierarchy.script_sources` contains one or more recursive patterns and an adapter name. [S1]

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

The discovery code removes duplicate matches when two patterns find the same file. [S8]

## Flexible path pointers

`path_defaults` defines named path values. Any project, character, environment, motion, profile, LoRA, script, or output pointer can use `${NAME}`. `${PROJECT_ROOT}` and `${CONTENT_ROOT}` are built in.

An environment variable named `SCENE_FACTORY_NAME` overrides the matching default. For example:

```sh
export SCENE_FACTORY_AD2184_SOURCE_ROOT="/new/location/ad2184"
export SCENE_FACTORY_COMFYUI_MODELS_ROOT="/new/location/comfyui/models"
export SCENE_FACTORY_OUTPUT_ROOT="/new/location/outputs"
```

The resolved values are recorded in `asset_index.json` and `generation_manifest.json`. This makes each run traceable. [S5][S6]

## Data relationships

```text
project
  +-- characters[] ---------+
  |      +-- concept_id     |
  |      +-- source_folder  |
  |                         |
  +-- environments[] -------+----> resolved by IDs
  |      +-- concept_id     |
  |      +-- reference_folder
  |
  +-- hierarchy
         +-- script_sources[] ----> scenes[]

concept registry
  +-- concepts[] -----------------> active_concepts[] in shots

script
  +-- scenes[]
         +-- environment_id
         +-- shots[]
                +-- cast[]
                +-- active_concepts[]
                +-- motion_reference_id
                +-- formations[]
```

## Compile path

1. Load `project.json` and `concepts.json`.
2. Resolve the content root.
3. Discover and adapt script files.
4. Validate IDs, duration, concept references, formation counts, and LoRA rules.
5. Index source media and calculate SHA-256 fingerprints.
6. Make one training task for each enabled training concept.
7. Make one key-frame task for each shot formation.
8. Make one video task for each key-frame task.
9. Calculate model-valid video frame counts.
10. Make the ordered assembly timeline. [S4][S5][S6]

## Readiness gates

- A LoRA concept must have `ready` status before its key frames are ready.
- A `reference` or `prompt_reference` concept must have reference media.
- Video tasks need an approved key frame and approved direction.
- Final execution still requires model adapters. [S6]

## Extension points

The current script adapters are `scene_factory_v1` and `ad2184_v1`. New adapters can convert another generated-script schema into the internal scene structure. [S8]

Future execution adapters should consume `generation_manifest.json`. They must not make new story or identity decisions.

## Related pages

- [Product summary](01_PRODUCT_SUMMARY.md)
- [LoRA system](04_LORA_SYSTEM.md)
- [Reference](08_REFERENCE.md)

[S1]: ../schemas/project.schema.json "Project structure"
[S2]: ../schemas/concepts.schema.json "Concept structure"
[S3]: ../schemas/script.schema.json "Script structure"
[S4]: ../scene_factory.py#L145 "Validation implementation"
[S5]: ../scene_factory.py#L297 "Index implementation"
[S6]: ../scene_factory.py#L349 "Compilation implementation"
[S7]: 07_STATUS_AND_ROADMAP.md "Execution boundary"
[S8]: ../scene_factory.py#L125 "Script discovery and adapters"
