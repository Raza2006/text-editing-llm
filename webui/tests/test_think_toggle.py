import asyncio
from conftest import load

tt = load("think_toggle")


def test_think_toggle_sets_kwarg():
    f = tt.Filter()
    assert f.toggle is True
    out = asyncio.run(f.inlet({"messages": [], "chat_template_kwargs": {"x": 1}}))
    assert out["chat_template_kwargs"] == {"x": 1, "enable_thinking": True}
