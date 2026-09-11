# Gage TTS manual handoff

Start with [`PLAN.md`](PLAN.md). It documents the current results, reference
profiles, audio-cleanup specifications, ComfyUI workflow, paragraph iteration,
master assembly, validation, and requirements for future fine-tuning.

Quick start:

```sh
cd /Users/voxels/SceneFactory/Voice
PROFILE=max_data ./scripts/stage_reference.sh
PROFILE=max_data ./scripts/prepare_workflows.sh
./scripts/submit_all.sh
# Wait for ComfyUI's queue to become empty.
./scripts/collect_outputs.sh
# Listen to and approve renders/paragraph_01.flac through paragraph_06.flac.
./scripts/assemble_final.sh
./scripts/validate_final.sh
```

`max_data` reproduces the voice profile closest to the preferred last pass.
`short_clean` prioritizes microphone clarity. Do not call a render final until
all six paragraphs have been reviewed by listening.
