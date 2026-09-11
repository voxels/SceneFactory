# 7. Status and Roadmap

## Summary

The project-definition and compilation layer works. The execution layer does not yet exist. This page separates verified results, warnings, blockers, and future work.

## Verified usable results

| Result | Verification |
|---|---|
| Python program parses | Python compilation test passed |
| New project creation | A temporary project was created, validated, indexed, compiled, and read by `status` |
| Ad2184 validation | Seven scenes and 60 seconds passed |
| Independent packaging | The application lives outside the source hierarchy and uses an overridable default pointer to the existing Ad2184 folder |
| Ad2184 compilation | 21 key-frame and 21 video tasks were made on a 60-second timeline |
| Gate correction | Missing `prompt_reference` media now blocks related tasks |
| Full process planning | Source, caption, character-sheet, storyboard, clip, sequence, and state records are generated |
| Caption lifecycle | Import, fingerprint validation, review, split, leakage check, and dataset minimum gates passed controlled tests |

Evidence is available in the compiler source and generated Ad2184 files. [S1][S2][S3]

## Current warnings

- The JSON schemas document the file contracts, but the program uses its own semantic validator. It does not currently run a full Draft 2020-12 schema engine.
- The `ad2184_v1` adapter uses fixed duration mapping for the current seven-shot source shape.
- Generated build files can become stale after source edits. Run `index` and `compile` again after changes.

## Current blockers

### Ad2184 content blockers

- The external source folder has 45 `k0l3k4` photos but no approved LoRA training set.
- No separate `k0l3k4` validation set.
- No masses reference media.
- No enforcer reference media.
- No environment reference media. The external motion-reference video is present.
- The k0l3k4 identity LoRA is `planned`, not `ready`. [S2][S3]

### Model execution blockers

- No generic ComfyUI key-frame adapter.
- The local Qwen3.5-9B vision caption adapter completed 45 of 45 structured captions. All 45 raw responses and validated results are present. Human review is pending.
- No generic FLUX.2 LoRA training adapter.
- No LTX 2.5 video adapter.
- No ComfyUI job monitor.
- No approval interface.
- No final assembly executor.
- The local LTX 2.5 installation also needs compatible nodes, weights, and enough storage.

## Next implementation order

1. Define a stable adapter interface from one compiled task to one ComfyUI API workflow.
2. Add a FLUX.2 Klein key-frame adapter.
3. Add output records and human approval states.
4. Add the FLUX.2 Klein LoRA training adapter.
5. Add fixed LoRA validation grids and promotion records.
6. Repair and validate the local LTX 2.5 installation.
7. Add the LTX image-to-video adapter.
8. Add job monitoring, retry rules, and retained logs.
9. Add final assembly and post-production records.
10. Add a non-technical local interface over the same project files.

## Acceptance boundary

Do not describe Scene Factory as a media-generation app until at least one compiled task completes through ComfyUI and produces a reviewed output. Current success is compilation success only.

## Related pages

- [Product summary](01_PRODUCT_SUMMARY.md)
- [Architecture](03_ARCHITECTURE.md)
- [Ad2184 example](05_AD2184_EXAMPLE.md)

[S1]: ../scene_factory.py "Current compiler source"
[S2]: ../examples/ad2184/build/asset_index.json "Current indexed evidence"
[S3]: ../examples/ad2184/build/generation_manifest.json "Current compiled evidence"
