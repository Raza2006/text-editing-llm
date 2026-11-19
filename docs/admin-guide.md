# Administrator guide

In this guide, `textedit` means `./textedit` on Linux and `.\textedit` on Windows. Run commands in the project folder.

## 1. First login

1. Open the address the installer printed (or run `textedit status`).
2. The browser warns "Your connection is not private". Click **Advanced → Continue** (Chrome/Edge) or **Advanced → Accept the risk** (Firefox). This happens once per browser.
3. Log in with the administrator email and password you chose during installation.
4. **Recommended:** change your password in **Settings (your name, bottom left) → Account**.

## 2. Adding and removing people

Only people you add can log in. Nobody can register on their own.

**To add someone:**
1. Click your name (bottom left), then **Admin Panel → Users**.
2. Click **+** (Add User).
3. Enter their name, email and a temporary password. Leave the role as **user**.
4. Send them the address and their temporary password privately, plus [user-guide.md](user-guide.md). Ask them to change the password after logging in.

**To remove someone:** in **Admin Panel → Users**, open the person's menu and choose **Delete**. To pause their access instead, change their role to **pending**.

**Privacy:** each person sees only their own chats. As an administrator, you can't open other people's chats either (this is switched off on purpose).

## 3. Editing modes (presets)

Users pick a mode from the model menu at the top of a chat:

| Mode | Use it to |
|---|---|
| Copy-edit (light touch) | Fix grammar, spelling and punctuation only |
| Clarity and flow | Rephrase awkward sentences and improve transitions |
| Make concise | Cut 20–30% without losing content |
| Match a reference style | Edit your text in the style of a reference paper |
| Polish an abstract | Restructure and tighten an abstract |
| Reviewer feedback | Get peer-review style comments without rewriting |
| General writing assistant | Ask anything about academic writing |

Every mode keeps LaTeX, citations, math and numbers exactly as written, and never adds claims. You'll also see **Gemma (raw model, admin only)**: the model without editing instructions, visible only to administrators.

To change a mode's instructions, edit `webui/presets/<mode>.json` (and `webui/presets/_rules.txt` for the shared rules), then run `textedit seed`.

## 4. Backups

- A backup of all accounts and chats is made **every night at 03:00** into `data/backups`. The last 14 are kept.
- To make one now: `textedit backup`.
- To restore one: `textedit restore webui-YYYYmmdd-HHMMSS.db` (run `textedit restore` alone to list them). The assistant stops for a few seconds while restoring.
- **Copy `data/backups` to another drive regularly.** If this computer's disk fails, the backups go with it.

## 5. Updating

```
textedit update
```

This gets the latest version from GitHub, downloads new parts if needed, restarts, and re-installs the editing modes. Users' accounts and chats are kept.

## 6. Settings

`config/defaults.env` holds the settings you may change, each with an explanation. After a change, run `textedit restart`. Common ones:

| Setting | Meaning |
|---|---|
| `WEBUI_NAME` | Name shown in the browser tab |
| `HTTPS_PORT` / `HTTP_PORT` | Change them if another program already uses ports 443/80; users then add `:port` to the address |
| `PARALLEL` | How many conversations the model handles at the same moment (default 8) |
| `BACKUP_KEEP`, `BACKUP_HOUR` | How many nightly backups to keep, and when they run |

The model's memory size is measured automatically the first time it starts. After changing the graphics card, run `textedit doctor --reprobe`.

## 7. Restarts and power cuts

- **Linux:** everything starts automatically when the computer starts.
- **Windows:** someone must **log in to Windows** after a restart; Docker Desktop then starts the assistant within a minute or two. To avoid this, set Windows to log in automatically (search for "netplwiz").

## 8. Checking that it handles 8 people

```
textedit loadtest
```

This simulates 8 people at once, 2 of them with very long documents, and reports how long each waited. Expect the short edits within a minute, and the long-document requests within several minutes.

## 9. Troubleshooting

Start with `textedit doctor`. It checks each part and prints the fix. Then:

| Problem | Fix |
|---|---|
| Page doesn't load | `textedit status`. If parts are stopped: `textedit start`. On Windows, check that Docker Desktop is running. |
| "Docker cannot use the graphics card" | Restart the computer. On Windows, update the NVIDIA driver. |
| "does not fit on this GPU" | Close games, video editors or other AI tools using the GPU, then `textedit doctor --reprobe`. |
| Very slow answers | Normal while someone works on a very long document. Check `textedit status` for GPU memory. If it's always slow, check that no other program uses the GPU. |
| Someone forgot their password | Admin Panel → Users → edit the person → set a new password. |
| You forgot the admin password | If there is a second administrator, they can set a new one in Admin Panel → Users. Otherwise ask a developer to reset it in the database (accounts and chats are not lost). |
| Disk full | Delete old files in `data/backups`, or free space elsewhere. |

### Re-installing the presets

`textedit seed` re-installs the editing modes and features. It uses a saved setup key. If it says the key no longer works:

1. Open `.env` and set `WEBUI_ADMIN_PASSWORD=` to your **current** admin password.
2. Run `textedit seed`.
3. Remove the password from `.env` again (leave `WEBUI_ADMIN_PASSWORD=` empty).

## 10. Security notes

- Passwords are stored hashed. The secret keys in `.env` are created on this computer and never leave it. **Never share or upload `.env`.**
- The AI model can only be reached through the web page, never directly from the network.
- Chats are stored in a database on this computer. For extra protection, enable disk encryption (BitLocker on Windows, LUKS on Linux).

## 11. Uninstalling

- `textedit uninstall` removes the running parts but keeps accounts, chats and the model; `textedit start` brings them back.
- `textedit uninstall --delete-data` removes **everything**, including all accounts and chats.
