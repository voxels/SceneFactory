# 5. Ad2184 Example

## Summary

Ad2184 is the first complete Scene Factory example. It maps the existing source hierarchy into seven scenes, seven shots, 21 shot formations, 21 key-frame tasks, 21 video tasks, and one 60-second assembly plan. [S1][S2][S3]

## Source records

| Record | Purpose |
|---|---|
| [project.json][S1] | Project format, model selection, characters, environments, motion reference, and hierarchy mapping |
| [concepts.json][S2] | k0l3k4 identity LoRA and group conditioning strategies |
| [script.json][S3] | Seven scenes, actions, audio, continuity, exclusions, and three formations per shot |

## Indexed evidence

The independent application contains the definitions but does not copy production media. The example defaults to the existing external Ad2184 folder. Its asset index records: [S4]

- 45 external `k0l3k4` foreground source photos.
- 0 masses reference files.
- 0 enforcer reference files.
- 0 environment reference files.
- A present external Apple 1984 motion-reference file.
- 0 approved LoRA training files.
- 0 separate LoRA validation files.

## Compiled evidence

The current generation manifest records: [S5]

- 7 scenes.
- 7 shots.
- 1 training task.
- 21 key-frame tasks.
- 21 video tasks.
- A 60-second assembly timeline.
- 0 ready key-frame tasks because required identity or reference conditioning is not ready.

## Shot formation map

| Shot | Duration | Formation 1 | Formation 2 | Formation 3 | LTX frames per formation |
|---:|---:|---|---|---|---:|
| 1 | 10 s | low tracking | lead worker | CRT detail | 81 |
| 2 | 10 s | corridor wide | frontal chase | hammer close | 81 |
| 3 | 10 s | hall high wide | aisle medium | worker and screen close | 81 |
| 4 | 7 s | rear charge | frontal run | face and guards | 57 |
| 5 | 7 s | wind-up orbit | release medium | trajectory close | 57 |
| 6 | 4 s | impact close | blast pullback | crowd reaction | 33 |
| 7 | 12 s | awakened faces | hall tilt | graphic slate | 97 |

The compiler selects frame counts that satisfy the configured `mod8_plus1` rule and records a shorter edit trim duration. [S5][S6]

## Current blockers by shot

| Shot | Blockers |
|---:|---|
| 1 | Missing masses references |
| 2 | k0l3k4 LoRA planned; missing enforcer references |
| 3 | Missing masses references |
| 4 | k0l3k4 LoRA planned; missing masses and enforcer references |
| 5 | k0l3k4 LoRA planned; missing masses references |
| 6 | Missing masses references |
| 7 | Missing masses references |

## Important interpretation

The packaged Ad2184 definition proves the compiler structure and timeline without copying the production source material into the application. It does not prove FLUX image fidelity, LoRA identity quality, LTX motion quality, audio quality, or final graphics. [S7]

## Related pages

- [Quick start](02_QUICK_START.md)
- [Operator manual](06_OPERATOR_MANUAL.md)
- [Status and roadmap](07_STATUS_AND_ROADMAP.md)

[S1]: ../examples/ad2184/project.json "Ad2184 project definition"
[S2]: ../examples/ad2184/concepts.json "Ad2184 repeating concepts"
[S3]: ../examples/ad2184/script.json "Ad2184 scene and formation script"
[S4]: ../examples/ad2184/build/asset_index.json "Ad2184 indexed evidence"
[S5]: ../examples/ad2184/build/generation_manifest.json "Ad2184 compiled evidence"
[S6]: ../scene_factory.py#L287 "Frame calculation"
[S7]: 07_STATUS_AND_ROADMAP.md "Verified boundary"
