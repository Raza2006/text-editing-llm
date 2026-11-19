import asyncio, json
import pytest
from conftest import load, Emitter

cc = load("context_compressor")


def words(n, tag="w"):
    return " ".join([tag] * n)


def make(llama_url, tmp_path, limit=1000):
    f = cc.Filter()
    f.valves = f.Valves(llama_url=llama_url, llama_key="k", per_chat_limit=limit, compress_at=0.9,
                        keep_recent_turns=1, cache_path=str(tmp_path / "cache.json"))
    return f


def convo(sizes, doc=None):
    msgs = [{"role": "system", "content": "SYS"}]
    if doc:
        msgs.append({"role": "user", "content": "[DOCUMENT] " + words(doc, "d")})
    for i, n in enumerate(sizes):
        msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": words(n, f"m{i}")})
    return msgs


def run(f, body, chat="c1"):
    em = Emitter()
    out = asyncio.run(f.inlet(body, __metadata__={"chat_id": chat}, __event_emitter__=em))
    return out, em


def test_under_threshold_unchanged(llama, tmp_path):
    url, stub = llama
    body = {"messages": convo([100, 100, 100])}
    out, em = run(make(url, tmp_path), json.loads(json.dumps(body)))
    assert out["messages"] == body["messages"] and em.events == []
    assert all(r[2] == "Bearer k" for r in stub.requests)


def test_over_threshold_summarises_and_keeps_recent_and_document(llama, tmp_path):
    url, _ = llama
    msgs = convo([300, 300, 200, 50], doc=100)
    out, em = run(make(url, tmp_path), {"messages": msgs})
    contents = [m["content"] for m in out["messages"]]
    assert contents[0] == "SYS"
    assert any("SUMMARY: user prefers British spelling" in c for c in contents)
    assert any(c.startswith("[DOCUMENT]") for c in contents)
    assert contents[-2:] == [msgs[-2]["content"], msgs[-1]["content"]]
    assert not any(c == msgs[2]["content"] for c in contents)  # oldest turn condensed
    assert "summarised" in em.events[-1]["data"]["description"]


def test_summary_cached_and_reused(llama, tmp_path):
    url, stub = llama
    f = make(url, tmp_path)
    run(f, {"messages": convo([400, 300, 200, 50])})
    n = sum(1 for r in stub.requests if r[0] == "/v1/chat/completions")
    run(f, {"messages": convo([400, 300, 200, 50])})
    assert sum(1 for r in stub.requests if r[0] == "/v1/chat/completions") == n == 1


def test_other_chat_untouched(llama, tmp_path):
    url, _ = llama
    f = make(url, tmp_path)
    run(f, {"messages": convo([400, 300, 200, 50])}, chat="big")
    small = {"messages": convo([10, 10])}
    out, _ = run(f, json.loads(json.dumps(small)), chat="small")
    assert out == small
    assert "small" not in json.loads((tmp_path / "cache.json").read_text())


def test_force_flag_compresses_once(llama, tmp_path):
    url, _ = llama
    f = make(url, tmp_path)
    (tmp_path / "cache.json").write_text(json.dumps({"c1": {"force": True}}))
    out, _ = run(f, {"messages": convo([50, 50, 50, 50])})
    assert any("SUMMARY" in m["content"] for m in out["messages"])
    assert json.loads((tmp_path / "cache.json").read_text())["c1"].get("force") is False


def test_still_too_long_raises_plain_message(llama, tmp_path):
    url, _ = llama
    with pytest.raises(Exception) as e:
        run(make(url, tmp_path), {"messages": convo([20, 1200])})
    assert "too long" in str(e.value) and "new chat" in str(e.value)


def test_model_error_while_summarising_gives_plain_message(llama, tmp_path):
    url, stub = llama
    stub.fail_completions = True
    with pytest.raises(Exception) as e:
        run(make(url, tmp_path), {"messages": convo([400, 300, 200, 50])})
    assert "HTTP" not in str(e.value) and ("too long" in str(e.value) or "busy" in str(e.value))


def test_oversized_history_trimmed_before_summary(llama, tmp_path):
    url, stub = llama
    # older part alone is far over the limit (2 x 700 words vs a 1000-token limit)
    run(make(url, tmp_path), {"messages": convo([700, 700, 100, 20])})
    summary_req = [b for p, b, _ in stub.requests if p == "/v1/chat/completions"][0]
    assert len(summary_req["messages"][1]["content"].split()) <= 1000
