"""Simulates several people using the assistant at the same moment."""
import concurrent.futures
import json
import time
import urllib.request

PARAGRAPH = ("In this paper we are proposing a novel method which is improving the accuracy of segmentation by "
             "4.2% as compare to \\cite{smith2023}, and it also reduce the computation time significantly. ")


def _ask(url, key, text):
    body = json.dumps({"model": "gemma", "temperature": 0.2, "max_tokens": 200,
                       "messages": [{"role": "user", "content": "Copy-edit this text:\n" + text}]}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=3600) as r:
        out = json.load(r)
    return time.time() - t, out.get("timings", {})


def run(url, key, users=8, long_users=2, long_tokens=200_000, out=print):
    long_text = PARAGRAPH * max(1, long_tokens // 45)
    jobs = [long_text if i < long_users else PARAGRAPH for i in range(users)]
    out(f"Sending {users} requests at the same moment ({long_users} with a long document)...")
    ok = True
    with concurrent.futures.ThreadPoolExecutor(max_workers=users) as pool:
        futures = [pool.submit(_ask, url, key, text) for text in jobs]
        for i, f in enumerate(futures):
            kind = "long document" if i < long_users else "paragraph"
            try:
                secs, timings = f.result()
                out(f"  user {i + 1} ({kind}): answered in {secs:.1f} s "
                    f"(read {timings.get('prompt_n', '?')} tokens)")
            except Exception as e:
                ok = False
                out(f"  user {i + 1} ({kind}): FAILED ({e})")
    out(f"All {users} users got an answer." if ok else "Some requests failed: see above.")
    return ok


def main(args):
    with open("/run/secrets/llama_key", encoding="utf-8") as f:
        key = f.read().strip()
    long_tokens = int(args[0]) if args else 200_000
    return run("http://llama:8080", key, long_tokens=long_tokens)
