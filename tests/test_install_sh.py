import os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "scripts", "lib.sh")


def sh(code, stdin="", cwd=None, env=None):
    return subprocess.run(["bash", "-c", f'source "{LIB}"; {code}'], input=stdin, capture_output=True, text=True,
                          cwd=cwd, env=dict(os.environ, **(env or {})), timeout=30)


def test_email_reasked_until_valid():
    r = sh('ask_email; echo "GOT=$ADMIN_EMAIL"', stdin="not-an-email\nalso bad@\nprof@iiit.ac.in\n")
    assert "GOT=prof@iiit.ac.in" in r.stdout
    assert r.stdout.count("does not look like an email") == 2


def test_password_mismatch_reasked():
    r = sh('ask_password; echo "GOT=$ADMIN_PASSWORD"', stdin="short\nlongenough1\ndifferent1\ngoodpass99\ngoodpass99\n")
    assert "GOT=goodpass99" in r.stdout
    assert "at least 8 characters" in r.stdout and "did not match" in r.stdout


def test_env_written_once_not_regenerated(tmp_path):
    (tmp_path / "data").mkdir()
    code = 'ADMIN_EMAIL=a@b.co ADMIN_PASSWORD=secret123 SITE_ADDRESSES=https://localhost write_env_once'
    sh(code, cwd=tmp_path)
    first = (tmp_path / ".env").read_text()
    assert "WEBUI_SECRET_KEY=" in first and "WEBUI_ADMIN_PASSWORD=secret123" in first
    key = (tmp_path / "data" / "secrets" / "llama_key").read_text().strip()
    assert len(key) == 40 and f"LLAMA_API_KEY={key}" in first
    assert oct((tmp_path / ".env").stat().st_mode)[-3:] == "600"
    sh(code, cwd=tmp_path)
    assert (tmp_path / ".env").read_text() == first


def test_driver_too_old_message():
    r = sh('driver_ok 550.90.07 && echo OK || echo OLD')
    assert r.stdout.strip() == "OLD"
    assert sh('driver_ok 575.57.08 && echo OK || echo OLD').stdout.strip() == "OK"


def test_state_file_skips_done_steps(tmp_path):
    (tmp_path / "data").mkdir()
    r = sh('mark_done docker; step_done docker && echo SKIP; step_done model || echo RUN', cwd=tmp_path)
    assert "SKIP" in r.stdout and "RUN" in r.stdout


def test_site_addresses_include_hostname_and_ips():
    r = sh('site_addresses_from labpc "192.168.1.5 10.0.0.2 172.17.0.1"')
    assert r.stdout.strip() == "https://labpc.local, https://192.168.1.5, https://10.0.0.2, https://localhost"


def test_password_with_special_characters_reasked():
    r = sh('ask_password; echo "GOT=$ADMIN_PASSWORD"', stdin="Pa$sw0rd!\nhas space1\nquote'1234\nGood-Pass_99!\nGood-Pass_99!\n")
    assert "GOT=Good-Pass_99!" in r.stdout
    assert r.stdout.count("cannot contain") == 3


def test_internet_check_works_without_curl(tmp_path):
    b = tmp_path / "bin"; b.mkdir()
    (b / "wget").write_text("#!/bin/sh\nexit 0\n"); (b / "wget").chmod(0o755)
    for tool in ("grep", "cut", "head", "cat"):
        os.symlink(subprocess.check_output(["which", tool], text=True).strip(), b / tool)
    r = subprocess.run(["/bin/bash", "-c", f'source "{LIB}"; internet_ok && echo ONLINE'],
                       capture_output=True, text=True, env={"PATH": str(b)})
    assert "ONLINE" in r.stdout, r.stderr


def test_random_string_works_under_strict_mode():
    # install.sh runs with "set -euo pipefail"; a generator that relies on SIGPIPE fails there.
    r = subprocess.run(["bash", "-c", f'set -euo pipefail; source "{LIB}"; for i in 1 2 3 4 5; do s=$(random_string 48); echo "${{#s}}"; done'],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["48"] * 5 and "Broken pipe" not in r.stderr
