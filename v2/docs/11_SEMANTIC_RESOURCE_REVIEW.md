# Ad2184 Semantic Resource Review Manual

This manual is the authoritative content specification for the Ad2184 reconstruction pipeline. It records the decisions made during `AD2184-SEMANTIC-REVIEW-001` and defines how each resource type must be derived, reviewed, updated, and invalidated.

The production is a controlled reconstruction of the declared reference video. It is not a text-prompt reinterpretation. Written descriptions exist to preserve and validate the reference semantics, not to replace them.

## 1. Governing rules

- Automatically extract representative frames and action beats from the reference video.
- Automatically derive visual contracts from those frames.
- Do not require frame-by-frame approval before deriving contracts.
- Written contracts and reference evidence must agree. An unresolved disagreement blocks generation.
- Produce a reference-faithful master track.
- Produce automatic alternate-POV coverage within the existing narrative.
- Generate approximately three times the final required duration for post-production selection.
- Preserve story-beat order and relative rhythm. Individual cut points may vary approximately.
- Strip and ignore source audio. Generate no audio.
- The user is the sole authority who may approve material for the post-production pool.

## 2. Source-authority matrix

Every production attribute must name its authority. Never merge attributes from different authorities into an undifferentiated prompt.

| Resource or attribute | Authority | Required treatment |
|---|---|---|
| K face | K source material | Preserve through identity conditioning. Never inherit the reference performer's face. |
| K body identity | K source material | Retain K's proportions and physical identity. |
| K hair | K source material | Preserve K's approved hair rather than copying the reference performer. |
| K wardrobe | Reference video | Reconstruct the reference wardrobe's design, colors, and materials; tailor it naturally to K. |
| K pose and movement | Reference video | Skeleton-track the performer and retarget the motion to K. |
| Workers | Reference video | Derive complete visual design and group motion from extracted frames/video. |
| Enforcers | Reference video | Derive complete visual design and coordinated group motion from extracted frames/video. |
| Hammer | Reference video | Derive topology, dimensions, materials, grip, state, flight, and impact. |
| Environments | Reference video | Reconstruct architecture, lighting, landmarks, occupancy, and damage state. |
| Camera and framing | Reference video | Match master-track camera position, movement, lens character, composition, and screen direction. |
| Story beats | Reference video | Preserve order, causality, and relative rhythm. |
| Final speaker overlay | Post-production MP4 | Provide a tracked green insert; do not generate the speaker image. |
| Final title and logo | Post-production | Do not generate exact text or logos. |
| Audio | None | Ignore and strip all audio. |

### Conflict rule

If project text differs from extracted reference evidence, do not silently choose one. Record the disagreement and block affected generation until the written contract is regenerated from the reference or a deliberate deviation is documented.

## 3. Required processing order

1. Resolve and fingerprint the source video.
2. Probe video duration, dimensions, frame rate, and streams.
3. Ignore its audio streams.
4. Map the existing narrative shots to approximate source ranges.
5. Extract representative start, action, and end frames automatically.
6. Tag frames by visible resource: K performer, workers, enforcers, hammer, environment, screen, and occluders.
7. Derive visual contracts with source-frame and timestamp provenance.
8. Compare derived contracts with `project.json` and `script.json`.
9. Produce tracking data.
10. Compile master and alternate-POV coverage.
11. Generate and review stills.
12. Generate short motion proofs only for accepted stills.
13. Extend only useful motion proofs.
14. Admit clips to the post-production pool only through explicit user approval.

## 4. Global project review

Primary resources:

- [Ad2184 project](../examples/ad2184/project.json)
- [Project schema](../schemas/project.schema.json)
- [Reference reconstruction plan](12_V1_IMPLEMENTATION_PLAN.md)

### Checklist

- [ ] The declared reference video resolves to an existing file.
- [ ] Reference reconstruction is enabled.
- [ ] Coverage multiplier is `3.0`.
- [ ] Audio policy is `strip_and_ignore`.
- [ ] Approval authority is `user_only`.
- [ ] Source-authority rules match the matrix in this manual.
- [ ] Master and alternate coverage are distinct plan types.
- [ ] Final graphics remain post-only.
- [ ] No global rule assigns enforcer, worker, or prop attributes to K.

### Review record

```markdown
### Global project review

- Reference video:
- Source fingerprint:
- Intended final duration:
- Planned coverage duration:
- Master duration:
- Alternate-POV duration:
- Audio policy:
- Approval authority:
- Contract conflicts:
- Decision: pass / blocked
```

## 5. Reference-video review

Existing resources:

- Declaration: `motion_references[apple_1984_motion]` in [project.json](../examples/ad2184/project.json)
- External source currently declared as `choreography_reference/apple_1984_ridley_scott_reference.mp4`
- [Motion-source instructions](../examples/ad2184/empty_sources/motion/DROP_MOTION_REFERENCE_HERE.md)

The label `motion_reference` is historically too narrow. This video is the reconstruction authority for design, environment, camera, action, and group motion in addition to individual motion.

### Checklist

- [ ] Video path resolves.
- [ ] SHA-256 is recorded.
- [ ] Duration, frame rate, and dimensions are recorded.
- [ ] Audio streams are identified but never extracted into production assets.
- [ ] Representative frames are extracted deterministically.
- [ ] Frame records contain timestamps and shot IDs.
- [ ] Frames are tagged by visible resource.
- [ ] Source ranges remain in narrative order.
- [ ] Relative story rhythm remains stable.

### Review record

```markdown
### Reference-video review

- Path:
- SHA-256:
- Duration:
- Frame rate:
- Dimensions:
- Audio ignored: yes / no
- Shot-range mapping:
- Extracted-frame manifest:
- Missing resource views:
- Decision: pass / blocked
```

## 6. K character review

Existing resources:

- [K character record](../examples/ad2184/characters/k0l3k4.character.json)
- K definition in [project.json](../examples/ad2184/project.json)
- [K base audition sheet](../examples/ad2184/assets/characters/k0l3k4/candidates/audition_sheet_01.png)
- [K production-direction audition sheet](../examples/ad2184/assets/characters/k0l3k4/candidates/audition_sheet_native_hawaiian_direction_01.png)
- [Isolation configuration](../examples/ad2184/isolation.json)

### Required semantics

- K's face, body identity, and hair come from K's source material.
- K's wardrobe comes from the reference video.
- K's pose and movement come from the reference performer through skeleton tracking.
- Motion is retargeted to K's proportions while preserving timing, balance, joint intent, and screen-space trajectory.
- K is rendered separately from enforcers whenever technically possible.
- The held hammer remains part of K's layer.
- K's layer requires a clean alpha or matte.
- Lighting, lens behavior, grain, and motion blur must match the reconstructed plate.

### Checklist

- [ ] Face conditioning uses only K identity sources.
- [ ] Body identity uses K rather than the reference performer.
- [ ] Hair uses K rather than the reference performer.
- [ ] Wardrobe contract cites reference frames and timestamps.
- [ ] Skeleton track cites source frames and timestamps.
- [ ] Retarget record states K's body proportions.
- [ ] Exactly two connected arms and hands remain visible where framing requires them.
- [ ] K has no worker or enforcer equipment unless a deliberate deviation is documented.
- [ ] Held-hammer contact remains coherent.
- [ ] Foreground matte is clean and suitable for compositing.

### Review record

```markdown
### K review

- Identity sources:
- Hair sources:
- Wardrobe reference frames:
- Skeleton track:
- Retarget profile:
- Held-prop state:
- Matte quality:
- Reference-plate match:
- Open issues:
- Decision: pass / blocked
```

## 7. Worker and enforcer review

Existing resources:

- Worker and enforcer definitions in [project.json](../examples/ad2184/project.json)
- [Worker audition sheet](../examples/ad2184/assets/characters/worker_male_01/candidates/audition_sheet_01.png)
- [Worker reference placeholder](../examples/ad2184/empty_sources/dystopian_masses/ADD_REFERENCES.md)
- [Enforcer reference placeholder](../examples/ad2184/empty_sources/enforcers/ADD_REFERENCES.md)

The reference video, not the current text or audition sheets, is authoritative. Existing descriptions and images are provisional until compared with automatically extracted reference frames.

### Required semantics

- Derive complete worker design from the reference.
- Derive complete enforcer design from the reference.
- Guide worker and enforcer group motion directly from the reference video.
- Do not skeleton-track every background figure individually.
- Render enforcers together as one coordinated group layer.
- Keep the enforcer group separate from K's layer.

### Checklist

- [ ] Worker contract cites reference evidence.
- [ ] Enforcer contract cites reference evidence.
- [ ] Existing text has been reconciled with the evidence.
- [ ] Group count and spacing match the relevant master shot.
- [ ] Group motion uses direct reference guidance.
- [ ] Enforcers remain one coordinated render layer.
- [ ] K identity, hair, wardrobe, and anatomy do not leak into either group.
- [ ] Worker/enforcer attributes do not leak onto K.

### Review record

```markdown
### Group review: workers / enforcers

- Reference frames:
- Derived design contract:
- Group-motion source range:
- Count and spacing:
- Layer ID:
- Conflicts with old text/assets:
- Open issues:
- Decision: pass / blocked
```

## 8. Hammer review

Existing resources:

- Hammer definition in [project.json](../examples/ad2184/project.json)
- [Hammer resource folder](../examples/ad2184/assets/props/hammer/README.md)
- Hammer-bearing shots in [script.json](../examples/ad2184/script.json)

The current written hammer geometry is provisional. Replace it wherever it disagrees with the reference.

### Required semantics

- Derive topology, dimensions, proportions, materials, and colors from the reference.
- Track grip and rigid-body motion from the reference.
- Keep the hammer in K's layer while held.
- Transfer it to a separate prop layer at release.
- Preserve release, flight, and impact timing approximately while maintaining beat order and rhythm.
- Prevent duplicates and untracked topology changes.

### Checklist

- [ ] Representative hammer frames cover held, release, flight, and impact states.
- [ ] Derived geometry cites those frames.
- [ ] Rigid-body track contains position, rotation, and scale over time.
- [ ] Ownership-transfer frame is recorded.
- [ ] Held state belongs to K's layer.
- [ ] Released state belongs to the hammer layer.
- [ ] No duplicate remains with K after release.
- [ ] Impact agrees with the screen-destruction beat.

### State record

| Shot | Entry state | Exit state | Layer owner | Tracking source | Pass |
|---|---|---|---|---|---|
| | | | | | [ ] |

## 9. Environment and camera review

Existing resources:

- Environment definitions in [project.json](../examples/ad2184/project.json)
- [Processing-tunnel placeholder](../examples/ad2184/empty_sources/environments/processing_tunnel/ADD_REFERENCES.md)
- [Pursuit-corridor placeholder](../examples/ad2184/empty_sources/environments/pursuit_corridor/ADD_REFERENCES.md)
- [Ideology-hall placeholder](../examples/ad2184/empty_sources/environments/ideology_hall/ADD_REFERENCES.md)
- Scene and formation records in [script.json](../examples/ad2184/script.json)

### Required semantics

- Reconstruct architecture, lighting, landmarks, occupancy, and damage state from reference frames.
- Match master camera position, framing, movement, lens character, and screen direction.
- Preserve environment continuity across connected shots.
- Alternate POVs may change viewpoint but cannot introduce a different location, event, or narrative outcome.

### Checklist

- [ ] Each environment contract cites reference frames.
- [ ] Architecture and landmarks remain consistent.
- [ ] Lighting direction and cinematic character match.
- [ ] Master camera path cites the reference range.
- [ ] Screen direction remains stable.
- [ ] Alternate POV remains inside the established environment and narrative.
- [ ] Damage state advances only at the reference story beat.

## 10. Master and alternate-POV review

Primary resource: [script.json](../examples/ad2184/script.json)

### Master track

- One master path reconstructs the reference narrative.
- Composition, action, design, lighting, and cinematic character should match closely.
- Pixel-level and frame-perfect reproduction are not required.
- Cut points may shift approximately.
- Story-beat order and relative rhythm are invariant.

### Alternate POV coverage

- Alternatives are creative coverage, not repair material.
- They may be proposed and generated automatically.
- They must remain within the existing narrative.
- Their usefulness and narrative fit are decided in post-production.
- They do not require pre-generation shot-by-shot approval.

### Duration budget

- Intended final duration: approximately 60 seconds.
- Total planned source coverage: approximately 180 seconds.
- Master coverage: approximately 60 seconds.
- Alternate-POV coverage: approximately 120 seconds.

### Checklist

- [ ] Every source shot has one master reconstruction task.
- [ ] Master tasks remain in source narrative order.
- [ ] Relative rhythm is preserved.
- [ ] Alternate tasks are marked optional.
- [ ] Alternate tasks introduce no new causal event or outcome.
- [ ] Planned coverage totals approximately three times final duration.
- [ ] Master and alternate duration budgets are reported separately.

## 11. Layer and compositing review

Required layer types, when visible:

1. Environment plate
2. Workers group
3. Enforcer group
4. K with held hammer
5. Released hammer
6. Convenience occluder
7. Tracked green insert

### Ownership rules

- K and enforcers are never conditioned as one visual subject.
- Enforcers are rendered together.
- The hammer belongs to K before release and to the hammer layer afterward.
- Convenience occluders may be simplified for compositing.
- Convenience occluders must remain visually invisible as a technique and cannot change apparent blocking.
- No separate contact-shadow or reflection pass is required.

### Checklist

- [ ] Layer manifest lists ownership, z-order, source range, and output path.
- [ ] K and enforcers are separate tasks.
- [ ] Foreground layers have mattes or alpha.
- [ ] Held/released hammer ownership changes exactly once.
- [ ] Occluder purpose and lifetime are explicit.
- [ ] Occluder does not attract attention or alter the story.
- [ ] Foreground lighting, lens, grain, and motion blur match the plate.

## 12. Green insert and post-graphics review

### Required semantics

- Replace the projected voice-over speaker with a chroma-green planar insert.
- Track the plane's perspective, camera movement, and occlusion.
- Keep the insert free of generated imagery and reflections.
- Prevent green spill outside its boundary.
- Shatter the insert with the physical screen at impact.
- The insert does not survive the screen-destruction beat.
- Final title and logo remain post-production assets.

### Checklist

- [ ] Four screen corners are tracked over time.
- [ ] Insert boundaries match the reference screen.
- [ ] Occlusion order is correct.
- [ ] Insert is solid and clean.
- [ ] Insert shatters at the reference impact beat.
- [ ] No insert plane exists after destruction.
- [ ] No prompt requests a final title, exact text, or logo.

## 13. Motion review

### K skeleton proof

- [ ] Opening pose matches the master reference.
- [ ] Retarget preserves K's proportions.
- [ ] Timing and balance match the reference.
- [ ] Joint intent and screen-space trajectory match.
- [ ] Face, hair, and identity remain K's.
- [ ] Wardrobe remains reference-derived.
- [ ] Hands and hammer contact remain coherent.

### Group-motion proof

- [ ] Workers/enforcers use direct reference-video guidance.
- [ ] Group spacing and rhythm match.
- [ ] Background figures do not merge with K.
- [ ] No individual background skeleton workflow is required.

### Hammer proof

- [ ] Held motion follows K and the rigid track.
- [ ] Ownership changes at release.
- [ ] Flight follows the tracked path.
- [ ] Impact aligns with screen destruction.
- [ ] Geometry and count remain stable.

## 14. Audio review

- [ ] Reference audio is ignored.
- [ ] Extracted frames and proxies contain no audio.
- [ ] Generated workflows contain no audio encoder, VAE, latent, sampler output, or muxed audio stream.
- [ ] Rough cuts are visual-only unless post-production audio is supplied separately outside this generation workflow.

Any audio-generation node or model requirement is a blocking defect.

## 15. Approval and invalidation

### Approval

- The user is the sole final approver.
- Automated checks may reject material but cannot grant final approval.
- Storyboard approval does not imply motion approval.
- Motion-proof approval does not automatically imply extension approval.
- Only an explicit user-approved record may add a shot to the post-production pool.

### Invalidation

Invalidate downstream material when any dependency changes:

- source video fingerprint;
- reference-frame extraction or timestamp;
- derived contract;
- K identity source;
- skeleton or rigid-body track;
- selected still;
- layer ownership;
- green-insert track;
- motion proof.

`compile` records runtime fingerprints and a dependency graph in
`build/invalidation_state.json`. A changed or removed node invalidates all transitive
descendants; affected layer states become `invalidated` and artifact approval resets to
pending. A second unchanged compile produces an empty invalidation set. Separately, the
reference disagreement gate hashes its project, script, index, and contract inputs, so a
stale audit blocks generation until `reference-contract-audit` is rerun.

### Approval record

```markdown
### User approval record

- Artifact ID:
- Artifact type: still / motion proof / extension / composite
- Source-frame hashes:
- Contract hashes:
- Tracking hashes:
- Open blocking issues:
- User decision: approved / rejected
- Post-production pool: include / exclude
- Notes:
```

## 16. Consolidated resource-change template

Use this template for content changes. Administrative metadata is optional.

```markdown
## Resource change

- Resource type:
- Resource ID:
- Current semantic:
- Intended semantic:
- Source authority:
- Reference frames/timestamps:
- Written resources to update:
- Tracking resources to update:
- Render layers affected:
- Master shots affected:
- Alternate coverage affected:
- Existing artifacts invalidated:
- Blocking conflicts:
- User decision:
```

## 17. Implementation tracking

Engineering status and acceptance tests are maintained in [V1 Reference Reconstruction Implementation Plan](12_V1_IMPLEMENTATION_PLAN.md). This manual defines what the pipeline must mean; the implementation plan defines how completion is verified.
