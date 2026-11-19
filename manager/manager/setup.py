"""Choose the model for this GPU and make sure it is downloaded and verified."""
import os
import subprocess

from . import download, gpu


def read_vram():
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout
    return out


def run(cfg, models_dir, vram_reader=read_vram, fetcher=download.fetch, progress=print):
    if cfg.get("MODEL_SET") == "ci":
        kind = "ci"
    elif cfg.get("FORCE_MODEL") in ("primary", "fallback"):
        kind = cfg["FORCE_MODEL"]
    else:
        total = gpu.total_vram_mib(vram_reader())
        kind = gpu.choose_model(total, cfg)
        progress(f"This GPU has {total / 1024:.0f} GB of memory.")
        if kind == "fallback":
            progress("That is less than the larger model needs, so the smaller model (Gemma 4 26B) will be used.")
    prefix = f"MODEL_{kind.upper()}_"
    repo, name = cfg[prefix + "REPO"], cfg[prefix + "FILE"]
    url = f"https://huggingface.co/{repo}/resolve/main/{name}"
    os.makedirs(models_dir, exist_ok=True)
    progress(f"Preparing the model {name} (this download happens only once).")
    fetcher(url, os.path.join(models_dir, name), cfg[prefix + "SIZE"], cfg[prefix + "SHA256"], progress)
    with open(os.path.join(models_dir, "selected.env"), "w", encoding="utf-8") as f:
        f.write(f"MODEL_FILE={name}\nMODEL_ALIAS=gemma\nMODEL_KIND={kind}\n")
    progress("Model ready.")
