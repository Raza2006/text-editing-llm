import os, stat, subprocess, textwrap
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "llama", "entrypoint.sh")


def _exe(path, body):
    path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def env(tmp_path):
    bin_ = tmp_path / "bin"; bin_.mkdir()
    st = tmp_path / "stub"; st.mkdir()
    models = tmp_path / "models"; models.mkdir()
    state = tmp_path / "state"; state.mkdir()
    (models / "selected.env").write_text("MODEL_FILE=m.gguf\nMODEL_ALIAS=gemma\n")
    _exe(bin_ / "llama-server", """
        ctx=""; prev=""
        for a in "$@"; do [ "$prev" = "-c" ] && ctx="$a"; prev="$a"; done
        echo "$ctx $*" >> "$STUB/calls.log"
        for c in $STUB_CRASH; do [ "$c" = "$ctx" ] && exit 1; done
        echo "$ctx" > "$STUB/ctx"; echo $$ > "$STUB/healthy"
        sleep "${STUB_LIFETIME:-3}"
    """)
    _exe(bin_ / "curl", 'p=$(cat "$STUB/healthy" 2>/dev/null) && kill -0 "$p" 2>/dev/null\n')
    _exe(bin_ / "nvidia-smi", 'c=$(cat "$STUB/ctx"); eval "v=\\${STUB_FREE_$c:-9999}"; echo "$v"\n')
    e = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", STUB=str(st), LLAMA_BIN=str(bin_ / "llama-server"),
             MODELS_DIR=str(models), STATE_DIR=str(state), HEALTH_TIMEOUT="5",
             CTX_CANDIDATES="524288 458752 393216", CTX_MAX_PER_CHAT="262144", MIN_FREE_MIB="2048", PARALLEL="8",
             API_KEY_FILE="/run/secrets/llama_key")
    return e, st, state


def run(e):
    return subprocess.run(["sh", SCRIPT], env=e, capture_output=True, text=True, timeout=60)


def test_first_candidate_fits(env):
    e, st, state = env
    r = run(e)
    assert r.returncode == 0, r.stderr
    assert "CTX=524288" in (state / "ctx.env").read_text()
    assert "--kv-unified" in (st / "calls.log").read_text()


def test_steps_down_on_crash(env):
    e, st, state = env
    e["STUB_CRASH"] = "524288 458752"
    assert run(e).returncode == 0
    assert "CTX=393216" in (state / "ctx.env").read_text()


def test_steps_down_on_low_free_memory(env):
    e, st, state = env
    e["STUB_FREE_524288"] = "1500"; e["STUB_FREE_458752"] = "3000"; e["STUB_LIFETIME"] = "3"
    assert run(e).returncode == 0
    assert "CTX=458752" in (state / "ctx.env").read_text()


def test_reuses_saved_ctx_without_probe(env):
    e, st, state = env
    (state / "ctx.env").write_text("CTX=393216\nPER_CHAT=196608\n")
    assert run(e).returncode == 0
    calls = (st / "calls.log").read_text().splitlines()
    assert len(calls) == 1 and calls[0].startswith("393216 ")


def test_nothing_fits_exit_3_with_message(env):
    e, st, state = env
    e["STUB_CRASH"] = "524288 458752 393216"
    r = run(e)
    assert r.returncode == 3
    assert "does not fit on this GPU" in r.stdout + r.stderr
    assert not (state / "ctx.env").exists()


def test_per_chat_is_half_pool_capped(env):
    e, st, state = env
    e["CTX_CANDIDATES"] = "262144"
    assert run(e).returncode == 0
    assert "PER_CHAT=131072" in (state / "ctx.env").read_text()
    e2 = dict(e, REPROBE="1", CTX_CANDIDATES="1048576")
    assert run(e2).returncode == 0
    assert "PER_CHAT=262144" in (state / "ctx.env").read_text()


def test_cpu_only_skips_gpu_flags(env):
    e, st, state = env
    e["CPU_ONLY"] = "1"; e["STUB_FREE_524288"] = "10"
    assert run(e).returncode == 0
    log = (st / "calls.log").read_text()
    assert "-ngl" not in log and "CTX=524288" in (state / "ctx.env").read_text()
