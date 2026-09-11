# Scene Factory Documentation

Scene Factory is a local production compiler for consistent character, environment, key-frame, and video work. It reads an existing folder hierarchy, checks the production definitions, indexes source media, and compiles model-ready work records. ComfyUI API graphs now exist, but a complete identity-to-sequence production cycle is not yet verified.

## Current status

| Area | State | Evidence |
|---|---|---|
| Project validation | Implemented and tested | [Validator source](../scene_factory.py#L145), [Ad2184 project](../examples/ad2184/project.json) |
| Existing hierarchy discovery | Implemented and tested | [Script discovery](../scene_factory.py#L125) |
| Asset indexing and fingerprints | Implemented and tested | [Indexer source](../scene_factory.py#L297), [Ad2184 asset index](../examples/ad2184/build/asset_index.json) |
| Concept and LoRA policy | Implemented in schema and compiler | [Concept schema](../schemas/concepts.schema.json), [LoRA policy](04_LORA_SYSTEM.md) |
| Shot and formation compilation | Implemented and tested | [Compiler source](../scene_factory.py#L349), [Ad2184 manifest](../examples/ad2184/build/generation_manifest.json) |
| ComfyUI graph generation | Implemented; full execution not verified | [Master checklist](10_MASTER_WORKFLOW_CHECKLIST.md) |
| LTX 2.5 graph generation | Implemented; completed clip not verified | [Master checklist](10_MASTER_WORKFLOW_CHECKLIST.md) |

## Read in this order

1. [Product summary](01_PRODUCT_SUMMARY.md) — what the software is, what it does, and what it does not do.
2. [Quick start](02_QUICK_START.md) — the shortest safe test of the installed software.
3. [Architecture](03_ARCHITECTURE.md) — folders, inputs, compiler stages, outputs, and gates.
4. [LoRA system](04_LORA_SYSTEM.md) — repeating concepts, datasets, strategies, stacks, and promotion states.
5. [Ad2184 example](05_AD2184_EXAMPLE.md) — the seven-scene reference implementation.
6. [Operator manual](06_OPERATOR_MANUAL.md) — complete user procedure and failure checks.
7. [Status and roadmap](07_STATUS_AND_ROADMAP.md) — verified work, gaps, blockers, and next implementation stage.
8. [Reference](08_REFERENCE.md) — commands, schemas, files, terms, and citation index.
9. [Complete production process](09_PRODUCTION_PROCESS.md) — captions, datasets, character sheets, storyboards, clips, and sequences.
10. [Master workflow checklist](10_MASTER_WORKFLOW_CHECKLIST.md) — all chat requirements, current evidence, missing work, and acceptance conditions.

## Main data path

```text
existing parent and child folders
              |
              v
project.json + concepts.json + script JSON + source media
              |
              v
        validate and index
              |
              v
        asset_index.json
              |
              v
           compile
              |
              v
    generation_manifest.json
              |
              v
ComfyUI API graphs and execution
```

## Documentation rules

- This folder is the documentation entry point.
- Numbered pages define the reading order.
- Each page starts with a summary.
- Each page links to related pages.
- Software claims cite code, schema, configuration, or generated evidence.
- Generated evidence proves compilation results. It does not prove media quality or ComfyUI execution.
- Old top-level guides remain available, but this documentation set is the canonical presentation.

## Fast paths

- I want to run a safe test: [Quick start](02_QUICK_START.md).
- I want the complete chat-audited checklist: [Master workflow checklist](10_MASTER_WORKFLOW_CHECKLIST.md).
- I want the manual test steps: [Operator manual](06_OPERATOR_MANUAL.md).
- I want to map my existing hierarchy: [Architecture: hierarchy overlay](03_ARCHITECTURE.md#hierarchy-overlay).
- I want to design repeating LoRAs: [LoRA system](04_LORA_SYSTEM.md).
- I want to inspect Ad2184: [Ad2184 example](05_AD2184_EXAMPLE.md).
- I want to know what is missing: [Status and roadmap](07_STATUS_AND_ROADMAP.md).
- I want the full text-to-sequence process: [Complete production process](09_PRODUCTION_PROCESS.md).
