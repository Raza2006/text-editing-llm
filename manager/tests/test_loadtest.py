import http.server, json, threading, time
from manager import loadtest


class Llama(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        time.sleep(0.2)
        data = json.dumps({"choices": [{"message": {"content": "ok"}}],
                           "timings": {"prompt_n": len(body["messages"][-1]["content"]) // 4, "predicted_n": 5}}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_runs_users_concurrently_and_reports():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Llama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    lines = []
    t0 = time.time()
    ok = loadtest.run(f"http://127.0.0.1:{srv.server_port}", "k", users=8, long_users=2, long_tokens=1000, out=lines.append)
    srv.shutdown()
    assert ok and time.time() - t0 < 1.5  # 8 requests of 0.2 s ran in parallel
    assert sum(l.startswith("  user") for l in lines) == 8
    assert any("All 8 users got an answer" in l for l in lines)
