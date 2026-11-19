import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_textedit_command_resolves_to_cmd_shim():
    # PowerShell prefers textedit.ps1 over textedit.cmd for ".\\textedit", and .ps1 files are
    # blocked by the default execution policy, so the PowerShell script must not sit next to the shim.
    assert not os.path.exists(os.path.join(ROOT, "textedit.ps1"))
    cmd = open(os.path.join(ROOT, "textedit.cmd"), newline="").read()
    assert "ExecutionPolicy Bypass" in cmd and r"scripts\textedit.ps1" in cmd and "\r\n" in cmd
