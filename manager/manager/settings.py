"""Read KEY=VALUE settings files. Later files win; environment variables win over files."""
import os


def _parse(path):
    values = {}
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    return values


def load(paths):
    cfg = {}
    for path in paths:
        if os.path.exists(path):
            cfg.update(_parse(path))
    for key in list(cfg):
        if key in os.environ:
            cfg[key] = os.environ[key]
    return cfg
