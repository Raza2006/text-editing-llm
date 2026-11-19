from manager import gpu

CFG = {"MIN_VRAM_PRIMARY_MIB": "40960"}


def test_total_vram_parses_first_gpu():
    assert gpu.total_vram_mib("49140\n24564\n") == 49140


def test_choose_model_primary_at_threshold():
    assert gpu.choose_model(40960, CFG) == "primary"


def test_choose_model_fallback_on_32gb_card():
    assert gpu.choose_model(32607, CFG) == "fallback"
