from manager import setup as setup_mod

CFG = {
    "MIN_VRAM_PRIMARY_MIB": "40960",
    "MODEL_PRIMARY_REPO": "u/big", "MODEL_PRIMARY_FILE": "big.gguf", "MODEL_PRIMARY_SIZE": "10", "MODEL_PRIMARY_SHA256": "a" * 64,
    "MODEL_FALLBACK_REPO": "u/small", "MODEL_FALLBACK_FILE": "small.gguf", "MODEL_FALLBACK_SIZE": "5", "MODEL_FALLBACK_SHA256": "b" * 64,
    "MODEL_CI_REPO": "u/tiny", "MODEL_CI_FILE": "tiny.gguf", "MODEL_CI_SIZE": "1", "MODEL_CI_SHA256": "c" * 64,
}


def run(tmp_path, cfg, vram="49140"):
    calls = []
    setup_mod.run(cfg, str(tmp_path), vram_reader=lambda: vram,
                  fetcher=lambda url, dest, size, sha, progress: calls.append((url, dest)), progress=lambda *_: None)
    return calls, (tmp_path / "selected.env").read_text()


def test_48gb_card_downloads_primary(tmp_path):
    calls, sel = run(tmp_path, dict(CFG))
    assert calls[0][0] == "https://huggingface.co/u/big/resolve/main/big.gguf"
    assert "MODEL_FILE=big.gguf" in sel and "MODEL_ALIAS=gemma" in sel and "MODEL_KIND=primary" in sel


def test_32gb_card_downloads_fallback(tmp_path):
    calls, sel = run(tmp_path, dict(CFG), vram="32607")
    assert calls[0][1].endswith("small.gguf") and "MODEL_KIND=fallback" in sel


def test_ci_set_needs_no_gpu(tmp_path):
    calls, sel = run(tmp_path, dict(CFG, MODEL_SET="ci"), vram=None)
    assert "MODEL_FILE=tiny.gguf" in sel


def test_force_model_overrides(tmp_path):
    calls, sel = run(tmp_path, dict(CFG, FORCE_MODEL="fallback"))
    assert "MODEL_FILE=small.gguf" in sel
