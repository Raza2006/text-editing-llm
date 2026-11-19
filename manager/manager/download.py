"""Resumable, checksum-verified downloads."""
import hashlib
import os
import urllib.request


class DownloadError(Exception):
    pass


def _sha256(path, chunk=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _stamp(dest):
    st = os.stat(dest)
    return f"{st.st_size}:{int(st.st_mtime)}"


def _mark_verified(dest, sha256):
    with open(dest + ".verified", "w", encoding="utf-8") as f:
        f.write(f"{sha256} {_stamp(dest)}")


def _already_verified(dest, sha256):
    try:
        with open(dest + ".verified", encoding="utf-8") as f:
            return f.read().strip() == f"{sha256} {_stamp(dest)}"
    except OSError:
        return False


def fetch(url, dest, size, sha256, progress=print):
    size = int(size)
    if os.path.exists(dest) and os.path.getsize(dest) == size:
        if _already_verified(dest, sha256):
            return
        progress(f"Checking the model file that is already downloaded ({os.path.basename(dest)})...")
        if _sha256(dest) == sha256:
            _mark_verified(dest, sha256)
            progress("The model file is complete and correct.")
            return
        os.remove(dest)

    part = dest + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if have > size:
        os.remove(part)
        have = 0
    if have < size:
        req = urllib.request.Request(url, headers={"User-Agent": "text-editing-llm"})
        if have:
            req.add_header("Range", f"bytes={have}-")
            progress(f"Resuming the download from {have / 1e9:.1f} GB...")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp, open(part, "ab" if have else "wb") as out:
                if have and resp.status != 206:
                    out.seek(0)
                    out.truncate()
                    have = 0
                last = 0
                while True:
                    block = resp.read(4 * 1024 * 1024)
                    if not block:
                        break
                    out.write(block)
                    have += len(block)
                    if have - last >= 500_000_000 or have == size:
                        progress(f"Downloaded {have / 1e9:.1f} of {size / 1e9:.1f} GB")
                        last = have
        except OSError as e:
            raise DownloadError(
                "The download was interrupted (" + str(e) + "). Check the internet connection and run the "
                "same command again: it continues where it stopped."
            ) from e

    if os.path.getsize(part) < size:
        raise DownloadError(
            "The download was interrupted. Check the internet connection and run the same command again: "
            "it continues where it stopped."
        )
    if os.path.getsize(part) != size or _sha256(part) != sha256:
        os.remove(part)
        raise DownloadError(
            "The downloaded model file is damaged and was deleted. Run the same command again to download it again."
        )
    os.replace(part, dest)
    _mark_verified(dest, sha256)
    progress("The model file is complete and correct.")
