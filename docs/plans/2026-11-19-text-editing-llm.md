# text-editing-llm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A repository that a non-technical person clones onto a Linux or Windows machine with a 48 GB NVIDIA GPU, then installs with fewer than 10 pasted commands, giving a private multi-user paper-editing assistant.

**Architecture:** Docker Compose runs four long-lived services: `llama` (llama.cpp server with Gemma 4), `webui` (Open WebUI), `caddy` (HTTPS) and `backup`. Two one-shot services run with the same `manager` image: `setup` (model download and checksum) and `seed` (presets and functions loaded through the Open WebUI API). Host scripts (`install.sh` / `install.ps1`, `textedit` / `textedit.ps1`) only install prerequisites, write `.env` and call `docker compose`. All logic that must behave identically on both systems lives inside containers, in Python (`manager/`) or POSIX shell (`llama/entrypoint.sh`).

**Tech Stack:** Docker Compose; llama.cpp `server-cuda-b12004`; Open WebUI `v0.13.4`; Caddy `2.11.9-alpine`; Python 3.12 (stdlib only plus `pytest` for tests); bash; PowerShell 5.1+.

**Spec:** `docs/design.md`

## Global Constraints

- The installer pastes **fewer than 10 commands** per OS. Every failure prints what failed in plain English, the exact fix, and the log path.
- No secrets, user data, models or databases in git: `.env`, `data/`, logs are git-ignored.
- Commits are authored by "Mohammed Raza <Raza2006@users.noreply.github.com>" with no co-author or tool attribution lines.
- Model: `unsloth/gemma-4-31B-it-qat-GGUF` / `gemma-4-31B-it-qat-UD-Q4_K_XL.gguf`, 17287670048 bytes, sha256 `00b5a7c497f0c8934033088c10a7fa9a4c015e46ee6d89e9c6890650ba5d0e71`.
- Fallback: `unsloth/gemma-4-26B-A4B-it-qat-GGUF` / `gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf`, 14249047104 bytes, sha256 `a7c5bc715f5ff8e99a3e8901ce7d2b42b402c669bf24f7c5250747633d0f5891`.
- CI test model: `ggml-org/gemma-3-270m-it-GGUF` / `gemma-3-270m-it-Q8_0.gguf`, 291545600 bytes, sha256 `0ef57d2c838458a1952664260dcba38e5bdda37494f3af732f06e4add24068e3`.
- Engine flags: `--parallel 8 --kv-unified -fa on -ctk q8_0 -ctv q8_0 --reasoning off --no-webui --api-key-file /run/secrets/llama_key --host 0.0.0.0 --port 8080 -ngl 99 --jinja`.
- Context pool candidates, in order: 524288, 458752, 393216, 327680, 262144. Keep the first that starts and leaves ≥ 2048 MiB free GPU memory. Per-chat limit = `min(262144, pool // 2)`. Compression triggers at 90% of the per-chat limit.
- Thinking is off unless the user's Think toggle sends `chat_template_kwargs.enable_thinking=true`.
- Open WebUI: `ENABLE_SIGNUP=False`, `ENABLE_ADMIN_CHAT_ACCESS=False`, `ENABLE_OLLAMA_API=False`, `ENABLE_WEB_SEARCH=False`, `ENABLE_IMAGE_GENERATION=False`, `ENABLE_CODE_INTERPRETER=False`, `ENABLE_COMMUNITY_SHARING=False`, `ENABLE_EVALUATION_ARENA_MODELS=False`, `USER_PERMISSIONS_CHAT_FILE_UPLOAD=False`, `ENABLE_VERSION_UPDATE_CHECK=False`, `WEBUI_NAME` from config (default "Lab Paper Assistant"). The "Open WebUI" branding stays (the licence allows changes only for ≤50 users, so we don't alter it).
- All user-facing text is plain English with no jargon.

## Review Focus

- **Re-running the installer** after a partial run (killed download, reboot on Windows) must resume, not duplicate users or presets, and not regenerate secrets. Pinned by tests in Tasks 2, 5 and 8.
- **A wrong admin password or email format typed at the prompt** must be re-asked, not crash. Pinned in Task 8.
- **A GPU with less than 40 GiB** must pick the fallback model and say so. Pinned in Task 2.
- **A conversation that is still over the limit after compression** must get a plain refusal, not a model error. Pinned in Task 4.
- **Restoring a backup while the app is running** must stop `webui` first and restart it after. Pinned in Task 6.

## Design adjustments (builder's calls, recorded in docs/design.md)

1. The installer **asks for the admin email and password** and creates the admin account automatically (Open WebUI `WEBUI_ADMIN_EMAIL`/`WEBUI_ADMIN_PASSWORD`, which also turns sign-up off). That way presets can be loaded during install. The password is used once for seeding; seeding then stores an admin API key in the `webui-data` volume and blanks the password in `.env`.
2. The model is chosen by total GPU memory (≥ 40 GiB → 31B, otherwise the 26B fallback), not by probe failure. The probe only picks the pool size.
3. The manual **Compress** button marks the chat. The compressed version is used from the user's next message, and the button says so.

---

### Task 1: Repository skeleton and pinned configuration

**Files:**
- Create: `.gitignore`, `.gitattributes`, `LICENSE` (Apache-2.0, "Copyright 2026 Mohammed Raza"), `config/defaults.env`, `config/versions.env`, `README.md` (stub, filled in Task 11)

**Interfaces:**
- Produces: `config/versions.env` keys `LLAMA_IMAGE`, `WEBUI_IMAGE`, `CADDY_IMAGE`, `PYTHON_IMAGE`, `MODEL_PRIMARY_REPO`, `MODEL_PRIMARY_FILE`, `MODEL_PRIMARY_SIZE`, `MODEL_PRIMARY_SHA256`, `MODEL_FALLBACK_*` (same four), `MODEL_CI_*` (same four). `config/defaults.env` keys `WEBUI_NAME`, `HTTPS_PORT=443`, `HTTP_PORT=80`, `PARALLEL=8`, `CTX_CANDIDATES="524288 458752 393216 327680 262144"`, `CTX_MAX_PER_CHAT=262144`, `COMPRESS_AT=0.9`, `MIN_FREE_MIB=2048`, `MIN_VRAM_PRIMARY_MIB=40960`, `BACKUP_KEEP=14`, `BACKUP_HOUR=3`.
- `.gitattributes`: `*.sh text eol=lf`, `textedit text eol=lf`, `*.ps1 text eol=crlf`, `*.py text eol=lf`.
- `.gitignore`: `.env`, `data/`, `*.log`, `__pycache__/`, `.pytest_cache/`.

- [ ] Step 1: Create the files with the values above (image tags: `ghcr.io/ggml-org/llama.cpp:server-cuda-b12004`, `ghcr.io/open-webui/open-webui:v0.13.4`, `caddy:2.11.9-alpine`, `python:3.12-slim`).
- [ ] Step 2: Verify: `grep -c = config/versions.env` prints 16; `git check-ignore .env data/x` prints both paths.
- [ ] Step 3: Commit `chore: repository skeleton and pinned versions`.

### Task 2: Manager package: settings, model choice, download

**Files:**
- Create: `manager/Dockerfile` (FROM `${PYTHON_IMAGE}`, copies `manager/`, entrypoint `python -m manager`), `manager/manager/__init__.py`, `__main__.py`, `settings.py`, `download.py`, `gpu.py`
- Test: `manager/tests/test_settings.py`, `test_download.py`, `test_gpu.py`

**Interfaces:**
- `settings.load(paths: list[str]) -> dict[str,str]`: later files override earlier ones; then `os.environ` overrides.
- `gpu.total_vram_mib(nvidia_smi_output: str) -> int`: parses `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits` (first GPU).
- `gpu.choose_model(total_mib: int, cfg: dict) -> str`: returns `"primary"` or `"fallback"`.
- `download.fetch(url: str, dest: str, size: int, sha256: str, progress=print) -> None`: resumes with an HTTP Range header from a `.part` file, verifies size and sha256, then atomically renames. On a mismatch it deletes `.part` and raises `DownloadError` with a plain message.
- CLI `python -m manager setup`: reads `/config/*.env`, chooses the model (`MODEL_SET=ci` forces the CI model; `FORCE_MODEL=primary|fallback` overrides), downloads into `/models/`, and writes `/models/selected.env` with `MODEL_FILE=...` and `MODEL_ALIAS=gemma`.

- [ ] Step 1: Write the failing tests: `test_load_override_order`, `test_total_vram_parses_first_gpu("49140\n24564\n") == 49140`, `test_choose_model(40960)=="primary"`, `test_choose_model(32607)=="fallback"`, `test_fetch_resumes_from_partial` (a local `http.server` serving bytes with Range support; a pre-written `.part` with the first half; asserts the final sha256 and that the server saw `Range: bytes=N-`), `test_fetch_bad_checksum_raises_and_cleans`, `test_fetch_skips_when_complete` (no HTTP request is made).
- [ ] Step 2: `pytest manager/tests -q`: these fail.
- [ ] Step 3: Implement.
- [ ] Step 4: `pytest manager/tests -q`: these pass.
- [ ] Step 5: Commit `feat(manager): settings, GPU-based model choice, resumable verified download`.

### Task 3: Engine start-up with context-pool probe

**Files:**
- Create: `llama/entrypoint.sh` (POSIX sh, run as the `llama` service entrypoint)
- Test: `tests/test_llama_entrypoint.py` (runs the script with stub `llama-server`, `nvidia-smi` and `curl` on PATH)

**Behaviour:**
- Reads `/models/selected.env`. If `/state/ctx.env` exists and `REPROBE` is unset, it starts directly with the saved `CTX`.
- Otherwise, for each value in `CTX_CANDIDATES`: start `llama-server` with the flags in Global Constraints plus `-c $CTX -m /models/$MODEL_FILE --alias $MODEL_ALIAS` in the background, then poll `curl -sf localhost:8080/health` for up to 600 s. If the process exits, try the next value. If healthy, read free MiB with `nvidia-smi --query-gpu=memory.free`. If free < `MIN_FREE_MIB`, kill it and try the next value; else write `CTX=$CTX` and `PER_CHAT=$(min 262144 CTX/2)` to `/state/ctx.env`, then `wait`.
- If no candidate works: print `ERROR: The model does not fit on this GPU even with the smallest setting. Run: textedit doctor` and exit 3.
- `CPU_ONLY=1` (CI) skips `nvidia-smi` and the free-memory check, and omits `-ngl`.

- [ ] Step 1: Write the failing tests: `test_first_candidate_fits` (CTX=524288 saved), `test_steps_down_on_crash` (the stub exits for 524288 and 458752; 393216 saved), `test_steps_down_on_low_free_memory` (the stub reports 1500 MiB free for 524288, 3000 for 458752; 458752 saved), `test_reuses_saved_ctx_without_probe`, `test_nothing_fits_exit_3_with_message`, `test_per_chat_is_half_pool_capped` (262144 → PER_CHAT=131072).
- [ ] Step 2: Run: they fail.
- [ ] Step 3: Implement.
- [ ] Step 4: Run: they pass. `shellcheck -s sh llama/entrypoint.sh` is clean.
- [ ] Step 5: Commit `feat(llama): start-up probe that picks the largest context pool that fits`.

### Task 4: Open WebUI functions: compression and the Think toggle

**Files:**
- Create: `webui/functions/context_compressor.py` (Filter, global, always on), `webui/functions/compress_button.py` (Action, global), `webui/functions/think_toggle.py` (Filter with `toggle = True`, global)
- Test: `webui/tests/test_context_compressor.py`, `test_compress_button.py`, `test_think_toggle.py`

**Interfaces:**
- Compressor `Valves`: `llama_url="http://llama:8080"`, `llama_key=""`, `per_chat_limit=262144`, `compress_at=0.9`, `keep_recent_turns=4`, `cache_path="/app/backend/data/compression_cache.json"`.
- `Filter.inlet(body: dict, __metadata__: dict, __event_emitter__=None) -> dict`
  1. Count tokens of all messages via `POST {llama_url}/tokenize` (sum of `len(tokens)`).
  2. If the chat is marked "force" in the cache, or count > `compress_at * per_chat_limit`: keep the system message, the last `keep_recent_turns` user+assistant pairs, and any user message starting with `[DOCUMENT]` word for word. Replace everything else with a single system message `"Summary of earlier conversation: ..."`. The summary comes from `POST {llama_url}/v1/chat/completions` (thinking off, temperature 0.2, prompt: summarise decisions, preferences and open tasks; under 1,500 words). Cache by `chat_id` together with the id of the last message covered, so the summary is reused until new messages are added, and clear "force".
  3. Emit status "Earlier messages were summarised to keep this chat within its size limit."
  4. If the count is still > `per_chat_limit`: raise `Exception("This conversation is too long for the assistant. Please start a new chat, or paste a shorter part of the document.")`.
- Compress button: `Action.action(body: dict, __event_emitter__=None) -> None` writes `force=true` for `body["chat_id"]` in the cache and emits "This chat will be compressed before your next message."
- Think toggle: `Filter.toggle = True`; `inlet(body) -> body` with `body.setdefault("chat_template_kwargs", {})["enable_thinking"] = True`.

- [ ] Step 1: Write the failing tests with a stub HTTP server for `/tokenize` and `/v1/chat/completions`: `test_under_threshold_unchanged`, `test_over_threshold_summarises_and_keeps_recent_and_document`, `test_summary_cached_and_reused`, `test_other_chat_untouched`, `test_force_flag_compresses_once`, `test_still_too_long_raises_plain_message`, `test_think_toggle_sets_kwarg`, `test_button_sets_force`.
- [ ] Step 2: Run: they fail.
- [ ] Step 3: Implement. Each function is a single self-contained file (Open WebUI loads each file on its own). The cache helpers are duplicated in the two compression files.
- [ ] Step 4: Run: they pass.
- [ ] Step 5: Commit `feat(webui): context compression filter, compress button, think toggle`.

### Task 5: Presets and seeding

**Files:**
- Create: `webui/presets/*.json` (7 files: `copy-edit`, `clarity-flow`, `concise`, `match-style`, `abstract-polish`, `reviewer`, `general`), `manager/manager/seed.py`
- Test: `manager/tests/test_seed.py` (stub Open WebUI API)

**Interfaces:**
- Preset JSON: `{"id","name","description","system","temperature"}`. Every `system` starts with the shared safety rules from design §5. `match-style` tells users to paste the reference paper first, starting with `[DOCUMENT]`.
- `seed.run(base_url, admin_email, admin_password, api_key_path, functions_dir, presets_dir, valves: dict) -> None`:
  - Authenticate with the API key from `api_key_path` if present. Otherwise `POST /api/v1/auths/signin`, create an API key with `POST /api/v1/auths/api_key`, and save it to `api_key_path` (chmod 600).
  - For each function file: create it (`POST /api/v1/functions/create`) or update it (`/id/{id}/update`) if it already exists; ensure it's active and global (`/id/{id}/toggle`, `/id/{id}/toggle/global`, toggling only when the state differs); set valves (`/id/{id}/valves/update`).
  - For each preset: create it (`POST /api/v1/models/create`) or update it (`/api/v1/models/model/update`) with `base_model_id="gemma"`, `params={"system":..., "temperature":...}`, and `access_grants=[{"principal_type":"user","principal_id":"*","permission":"read"}]`.
  - Hide the raw `gemma` model from users.
- CLI `python -m manager seed`.

- [ ] Step 1: Write the failing tests: `test_first_run_signs_in_and_saves_key`, `test_second_run_uses_key_and_updates_not_duplicates`, `test_functions_made_global_and_active_once`, `test_presets_public_and_based_on_gemma`, `test_all_presets_contain_safety_rules`.
- [ ] Step 2: Run: they fail.
- [ ] Step 3: Implement (`urllib` only). Check the exact API key route and the "hide model" call against Open WebUI v0.13.4 source before coding.
- [ ] Step 4: Run: they pass.
- [ ] Step 5: Commit `feat: seven editing presets and idempotent seeding`.

### Task 6: Backup and restore

**Files:**
- Create: `manager/manager/backup.py`
- Test: `manager/tests/test_backup.py`

**Interfaces:**
- `backup.make(db_path, out_dir, keep:int) -> str`: uses the sqlite3 online backup API to write `webui-YYYYmmdd-HHMMSS.db` and deletes the oldest beyond `keep`. Returns the path.
- `backup.restore(src, db_path) -> None`: checks with `PRAGMA integrity_check`, then copies over `db_path` (the caller stops `webui` first).
- `backup.loop(db_path, out_dir, keep, hour)`: sleeps until `hour`:00 local time, then runs `make` daily. CLI `python -m manager backup-loop|backup-now|restore <file>`.

- [ ] Step 1: Write the failing tests: `test_make_creates_consistent_copy_while_writer_open`, `test_retention_keeps_last_n`, `test_restore_rejects_corrupt_file`, `test_restore_replaces_db`.
- [ ] Step 2–4: Fail, implement, pass.
- [ ] Step 5: Commit `feat(manager): nightly database backup and safe restore`.

### Task 7: Compose stack and HTTPS

**Files:**
- Create: `compose.yaml`, `compose.ci.yaml`, `caddy/Caddyfile`

**Interfaces:**
- Services:
  - `setup` (build `manager/`, profile-less one-shot, GPU requested so it can run `nvidia-smi`, volumes `models:/models`, `./config:/config:ro`);
  - `llama` (`${LLAMA_IMAGE}`, entrypoint `/entrypoint.sh` bind-mounted, GPU all, volumes `models`, `llama-state:/state`, secret `llama_key`, `depends_on setup: service_completed_successfully`, healthcheck `curl -sf localhost:8080/health`, `restart: unless-stopped`);
  - `webui` (`${WEBUI_IMAGE}`, env from Global Constraints plus `OPENAI_API_BASE_URLS=http://llama:8080/v1`, `OPENAI_API_KEYS=${LLAMA_API_KEY}`, `WEBUI_SECRET_KEY`, `WEBUI_ADMIN_*`, `DEFAULT_MODELS=copy-edit`, volume `webui-data:/app/backend/data`, depends on `llama` healthy, `restart: unless-stopped`);
  - `caddy` (ports `${HTTP_PORT}:80`, `${HTTPS_PORT}:443`, env `SITE_ADDRESSES`, volume `caddy-data`, `restart: unless-stopped`);
  - `backup` (manager image, `backup-loop`, volumes `webui-data:/data:ro`, `./data/backups:/backups`, `restart: unless-stopped`);
  - `seed` (manager image, profile `tools`).
- Only `caddy` publishes ports.
- `Caddyfile`: `{$SITE_ADDRESSES} { tls internal; reverse_proxy webui:8080 }` (WebSockets pass through).
- `compose.ci.yaml` overrides: llama image `server-b12004` (CPU), `CPU_ONLY=1`, `MODEL_SET=ci`, `CTX_CANDIDATES="16384 8192"`, no GPU reservations, `HTTPS_PORT=8443`.

- [ ] Step 1: With a sample `.env`: `docker compose config -q` and `docker compose -f compose.yaml -f compose.ci.yaml config -q` both exit 0.
- [ ] Step 2: `docker compose config | grep -c published` shows only caddy's two ports.
- [ ] Step 3: Commit `feat: compose stack with HTTPS, health checks and restarts`.

### Task 8: Linux installer and helper

**Files:**
- Create: `install.sh`, `textedit`, `scripts/lib.sh` (shared bash functions)
- Test: `tests/test_install_sh.py` (sources `scripts/lib.sh` with stubbed commands)

**Behaviour of `install.sh`** (run with sudo; resumable via `data/install-state`):
1. Check, with plain messages: Ubuntu 22.04/24.04, root, NVIDIA GPU (`lspci`), driver ≥ 570 (`nvidia-smi`; if missing or old: `ubuntu-drivers install`, then "Please restart the computer and run the same command again"), ≥ 100 GB free, internet.
2. Install Docker Engine + compose plugin + NVIDIA Container Toolkit if missing (official apt repos); `nvidia-ctk runtime configure --runtime=docker`; restart docker; verify with `docker run --rm --gpus all ${LLAMA_IMAGE} nvidia-smi`.
3. Write `.env` once: random `WEBUI_SECRET_KEY` (48 chars) and `LLAMA_API_KEY` (40 chars), plus `SITE_ADDRESSES` (`$(hostname).local`, each LAN IPv4, `localhost`). Prompt for the admin email (re-ask until it matches `^[^@ ]+@[^@ ]+\.[^@ ]+$`) and password (≥ 8 chars, typed twice, re-ask on mismatch). Write `data/secrets/llama_key`. Set mode 600 on both.
4. `docker compose pull && docker compose build`; `docker compose run --rm setup`; `docker compose up -d`; wait for `webui` healthy (up to 30 min, showing progress); `docker compose run --rm seed`; blank `WEBUI_ADMIN_PASSWORD` in `.env`.
5. Print the box: address(es), "Log in with the admin email and password you just chose", and `docs/admin-guide.md`.
- `textedit` subcommands: `status`, `start`, `stop`, `restart`, `logs`, `doctor`, `backup`, `restore <file>`, `update`, `loadtest`, `uninstall [--delete-data]`. Each maps to `docker compose` or a `manager` command.

- [ ] Step 1: Write the failing tests: `test_email_reasked_until_valid`, `test_password_mismatch_reasked`, `test_env_written_once_not_regenerated`, `test_driver_too_old_message`, `test_state_file_skips_done_steps`.
- [ ] Step 2–4: Fail, implement, pass. `shellcheck install.sh textedit scripts/lib.sh` is clean.
- [ ] Step 5: Commit `feat: Linux installer and textedit helper`.

### Task 9: Windows installer and helper

**Files:**
- Create: `install.ps1`, `textedit.ps1`, `scripts/lib.ps1`

**Behaviour:** the same steps as Task 8, adapted:
- Requires administrator (otherwise: "Close this window, right-click PowerShell, choose Run as administrator").
- Refreshes PATH from the registry first, so `git` and `docker` are found right after `winget`.
- Checks the NVIDIA driver ≥ 570 (`nvidia-smi`; if missing, prints the NVIDIA driver download link and exits).
- `wsl --install --no-distribution` if WSL is missing, then asks for a reboot with "run the same command again after restarting".
- `winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements`, then starts Docker Desktop and waits for `docker info` (up to 5 min).
- Sets Docker Desktop to start at login.
- Secrets come from `[System.Security.Cryptography.RandomNumberGenerator]`. `.env` and `data\secrets` get ACLs limited to Administrators.
- `textedit.ps1` has the same subcommands as `textedit`.

- [ ] Step 1: The functions are written to be testable: email and password validation and `.env` writing in `scripts/lib.ps1`. Pester tests are in `tests/install.Tests.ps1`: `email re-asked`, `password mismatch re-asked`, `.env written once`.
- [ ] Step 2: Implement.
- [ ] Step 3: Verified in CI on `windows-latest`: `Invoke-ScriptAnalyzer -Severity Error` is clean and the Pester tests pass.
- [ ] Step 4: Commit `feat: Windows installer and textedit helper`.

### Task 10: Continuous integration and end-to-end test

**Files:**
- Create: `.github/workflows/ci.yml`, `tests/e2e.sh`

**Jobs:**
- `unit` (ubuntu): `pytest`, shellcheck.
- `windows` (windows-latest): PSScriptAnalyzer and Pester.
- `e2e` (ubuntu): writes a test `.env` non-interactively (`install.sh --ci`), then runs the CI stack. `tests/e2e.sh` checks:
  1. admin login through `https://localhost:8443` with `-k`;
  2. 7 presets are listed;
  3. a chat completion through `copy-edit` returns text;
  4. with `per_chat_limit` set low by valve, a long chat gets the summary status;
  5. the Think toggle adds `enable_thinking`;
  6. `textedit backup` then `restore` works;
  7. `docker compose restart` comes back healthy;
  8. a non-admin added via the API can't list another user's chats.
- [ ] Step 1: Write the workflow and script.
- [ ] Step 2: Run `tests/e2e.sh` against the stub-free CI stack on GitHub. All jobs green.
- [ ] Step 3: Commit `ci: unit, Windows and end-to-end checks`.

### Task 11: Documentation

**Files:**
- Create or complete: `README.md`, `docs/admin-guide.md`, `docs/user-guide.md`. Modify: `docs/design.md` (record the three builder's calls above).

**Content:**
- README: what it is; requirements table; the exact commands for Linux (3) and Windows (4); what happens next; troubleshooting table (each `doctor` message → fix).
- Admin guide: first login, adding users, presets, backup and restore, update, uninstall, the browser warning, changing the admin password, disk encryption advice, first-run checklist plus `textedit loadtest`.
- User guide (one page): logging in, picking a preset, the `[DOCUMENT]` convention, Think, Compress, "always read the edits".

- [ ] Step 1: Write them. Every command in the docs must exist in the scripts (`grep` check).
- [ ] Step 2: Commit `docs: README, admin and user guides`.
