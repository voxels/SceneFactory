#!/usr/bin/env python3
"""Verify every model the Cezar ComfyUI package needs, on the machine that
will run the workflows (the Mac).

Run:  python3 verify_models.py [--comfyui-dir ~/ComfyUI]
      HF cache is read from $HF_HOME, else ~/.cache/huggingface.

Prints a PASS/MISSING table and exits 1 if anything required is missing.
The Cezar LoRA is expected only AFTER the 3080 Ti training run — it is
flagged EXPECTED-LATER rather than MISSING until then.
"""
import argparse, os, sys
from pathlib import Path

def scan_hub(hub_dir, needle):
    """Find model repos in the HF hub cache whose repo dir matches needle."""
    hub = Path(hub_dir)
    found = []
    if not hub.is_dir():
        return found
    for child in hub.iterdir():
        if child.is_dir() and needle.lower() in child.name.lower():
            snaps = child / "snapshots"
            total = 0
            newest = None
            if snaps.is_dir():
                for s in snaps.iterdir():
                    if s.is_dir():
                        sz = sum(f.stat().st_size for f in s.rglob("*") if f.is_file())
                        total = max(total, sz)
                        newest = s.name
            found.append((child.name, total, newest))
    return found

def scan_dir(d, patterns):
    out = []
    d = Path(d)
    if not d.is_dir():
        return out
    for pat in patterns:
        for f in d.glob(pat):
            if f.is_file():
                out.append((f.name, f.stat().st_size))
    return out

def gb(b):
    return f"{b/1e9:.2f} GB" if b else "0 B"

def candidate_models_dirs(roots):
    """Yield models dirs: <root>/models plus <root>/*/models (multi-install)."""
    seen = set()
    for root in roots:
        root = Path(os.path.expanduser(root))
        if not root.is_dir():
            continue
        for cand in [root / "models"] + [s / "models" for s in root.iterdir() if s.is_dir()]:
            if cand.is_dir() and cand not in seen:
                seen.add(cand)
                yield cand

WEIGHT_EXTS = ("*.safetensors", "*.bin", "*.pth", "*.onnx", "*.ckpt")

def scan_flat_weights(root):
    """Flat scan: top level + one subdir deep, for roots that are not
    ComfyUI models/ trees (e.g. SovereignSurvivalKit/import/model-weights)."""
    out = []
    r = Path(os.path.expanduser(root))
    if not r.is_dir():
        return out
    for pat in WEIGHT_EXTS:
        for f in list(r.glob(pat)) + list(r.glob("*/" + pat)):
            if f.is_file():
                out.append((f.name, f.stat().st_size, str(f.parent)))
    return out

def scan_dirs(dirs, sub, patterns):
    out = []
    for d in dirs:
        for name, size in scan_dir(d / sub, patterns):
            out.append((f"{d.parent.name}/{sub}/{name}", name, size))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfyui-dir", action="append", default=None,
                    help="repeatable; defaults to ~/ComfyUI-Installs and ~/ComfyUI-Shared")
    args = ap.parse_args()
    roots = args.comfyui_dir or ["~/ComfyUI-Installs", "~/ComfyUI-Shared"]
    flat_roots = ["/Users/voxels/SovereignSurvivalKit/import/model-weights"]
    models_dirs = list(candidate_models_dirs(roots))
    flat = []
    for fr in flat_roots:
        flat.extend(scan_flat_weights(fr))

    def flat_match(needle):
        return [(f"{p}/{n}", n, s) for n, s, p in flat if needle in n.lower()]

    rows = []
    def row(name, where, ok, detail):
        rows.append((name, where, ok, detail))

    hf_home = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    hub = os.path.join(hf_home, "hub")

    # 1. LTX-Video 2.5 checkpoint: ComfyUI checkpoints (+ diffusion_models), HF hub, flat weights
    ltx = scan_dirs(models_dirs, "checkpoints", ["*ltx*2.5*", "*ltx-2.5*", "*ltx*2_5*", "*LTX*"])
    ltx += scan_dirs(models_dirs, "diffusion_models", ["*ltx*2.5*", "*ltx-2.5*", "*LTX*"])
    ltx += flat_match("ltx")
    ltx_hub = scan_hub(hub, "ltx")
    ltx_detail = ", ".join(f"{n} ({gb(s)})" for _, n, s in ltx)
    ltx_detail += (", " if ltx and ltx_hub else "") + ", ".join(
        f"hub:{n}@{sn} ({gb(s)})" for n, s, sn in ltx_hub)
    if not (ltx or ltx_hub):
        # show what's actually there so the miss is diagnosable
        have = []
        for d in models_dirs:
            for sub in ("checkpoints", "diffusion_models"):
                have += [f"{sub}/{n}" for n, _ in scan_dir(d / sub, ["*"])]
        ltx_detail = "none found; checkpoints dir holds: " + (", ".join(have[:20]) or "(empty)")
    row("LTX-Video 2.5 checkpoint", ", ".join(str(d) for d in models_dirs) or "(no models dirs found)",
        bool(ltx or ltx_hub), ltx_detail)

    # 2. LTX VAE
    vae = scan_dirs(models_dirs, "vae", ["*ltx*"])
    vae += [m for m in flat_match("vae") if "ltx" in m[1].lower()]
    row("LTX VAE", "",
        bool(vae), ", ".join(f"{n} ({gb(s)})" for _, n, s in vae) or "none found")

    # 3. Cezar LoRA (post-training)
    lora = scan_dirs(models_dirs, "loras", ["*cezar*"])
    lora += flat_match("cezar")
    row("Cezar identity LoRA", "",
        "LATER" if not lora else True,
        ", ".join(f"{n} ({gb(s)})" for _, n, s in lora) or "expected after 3080 Ti training run")

    # 4. SAM3 checkpoint in HF hub cache (+ flat model-weights)
    sam = scan_hub(hub, "sam3")
    sam_flat = flat_match("sam3")
    sam_where = hub + (" + " + flat_roots[0] if sam_flat else "")
    row("SAM3 / SAM 3.1 checkpoint", sam_where,
        bool(sam or sam_flat),
        ", ".join(f"{n} snapshot {sn} ({gb(s)})" for n, s, sn in sam) +
        (", " if sam and sam_flat else "") +
        ", ".join(f"{n} ({gb(s)})" for _, n, s in sam_flat)
        or "none — HF-gated, request access then `hf auth login`")

    # 5. transformers (SAM3 MPS backend)
    try:
        import transformers  # noqa
        row("transformers (SAM3 MPS backend)", "python env", True,
            f"v{transformers.__version__}")
    except Exception as e:
        row("transformers (SAM3 MPS backend)", "python env", False, str(e))

    # 6. VideoHelperSuite (optional) — check every install root's custom_nodes
    vhs_roots = []
    for r in roots:
        r = Path(os.path.expanduser(r))
        if not r.is_dir():
            continue
        for cand in [r] + [s for s in r.iterdir() if s.is_dir()]:
            if (cand / "custom_nodes" / "ComfyUI-VideoHelperSuite").is_dir():
                vhs_roots.append(str(cand))
    row("VideoHelperSuite (optional)", ", ".join(vhs_roots) or "custom_nodes",
        "OPTIONAL" if not vhs_roots else True,
        "installed" if vhs_roots else "workflows B/C need a video loader/saver without it")

    print(f"\nHF_HOME: {hf_home}")
    print(f"ComfyUI roots: {', '.join(roots)}")
    print(f"models dirs found: {', '.join(str(d) for d in models_dirs) or 'none'}\n")
    w = max(len(r[0]) for r in rows)
    failed = False
    for name, where, ok, detail in rows:
        if ok is True:
            tag, failed_now = "PASS", False
        elif ok == "LATER":
            tag, failed_now = "EXPECTED-LATER", False
        elif ok == "OPTIONAL":
            tag, failed_now = "OPTIONAL", False
        else:
            tag, failed_now = "MISSING", True
        failed = failed or failed_now
        print(f"[{tag:13}] {name:<{w}}  {detail}\n{' ' * 17}  @ {where}")
    print()
    print("RESULT:", "MISSING models — see above" if failed else "all required models local")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
