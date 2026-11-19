"""Load presets and functions into Open WebUI through its API. Safe to run repeatedly."""
import glob
import json
import os
import time
import urllib.error
import urllib.request

PUBLIC_READ = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]
BASE_MODEL = "gemma"
FUNCTIONS = {
    # id: (name, valves taken from the seed settings)
    "context_compressor": ("Context Compressor", ("llama_url", "llama_key", "per_chat_limit", "compress_at")),
    "compress_button": ("Compress chat", ()),
    "think_toggle": ("Think", ()),
}


class SeedError(Exception):
    pass


class Api:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.token = None

    def call(self, method, path, body=None, ok_codes=(200,)):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read() or b"null")
            except ValueError:
                detail = None
            return e.code, detail


def _authenticate(api, email, password, key_path):
    if os.path.exists(key_path):
        with open(key_path, encoding="utf-8") as f:
            api.token = f.read().strip()
        if api.call("GET", "/api/v1/functions/id/think_toggle")[0] != 401 or not password:
            return
    if not password:
        raise SeedError("The saved setup key no longer works. See docs/admin-guide.md, section 'Re-installing the presets'.")
    code, out = api.call("POST", "/api/v1/auths/signin", {"email": email, "password": password})
    if code != 200 or not out or "token" not in out:
        raise SeedError("Could not log in with the admin email or password from the installer.")
    api.token = out["token"]
    code, out = api.call("POST", "/api/v1/auths/api_key")
    if code != 200 or not out.get("api_key"):
        raise SeedError("Open WebUI did not create an access key for setup (is ENABLE_API_KEYS on?).")
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(out["api_key"])
    os.chmod(key_path, 0o600)
    api.token = out["api_key"]


def _seed_function(api, fid, name, content, valves):
    form = {"id": fid, "name": name, "content": content, "meta": {"description": name}}
    code, out = api.call("POST", "/api/v1/functions/create", form)
    if code != 200:
        code, out = api.call("POST", f"/api/v1/functions/id/{fid}/update", form)
        if code != 200:
            raise SeedError(f"Could not install the '{name}' feature ({out}).")
    code, info = api.call("GET", f"/api/v1/functions/id/{fid}")
    info = info if code == 200 and info else out
    if not info.get("is_active"):
        api.call("POST", f"/api/v1/functions/id/{fid}/toggle")
    if not info.get("is_global"):
        api.call("POST", f"/api/v1/functions/id/{fid}/toggle/global")
    if valves:
        code, out = api.call("POST", f"/api/v1/functions/id/{fid}/valves/update", valves)
        if code != 200:
            raise SeedError(f"Could not save the settings of the '{name}' feature ({out}).")


def _upsert_model(api, form):
    code, out = api.call("POST", "/api/v1/models/create", form)
    if code != 200:
        code, out = api.call("POST", "/api/v1/models/model/update", form)
        if code != 200:
            raise SeedError(f"Could not install the preset '{form['name']}' ({out}).")
        # Updating a model keeps its old access rules, so set them explicitly.
        code, out = api.call("POST", "/api/v1/models/model/access/update",
                             {"id": form["id"], "name": form["name"], "access_grants": form["access_grants"]})
        if code != 200:
            raise SeedError(f"Could not set who may use '{form['name']}' ({out}).")


def run(base_url, admin_email, admin_password, api_key_path, functions_dir, presets_dir, valves, progress=print):
    api = Api(base_url)
    _authenticate(api, admin_email, admin_password, api_key_path)

    for fid, (name, valve_keys) in FUNCTIONS.items():
        with open(os.path.join(functions_dir, fid + ".py"), encoding="utf-8") as f:
            content = f.read()
        _seed_function(api, fid, name, content, {k: valves[k] for k in valve_keys if k in valves})
        progress(f"Installed: {name}")

    # Everyone needs read access to the base model for the presets to work (Open WebUI checks the
    # base model too), but it is hidden from the model menu so people only see the presets.
    _upsert_model(api, {"id": BASE_MODEL, "base_model_id": None, "name": "Gemma (raw model)",
                        "meta": {"description": "The model without editing instructions.", "hidden": True},
                        "params": {}, "access_grants": PUBLIC_READ, "is_active": True})

    with open(os.path.join(presets_dir, "_rules.txt"), encoding="utf-8") as f:
        rules = f.read().strip()
    for path in sorted(glob.glob(os.path.join(presets_dir, "*.json"))):
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        _upsert_model(api, {
            "id": p["id"], "base_model_id": BASE_MODEL, "name": p["name"],
            "meta": {"description": p["description"]},
            "params": {"system": p["system"] + "\n\n" + rules, "temperature": p["temperature"]},
            "access_grants": PUBLIC_READ, "is_active": True,
        })
        progress(f"Installed preset: {p['name']}")


def _read_env(path):
    values = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, _, v = line.strip().partition("=")
                    values[k] = v
    return values


def main(cfg):
    """Entry point inside the seed container."""
    with open("/run/secrets/llama_key", encoding="utf-8") as f:
        llama_key = f.read().strip()
    per_chat = int(_read_env("/state/ctx.env").get("PER_CHAT", cfg.get("CTX_MAX_PER_CHAT", "262144")))
    base_url = cfg.get("WEBUI_URL", "http://webui:8080")
    for _ in range(120):  # wait up to 10 minutes for the web app
        if Api(base_url).call("GET", "/health")[0] == 200:
            break
        time.sleep(5)
    run(base_url, cfg.get("WEBUI_ADMIN_EMAIL", ""), cfg.get("WEBUI_ADMIN_PASSWORD", ""),
        "/data/seed_api_key", "/app/webui/functions", "/app/webui/presets",
        {"llama_url": "http://llama:8080", "llama_key": llama_key, "per_chat_limit": per_chat,
         "compress_at": float(cfg.get("COMPRESS_AT", "0.9"))})
    print("Presets and features are installed.")
