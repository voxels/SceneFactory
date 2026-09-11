# Reconstruction render pipeline status

Date: 2026-08-26

This document covers burn-down items 5, 8, and 9. It distinguishes an executable
mechanical proof from production image generation.

## Outcome

The v1-side motion-control compiler, strict render queue, alpha/matte inspector,
and visual-only compositor are implemented and tested. A synthetic technical
proof demonstrates that ordered alpha layers and the green insert composite into
a visual-only MP4. It is not a production reconstruction proof.

No production LTX clip was rendered. The exact remaining model blocker is the
official motion-track IC-LoRA checkpoint; the base LTX 2.5 transformer, video
VAE, and projected text encoder are already present.

## Local LTX audit

The machine audit is recorded in
`examples/ad2184/build/ltx_motion_preflight.json`.

| Component | State |
|---|---|
| Comfy core | `7a131a3afadc8200120f67f9236311a2c48b7445` |
| Official LTX extension | Clean at `15d09abb5a187a8dcaea2fc31fe51ee96e6c9d0d` |
| Required extension source files | Present |
| Official LTX 2.5 motion workflow | Present |
| LTX 2.5 22B distilled transformer | Present, 42.0 GB |
| LTX 2.5 video VAE | Present, 1.47 GB |
| LTX 2.5 projected text encoder | Present, 15.37 GB |
| Motion-track IC-LoRA | Missing |
| Runtime dependency | `/Users/voxels/comfy/.venv/bin/python`, Kornia 0.8.2 |
| Live Comfy node registration | Verified externally after clean import; sandboxed preflight cannot reach loopback without a saved `/object_info` response |

The old statement that the official extension is broken is stale. Do not repair,
replace, or reinstall it without a new failing import audit.

## Official motion-control contract

The workflow is derived from the official Lightricks template:

- Extension: <https://github.com/Lightricks/ComfyUI-LTXVideo>
- Workflow: `example_workflows/2.5/LTX-2.5_ICLoRA_Motion_Track_Distilled.json`
- Weight source: <https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control>
- Exact filename: `ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors`
- Expected location: `/Users/voxels/ComfyUI-Shared/models/loras/`
- Published size: approximately 327 MB
- License: LTX-2 Community License; the user must accept the repository terms

The compiled workflow uses the official reference-downscale factor of 2 and
requires a full-frame sparse trajectory. For a three-second, 24 fps proof, that
is exactly 73 points per trajectory. A short or malformed track is rejected.
There is no fallback to text-only I2V for K.

The official UI workflow contains an audio VAE, empty audio latent, AV latent
concatenation/separation, and audio decode. It is therefore retained only as the
authoritative wiring reference. `compile-motion-api` emits the production API
variant using the same motion nodes but a strictly video-only latent, sampler,
crop, decode, and save path.

Required official node types:

- `LTXICLoRALoaderModelOnly`
- `LTXAddVideoICLoRAGuide`
- `LTXVDrawTracks`
- `LTXVSparseTrackEditor`
- `LTXVCropGuides`

## Added implementation

`render_pipeline.py` provides:

- `audit-ltx`: read-only extension/model preflight with commits and exact paths;
- `compile-motion-workflow`: configures the official workflow and validates the
  trajectory frame count; this is a UI/reference artifact because the official
  template includes audio;
- `compile-motion-api`: emits the executable video-only Comfy API graph with
  motion IC-LoRA and a saved track-guide preview;
- `plan-project`: compiles all master/alternate layer and composite jobs with
  explicit missing inputs;
- `inspect-output`: verifies video presence, alpha when required, and absence of
  audio;
- `composite`: overlays ordered alpha layers and always strips audio;
- `make-linear-track`: creates only a labeled synthetic test trajectory.

The generated production queue is
`examples/ad2184/build/reconstruction_render_queue.json`. It contains 152 total
jobs, of which 124 are required. After contract/tracking scaffolding landed, 68
required jobs are ready and 56 remain blocked by missing production inputs,
rendered descendants, or approvals. A ready queue record is permission to start
that stage, not evidence that the output was rendered.

## Technical compositor proof

The proof directory is
`examples/ad2184/build/proofs/compositor_smoke/`.

It contains:

- an opaque plate;
- a QTRLE/ARGB foreground layer with real alpha;
- a standalone FFV1 grayscale matte extracted from that alpha;
- a QTRLE/ARGB `#00FF00` insert layer with real alpha;
- an H.264 layered composite;
- `report.json`, which records the inputs, command, output hash, pixel format,
  stream counts, and `production_artifact: false`.

The composite has one video stream and zero audio streams. This proves the
mechanics of item 9 only. It does not prove production segmentation, tracking,
lighting, lens/grain matching, screen homography, shattering, or reconstruction
quality.

The proof directory `examples/ad2184/build/proofs/ltx_motion_control/` contains a
configured copy of the official workflow, a video-only API workflow, and a
synthetic 73-frame trajectory. Their metadata says `compiled_not_executed`; they
are not rendered clips.

During live import, the restored official extension hit upstream
Lightricks issue #494: Kornia 0.8.3 removed the `pad` re-export imported by
`pyramid_blending.py`. The active Comfy runtime was pinned to Kornia 0.8.2 and
the official extension then imported successfully. The clean extension source
was not patched. See <https://github.com/Lightricks/ComfyUI-LTXVideo/issues/494>.

## Minimum proof weights

Only these four weights are justified for the K motion-plus-matte proof. SAM3.1,
Depth Anything 3, and RAFT should wait for their separate proofs.

| File | Size | Target | License / checksum |
|---|---:|---|---|
| `sdpose_wholebody_fp16.safetensors` | 1.92 GB | `models/checkpoints/` | MIT; SHA-256 `63d01f9a7494560693b24767f4469d59c9d3266b31ff0a253e74d1e611442721` |
| `rt_detr_v4-x-hgnet_fp16.safetensors` | 124 MB | `models/diffusion_models/` | Apache-2.0; SHA-256 `581f9af9bbabb664d1891cbccd823308b176ecd409146f954dfa39af3bec2476` |
| `ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors` | 327 MB | `models/loras/` | LTX-2 Community License; gated; SHA-256 `e279807ee3aa3db1ce60188d665ff83342860367dcd6bac19f8bd5a99a9e1dca` |
| `birefnet.safetensors` | 444,473,596 bytes | `models/background_removal/` | MIT; SHA-256 `9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154` |

Official sources:

- <https://huggingface.co/Comfy-Org/SDPose>
- <https://huggingface.co/Comfy-Org/RT-DETR>
- <https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control>
- <https://huggingface.co/Comfy-Org/BiRefNet>

## Exact actions requiring user authority

1. Accept the LTX-2 Community License on the official Hugging Face repository.
2. Authorize downloading the 327 MB motion-track checkpoint to the exact LoRA
   path above. Do not download additional LTX control models for this proof.
3. Start/restart Comfy after the weight is present and verify all five required
   node types through `/object_info`.
4. Supply or approve the production K start image and K sparse tracks produced by
   the tracking pipeline.
5. Explicitly approve each proof after visual review. Software must not write the
   user's approval.

The filesystem currently has about 55 GB free. The checkpoint fits, but full
master/alternate rendering can produce much more intermediate media; choose an
output/storage policy before expanding beyond the three-second proof.

## Commands

Run from `/Users/voxels/SceneFactory/v1`:

```bash
python3 render_pipeline.py audit-ltx \
  --comfy-root /Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI \
  --models-root /Users/voxels/ComfyUI-Shared/models \
  --runtime-python /Users/voxels/comfy/.venv/bin/python \
  --output examples/ad2184/build/ltx_motion_preflight.json

python3 render_pipeline.py plan-project examples/ad2184 \
  --comfy-root /Users/voxels/ComfyUI-Installs/ComfyUI/ComfyUI \
  --models-root /Users/voxels/ComfyUI-Shared/models

python3 -m unittest discover -s tests -v
```

After the weight and production track exist, use `compile-motion-api` to create
the visual-only K proof graph and submit that JSON to Comfy's `/prompt` endpoint.
The configured official UI artifact must not be submitted directly to `/prompt`
and must not be used for production because it includes audio-generation nodes.
