# 8. Reference

## Summary

This page is the command, file, schema, term, and citation index for Scene Factory.

## Commands

| Command | Result | Implementation |
|---|---|---|
| `new` | Copy the project template and model profiles | [Source](../scene_factory.py#L518) |
| `validate` | Check project relationships and rules | [Source](../scene_factory.py#L533) |
| `index` | Resolve and fingerprint source media | [Source](../scene_factory.py#L546) |
| `compile` | Make the generation manifest | [Source](../scene_factory.py#L560) |
| `status` | Summarize errors, warnings, task counts, and readiness | [Source](../scene_factory.py#L573) |
| `prepare` | Create source, caption, character-sheet, storyboard, clip, sequence, and pipeline-state records | [Source](../pipeline.py) |
| `caption-run` | Run structured image captions through the configured local Hugging Face or Ollama vision model | [Source](../pipeline.py) |
| `reference-contract-run` | Execute pending reference-frame contracts through the configured local Hugging Face vision model | [Source](../reference_contracts.py) |
| `reference-contract-audit` | Aggregate field-provenance contracts and refresh the written-disagreement generation gate | [Source](../reference_contracts.py) |
| `caption-audit` | Validate all caption evidence and create the manual review report | [Source](../pipeline.py) |
| `caption-import` | Import structured captions from another system | [Source](../pipeline.py) |
| `caption-review` | Approve or reject a caption and assign its split | [Source](../pipeline.py) |
| `dataset-build` | Build reviewed concept dataset manifests | [Source](../pipeline.py) |
| `pipeline-status` | Show the status and blockers for every production stage | [Source](../pipeline.py) |

General form:

```sh
./scene_factory.py <command> <project-folder>
```

The `new` command also needs `--id` and `--title`.

## Path pointers

| Pointer | Source |
|---|---|
| `${PROJECT_ROOT}` | Built-in project folder |
| `${CONTENT_ROOT}` | Resolved hierarchy content root |
| `${NAME}` | Value from `project.json` `path_defaults.NAME` |
| `SCENE_FACTORY_NAME` | Environment override for `path_defaults.NAME` |

Resolved pointer values are stored in the generated index and manifest.

## Canonical documentation

| File | Purpose |
|---|---|
| [Documentation home](README.md) | Reading order and status dashboard |
| [Product summary](01_PRODUCT_SUMMARY.md) | Scope and boundary |
| [Quick start](02_QUICK_START.md) | Short safe test |
| [Architecture](03_ARCHITECTURE.md) | Components and data flow |
| [LoRA system](04_LORA_SYSTEM.md) | Repeating concept policy |
| [Ad2184 example](05_AD2184_EXAMPLE.md) | Reference implementation |
| [Operator manual](06_OPERATOR_MANUAL.md) | Full user procedure |
| [Status and roadmap](07_STATUS_AND_ROADMAP.md) | Verified work and gaps |
| [Complete production process](09_PRODUCTION_PROCESS.md) | Full source-to-sequence stage system |

## Schemas

| Schema | Defines |
|---|---|
| [project.schema.json](../schemas/project.schema.json) | Project, models, defaults, characters, environments, hierarchy, and concept registry path |
| [concepts.schema.json](../schemas/concepts.schema.json) | Repeating concepts, training, conditioning, weights, state, and compatibility |
| [script.schema.json](../schemas/script.schema.json) | Scenes, shots, cast, action, formations, motion, audio, and continuity |
| [caption.schema.json](../schemas/caption.schema.json) | Structured per-image training description and review state |
| [pipeline.schema.json](../schemas/pipeline.schema.json) | Ordered stages, statuses, inputs, outputs, and blockers |

## Templates and profiles

| File | Purpose |
|---|---|
| [Template project](../template/project.json) | Default project record |
| [Template concepts](../template/concepts.json) | Default identity concept |
| [Template script](../template/scripts/script.json) | One-scene, three-formation example |
| [FLUX.2 identity profile](../profiles/flux2_klein_identity_lora.json) | Current identity training baseline |

## Ad2184 evidence

| File | Evidence |
|---|---|
| [Project](../examples/ad2184/project.json) | Model and hierarchy choices |
| [Concepts](../examples/ad2184/concepts.json) | Identity and group strategies |
| [Script](../examples/ad2184/script.json) | Seven-scene production definition |
| [Asset index](../examples/ad2184/build/asset_index.json) | Resolved source counts and fingerprints |
| [Generation manifest](../examples/ad2184/build/generation_manifest.json) | Compiled task, blocker, timing, and output records |

## Glossary

| Term | Meaning |
|---|---|
| Active concept | A visual concept that a shot needs |
| Adapter | Code that converts one file or task format into another |
| Assembly | Ordered clip placement on the final timeline |
| Conditioning strategy | Prompt, reference, prompt plus reference, or LoRA |
| Content root | Common parent folder for source discovery |
| Formation | One camera and framing treatment inside a shot |
| Generation manifest | Compiled list of future training, image, video, and edit work |
| Identity tag | Stable token used for one repeating character identity |
| LoRA stack | LoRA concepts active in one generation task |
| Motion reference | Video used for timing or movement, not identity |
| Promotion state | Planned, training, validation, ready, or rejected |
| Reference media | Approved images or video used for visual conditioning |
| Review gate | Required approval before the next stage |
| Script adapter | Converter from a generated-script schema to Scene Factory scenes |

## Citation rule

Documentation claims use page-local source labels such as `[S1]`. Each label resolves to code, a schema, a project record, or generated evidence. Generated evidence cites compilation state only. It does not cite output quality.
