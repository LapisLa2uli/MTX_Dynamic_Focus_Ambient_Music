"""Resume-download a large file with HTTP Range, single connection, retries."""
from __future__ import annotations
import os, sys, time, urllib.request

URL = sys.argv[1]
PATH = sys.argv[2]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def head_len(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])

def main() -> int:
    expected = head_len(URL)
    print(f"expected={expected}", flush=True)
    # Remove aria2 control so we treat file as contiguous prefix resume
    ctrl = PATH + ".aria2"
    if os.path.exists(ctrl):
        os.remove(ctrl)
        print("removed aria2 control", flush=True)
    # If sparse oversized incomplete, truncate to 0 and restart? Check if size > expected
    cur = os.path.getsize(PATH) if os.path.exists(PATH) else 0
    if cur > expected:
        print(f"oversized sparse file {cur}; truncating", flush=True)
        os.remove(PATH)
        cur = 0
    retries = 0
    while cur < expected:
        try:
            req = urllib.request.Request(URL, headers={
                "User-Agent": UA,
                "Range": f"bytes={cur}-",
            })
            with urllib.request.urlopen(req, timeout=120) as r:
                mode = "ab" if cur else "wb"
                with open(PATH, mode) as out:
                    while True:
                        chunk = r.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        cur += len(chunk)
                        if cur % (32 * 1024 * 1024) < 1024 * 1024:
                            pct = 100.0 * cur / expected
                            print(f"progress {cur}/{expected} ({pct:.1f}%)", flush=True)
            cur = os.path.getsize(PATH)
            retries = 0
        except Exception as e:
            retries += 1
            print(f"retry {retries} at {cur}: {type(e).__name__}: {e}", flush=True)
            time.sleep(min(2 * retries, 30))
            cur = os.path.getsize(PATH) if os.path.exists(PATH) else 0
            if retries > 200:
                return 1
    print(f"COMPLETE {cur}", flush=True)
    return 0 if cur == expected else 2

if __name__ == "__main__":
    raise SystemExit(main())
