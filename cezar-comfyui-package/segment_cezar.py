#!/usr/bin/env python3
"""segment_cezar.py — swappable segmentation backend for the Cezar pipeline.

Video in -> per-frame Cezar masks out, as PGM sequence + manifest.json using
the EXACT contract of SceneFactorySAM3SaveMaskSequence:

    mask_000000.pgm ... (binary P5, W H, 255, uint8 = mask*255)
    manifest.json: {schema_version: 1, frames: [{index, path,
        timestamp_seconds, nonempty}], fps, start_timestamp_seconds,
        generated_utc}  (+ a provenance block naming the backend)

Backends (swappable via --backend):
  rembg   Works TODAY. u2net_human_seg.onnx (~176 MB, auto-downloads on first
          run to ~/.u2net). Human-specific masks, per frame. No text prompt,
          so --keep selects Cezar's mask among the people found.
  sam3    Flag-flip for when the facebook/sam3 checkpoint lands (gated:
          request access, then `hf auth login`, then
          `huggingface-cli download facebook/sam3 sam3.pt`). Uses the native
          sam3 package per-frame with --prompt. (Untested here: no checkpoint,
          no CUDA in this environment. The tracked-video route remains
          workflow B in ComfyUI.)

Usage:
  python3 segment_cezar.py --input IMG_1841.MP4 --out masks/run_point
  python3 segment_cezar.py --input clip.mp4 --out masks/x --backend sam3 \\
      --prompt "person in black shorts" --sam3-checkpoint ~/checkpoints/sam3.pt
  python3 segment_cezar.py --input clip.mp4 --out masks/test --stride 10 --max-frames 30

--keep choices (rembg only; picks Cezar among detected people):
  darkest-shorts  component whose lower third is darkest (Cezar = black shorts,
                  Matt = mustard shorts). Default; falls back to largest on ties.
  largest         largest connected component.
  left / right    leftmost / rightmost component centroid.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


# ---------------------------------------------------------------- I/O

def read_frames(path, stride=1, max_frames=0):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        sys.exit(f"error: cannot open video {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames, idx, kept = [], 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            frames.append(frame)
            kept += 1
            if max_frames and kept >= max_frames:
                break
        idx += 1
    cap.release()
    if not frames:
        sys.exit(f"error: no frames read from {path}")
    return frames, float(fps)


def write_masks(out_dir, masks, fps, provenance):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, m in enumerate(masks):
        pixels = np.clip(np.asarray(m, dtype=np.float32) * 255.0, 0, 255).astype(np.uint8)
        name = f"mask_{i:06d}.pgm"
        with open(out_dir / name, "wb") as fh:
            fh.write(f"P5\n{pixels.shape[1]} {pixels.shape[0]}\n255\n".encode())
            fh.write(pixels.tobytes())
        frames.append({
            "index": i,
            "path": name,
            "timestamp_seconds": round(i / float(fps), 4),
            "nonempty": bool(pixels.any()),
        })
    manifest = {
        "schema_version": 1,
        "frames": frames,
        "fps": float(fps),
        "start_timestamp_seconds": 0.0,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out_dir / "manifest.json"


# ---------------------------------------------------------------- rembg backend

def _components(mask_bin):
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(
        (mask_bin > 0).astype(np.uint8), connectivity=8)
    comps = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 64:
            continue
        comps.append({"id": i, "area": int(area),
                      "labels": labels, "centroid": centroids[i]})
    return comps


def _pick_cezar(mask, frame_bgr, keep):
    """Select Cezar's component from a multi-person mask."""
    comps = _components(mask > 0.5)
    if not comps:
        return np.zeros_like(mask)
    if len(comps) == 1:
        return (mask > 0.5).astype(np.float32)

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h = gray.shape[0]

    def comp_mask(c):
        return (c["labels"] == c["id"])

    if keep == "largest":
        best = max(comps, key=lambda c: c["area"])
    elif keep in ("left", "right"):
        best = (min if keep == "left" else max)(comps, key=lambda c: c["centroid"][0])
    else:  # darkest-shorts: black shorts (Cezar) vs mustard shorts (Matt)
        scored = []
        for c in comps:
            m = comp_mask(c)
            ys = np.where(m)[0]
            if len(ys) == 0:
                continue
            lo = np.clip(int(ys.min() + 0.66 * (ys.max() - ys.min())), 0, h - 1)
            region = m.copy()
            region[:lo, :] = False
            vals = gray[region]
            if vals.size == 0:
                continue
            scored.append((float(vals.mean()), -c["area"], c))
        if not scored:
            best = max(comps, key=lambda c: c["area"])
        else:
            scored.sort()
            # tie -> largest area wins
            if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 8.0:
                best = max(comps, key=lambda c: c["area"])
            else:
                best = scored[0][2]

    sel = (best["labels"] == best["id"])
    return (sel & (mask > 0.25)).astype(np.float32)


def run_rembg(frames, keep):
    try:
        from rembg import new_session, remove
    except ImportError:
        sys.exit("error: rembg not installed — run: pip install rembg onnxruntime")
    session = new_session("u2net_human_seg")  # ~176 MB, auto-downloads on first run
    masks = []
    for i, frame in enumerate(frames):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        m = remove(rgb, session=session, only_mask=True)
        m = np.asarray(m, dtype=np.float32) / 255.0
        if m.shape[:2] != frame.shape[:2]:
            m = cv2.resize(m, (frame.shape[1], frame.shape[0]),
                           interpolation=cv2.INTER_LINEAR)
        masks.append(_pick_cezar(m, frame, keep))
        print(f"  frame {i + 1}/{len(frames)}", end="\r", flush=True)
    print()
    return masks


# ---------------------------------------------------------------- sam3 backend

def _find_sam3_checkpoint(explicit):
    if explicit and Path(explicit).exists():
        return str(explicit)
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    if hub.exists():
        for d in hub.glob("models--facebook--sam3*"):
            for pt in sorted(d.glob("snapshots/*/sam3*.pt")):
                return str(pt)
    return None


def run_sam3(frames, prompt, checkpoint_arg):
    ckpt = _find_sam3_checkpoint(checkpoint_arg)
    if not ckpt:
        sys.exit(
            "error: no SAM3 checkpoint found.\n"
            "  1. request access: https://huggingface.co/facebook/sam3\n"
            "  2. hf auth login\n"
            "  3. huggingface-cli download facebook/sam3 sam3.pt --local-dir ~/checkpoints/\n"
            "  then re-run with --backend sam3 (or pass --sam3-checkpoint <path>)."
        )
    try:
        from sam3.model_builder import build_sam3_image_model
    except ImportError:
        sys.exit("error: sam3 package not installed — pip install -e <facebookresearch/sam3 checkout>")
    print(f"  sam3 checkpoint: {ckpt}")
    # NOTE: per-frame prompted segmentation. The tracked-video route is
    # workflow B (SceneFactorySAM3SegmentVideo) in ComfyUI; both write the
    # same PGM + manifest contract. Untested here (no checkpoint/CUDA).
    model = build_sam3_image_model(checkpoint=ckpt)
    masks = []
    for i, frame in enumerate(frames):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        out = model.predict(rgb, prompt)  # native session text-prompt API
        m = np.asarray(out, dtype=np.float32)
        m = (m - m.min()) / max(m.max() - m.min(), 1e-6)
        masks.append(m)
        print(f"  frame {i + 1}/{len(frames)}", end="\r", flush=True)
    print()
    return masks


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Swappable Cezar segmentation: video -> PGM masks + manifest.json")
    ap.add_argument("--input", required=True, help="input video file")
    ap.add_argument("--out", required=True, help="output directory for mask_*.pgm + manifest.json")
    ap.add_argument("--backend", choices=["rembg", "sam3"], default="rembg")
    ap.add_argument("--keep", choices=["darkest-shorts", "largest", "left", "right"],
                    default="darkest-shorts", help="rembg: which person is Cezar")
    ap.add_argument("--prompt", default="person in black shorts", help="sam3 text prompt")
    ap.add_argument("--sam3-checkpoint", default=None, help="explicit path to sam3.pt")
    ap.add_argument("--stride", type=int, default=1, help="process every Nth frame")
    ap.add_argument("--max-frames", type=int, default=0, help="cap frames (0 = all)")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"error: input not found: {src}")

    print(f"reading {src} ...")
    frames, fps = read_frames(src, stride=args.stride, max_frames=args.max_frames)
    print(f"  {len(frames)} frames @ {fps:.2f} fps")

    if args.backend == "rembg":
        print("backend: rembg/u2net_human_seg  keep:", args.keep)
        masks = run_rembg(frames, args.keep)
        provenance = {"backend": "rembg", "model": "u2net_human_seg",
                      "keep": args.keep, "sam3_prompt_equivalent": args.prompt}
    else:
        print("backend: sam3  prompt:", args.prompt)
        masks = run_sam3(frames, args.prompt, args.sam3_checkpoint)
        provenance = {"backend": "sam3", "prompt": args.prompt}
    provenance.update({"source": str(src), "frames": len(frames), "fps": fps,
                       "stride": args.stride})

    manifest = write_masks(args.out, masks, fps, provenance)
    nonempty = sum(1 for m in masks if np.asarray(m).any())
    print(f"done: {len(masks)} masks ({nonempty} nonempty) -> {manifest}")


if __name__ == "__main__":
    main()
