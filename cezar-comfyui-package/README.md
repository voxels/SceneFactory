# Cezar ComfyUI Package

Open any of these in ComfyUI (drag-and-drop the JSON onto the canvas).
They are the connected workflows for the Cezar teaser identity and
generation stages. Everything is authored, NOT verified — there is no
GPU on the machine that wrote them. The Mac run is the proof.

## The three workflows

| File | Stage | What it does |
|---|---|---|
| `A_identity_gate_ltx2.json` | Proof run + identity gate | LTX-Video 2.5 + Cezar LoRA, image-to-video from a held-pose reference frame, 25 frames, near-static. Generates identity candidates → PreviewImage → **his eye is the gate**. No candidate ships without passing. |
| `B_sam3_segmentation.json` | Stage B0 (separation) | SceneFactory SAM3 text-prompted segmentation ("person in black shorts") over IMG_1841 / IMG_1842 → per-frame masks → PGM sequence + manifest. Matt and any incidental figures are segmented out per the standing rule. |
| `C_poseheld_take_ltx2.json` | Stage C (per-event takes) | LTX-Video 2.5 + Cezar LoRA, image-to-video from an event held-pose reference, 97 frames, very slow drift. One take per event. Copy the graph per event and swap the reference image + `EVENT_ACTION` + filename prefix. |

## Swappable segmentation pipeline (works today)

`segment_cezar.py` — video in → per-frame Cezar masks out (PGM sequence +
`manifest.json`), byte-identical contract to
`SceneFactorySAM3SaveMaskSequence`, so everything downstream never changes.

```bash
pip install rembg onnxruntime opencv-python   # once
python3 segment_cezar.py --input IMG_1841.MP4 --out masks/run_point
#  --backend rembg  (default, works now; u2net_human_seg ~176 MB auto-downloads)
#  --backend sam3   (flag-flip when the facebook/sam3 checkpoint lands;
#                    same PGM + manifest output; --prompt "person in black shorts")
#  --keep darkest-shorts|largest|left|right   (which detected person is Cezar;
#                    default darkest-shorts = black shorts vs Matt's mustard)
#  --stride 10 --max-frames 30               (quick smoke test)
```

Backend swap rule: run with `rembg` until `sam3.pt` is local, then re-run
with `--backend sam3`. Same output dir layout, same manifest schema —
downstream (mattes, layering, workflow B's saver) is untouched.

## Inputs you point at on the Mac

| Input | Where it lives |
|---|---|
| Trained LoRA | output of the 3080 Ti training run (set the `lora_name` widget) |
| LTX-Video 2.5 checkpoint + VAE | your ComfyUI models dir (set the two loader widgets) |
| Held-pose reference frames | `teaser_kit/events/event_0*/` stills, or `album/stills/` (frame picks are yours) |
| IMG_1841 / IMG_1842 | `album/videos/` (26.27 s run/point, 16.97 s handstands) |
| Training set (37 images) | `cezar-teaser-mac-handoff.zip` (already packed, 38 MB) |
| Identity impression | `teaser_kit/face_id/v3/cezar_id_impression.npy` (eval reference; diagnostic only — your eye adjudicates) |
| Camera motion | `teaser_kit/output/roughcut/camera_path_v2.json` (10 vehicles, 2119 samples, 0–423.6 s; motion in workflow C is prompt-driven and parameterized per assigned vehicle/sample range) |

## Hard rules, encoded

- **No color nodes anywhere.** No grading, LUT, color-space, EQ/saturation/
  contrast/exposure/hue nodes exist in these graphs. Clean structural
  generation only — he grades every frame by hand.
- **No invented motion.** Held poses from references or skeleton takes
  only (C: skeleton slot is `skeleton_take: null` until takes land).
- **Footage is conceptual reference, never literal pixels** — fixed who
  (Cezar, action-identified) + fixed what (action concept) + variable POV
  + parameterized camera motion.
- **Identity arbiter: him alone.** Workflow A exists for one purpose:
  produce candidates for his eye. The 0.45/0.65 gate and R-FaceSim are
  triage, never verdict.
- **No re-cut previews.** These generate NEW scenes and NEW viewpoints;
  nothing here re-cuts existing footage.

## Node-name grounding

- `SceneFactorySAM3SegmentVideo` / `SceneFactorySAM3SaveMaskSequence`:
  verified against `SceneFactory/comfy_nodes/scene_factory_sam3/__init__.py`
  (exact INPUT_TYPES, incl. the `backend` widget — set to `transformers`
  for Apple Silicon MPS, `native` for CUDA).
- LTX nodes (`LTXVModelLoader`, `CLIPTextEncodeLTXV`,
  `EmptyLTXVLatentVideo`, `LTXVImgToVideoLatent`, `LTXVScheduler`,
  `LTXVConditioning`, `VAELoader`): the official ComfyUI-LTXVideo example
  node family — the same family his stack runs. If the installed pack
  names differ, remap on the Mac side and tell the agent so the package
  gets corrected.
- `VHS_LoadVideo` / `VHS_VideoCombine`: VideoHelperSuite (optional;
  swap for whatever loader/saver his install carries).

## Run order

**Fastest path on your machine:** you already have a configured official
workflow at
`SceneFactory/v1/examples/ad2184/build/proofs/ltx_motion_control/configured_official_workflow.ui.json`
(core ComfyUI on 127.0.0.1:8188; LTX Desktop is only a weight source).
Clone that, add the Cezar LoRA + the fixed who/what prompts, and use
workflows A/C here as the reference graphs. The packaged JSONs stand
alone if you prefer a clean build.

1. **Segmentation** — `python3 segment_cezar.py --input IMG_1841.MP4 --out masks/run_point`
   (rembg backend today; `--backend sam3` the moment the checkpoint lands —
   same PGM + manifest either way). Workflow **B** JSON is the ComfyUI-native
   tracked-video route for the same stage once SAM3 is local.
2. Train the LoRA on the 3080 Ti (37-image set, `lora_training_set_manifest.json`).
3. **A** — the proof run. Generate candidates per event. He judges:
   is this Cezar's face, same man across frames? Anything failing is
   discarded, not fixed in post.
4. **C** — per-event takes, only after the gate passes on A.
5. Per-take manifest (event, beat/phrase, camera sample range, LoRA
   version, skeleton_take null). Cut to the 27 vocal-phrase onsets;
   3 s min / 12 s max shots, ≥25° angle change. Layering via SAM3
   holdout/matte masks, depth-correct, 9:16 assembly, no color treatment.

## Open rulings that still sit with him

- k_pursuit 0.8 vs sweep winner 0.3 (camera sim, not render-blocking).
- Web generation route: policy-blocked, undecided — nothing proceeds
  there until he decides.
- Reel duration: full 7:04 or sub-3:00 cutdown (single EDL filter).
