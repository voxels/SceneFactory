# 4. LoRA System

## Summary

Scene Factory treats a LoRA as one possible strategy for a repeating visual concept. It does not require a LoRA for every character, group, environment, prop, wardrobe, or style. [S1][S2]

## Conditioning strategies

| Strategy | Use | Consumes a LoRA slot | Readiness rule |
|---|---|---:|---|
| `prompt` | The base model already understands the concept | No | Valid prompt definition |
| `reference` | Approved images must control the design | No | Reference media exists |
| `prompt_reference` | Prompt and approved references work together | No | Reference media exists |
| `lora` | A trained repeating concept is necessary | Yes | LoRA state is `ready` |

These strategy names are defined in the concept schema. [S1]

## Concept types

- `character_identity`
- `background_group`
- `environment`
- `wardrobe`
- `prop`
- `style` [S1]

## Training source rules

- Training and validation globs are separate.
- Near duplicates must not cross the two sets.
- Generated sources are off by default.
- One stable trigger token and class token identify the concept.
- Captions describe visible variables without binding unwanted backgrounds or poses to identity.
- A training profile belongs to one model family and concept type. [S2][S3]

## Promotion states

```text
planned -> training -> validation -> ready
                              -> rejected
```

A model file on disk is not enough. The registry status must show that validation passed. [S1][S2]

## Stack rules

- The project defines the maximum active LoRA count.
- Only `lora` strategies consume slots.
- Every LoRA has a minimum, default, and maximum weight.
- Blocked combinations fail validation.
- When combination validation is required, every active LoRA pair must be allowed.
- Each allowed combination needs a fixed prompt set and weight sweep. [S1][S4]

## Included FLUX.2 Klein identity baseline

The included profile uses the official Diffusers FLUX.2 Klein trainer, FLUX.2 Klein base 4B for training, and the distilled model for inference. It defines the current 512-pixel, rank-16, alpha-16, 500-step Ad2184 baseline and a validation weight sweep. [S3]

This profile is a baseline. It is not a universal optimum. Environment, style, prop, and wardrobe concepts need separate calibration.

## Ad2184 decision

`k0l3k4_identity` uses the `lora` strategy and is still `planned`. The masses and enforcers use `prompt_reference`. They do not consume LoRA slots, but they need reference media before their tasks are ready. [S5][S6]

## Related pages

- [Architecture](03_ARCHITECTURE.md)
- [Ad2184 example](05_AD2184_EXAMPLE.md)
- [Full policy source](../LORA_CONCEPT_POLICY.md)

[S1]: ../schemas/concepts.schema.json "Concept schema"
[S2]: ../LORA_CONCEPT_POLICY.md "Detailed LoRA policy"
[S3]: ../profiles/flux2_klein_identity_lora.json "FLUX.2 Klein identity baseline"
[S4]: ../scene_factory.py#L145 "Stack validation implementation"
[S5]: ../examples/ad2184/concepts.json "Ad2184 concept decisions"
[S6]: ../examples/ad2184/build/generation_manifest.json "Compiled strategy and readiness evidence"
