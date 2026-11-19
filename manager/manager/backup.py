"""Database backups (online, consistent) and restore."""
import glob
import os
import shutil
import sqlite3
import time

DB = "/data/webui.db"
OUT = "/backups"


class BackupError(Exception):
    pass


def make(db_path, out_dir, keep):
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, time.strftime("webui-%Y%m%d-%H%M%S.db"))
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close(); dst.close()
    files = sorted(glob.glob(os.path.join(out_dir, "webui-*.db")))
    for old in files[: max(0, len(files) - int(keep))]:
        os.remove(old)
    return dest


def restore(src, db_path):
    try:
        con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        con.close()
    except sqlite3.DatabaseError:
        ok = False
    if not ok:
        raise BackupError("That backup file is damaged or is not a backup. Nothing was changed.")
    tmp = db_path + ".restoring"
    shutil.copyfile(src, tmp)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)
    os.replace(tmp, db_path)


def seconds_until(hour, now=None):
    now = time.time() if now is None else now
    lt = time.localtime(now)
    target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, int(hour), 0, 0, 0, 0, -1))
    if target <= now:
        target += 24 * 3600
    return target - now


def main(cmd, args, cfg):
    keep = int(cfg.get("BACKUP_KEEP", "14"))
    if cmd == "backup-now":
        print("Backup saved: " + os.path.basename(make(DB, OUT, keep)))
    elif cmd == "restore":
        if not args:
            raise BackupError("Say which backup to restore, for example: textedit restore webui-20261119-030000.db")
        name = os.path.basename(args[0])
        restore(os.path.join(OUT, name), DB)
        print(f"Restored {name}.")
    else:
        while True:
            time.sleep(seconds_until(cfg.get("BACKUP_HOUR", "3")))
            try:
                print("Nightly backup saved: " + os.path.basename(make(DB, OUT, keep)), flush=True)
            except Exception as e:  # keep the loop alive
                print(f"Nightly backup failed: {e}", flush=True)
