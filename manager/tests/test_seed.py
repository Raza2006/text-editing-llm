import http.server, json, os, threading
import pytest
from manager import seed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FUNCS = os.path.join(ROOT, "webui", "functions")
PRESETS = os.path.join(ROOT, "webui", "presets")


class WebUI(http.server.BaseHTTPRequestHandler):
    state = {}

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)

    def _auth_ok(self):
        h = self.headers.get("Authorization", "")
        return h in ("Bearer jwt-token", "Bearer sk-saved")

    def do_GET(self):
        s = type(self).state
        s["calls"].append(("GET", self.path))
        if not self._auth_ok():
            return self._send(401, {"detail": "no"})
        if self.path.startswith("/api/v1/functions/id/"):
            fid = self.path.split("/")[5]
            return self._send(200, s["functions"][fid]) if fid in s["functions"] else self._send(401, {"detail": "nf"})
        self._send(404, {})

    def do_POST(self):
        s = type(self).state
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        s["calls"].append(("POST", self.path))
        p = self.path
        if p == "/api/v1/auths/signin":
            ok = body == {"email": "a@b.co", "password": "secret123"}
            return self._send(200, {"token": "jwt-token"}) if ok else self._send(400, {"detail": "bad"})
        if not self._auth_ok():
            return self._send(401, {"detail": "no"})
        if p == "/api/v1/auths/api_key":
            return self._send(200, {"api_key": "sk-saved"})
        if p == "/api/v1/functions/create":
            if body["id"] in s["functions"]:
                return self._send(400, {"detail": "taken"})
            s["functions"][body["id"]] = {"id": body["id"], "is_active": False, "is_global": False, "content": body["content"]}
            return self._send(200, s["functions"][body["id"]])
        if p.startswith("/api/v1/functions/id/"):
            parts = p.split("/"); fid = parts[5]; action = "/".join(parts[6:])
            f = s["functions"][fid]
            if action == "update":
                f["content"] = body["content"]; s["updates"] += 1
            elif action == "toggle":
                f["is_active"] = not f["is_active"]
            elif action == "toggle/global":
                f["is_global"] = not f["is_global"]
            elif action == "valves/update":
                if s.get("fail_valves"):
                    return self._send(400, {"detail": "bad valves"})
                f["valves"] = body
            return self._send(200, f)
        if p == "/api/v1/models/create":
            if body["id"] in s["models"]:
                return self._send(401, {"detail": "taken"})
            s["models"][body["id"]] = body
            return self._send(200, body)
        if p == "/api/v1/models/model/update":
            grants = s["models"][body["id"]]["access_grants"]  # real API keeps grants on update
            s["models"][body["id"]] = dict(body, access_grants=grants); s["model_updates"] += 1
            return self._send(200, body)
        if p == "/api/v1/models/model/access/update":
            s["models"][body["id"]]["access_grants"] = body["access_grants"]
            return self._send(200, s["models"][body["id"]])
        self._send(404, {})

    def log_message(self, *a):
        pass


@pytest.fixture
def webui():
    WebUI.state = {"calls": [], "functions": {}, "models": {}, "updates": 0, "model_updates": 0}
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), WebUI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", WebUI.state
    srv.shutdown()


def run(url, tmp_path, password="secret123"):
    seed.run(url, "a@b.co", password, str(tmp_path / "key"), FUNCS, PRESETS,
             {"llama_key": "lk", "per_chat_limit": 262144}, progress=lambda *_: None)


def test_first_run_signs_in_and_saves_key(webui, tmp_path):
    url, s = webui
    run(url, tmp_path)
    assert (tmp_path / "key").read_text() == "sk-saved"
    assert oct((tmp_path / "key").stat().st_mode)[-3:] == "600"


def test_second_run_uses_key_and_updates_not_duplicates(webui, tmp_path):
    url, s = webui
    run(url, tmp_path)
    s["calls"].clear()
    run(url, tmp_path, password="")
    assert ("POST", "/api/v1/auths/signin") not in s["calls"]
    assert len(s["functions"]) == 3 and s["updates"] == 3
    assert len(s["models"]) == 8 and s["model_updates"] == 8


def test_functions_made_global_and_active_once(webui, tmp_path):
    url, s = webui
    run(url, tmp_path); run(url, tmp_path)
    for f in s["functions"].values():
        assert f["is_active"] and f["is_global"]
    assert s["functions"]["context_compressor"]["valves"]["llama_key"] == "lk"
    assert s["functions"]["context_compressor"]["valves"]["per_chat_limit"] == 262144


def test_presets_public_and_based_on_gemma(webui, tmp_path):
    url, s = webui
    run(url, tmp_path)
    m = s["models"]["copy-edit"]
    assert m["base_model_id"] == "gemma"
    assert m["access_grants"] == [{"principal_type": "user", "principal_id": "*", "permission": "read"}]
    assert m["params"]["temperature"] == 0.2
    assert s["models"]["gemma"]["access_grants"] == m["access_grants"]  # users need read access to the base
    assert s["models"]["gemma"]["meta"]["hidden"] is True  # but it is hidden from the model menu


def test_all_presets_contain_safety_rules(webui, tmp_path):
    url, s = webui
    run(url, tmp_path)
    presets = [m for k, m in s["models"].items() if k != "gemma"]
    assert len(presets) == 7
    for m in presets:
        assert "citation key" in m["params"]["system"] and "Preserve the author's meaning" in m["params"]["system"]


def test_wrong_password_gives_plain_error(webui, tmp_path):
    url, s = webui
    with pytest.raises(seed.SeedError) as e:
        run(url, tmp_path, password="nope")
    assert "admin email or password" in str(e.value)


def test_grants_reapplied_when_model_already_exists(webui, tmp_path):
    url, s = webui
    run(url, tmp_path)
    for m in s["models"].values():
        m["access_grants"] = []  # e.g. created by an older version
    run(url, tmp_path)
    assert all(m["access_grants"] == seed.PUBLIC_READ for m in s["models"].values())


def test_failed_valves_update_is_reported(webui, tmp_path):
    url, s = webui
    s["fail_valves"] = True
    with pytest.raises(seed.SeedError) as e:
        run(url, tmp_path)
    assert "settings" in str(e.value)
