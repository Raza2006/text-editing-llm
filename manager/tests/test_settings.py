from manager import settings


def test_load_override_order(tmp_path, monkeypatch):
    a = tmp_path / "a.env"; a.write_text("X=1\nY=a\n# comment\n\nZ=keep\n")
    b = tmp_path / "b.env"; b.write_text("X=2\nW=list of words\n")
    monkeypatch.setenv("Y", "from-env")
    cfg = settings.load([str(a), str(b), str(tmp_path / "missing.env")])
    assert cfg["X"] == "2"
    assert cfg["Y"] == "from-env"
    assert cfg["Z"] == "keep"
    assert cfg["W"] == "list of words"
