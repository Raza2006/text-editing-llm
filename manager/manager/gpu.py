"""GPU memory helpers."""


def total_vram_mib(nvidia_smi_output):
    first = nvidia_smi_output.strip().splitlines()[0]
    return int(first.strip().split()[0])


def choose_model(total_mib, cfg):
    return "primary" if total_mib >= int(cfg["MIN_VRAM_PRIMARY_MIB"]) else "fallback"
