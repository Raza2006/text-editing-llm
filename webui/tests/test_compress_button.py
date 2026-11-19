import asyncio, json
from conftest import load, Emitter

cb = load("compress_button")


def test_button_sets_force(tmp_path):
    a = cb.Action(); a.valves = a.Valves(cache_path=str(tmp_path / "cache.json"))
    em = Emitter()
    asyncio.run(a.action({"chat_id": "c9", "messages": []}, __event_emitter__=em))
    assert json.loads((tmp_path / "cache.json").read_text())["c9"]["force"] is True
    assert "next message" in em.events[-1]["data"]["description"]
