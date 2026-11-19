import os, sqlite3, time
import pytest
from manager import backup


def make_db(path, rows=100):
    con = sqlite3.connect(path)
    con.execute("create table chat(id integer primary key, text)")
    con.executemany("insert into chat(text) values (?)", [(f"msg {i}",) for i in range(rows)])
    con.commit()
    return con


def count(path):
    return sqlite3.connect(path).execute("select count(*) from chat").fetchone()[0]


def test_make_creates_consistent_copy_while_writer_open(tmp_path):
    db = tmp_path / "webui.db"
    con = make_db(str(db))
    con.execute("insert into chat(text) values ('uncommitted')")  # open write transaction
    out = backup.make(str(db), str(tmp_path / "b"), keep=14)
    assert os.path.basename(out).startswith("webui-") and out.endswith(".db")
    assert count(out) == 100


def test_retention_keeps_last_n(tmp_path):
    db = tmp_path / "webui.db"; make_db(str(db)).close()
    outdir = tmp_path / "b"; outdir.mkdir()
    for i in range(5):
        (outdir / f"webui-2026010{i}-000000.db").write_text("old")
    backup.make(str(db), str(outdir), keep=3)
    names = sorted(os.listdir(outdir))
    assert len(names) == 3 and "webui-20260100-000000.db" not in names


def test_restore_rejects_corrupt_file(tmp_path):
    db = tmp_path / "webui.db"; make_db(str(db)).close()
    bad = tmp_path / "bad.db"; bad.write_bytes(b"not a database" * 100)
    with pytest.raises(backup.BackupError) as e:
        backup.restore(str(bad), str(db))
    assert "damaged" in str(e.value)
    assert count(str(db)) == 100


def test_restore_replaces_db(tmp_path):
    db = tmp_path / "webui.db"; make_db(str(db), rows=5).close()
    src = tmp_path / "src.db"; make_db(str(src), rows=42).close()
    backup.restore(str(src), str(db))
    assert count(str(db)) == 42


def test_seconds_until_hour():
    t = time.mktime((2026, 1, 1, 2, 30, 0, 0, 0, -1))
    assert backup.seconds_until(3, now=t) == 1800
    assert backup.seconds_until(2, now=t) == 23.5 * 3600
