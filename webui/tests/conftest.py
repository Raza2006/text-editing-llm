import http.server, importlib.util, json, os, threading
import pytest

FUNCS = os.path.join(os.path.dirname(__file__), "..", "functions")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(FUNCS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Stub(http.server.BaseHTTPRequestHandler):
    """Fake llama-server: 1 token per word; summaries are fixed text."""
    requests = []
    fail_completions = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append((self.path, body, self.headers.get("Authorization")))
        if self.path != "/tokenize" and type(self).fail_completions:
            self.send_response(400); self.send_header("Content-Length", "0"); self.end_headers()
            return
        if self.path == "/tokenize":
            out = {"tokens": list(range(len(body["content"].split())))}
        else:
            out = {"choices": [{"message": {"content": "SUMMARY: user prefers British spelling"}}]}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def llama():
    Stub.requests = []
    Stub.fail_completions = False
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", Stub
    srv.shutdown()


class Emitter:
    def __init__(self):
        self.events = []

    async def __call__(self, event):
        self.events.append(event)
