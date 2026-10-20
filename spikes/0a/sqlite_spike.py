"""Stage 0a spike: SQLite durability cost and single-writer lock. Usage: sqlite_spike.py <dir>"""

import fcntl
import os
import sqlite3
import statistics
import subprocess
import sys
import time

d = sys.argv[1]
os.makedirs(d, exist_ok=True)


def bench(sync: str, n: int = 2000) -> dict:
    path = os.path.join(d, f"bench-{sync}.db")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)
    db = sqlite3.connect(path, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(f"PRAGMA synchronous={sync}")
    db.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, conversation TEXT, type TEXT, payload TEXT)")
    db.execute("CREATE TABLE actions (id TEXT PRIMARY KEY, state TEXT, updated INTEGER)")
    payload = '{"v":1,"type":"action.started","payload":{"k":"' + "x" * 300 + '"}}'
    lat = []
    for i in range(n):
        t0 = time.perf_counter()
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO events (conversation, type, payload) VALUES (?, ?, ?)", ("c1", "action.started", payload))
        db.execute("INSERT OR REPLACE INTO actions VALUES (?, ?, ?)", (f"a{i % 50}", "STARTED", i))
        db.execute("COMMIT")
        lat.append((time.perf_counter() - t0) * 1000)
    db.close()
    lat.sort()
    return {"sync": sync, "n": n, "p50_ms": round(statistics.median(lat), 3),
            "p99_ms": round(lat[int(0.99 * n)], 3), "max_ms": round(lat[-1], 3),
            "commits_per_s": round(n / (sum(lat) / 1000))}


def lock_test() -> str:
    lock_path = os.path.join(d, "mei.lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    probe = ("import fcntl,os,sys;fd=os.open(sys.argv[1],os.O_RDWR);"
             "\ntry:\n fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);print('second instance GOT lock')"
             "\nexcept BlockingIOError:\n print('second instance refused (EWOULDBLOCK)')")
    held = subprocess.run([sys.executable, "-c", probe, lock_path], capture_output=True, text=True).stdout.strip()
    os.close(fd)  # simulate the first instance dying: the kernel drops the lock with the fd
    freed = subprocess.run([sys.executable, "-c", probe, lock_path], capture_output=True, text=True).stdout.strip()
    return f"while held: {held}; after holder exit: {freed}"


fs = subprocess.run(["stat", "-f", "-c", "%T", d], capture_output=True, text=True).stdout.strip()
print(f"python {sys.version.split()[0]} sqlite {sqlite3.sqlite_version} fs={fs}")
for sync in ("FULL", "NORMAL"):
    print(bench(sync))
print("lock:", lock_test())
con = sqlite3.connect(":memory:")
con.enable_load_extension(True)
print("enable_load_extension: available")
