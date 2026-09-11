# Runtime Dependencies

Required ComfyUI custom nodes:

- [`ComfyUI-PuLID-Flux2`](https://github.com/iFayens/ComfyUI-PuLID-Flux2) — PuLID face embedding and FLUX.2 Klein injection. On Apple Silicon use CPU InsightFace with `onnxruntime`, not `onnxruntime-gpu`.
- `ComfyUI-LTXVideo` — LTX 2.5 image-to-video nodes and workflow support.
- `ComfyUI-Impact-Pack` — regional masks that keep identity conditioning scoped to its named subject.

Required PuLID weight: `pulid_flux2_klein_v2.safetensors` under ComfyUI `models/pulid/`.

When downloading `LTX-2.5-Diffusers`, exclude the non-distilled transformer tree to avoid an unnecessary second model download:

```sh
huggingface-cli download Lightricks/LTX-2.5-Diffusers \
  --exclude "transformer_full/*" \
  --local-dir /absolute/path/to/ltx-2.5
```

Source `runtime.env.sh` before launching ComfyUI and the prompt planner.
