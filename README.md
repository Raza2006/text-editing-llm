# text-editing-llm

A **private AI assistant for editing research papers**. It runs entirely on one computer with an NVIDIA graphics card, so unpublished papers never leave your network.

- Edits academic text without changing your meaning, citations, LaTeX, math or numbers.
- Up to **8 people at the same time**, each with their own login and their own saved chats.
- Handles long documents: up to **256,000 tokens per chat** (a whole thesis).
- Ready-made editing modes: copy-edit, clarity and flow, make concise, match a reference style, polish an abstract, reviewer feedback, general help.
- Long chats are summarised automatically before they get too big. A **Compress** button does it on demand.
- A **Think** switch for deeper (slower) answers, off by default.
- Nightly backups. Restarts itself after a crash or reboot.

Under the hood: [Gemma 4 31B](https://huggingface.co/unsloth/gemma-4-31B-it-qat-GGUF) (Google, 4-bit QAT) served by [llama.cpp](https://github.com/ggml-org/llama.cpp), with the [Open WebUI](https://github.com/open-webui/open-webui) chat interface, all in Docker.

---

## What you need

| | |
|---|---|
| Graphics card | NVIDIA with **48 GB** of memory (e.g. RTX 5090 48 GB). Cards with 32–40 GB work with a smaller model, chosen automatically. |
| Operating system | **Ubuntu 22.04 / 24.04**, or **Windows 10 / 11** (64-bit) |
| Disk | **100 GB free** (SSD recommended) |
| Memory (RAM) | 32 GB or more |
| Internet | For installation only (about 25 GB of downloads) |
| Rights | An administrator account on the computer |

---

## Install

Copy each line, paste it into the terminal, and press Enter. Wait for each one to finish before the next.

### Ubuntu Linux

Open **Terminal** (press Ctrl+Alt+T) and run:

```
sudo apt install -y git
git clone https://github.com/Raza2006/text-editing-llm.git
cd text-editing-llm
sudo ./install.sh
```

### Windows

Click Start, type **PowerShell**, right-click **Windows PowerShell**, and choose **Run as administrator**. Then run:

```
winget install --id Git.Git -e --source winget
```

**Close that window and open PowerShell as administrator again**, then run:

```
cd $HOME
git clone https://github.com/Raza2006/text-editing-llm.git
cd text-editing-llm
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### What happens next

1. The installer checks the computer. If something needs fixing, it says exactly what to do.
2. It may ask you to **restart once**: on Linux to finish the NVIDIA driver, on Windows to finish WSL. After restarting, open the terminal in the same folder and **run the last command again**. It continues where it stopped.
3. It asks you to choose the **administrator email and password**. You'll use these to log in.
4. It downloads everything and starts the assistant. **The first time takes 20–60 minutes.**
5. It prints the address to open in a web browser, for example `https://labpc.local`.

**The first time each person opens the address,** the browser warns that the connection is not private. This is expected (the connection is encrypted with the computer's own certificate). Click **Advanced**, then **Continue**.

---

## Everyday use

Run these in the project folder. On Linux, use `./textedit` (it asks for your password when needed). On Windows, use `.\textedit`.

| Command | What it does |
|---|---|
| `textedit status` | Is it running? Shows the address to open |
| `textedit doctor` | Checks everything and tells you how to fix problems |
| `textedit stop` / `start` / `restart` | As named |
| `textedit backup` | Back up all accounts and chats now (it also happens every night) |
| `textedit restore <file>` | Put back a backup |
| `textedit update` | Get the latest version |
| `textedit logs` | Recent messages, useful when asking for help |

- **Administrators:** read [docs/admin-guide.md](docs/admin-guide.md) (adding users, backups, troubleshooting).
- **Users:** read [docs/user-guide.md](docs/user-guide.md) (one page).

---

## If something goes wrong

| You see | Do this |
|---|---|
| "needs administrator rights" | Linux: start the command with `sudo`. Windows: open PowerShell with **Run as administrator**. |
| "NVIDIA driver is missing or too old" | Linux: the installer fixes it; restart when asked. Windows: install the latest driver from nvidia.com, restart, run the installer again. |
| "Hardware virtualization is switched off" (Windows) | Enable Intel VT-x / AMD-V in the BIOS, then run the installer again. |
| The download stopped | Run the same command again. It continues where it stopped. |
| "Docker cannot use the graphics card" | Restart the computer, then `textedit start`. |
| "does not fit on this GPU" | Close other programs using the graphics card, then `textedit doctor --reprobe`. |
| The page doesn't open after a Windows restart | Log in to Windows. Docker Desktop starts the assistant after login. |
| Anything else | `textedit doctor`, then `textedit logs`. Full installer details are in `data/install.log`. |

---

## For developers

- Design: [docs/design.md](docs/design.md). Plan: [docs/plans/](docs/plans/).
- Tests: `python -m pytest -q` (Python), `pwsh -File tests/windows_lib.tests.ps1` (Windows helpers). The full stack is tested end to end with a tiny CPU model on every push (`.github/workflows/ci.yml`).
- Pinned versions live in `config/versions.env`. Tunable settings are in `config/defaults.env`.

## Licence

Apache-2.0, © 2026 Mohammed Raza. Bundled software keeps its own licences: Gemma (Apache-2.0), llama.cpp (MIT), Open WebUI (Open WebUI License: its branding must stay unless you have 50 users or fewer), Caddy (Apache-2.0).
