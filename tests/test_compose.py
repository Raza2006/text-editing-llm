import json, os, shutil, subprocess
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not available")


@pytest.fixture(scope="module")
def cfg(tmp_path_factory):
    d = tmp_path_factory.mktemp("env")
    env = d / "test.env"
    env.write_text("WEBUI_SECRET_KEY=x\nLLAMA_API_KEY=y\nWEBUI_ADMIN_EMAIL=a@b.co\nSITE_ADDRESSES=https://localhost\n")
    os.makedirs(os.path.join(ROOT, "data", "secrets"), exist_ok=True)
    key = os.path.join(ROOT, "data", "secrets", "llama_key")
    if not os.path.exists(key):
        open(key, "w").write("k\n")
    out = subprocess.check_output(
        ["docker", "compose", "--env-file", "config/versions.env", "--env-file", "config/defaults.env",
         "--env-file", str(env), "config", "--format", "json"], cwd=ROOT, text=True)
    return json.loads(out)["services"]


def _seconds(v):
    if isinstance(v, (int, float)):
        return v / 1e9 if v > 1e6 else v
    import re
    total = 0
    for num, unit in re.findall(r"(\d+)([hms])", str(v)):
        total += int(num) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total


def test_webui_has_generous_start_period(cfg):
    hc = cfg["webui"].get("healthcheck", {})
    assert hc.get("test"), "webui needs its own healthcheck"
    assert _seconds(hc["start_period"]) >= 600


def test_backup_can_read_wal_database(cfg):
    mounts = [v for v in cfg["backup"]["volumes"] if v["target"] == "/data"]
    assert mounts and not mounts[0].get("read_only", False)


def test_only_caddy_publishes_ports(cfg):
    assert [k for k, v in cfg.items() if v.get("ports")] == ["caddy"]
