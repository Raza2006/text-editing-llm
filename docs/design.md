# text-editing-llm: design

- **Author:** Mohammed Raza
- **Status:** draft for approval (stakeholder answers on Windows restart, HTTPS and the model fallback included)
- **Date:** 2026-11-19

## 1. What this is and why

A self-hosted AI assistant for **editing research papers**, for a university research group. It runs entirely on one machine the group controls, so unpublished papers never go to a commercial AI service.

Unusual constraints shape the design:

- **The author doesn't have the target machine.** The repository is built and tested elsewhere, then handed over.
- **The person who installs it has no IT background.** They clone the repo and paste **fewer than 10 commands** into a terminal. After that, everything must work without further decisions, editing of files, or debugging.
- **Both Linux and Windows** must be supported, and the repository should be suitable for release as an **open-source project** later.

**Success looks like this:** the installer pastes the commands, a URL is printed, the admin logs in, creates accounts for colleagues, and up to 8 people edit papers at the same time, with chat history kept per user on the server.

## 2. Goals, non-goals, anti-goals

**Goals**
- High-quality editing of academic text, including LaTeX, without changing meaning, citations, math or numbers.
- Up to **8 concurrent users** on one GPU.
- Long documents: up to **256K tokens per conversation** (the model's maximum).
- Per-user logins; access only for people the admin approves.
- Per-user chat history stored **on the server**, in a database.
- Context compression: a manual button, plus automatic compression at 90% of the per-chat limit.
- Thinking (reasoning) mode is **off by default** and turned on **only manually by the user**.
- A non-technical person can install it, and restore or update it, with copy-paste commands.
- It survives reboots and crashes (automatic restart).

**Non-goals**
- RAG or document search, web search, image generation, voice.
- Multi-machine or multi-GPU scaling.
- Access from outside the local network (the group uses a VPN for that).
- Fine-tuning or training.

**Anti-goals** (failures even if it "works")
- An installer that stops with a technical error and no plain-English next step.
- Anything that makes users' text leave the machine.
- One heavy user making the system unusable for everyone else.
- Secrets, user data or chat history committed to the repository.
- Silent quality loss, such as unrequested model swaps or heavier quantization.

## 3. Constraints

| Item | Value |
|---|---|
| GPU | NVIDIA RTX 5090 variant with **48 GB** VRAM (Blackwell, compute capability 12.0) |
| OS | Ubuntu Linux (22.04/24.04) **or** Windows 10/11; both must work |
| Installer's rights | Can run commands as administrator (`sudo` / "Run as administrator") |
| Network | Internet needed for installation (about 25–30 GB of downloads); not needed afterwards |
| Disk | At least 100 GB free on an SSD |
| System RAM | 32 GB or more recommended |
| Users | 8 concurrent, on the same local network |

## 4. Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| **A. Docker everywhere.** Linux: Docker Engine + NVIDIA Container Toolkit. Windows: Docker Desktop on WSL2 | One identical, version-pinned stack on both systems; the standard way open-source self-hosted apps ship. Windows needs WSL2 and hardware virtualization, and one reboot during install | **Chosen** |
| B. Native installs (llama.cpp binaries + Python Open WebUI + OS services) | No Docker, but two very different install paths and fragile Python dependencies; restart and backup logic built twice | Rejected |
| C. Docker on Linux, native on Windows | Both sets of problems | Rejected |

## 5. Decisions made with the stakeholder

### Model and inference

| Setting | Value |
|---|---|
| Model | **Gemma 4 31B-it, QAT, Unsloth GGUF `UD-Q4_K_XL`** (about 17.3 GB). Chosen over Qwen3.6-35B-A3B and Gemma 4 26B-A4B for writing quality (higher human-preference rating); 4-bit QAT keeps near-full quality |
| Engine | **llama.cpp `llama-server`**, CUDA build supporting Blackwell (sm_120) |
| Context | **512K-token shared pool** (`--kv-unified`), **256K max per conversation** |
| Context-memory precision | 8-bit (`-ctk q8_0 -ctv q8_0`, flash attention on) |
| Concurrency | `--parallel 8`; extra requests queue |
| Per-chat limit | *Builder's call:* `min(256K, measured pool ÷ 2)`, so two maximum-size chats always fit together. Compression triggers at 90% of this limit. With the target 512K pool this is the full 256K |
| Thinking | Off by default; on only when a user turns it on for their chat |
| Model fallback | **Decided:** if Gemma 4 31B doesn't fit (measured) or its file is unavailable, the installer automatically uses **Gemma 4 26B-A4B QAT `UD-Q4_K_XL`** and tells the admin clearly. No other substitutions |
| Expected VRAM | About 43–44 GiB of 48, constant from start-up. **This is an estimate** from the model config (full-attention context ≈ 42.5 KB/token at 8-bit; sliding-window memory ≈ 0.45 GB per slot) |

**Why the pool is shared, not fixed per user:** 8 × 256K reserved per user does not fit with this model on 48 GB. A shared pool gives any one chat up to 256K, and realistic use (papers of 10K–40K tokens) leaves plenty for everyone. Per-chat compression stops any one conversation from taking over the pool.

### Web application

| Setting | Value |
|---|---|
| Front end | **Open WebUI** (version-pinned), customised, not rewritten |
| Database | SQLite (Open WebUI default) in a persistent data folder |
| Accounts | Public sign-up **off**. The admin creates accounts in the Admin Panel. The first account created becomes admin |
| Passwords | Hashed (bcrypt, Open WebUI default). Sessions signed with a secret generated at install |
| Admin reading users' chats | **Disabled** (`ENABLE_ADMIN_CHAT_ACCESS=False`) |
| Model access | `llama-server` is reachable only from the Open WebUI container, protected by an API key generated at install. Never exposed to the network |
| Network exposure | Only the web app's port is reachable on the local network |
| HTTPS | Yes, via a small reverse proxy (Caddy) with a locally generated certificate. **Decided:** each browser shows a one-time "connection not private" warning, which users accept (the user guide shows exactly what to click). No per-client certificate install. Plain HTTP is not exposed |
| Address | `https://<machine-name>.local` (survives IP changes); the IP address is printed as a fallback. The certificate covers both |
| Branding | Product name, logo and welcome text set from config ("Lab Paper Assistant" by default) |
| Features hidden | RAG/documents, web search, image generation, voice, extra model connections, community sharing |

### Presets

These are shipped as seed data and loaded into a fresh database on first start. All of them include the safety rules: preserve meaning; never add claims, results or citations; keep LaTeX commands, citation keys, labels, references, math and numbers exactly; return only the edited text unless asked otherwise.

1. Copy-edit (light touch)
2. Clarity and flow
3. Concise (cut 20–30%)
4. Match reference style (the user pastes a reference paper first, then their own sections)
5. Abstract polish
6. Reviewer feedback (critique, no rewriting)
7. General writing assistant

### Context compression (custom Open WebUI plugin)

- **Scope:** one conversation only. Other chats and users are never touched.
- **Manual:** a **Compress** button in the chat.
- **Automatic:** before each request, the plugin counts the conversation's tokens with the model's own tokenizer (`llama-server /tokenize`). Above **90% of 256K**, it compresses before sending.
- **What is compressed:** older back-and-forth becomes a summary, made by the same model with thinking off. **Kept word for word:** the system prompt, the most recent turns, and any message the user marked as the source document (e.g. the paper being edited or the reference paper).
- **Visible to the user:** a short notice says the chat was compressed. The full original history stays in the database and stays visible in the chat history.
- **Hard limit:** a request still above 256K after compression is refused with a plain message ("This conversation is too long; start a new chat or remove the pasted document").

### Thinking switch (custom Open WebUI plugin)

A **Think** on/off toggle in the chat input, off by default. When on, requests carry `chat_template_kwargs: {"enable_thinking": true}`. Presets never change it.

## 6. Installation experience (the contract)

**Linux** (all in one terminal):

```
git clone https://github.com/Raza2006/text-editing-llm.git
cd text-editing-llm
sudo ./install.sh
```

**Windows** (PowerShell opened with "Run as administrator"):

```
winget install --id Git.Git -e --source winget
git clone https://github.com/Raza2006/text-editing-llm.git
cd text-editing-llm
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

On Windows, if WSL2 or Docker Desktop has to be installed, the installer asks for **one reboot**. Running the same last command after the reboot continues where it stopped. *Builder's call:* the installer refreshes PATH itself, so `git` works right after `winget` in the same window; if that fails, the README says "close and reopen PowerShell as administrator". The fewer-than-10-commands promise holds.

**Windows after a restart (decided):** Docker Desktop starts when a user logs in, so someone logs into Windows after a restart (or Windows is set to log in automatically). The service doesn't run while nobody is logged in. The installer sets Docker Desktop to start at login.

**The installer must:**

1. Check, in plain English: OS version, administrator rights, NVIDIA GPU present, driver new enough for the CUDA build, VRAM ≥ 46 GB usable (warn and adapt below that), free disk ≥ 100 GB, internet reachable, and hardware virtualization (Windows). *Builder's call on drivers:* on Ubuntu, a missing or too-old NVIDIA driver is installed automatically (`ubuntu-drivers`), followed by one reboot, with Secure Boot handling explained in plain words if it's needed. On Windows, the installer stops with the exact NVIDIA download link and continues after it's installed.
2. Install missing prerequisites itself (Docker Engine + NVIDIA Container Toolkit on Linux; WSL2 + Docker Desktop on Windows). It never asks the user to edit a file.
3. Generate all secrets (web app secret, model API key) into a local `.env` that is never committed.
4. Download the model with resume support and verify its SHA-256 checksum.
5. **Measure** what fits: start the engine with the 512K pool, and if it runs out of memory, step down (448K → 384K → 320K → 256K) and save the largest size that leaves at least **2 GiB of actually free** GPU memory (measured, so a monitor attached to the card is accounted for). Below 256K with the 31B model, switch to the approved fallback model and repeat. Report the chosen model and size.
6. Start everything, wait until healthy, load the presets, and print:
   - the address to open (`https://<machine-ip>`),
   - "Create the first account now: it becomes the administrator",
   - where the admin guide is.
7. Be **idempotent and resumable:** running it again never breaks anything and continues unfinished steps.
8. On any failure, stop with: what failed, in plain words; the exact command or action to fix it; and where the full log is.

**After installation**, a single helper command, `./textedit` on Linux or `.\textedit.ps1` on Windows, with:

| Command | Does |
|---|---|
| `status` | Is everything running? Address, GPU memory, users online |
| `start` / `stop` / `restart` | As named |
| `doctor` | Re-runs every check and prints fixes |
| `backup` / `restore <file>` | Database backup and restore |
| `update` | Pulls the repo, then images and model only if the pinned versions changed, then restarts |
| `logs` | The last lines of each component's log |
| `uninstall` | Stops and removes containers. Keeps data unless `--delete-data` is given |

**Automatic behaviour:**
- containers restart on crash and after reboot;
- a **nightly database backup** to `data/backups/`, keeping the last 14;
- health checks on every component.

## 7. Repository layout (proposed)

```
text-editing-llm/
├── README.md                 what it is + the install commands + troubleshooting
├── LICENSE                   (licence chosen by author, see open items)
├── install.sh / install.ps1
├── textedit / textedit.ps1   helper command
├── compose.yaml              llama-server, open-webui, caddy, backup
├── config/
│   ├── defaults.env          all tunables (model, context, slots, branding) with comments
│   ├── models.lock           model repo, file, size, sha256; image versions
│   └── Caddyfile
├── webui/
│   ├── presets/*.json        the 7 presets (seed data)
│   ├── functions/compress.py
│   ├── functions/think_toggle.py
│   └── seed.py               loads presets/functions into a fresh database via the API
├── scripts/                  shared install/check logic (bash + PowerShell)
├── tests/                    unit tests for plugins; end-to-end test with a tiny CPU model
├── docs/
│   ├── design.md             this document
│   ├── admin-guide.md        start/stop, add users, backup/restore, update (with screenshots)
│   └── user-guide.md         one page for end users
└── .gitignore                .env, data/, models/, logs/, *.db
```

Never in git: `.env`, `data/` (database, backups), `models/`, logs.

## 8. Testing (no target GPU available to the author)

- **Unit tests:** the compression plugin (token counting, the 90% trigger, what's kept and what's summarised, the hard limit, no effect on other chats), the think toggle, and preset seeding.
- **End-to-end on CI (GitHub Actions, Linux, CPU):** the full compose stack with a **tiny GGUF model** standing in for Gemma, then: create the admin, add a user, chat, compress, back up and restore, restart.
- **Script checks:** shellcheck for bash, PSScriptAnalyzer for PowerShell, and a Windows CI run of the PowerShell installer's checks (without the GPU parts).
- **On the real machine:** the installer's memory probe and `doctor` act as the acceptance test. A short "first run checklist" in the admin guide covers what to verify.
- **Load test script** (`textedit loadtest`): 8 simultaneous users, including 2 long contexts, reporting latency, for the acceptance run.

## 9. Security summary

- Passwords hashed; secrets generated per install and never committed.
- Sign-up off; admin-created accounts only; admin cannot read other users' chats in the app.
- The model engine is never exposed outside the Docker network and requires an API key.
- HTTPS on the local network.
- Data at rest (the SQLite database) isn't encrypted by the app. The admin guide recommends OS disk encryption (BitLocker / LUKS).

## 10. Left to the builder

- Exact pinned versions: llama.cpp image (must include sm_120), Open WebUI, Caddy. Record them in `config/models.lock`.
- Confirm the exact Hugging Face repos and files for Gemma 4 31B QAT and the 26B-A4B fallback (`UD-Q4_K_XL`), and record their SHA-256 checksums.
- Confirm that per-request `enable_thinking: true` overrides the server default in the pinned llama.cpp version, and adjust the server flag if not.
- How Open WebUI enforces the 256K per-chat cap together with the compression plugin (filter inlet), and how users mark a message as "the document".
- Implementation details of the memory probe, the HTTPS certificate, and backup scheduling inside compose.
- Wording of all user-facing messages (plain English, no jargon).
