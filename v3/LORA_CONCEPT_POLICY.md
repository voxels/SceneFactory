# Repeating Concept LoRA Policy

> Documentation entry point: [Scene Factory Documentation](docs/README.md). Presented LoRA summary: [LoRA System](docs/04_LORA_SYSTEM.md).

## Decision rule

Use the lightest conditioning method that gives stable results.

1. Start with prompt conditioning.
2. Add approved image references when the concept has a fixed visible design.
3. Train a LoRA only when the concept repeats and prompt plus references do not keep it stable.

This rule prevents a large LoRA stack from fighting the identity model.

## Good LoRA candidates

- A foreground character who appears in many scenes.
- A distinct background population that must keep one design.
- A unique location that appears across many camera angles.
- A unique wardrobe or prop that appears across many shots.
- One controlled style that the base model cannot keep with prompts.

## Poor LoRA candidates

- Age, mood, color, lighting, lens, or camera movement.
- A generic object or location that the base model already knows.
- A concept that appears in only one shot.
- A concept with too few independent source images.
- A concept that is mixed with another identity in most sources.

## Dataset isolation

- Each source has a provenance record and a review state.
- Training and validation sources are separate.
- Near-duplicate images stay in one split only.
- The concept must be visible enough to label.
- Captions use one stable trigger token and one stable class token.
- Captions describe visible variable attributes. They do not attach a background, pose, or wardrobe to the identity when that item must remain variable.
- Generated sources are off by default. If they are enabled, they need a separate identity and provenance review.

## Character identity policy

- Keep identity, face shape, apparent age, and body build stable.
- Keep expression, pose, camera, light, and background variable.
- Put a repeating fixed wardrobe in the character LoRA only if it must never change.
- Use a separate wardrobe concept when the same character needs different approved wardrobe sets.
- Do not use detected age as a verified personal fact.

## LoRA stack policy

- The project sets a maximum active LoRA count.
- Prompt-only and reference-only concepts do not consume a LoRA slot.
- Each LoRA has a minimum, default, and maximum weight.
- Each pair of active LoRAs needs an allowed-combination record.
- Validate each LoRA alone before combination tests.
- Validate every allowed combination with a fixed prompt set and weight sweep.
- Reject a combination that changes identity, age, anatomy, wardrobe, environment geometry, or trigger isolation.

## Model profile policy

Training settings belong to a model and concept profile. Do not use identity settings for environment, style, prop, or wardrobe training without a calibration run. The included FLUX.2 Klein identity profile is the current Ad2184 baseline.

## Promotion states

```text
planned -> training -> validation -> ready
                              -> rejected
```

Only a `ready` LoRA can make a key-frame task ready. A model file on disk is not proof that the LoRA passed validation.
