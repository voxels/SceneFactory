# 9. Complete Production Process

## Summary

Scene Factory now prepares durable records for the complete path from text and reference images to captions, concept datasets, character sheets, storyboards, scripted clips, extended sequences, and final assembly. Model execution adapters remain required for generation stages.

## Stage order

```text
1. Source ingestion and fingerprinting
2. Structured image captioning
3. Human caption review and train or validation split
4. Concept dataset build
5. Concept LoRA training and validation
6. Character-sheet generation and review
7. Storyboard generation and review
8. Production key frames and motion direction
9. Scripted clip generation and review
10. Extended sequence assembly and continuity review
11. Audio, graphics, and final assembly
```

Each stage stores its inputs, outputs, status, and blockers in `build/pipeline_state.json`. [S1][S2]

## Prepare all records

```sh
./scene_factory.py prepare ./examples/ad2184
```

This creates:

| File | Purpose |
|---|---|
| `build/source_catalog.json` | Source paths, fingerprints, ownership, concept IDs, provenance, and duplicate groups |
| `build/caption_tasks.json` | One structured-caption task per source image |
| `build/character_sheet_plan.json` | Identity views, profiles, full-body views, expressions, and wardrobe sheets |
| `build/storyboard_plan.json` | One low-cost composition task per shot formation |
| `build/scripted_clip_plan.json` | Motion, handles, and continuity checks for every clip |
| `build/sequence_plan.json` | Scene sequences, extension policy, audio cues, and final timeline |
| `build/pipeline_state.json` | Stage status and blockers |

## Structured captions

The caption schema stores:

- Source fingerprint and concept ID
- Visible description and subjects
- Framing, view, and camera angle
- Lighting and environment
- Visible text
- Sharpness, occlusion, usability, and risks
- Identity and attribute tags
- Final training caption
- Caption model
- Review state
- Train, validation, or reject split [S3]

Run the configured vision model:

```sh
./scene_factory.py caption-run ./examples/ad2184
```

Run only a small batch:

```sh
./scene_factory.py caption-run ./examples/ad2184 --limit 3
```

Regenerate one asset and replace its raw response and validated result:

```sh
./scene_factory.py caption-run ./examples/ad2184 --asset-id ASSET_ID --force
```

Audit all caption evidence and make the manual review table:

```sh
./scene_factory.py caption-audit ./examples/ad2184
```

The audit re-hashes every current source image. It checks the raw response, validated result, source fingerprint, required fields, identity tag, and declared training-caption order. The manual review table links each source, raw response, and validated result.

Run the caption regression tests:

```sh
python3 -m unittest discover -s tests -v
```

The current test set covers fenced JSON, truncated group output, ordered captions, multi-person isolation, declared-class mismatch, and recovery from saved raw output.

The Ad2184 example uses the local Qwen3.5-9B Hugging Face weights. It uses the compatible processor files from the local Qwen3.8-27B snapshot. Scene Factory keeps these paths separate and does not copy or change either model cache. The command automatically restarts with the configured vision Python environment.

The caption processor limits each source image to 1,048,576 processed pixels. This keeps face, clothing, pose, framing, and environment detail while avoiding unnecessary vision tokens from the full source resolution. The source files are not resized or changed.

The command prints these progress events:

- Processor loading
- Model loading
- Current image number and path
- Final result count and pipeline state

Each completed result is saved immediately. A stopped run can continue without repeating completed images. The unmodified model response is stored under `build/captions/raw/`. The validated record is stored under `build/captions/results/`.

At restart, Scene Factory first tries to recover missing results from saved raw responses. One invalid asset does not stop later assets. Per-asset errors are stored under `build/captions/failures/` for correction and another run.

If a complex image reaches the normal output-token limit before it closes the JSON object, Scene Factory retries that asset with the configured larger retry limit. The fallback JSON reader accepts only a complete top-level caption record. It does not mistake a nested subject object for the full result.

For a character-identity task, a caption that lists more than one visible person is not training-ready. Scene Factory adds a subject-isolation risk and sets `quality.training_usable` to `false`. A later face-mask or subject-mask review can isolate the correct person before approval.

The first verified local test created one structured caption. The remaining captions still require execution and human review.

Caption results can also come from another application:

```sh
./scene_factory.py caption-import ./examples/ad2184 /path/to/caption-results.json
```

Imported results must match the asset ID and source fingerprint.

## Human caption review

Approve one result for training:

```sh
./scene_factory.py caption-review ./examples/ad2184 ASSET_ID --decision approved --split train
```

Approve a separate validation result:

```sh
./scene_factory.py caption-review ./examples/ad2184 ASSET_ID --decision approved --split validation
```

Reject a result:

```sh
./scene_factory.py caption-review ./examples/ad2184 ASSET_ID --decision rejected --split reject --note "wrong identity"
```

## Build concept datasets

```sh
./scene_factory.py dataset-build ./examples/ad2184
```

The dataset builder:

- Includes only approved captions.
- Keeps the training and validation splits separate.
- Checks exact fingerprint leakage across splits.
- Enforces the concept minimum training-image count.
- Stores the source path, fingerprint, caption, and caption-result evidence.

## Character sheets

Each foreground character receives planned tasks for:

- Front face
- Left and right three-quarter face
- Left and right profile
- Front and back full body
- Expression sheet
- Wardrobe sheet

Character-sheet tasks stay blocked until approved captions, a ready identity concept, an image adapter, and human review are available.

## Storyboards

Each shot formation becomes one storyboard task with up to four cheap candidates. A storyboard is a low-cost approval frame for composition, blocking, lens, action readability, subject binding, anatomy, prop geometry, and continuity. It is not the final production key frame.

Character attributes must remain inside named subject contracts. Do not concatenate the wardrobe and equipment of multiple cast members into one attribute list. Props must use named geometry contracts, and complex poses should declare subject positions, anatomy, and prop state in the formation blocking contract.

No video workflow is compiled until one storyboard candidate is explicitly approved with zero open issues. The first animation is a short motion proof. Longer clips are compiled only for motion proofs explicitly approved for extension.

## Scripted clips

Each approved formation becomes one clip task with:

- Approved start key frame
- Character action
- Camera path and lens behavior
- Motion-reference ID
- Identity locks
- Negative motion
- Model-valid frame count
- Head and tail handles
- Continuity review fields

## Extended sequences

Clips are grouped by scene. Extension can start only from approved boundary frames. It must preserve identity, wardrobe, prop state, environment geometry, screen direction, and motion velocity.

## Read process status

```sh
./scene_factory.py pipeline-status ./examples/ad2184
```

The status reports each stage as pending, ready, in progress, complete, blocked, or rejected.

## Current Ad2184 state

- Source ingestion: complete for 45 images.
- Structured captions: complete for 45 of 45 images.
- Caption evidence: 45 raw model responses and 45 validated JSON results.
- Caption audit: 45 valid and 0 invalid.
- Training readiness before human review: 13 model-marked usable and 32 that need isolation or rejection.
- Caption review: blocked at 0 of 45.
- Concept datasets: blocked.
- Training and all media-generation stages: blocked by their declared adapters and reviews.
- Local caption model: Qwen3.5-9B with the compatible local Qwen3.8 processor.

## Related pages

- [Architecture](03_ARCHITECTURE.md)
- [LoRA system](04_LORA_SYSTEM.md)
- [Status and roadmap](07_STATUS_AND_ROADMAP.md)
- [Caption schema](../schemas/caption.schema.json)
- [Pipeline schema](../schemas/pipeline.schema.json)

[S1]: ../pipeline.py "Production pipeline implementation"
[S2]: ../schemas/pipeline.schema.json "Pipeline state contract"
[S3]: ../schemas/caption.schema.json "Structured caption contract"
