"""Resume a search across shutdowns (owner 10-31: 'auto-validates should remember where they were
when paused or shut down').

Two saves, both on disk under C:/EdgeLog/state/resume_ckpt/ (EDGELOG_RESUME_DIR overrides):
  - a WHOLE run_auto result (Stage A of a validate, a plain auto search, either walk-forward
    scheme of Stage B) once that call returns, and
  - each walk-forward FOLD row as that fold finishes, so a sign-out mid-Stage-B loses at most the
    folds that were still running.
A restarted job calls run_auto with the same arguments, finds the saves and skips that work.

The key is everything that can change a result: the strategy's file closure sha (the trial
cache's own), the master file's path + size + mtime, the engine's own source (auto.py,
validate.py, this file, wf_pool.py, trial_cache.py), and every run_auto argument except the
progress callback and the worker count (folds are identical at any worker count). Any change ->
a different key -> nothing is reused. A key is never guessed: if a field cannot be read the
call runs with no saves.

Kill switch AUGUR_RESUME=0. Saves older than KEEP_DAYS are pruned on write.
"""
import hashlib
import os
import pickle
import threading
import time

KEEP_DAYS = 21
_ENGINE_FILES = ("auto.py", "validate.py", "resume_ckpt.py", "wf_pool.py", "trial_cache.py",
                 "data.py")
_IGNORED = ("progress_cb", "workers")
_local = threading.local()


def enabled():
    return os.environ.get("AUGUR_RESUME", "1") != "0"


def root():
    return (os.environ.get("EDGELOG_RESUME_DIR")
            or os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "state",
                            "resume_ckpt"))


def _engine_sha():
    h = hashlib.sha256()
    here = os.path.dirname(os.path.abspath(__file__))
    for name in _ENGINE_FILES:
        with open(os.path.join(here, name), "rb") as fh:
            h.update(name.encode() + b"\0" + fh.read())
    return h.hexdigest()


def call_key(strategy, kw):
    """The key of one run_auto call, or None when it cannot be sourced cleanly."""
    if not enabled() or not isinstance(strategy, str) or kw.get("arrays") is not None:
        return None
    try:
        from .strategies import strategy_closure_sha
        from .data import find_master  # noqa: F401 (and UPLOADS below)
        ssha = strategy_closure_sha(strategy)
        if not ssha:
            return None
        m = kw.get("master")
        if m is None:
            m = find_master(kw.get("instrument"), kw.get("timeframe", "5m"),
                            kw.get("session", "rth"), kw.get("source"))
        if not isinstance(m, dict) or not m.get("filename"):
            return None
        from .data import UPLOADS
        path = os.path.join(UPLOADS, m["filename"])
        if not path or not os.path.isfile(path):
            return None
        st = os.stat(path)
        args = sorted((k, repr(v)) for k, v in kw.items() if k not in _IGNORED)
        blob = repr((ssha, os.path.abspath(path), st.st_size, int(st.st_mtime),
                     _engine_sha(), args))
        return hashlib.sha256(blob.encode()).hexdigest()[:40]
    except Exception:
        return None


def _path(key, part):
    return os.path.join(root(), key[:2], "%s_%s.pkl" % (key, part))


def load(key, part):
    if not key:
        return None
    p = _path(key, part)
    try:
        with open(p, "rb") as fh:
            return pickle.load(fh)
    except Exception:
        return None


def save(key, part, obj):
    """Atomic write (tmp + replace). Never raises: a failed save only costs a replay."""
    if not key:
        return False
    p = _path(key, part)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".%d.tmp" % os.getpid()
        with open(tmp, "wb") as fh:
            pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, p)
        _prune()
        return True
    except Exception as e:
        print("[resume] could not save %s/%s: %s" % (key[:8], part, e))
        return False


_last_prune = [0.0]


def _prune():
    now = time.time()
    if now - _last_prune[0] < 3600:
        return
    _last_prune[0] = now
    cut = now - KEEP_DAYS * 86400
    for dp, _dn, fns in os.walk(root()):
        for fn in fns:
            fp = os.path.join(dp, fn)
            try:
                if os.path.getmtime(fp) < cut:
                    os.remove(fp)
            except OSError:
                pass


# the key of the run_auto call now running on this thread, so the fold loop can save per fold
def set_current(key):
    _local.key = key


def current():
    return getattr(_local, "key", None)
