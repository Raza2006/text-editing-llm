import hashlib, http.server, os, threading
import pytest
from manager import download

DATA = os.urandom(200_000)
SHA = hashlib.sha256(DATA).hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
    seen_ranges = []
    hits = 0
    truncate_at = None

    def do_GET(self):
        type(self).hits += 1
        rng = self.headers.get("Range")
        type(self).seen_ranges.append(rng)
        start = 0
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(DATA)-1}/{len(DATA)}")
        else:
            self.send_response(200)
        body = DATA[start:]
        if type(self).truncate_at:
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body[: type(self).truncate_at])  # connection closes early, no error
            return
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    Handler.seen_ranges = []
    Handler.hits = 0
    Handler.truncate_at = None
    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{srv.server_port}/model.gguf"
    srv.shutdown()


def test_fetch_resumes_from_partial(server, tmp_path):
    dest = tmp_path / "model.gguf"
    (tmp_path / "model.gguf.part").write_bytes(DATA[:100_000])
    download.fetch(server, str(dest), len(DATA), SHA, progress=lambda *_: None)
    assert dest.read_bytes() == DATA
    assert Handler.seen_ranges == ["bytes=100000-"]
    assert not (tmp_path / "model.gguf.part").exists()


def test_fetch_bad_checksum_raises_and_cleans(server, tmp_path):
    dest = tmp_path / "model.gguf"
    with pytest.raises(download.DownloadError) as e:
        download.fetch(server, str(dest), len(DATA), "0" * 64, progress=lambda *_: None)
    assert "damaged" in str(e.value)
    assert not dest.exists() and not (tmp_path / "model.gguf.part").exists()


def test_fetch_skips_when_complete(server, tmp_path):
    dest = tmp_path / "model.gguf"; dest.write_bytes(DATA)
    download.fetch(server, str(dest), len(DATA), SHA, progress=lambda *_: None)
    assert Handler.hits == 0


def test_verified_file_not_rehashed(server, tmp_path, monkeypatch):
    dest = tmp_path / "model.gguf"; dest.write_bytes(DATA)
    download.fetch(server, str(dest), len(DATA), SHA, progress=lambda *_: None)
    calls = []
    monkeypatch.setattr(download, "_sha256", lambda p: calls.append(p) or SHA)
    download.fetch(server, str(dest), len(DATA), SHA, progress=lambda *_: None)
    assert calls == [] and Handler.hits == 0


def test_short_download_keeps_partial_file(server, tmp_path):
    dest = tmp_path / "model.gguf"
    Handler.truncate_at = 50_000
    with pytest.raises(download.DownloadError) as e:
        download.fetch(server, str(dest), len(DATA), SHA, progress=lambda *_: None)
    assert "continues where it stopped" in str(e.value)
    assert (tmp_path / "model.gguf.part").stat().st_size == 50_000
