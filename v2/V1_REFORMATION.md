# Scene Factory v1 reformation

V1 treats visual generation as an approval-gated production process rather than a Cartesian product of seeds and clip lengths.

## What changed

- Character attributes remain inside named `subjects` contracts. They are never flattened into a shared prompt list.
- Props have named geometry contracts. The Ad2184 hammer is one handle with one head at the striking end and a bare grip end.
- Formations may declare structured blocking for subject positions, anatomy, and prop state.
- Forbidden attributes become subject-bound negatives such as `helmet on SUBJECT k0l3k4`.
- Four low-cost storyboard candidates may be generated, but video graphs are not compiled until one candidate is explicitly approved with zero open issues.
- The first video is a three-second motion proof. A five-second extension is compiled only when that proof is explicitly approved for extension.

## Enforced production controls

- K and enforcers compile to disjoint conditioning scopes. Only K's layer may load the K identity LoRA; K's scope forbids helmets, visors, and riot armor, while the enforcer scope explicitly excludes K identity, face, hair, and wardrobe.
- Production pose tracks must declare their shot ID, use `single_shot_no_cross_cut`, contain timestamped samples inside the authoritative reference range, and be marked operational. A cross-cut slice is a hard blocker rather than a fallback to unconstrained image-to-video.
- The hammer is never generated inside K's identity layer. Held and released hammer layers use hammer-only conditioning, a rigid-body track, and the locked geometry `one straight handle + one crosswise head + bare grip end`. The held layer additionally requires grip alignment with K.

## Review sequence

1. Compile the project and image workflows.
2. Generate and review storyboard candidates.
3. Copy `review_templates/storyboard_selections.json` to `build/review/storyboard_selections.json` and record one approved candidate per accepted formation.
4. Rebuild workflows. Only the approved candidates receive motion-proof graphs.
5. Review the proofs and copy `review_templates/motion_proof_reviews.json` to `build/review/motion_proof_reviews.json`.
6. Mark `extend: true` only for clips that editorially need extension, then rebuild workflows.

An item with any open issue code is not approved. A different seed is not a substitute for repairing a systemic compiler, asset, or blocking error.
