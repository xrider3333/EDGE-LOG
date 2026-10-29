"""RAM/GPU guard (AUTOMATIONS.md B2) - tells heavy work to yield when free RAM is low.

  python tools/ram_guard.py check                 free RAM/VRAM, quiet mode, qwen_lab STOP; exit 0 = ok, 2 = yield
  python tools/ram_guard.py watch [--interval 60] [--once]
      free RAM < 6 GB  -> ONE plain phone push (at most every 30 min) + write C:\\EdgeLog\\qwen_lab\\STOP
      free RAM > 8 GB for 10 min -> remove the STOP only if this guard wrote it (header line)
  While Strata (local server, 127.0.0.1:8080, holds 20+ GB by design) is serving (MANAGER #213):
      no STOP is written, a guard-written STOP is removed, and the push fires only when
      free RAM < 1 GB for 3 checks in a row (still at most every 30 min).
Never kills processes, never touches Ollama models. State: C:\\EdgeLog\\state\\ram_guard.json.
Importable: should_yield(min_free_ram_gb=6.0, min_free_vram_gb=None, backend="ollama") -> (bool, reason).
  backend="strata" never yields on RAM; "ollama" (default, the lab) still yields below 6 GB.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HOME = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
LOW_GB = 6.0
CLEAR_GB = 8.0
CLEAR_HOLD_S = 600
PUSH_EVERY_S = 1800
STOP_HEADER = "# written by tools/ram_guard.py (B2)"
STRATA_URL = os.environ.get("STRATA_URL") or "http://127.0.0.1:8080/v1"
STRATA_MODEL = "qwen3.8-flash-next-gyro-gyro-s"
STRATA_TIMEOUT_S = 3
STRATA_CRIT_GB = 1.0
STRATA_CRIT_CHECKS = 3
_TOOLS = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_TOOLS)


def stop_path():
    return os.environ.get("RAM_GUARD_STOP") or os.path.join(HOME, "qwen_lab", "STOP")


def state_path():
    return os.environ.get("RAM_GUARD_STATE") or os.path.join(HOME, "state", "ram_guard.json")


def free_ram_gb():
    """Available physical RAM in GB (psutil; ctypes fallback on Windows); None when unknown."""
    try:
        import psutil
        return psutil.virtual_memory().available / 1024 ** 3
    except ImportError:
        pass
    if os.name == "nt":
        import ctypes

        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong),
                        ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
        m = _MS()
        m.dwLength = ctypes.sizeof(_MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return m.ullAvailPhys / 1024 ** 3
    return None


def free_vram_gb():
    """Largest free VRAM across GPUs in GB from nvidia-smi; None when absent."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        vals = [float(x) for x in out.split() if x.strip()]
        return max(vals) / 1024 if vals else None
    except Exception:
        return None


def strata_serving(timeout=STRATA_TIMEOUT_S):
    """True when GET {STRATA_URL}/models answers within `timeout` s and lists STRATA_MODEL as loaded."""
    try:
        with urllib.request.urlopen(STRATA_URL.rstrip("/") + "/models", timeout=timeout) as r:
            doc = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return False
    for m in (doc.get("data") or []) if isinstance(doc, dict) else []:
        if not isinstance(m, dict) or m.get("id") != STRATA_MODEL:
            continue
        st = m.get("status")
        if isinstance(st, dict):
            st = st.get("value") or st.get("status")
        if str(st or "").lower() == "loaded":
            return True
    return False


def quiet_on():
    """(on, why) from tools/quiet.py current_state; (False, 'unknown ...') on any error."""
    try:
        if _TOOLS not in sys.path:
            sys.path.insert(0, _TOOLS)
        import quiet
        st = quiet.current_state()
        return bool(st.get("quiet")), st.get("why")
    except Exception as e:
        return False, "unknown (%s)" % type(e).__name__


def should_yield(min_free_ram_gb=LOW_GB, min_free_vram_gb=None, ram_fn=None, vram_fn=None,
                 backend="ollama"):
    """(True, reason) when heavy work must wait. Unknown readings never force a yield.
    backend="strata": never yield on RAM (Strata holds its RAM by design); "ollama" unchanged."""
    if backend not in ("ollama", "strata"):
        raise ValueError("backend must be 'ollama' or 'strata'")
    ram = (ram_fn or free_ram_gb)()
    if backend == "ollama" and ram is not None and ram < min_free_ram_gb:
        return True, "free RAM %.1f GB < %.1f GB" % (ram, min_free_ram_gb)
    if min_free_vram_gb is not None:
        vram = (vram_fn or free_vram_gb)()
        if vram is not None and vram < min_free_vram_gb:
            return True, "free VRAM %.1f GB < %.1f GB" % (vram, min_free_vram_gb)
    return False, "free RAM %s GB" % ("?" if ram is None else "%.1f" % ram)


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    os.replace(tmp, path)


def send_push(ram_gb, log=print, strata=False):
    """One plain phone note through api/ntfy_push (plain + push_result). Returns (ok, detail); never raises."""
    try:
        if _REPO not in sys.path:
            sys.path.insert(0, _REPO)
        from api import ntfy_push
        if strata:
            note = ntfy_push.plain("PC memory", "heads up", None,
                                   "PC about to run out of memory while Strata serves - free RAM %.1f GB"
                                   % ram_gb, "close something heavy or stop Strata", priority="default")
        else:
            note = ntfy_push.plain("PC memory", "heads up", None,
                                   "free RAM %.1f GB (below %.0f GB) - Qwen lab paused" % (ram_gb, LOW_GB),
                                   "close something heavy if you can", priority="default")
        return ntfy_push.push_result(note["message"], title=note["title"], priority=note["priority"], log=log)
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:80])


def _guard_wrote_stop(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.readline().strip() == STOP_HEADER
    except OSError:
        return False


def _watch_strata(st, ram, now, stp, pusher, log):
    """Strata serving: never write the STOP, remove our own, push only on < 1 GB x3."""
    st["clear_since"] = None
    if _guard_wrote_stop(stp):
        os.remove(stp)
        log("ram_guard: Strata serving - removed its own STOP")
    st["strata_low_count"] = (int(st.get("strata_low_count") or 0) + 1) if ram < STRATA_CRIT_GB else 0
    if st["strata_low_count"] >= STRATA_CRIT_CHECKS:
        last = st.get("last_push")
        if last is None or now - float(last) >= PUSH_EVERY_S:
            ok, detail = (pusher or (lambda r: send_push(r, strata=True)))(ram)
            st["last_push"] = now
            st["last_push_result"] = [ok, detail]
            log("ram_guard: Strata push %s (%s)" % (ok, detail))


def watch_once(now=None, ram_fn=None, pusher=None, log=print, strata_fn=None):
    now = time.time() if now is None else now
    ram = (ram_fn or free_ram_gb)()
    sp, stp = state_path(), stop_path()
    st = _load(sp)
    if ram is None:
        log("ram_guard: free RAM unknown - nothing done")
        return st
    strata = bool((strata_fn or strata_serving)())
    st["strata_serving"] = strata
    if strata:
        _watch_strata(st, ram, now, stp, pusher, log)
    elif ram < LOW_GB:
        st["clear_since"] = None
        if not os.path.exists(stp):
            os.makedirs(os.path.dirname(stp), exist_ok=True)
            with open(stp, "w", encoding="utf-8") as f:
                f.write("%s\nreason: free RAM %.1f GB < %.1f GB at %s\n"
                        % (STOP_HEADER, ram, LOW_GB, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))))
            log("ram_guard: wrote %s" % stp)
        last = st.get("last_push")
        if last is None or now - float(last) >= PUSH_EVERY_S:
            ok, detail = (pusher or send_push)(ram)
            st["last_push"] = now
            st["last_push_result"] = [ok, detail]
            log("ram_guard: push %s (%s)" % (ok, detail))
    elif ram > CLEAR_GB:
        st["clear_since"] = st.get("clear_since") or now
        if now - st["clear_since"] >= CLEAR_HOLD_S and _guard_wrote_stop(stp):
            os.remove(stp)
            log("ram_guard: RAM above %.0f GB for 10 min - removed its own STOP" % CLEAR_GB)
    else:
        st["clear_since"] = None
    if not strata:
        st["strata_low_count"] = 0
    st["last_ram_gb"] = round(ram, 2)
    st["last_check"] = now
    _save(sp, st)
    return st


def check(log=print):
    ram, vram = free_ram_gb(), free_vram_gb()
    q, why = quiet_on()
    stop = os.path.exists(stop_path())
    y, reason = should_yield(ram_fn=lambda: ram)
    log("free RAM : %s GB" % ("?" if ram is None else "%.1f" % ram))
    log("free VRAM: %s GB" % ("n/a" if vram is None else "%.1f" % vram))
    log("quiet    : %s" % (("ON (%s)" % why) if q else "off"))
    log("STOP     : %s (%s)" % ("present" if stop else "absent", stop_path()))
    must = y or q or stop
    log("verdict  : %s" % (("YIELD - " + (reason if y else "quiet" if q else "STOP file")) if must else "ok"))
    return 2 if must else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="RAM/GPU guard (AUTOMATIONS.md B2)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    w = sub.add_parser("watch")
    w.add_argument("--interval", type=float, default=60)
    w.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        return check()
    while True:
        watch_once()
        if a.once:
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
