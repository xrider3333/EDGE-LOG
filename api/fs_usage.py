"""api/fs_usage.py -- per-caller Firestore read / write counters (MANAGER GO 11-18, after the 11-13 429).

On 11-13 the whole Firebase project ran out of its free 50k reads/day at about 14:30 ET and the
box's lease went blind for the rest of the session; the box itself had made ~1,700 reads, and nothing
could say who made the other 45k. This module counts, in every Python process that imports `api`,
the Firestore reads and writes it makes, and appends a per-process tally to a LOCAL JSONL file:

    PC:  C:/EdgeLog/fs_usage/<YYYY-MM-DD>.jsonl      box: /home/ubuntu/edgelog/fs_usage/<date>.jsonl
    (override: EDGELOG_FS_USAGE_DIR; off: EDGELOG_FS_USAGE=0)

It adds NO Firestore load: counting wraps the SDK's own calls, the tally goes to disk only. The date is
the quota day (midnight US/Pacific -- the free-tier reset). tools/fs_usage_report.py sums the files
(plus the web page's own tally doc) into a top-readers table.

How each call is billed (Firestore pricing): a document get = 1 read; a query = 1 read per document
returned (min 1); a listener = 1 read per document in each snapshot's changes; a commit = 1 write per
document written. Hooks: Query.stream (CollectionReference.get/stream and Query.get go through it),
DocumentReference.get, Client.get_all, WriteBatch.commit, Transaction._commit, on_snapshot callbacks.
"""
import atexit
import datetime as _dt
import json
import os
import socket
import sys
import threading

FLUSH_EVERY_SEC = 300

# ---- quota breaker (MANAGER 11-26, after the second 429) ----------------------------------------
# The free tier is 50,000 reads and 20,000 writes a Pacific day. On 11-26 bulk backfills took the day
# to 31.5k reads and 18.2k writes with the market shut, and the runner went into back-off: the LIVE
# box publish is what must never be starved. So every process that imports `api` now stops itself
# before the day's last slice is gone, and only the live path may spend it.
#
# A caller is EXEMPT (may spend to the free-tier limit) when it is in CRITICAL_CALLERS or when it
# sets EDGELOG_FS_CRITICAL=1. Everything else -- backfills, series rebuilds, research, reports --
# raises FsQuotaBreaker once the day crosses the reserve. The day total is read from the SAME local
# JSONL the tallies go to, so the check costs no Firestore reads and no network.
FREE_READS, FREE_WRITES = 50000, 20000
RESERVE_READS = int(os.environ.get("EDGELOG_FS_RESERVE_READS", "42000"))
RESERVE_WRITES = int(os.environ.get("EDGELOG_FS_RESERVE_WRITES", "16000"))
# EXEMPT = the live path only: the runner's publish / lease loop, the box, the executors and the
# counter's own reader. EVERYTHING ELSE IS NON-CRITICAL BY DEFAULT -- a job only has to be named
# here (or set EDGELOG_FS_CRITICAL=1) to spend the reserve, never the other way round.
CRITICAL_CALLERS = {
    "runner", "api.runner", "qqq_exec", "box_publish", "box_lease", "keel", "webull", "webull_exec",
    "ownbar_shadow", "paper_publish", "fs_usage_report",
}
_day_cache = {"day": None, "reads": 0, "writes": 0, "at": 0.0, "pid_seen": 0}


class FsQuotaBreaker(RuntimeError):
    """This job was stopped so the live box publish keeps its slice of today's free tier."""


def _exempt():
    if os.environ.get("EDGELOG_FS_CRITICAL") == "1":
        return True
    if os.environ.get("EDGELOG_FS_BREAKER", "1") == "0":
        return True
    return caller_name() in CRITICAL_CALLERS


def day_totals(max_age_sec=60):
    """Today's counted reads / writes from the local JSONL, including this process. Never raises."""
    import time
    now = time.time()
    day = _quota_day()
    if _day_cache["day"] == day and now - _day_cache["at"] < max_age_sec:
        base_r, base_w = _day_cache["reads"], _day_cache["writes"]
    else:
        base_r = base_w = 0
        try:
            with open(os.path.join(out_dir(), day + ".jsonl"), "r", encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                    except Exception:
                        continue
                    if r.get("pid") == os.getpid():
                        continue          # this process's own rows are added live below
                    base_r += int(r.get("reads", 0) or 0) + int(r.get("listen_reads", 0) or 0)
                    base_w += int(r.get("writes", 0) or 0)
        except Exception:
            pass
        _day_cache.update({"day": day, "reads": base_r, "writes": base_w, "at": now})
    with _lock:
        mine_r = _tot.get("reads", 0) + _tot.get("listen_reads", 0)
        mine_w = _tot.get("writes", 0)
    return base_r + mine_r, base_w + mine_w


def quota_check():
    """Raise FsQuotaBreaker when a non-critical caller has reached the day's reserve."""
    if _exempt():
        return
    reads, writes = day_totals()
    if reads >= RESERVE_READS or writes >= RESERVE_WRITES:
        flush()
        raise FsQuotaBreaker(
            "Firestore quota breaker: today is at %s reads / %s writes (reserve %s / %s, free tier "
            "%s / %s). '%s' stopped so the live box publish keeps its slice. Re-run after the "
            "Pacific midnight reset, or set EDGELOG_FS_CRITICAL=1 if this IS the live path."
            % (reads, writes, RESERVE_READS, RESERVE_WRITES, FREE_READS, FREE_WRITES, caller_name()))

_lock = threading.Lock()
_tot = {"reads": 0, "writes": 0, "listen_reads": 0, "calls": 0}
_flushed = {"reads": 0, "writes": 0, "listen_reads": 0, "calls": 0}
_state = {"installed": False, "last_flush": 0.0, "caller": None}


def _quota_day(now=None):
    try:
        from zoneinfo import ZoneInfo
        return (now or _dt.datetime.now(ZoneInfo("America/Los_Angeles"))).date().isoformat()
    except Exception:
        return _dt.datetime.utcnow().date().isoformat()


def out_dir():
    d = os.environ.get("EDGELOG_FS_USAGE_DIR")
    if d:
        return d
    return "C:/EdgeLog/fs_usage" if os.name == "nt" else "/home/ubuntu/edgelog/fs_usage"


def caller_name():
    """Who is reading: EDGELOG_FS_CALLER, else the script / module that started the process."""
    if _state["caller"]:
        return _state["caller"]
    n = os.environ.get("EDGELOG_FS_CALLER")
    if not n:
        argv0 = (sys.argv[0] if sys.argv else "") or "python"
        base = os.path.basename(argv0)
        if base in ("-m", "-c", "") or base.startswith("__main__"):
            base = (getattr(sys.modules.get("__main__"), "__spec__", None) or type("x", (), {"name": "python"})).name
        if base.endswith(".py"):
            base = base[:-3]
        if base == "__main__":     # python -m pkg.mod
            base = getattr(getattr(sys.modules.get("__main__"), "__spec__", None), "name", "python") or "python"
        n = base
    _state["caller"] = n
    return n


def set_caller(name):
    """Rename this process's caller from here on; returns the name it had (None if unset)."""
    with _lock:
        was = _state["caller"]
        _state["caller"] = name or None
    return was


class as_caller(object):
    """`with fs_usage.as_caller('runner_job'):` -- tag one stretch of work, restore after.

    The runner is one long-lived process that both publishes live data and runs queued backtests
    and series builds. Under the one label 'runner' the bulk work inherited the live path's
    exemption, which is how 11-26 went to 22k reads with the market shut."""

    def __init__(self, name):
        self.name, self._was, self._had = name, None, False

    def __enter__(self):
        self._had = True
        self._was = set_caller(self.name)
        return self

    def __exit__(self, *exc):
        if self._had:
            flush()                 # bill the tagged stretch under its own name before restoring
            set_caller(self._was)
        return False


def count(kind, n=1):
    with _lock:
        _tot[kind] = _tot.get(kind, 0) + int(n)
        _tot["calls"] += 1
        calls = _tot["calls"]
    _maybe_flush()
    # the breaker reads a local file, so check it every 50 calls rather than on every one
    if calls % 50 == 0:
        quota_check()


def snapshot():
    with _lock:
        return dict(_tot)


def _maybe_flush(force=False):
    import time
    now = time.time()
    if not force and now - _state["last_flush"] < FLUSH_EVERY_SEC:
        return
    _state["last_flush"] = now
    flush()


def flush():
    """Append this process's delta since the last flush to today's JSONL. Never raises."""
    if os.environ.get("EDGELOG_FS_USAGE", "1") == "0":
        return None
    if "pytest" in sys.modules and not os.environ.get("EDGELOG_FS_USAGE_DIR"):
        return None
    with _lock:
        delta = {k: _tot[k] - _flushed.get(k, 0) for k in _tot}
        if not any(delta[k] for k in ("reads", "writes", "listen_reads")):
            return None
        _flushed.update(_tot)
    rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"), "day": _quota_day(),
           "host": socket.gethostname(), "caller": caller_name(), "pid": os.getpid(), **delta}
    try:
        d = out_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, rec["day"] + ".jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        return None
    return rec


def _wrap_stream(orig):
    def stream(self, *a, **k):
        it = orig(self, *a, **k)
        n = 0
        try:
            for doc in it:
                n += 1
                yield doc
        finally:
            count("reads", max(n, 1))
    stream.__wrapped__ = orig
    return stream


def _wrap_get_all(orig):
    def get_all(self, *a, **k):
        n = 0
        try:
            for doc in orig(self, *a, **k):
                n += 1
                yield doc
        finally:
            count("reads", max(n, 1))
    get_all.__wrapped__ = orig
    return get_all


def _wrap_doc_get(orig):
    def get(self, *a, **k):
        try:
            return orig(self, *a, **k)
        finally:
            count("reads", 1)
    get.__wrapped__ = orig
    return get


def _wrap_commit(orig, attr="_write_pbs"):
    def commit(self, *a, **k):
        n = len(getattr(self, attr, None) or []) or 1
        try:
            return orig(self, *a, **k)
        finally:
            count("writes", n)
    commit.__wrapped__ = orig
    return commit


def _wrap_on_snapshot(orig):
    def on_snapshot(self, callback, *a, **k):
        def cb(docs, changes, read_time, *rest):
            try:
                count("listen_reads", len(changes or []) or (len(docs) if isinstance(docs, list) else 1))
            except Exception:
                pass
            return callback(docs, changes, read_time, *rest)
        return orig(self, cb, *a, **k)
    on_snapshot.__wrapped__ = orig
    return on_snapshot


def install():
    """Patch the Firestore SDK once per process. Safe to call many times; never raises."""
    if _state["installed"] or os.environ.get("EDGELOG_FS_USAGE", "1") == "0":
        return False
    try:
        from google.cloud.firestore_v1 import batch, client, document, query, transaction
    except Exception:
        return False
    try:
        query.Query.stream = _wrap_stream(query.Query.stream)
        document.DocumentReference.get = _wrap_doc_get(document.DocumentReference.get)
        client.Client.get_all = _wrap_get_all(client.Client.get_all)
        batch.WriteBatch.commit = _wrap_commit(batch.WriteBatch.commit)
        if hasattr(transaction.Transaction, "_commit"):
            transaction.Transaction._commit = _wrap_commit(transaction.Transaction._commit)
        document.DocumentReference.on_snapshot = _wrap_on_snapshot(document.DocumentReference.on_snapshot)
        query.Query.on_snapshot = _wrap_on_snapshot(query.Query.on_snapshot)
    except Exception:
        return False
    _state["installed"] = True
    atexit.register(flush)
    return True



class _AfterImport:
    """Meta-path hook: patch the SDK right after `google.cloud.firestore` (which loads every
    firestore_v1 submodule) finishes importing -- so `import api` costs nothing for processes that
    never touch Firestore."""
    TARGETS = ("google.cloud.firestore", "google.cloud.firestore_v1")

    def find_spec(self, name, path=None, target=None):
        if name not in self.TARGETS:
            return None
        for f in sys.meta_path:
            if f is self or not hasattr(f, "find_spec"):
                continue
            spec = f.find_spec(name, path, target)
            if spec is not None and spec.loader is not None and hasattr(spec.loader, "exec_module"):
                orig = spec.loader.exec_module

                def exec_module(module, _orig=orig):
                    _orig(module)
                    install()
                spec.loader.exec_module = exec_module
                return spec
            if spec is not None:
                return spec
        return None


def enable():
    """Called from api/__init__: patch now if the SDK is already loaded, else right after its import."""
    if os.environ.get("EDGELOG_FS_USAGE", "1") == "0":
        return
    if "google.cloud.firestore_v1.client" in sys.modules:
        install()
        return
    if not any(isinstance(f, _AfterImport) for f in sys.meta_path):
        sys.meta_path.insert(0, _AfterImport())
