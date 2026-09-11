# Multimodal identity model

## Evidence is modality-specific

V4 records every source with a hash and keeps raw evidence separate from derived
training material. This prevents a web thumbnail, a synthetic voice performance,
or a textured scan from silently becoming equivalent to an approved photograph.

| Evidence | Characteristics it may support | Default production use |
| --- | --- | --- |
| Direct images | face, hair, skin appearance, proportions, expressions | visual identity training and validation after review |
| Video | movement, posture, expression dynamics, speaking motion | motion and temporal conditioning; reviewed frames may enter visual training |
| Webarchives | provenance, appearance history, embedded image candidates | extract locally, deduplicate, then review before training |
| Audio + transcript | voiceprint, prosody, pacing, pronunciation, performance timing | voice conditioning and final synchronized performance |
| Head USDZ | craniofacial proportions and view consistency | geometry conditioning and turntable/reference rendering |
| Body/model-fit USDZ | stature, silhouette, limb and torso proportions | geometry/pose conditioning and body-consistency checks |
| Textured USDZ | geometry plus appearance cross-checks | secondary appearance evidence; never silently flattened into LoRA images |

## Authority and fusion

The example's `identity.json` defines an ordered authority list for each stable
characteristic. Geometry evidence wins for shape when it is a direct capture;
reviewed high-resolution photography wins for surface appearance; audio wins for
voice; and video wins for movement. Lower-authority evidence fills gaps but may
not override a contradiction without a recorded review decision.

Each modality remains a separate conditioning channel in production. The final
identity is fused at planning/inference time instead of concatenating incompatible
files into one visual training set.

`conditioning_manifest.json` is the downstream handoff contract. It keeps visual
training, webarchive derivatives, sampled motion, native USDZ geometry, extracted
scan textures, generated voice, and the TTS transcript in explicit channels.
`review_manifest.json` persists approvals and rejections by content-stable asset
ID, while `selection_manifest.json` records quality filtering, duplicate clusters,
and the leakage-safe train/validation assignment.

Generated audio is decoded into a normalized mono analysis stream and checked for
duration, peak and RMS level, clipping, silence, DC offset, and transcript-relative
speaking pace. These diagnostics do not replace listening or transcript review;
both remain explicit approval gates before voice conditioning or export.

## Review gates

Review gates are disabled in the default `automatic` mode. They become blocking
only when `fine_tuning` mode is explicitly requested. Automatic mode still records
quality diagnostics, deduplication, provenance, and optional review data, but it
completes and exports without human decisions or absent optional modalities.

- Confirm permission and identity ownership before training or cloning.
- Confirm every source depicts the intended adult subject.
- Deduplicate near-identical images before train/validation splitting.
- Review webarchive extractions; icons, ads, and unrelated people are expected.
- Verify USDZ coordinate scale and that head/body scans belong to the same subject.
- Verify the supplied audio matches `voice/tts_text.txt`; synthetic audio is
  authoritative for the requested performance only, not proof of biography.
- Hold out front, three-quarter, profile, full-body, motion, and speech samples for
  independent validation.
