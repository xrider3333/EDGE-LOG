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


def count(kind, n=1):
    with _lock:
        _tot[kind] = _tot.get(kind, 0) + int(n)
        _tot["calls"] += 1
    _maybe_flush()


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
