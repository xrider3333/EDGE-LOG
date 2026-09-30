"""Reuse optimizer.py's PROVEN auto-refresh (Yahoo pull + TradingView watch-folder
ingest) from the streamlit-free runner — without re-porting hundreds of lines.

optimizer.py is the Streamlit desktop app; it `import streamlit as st` and calls
`st.set_page_config(...)` at module load, so it can't be imported directly outside a
Streamlit runtime. But the data-refresh helpers (auto_refresh_masters and friends) only
touch streamlit through `@st.cache_data` decorators — no runtime st.* calls. So we install
a tiny no-op `streamlit` shim, exec ONLY the backend half of the file (everything before
the `#  AUGUR v4.0  —  UI Layer` marker), and call its auto_refresh_masters() unchanged.

This keeps the refresh logic SINGLE-SOURCED in optimizer.py (the app and the runner share
the exact same Yahoo/ingest/master-save code), so they can never drift.
"""
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPT = os.path.join(ROOT, "optimizer.py")
_UI_MARKER = "UI Layer"   # the unique '#  AUGUR v4.0  —  UI Layer' banner line

_backend = None   # cached exec'd namespace


def _install_streamlit_shim():
    """Put a permissive no-op `streamlit` into sys.modules so the backend half imports.

    Covers the only two streamlit usages in the backend half: module-level
    set_page_config (no-op) and @st.cache_data / @st.cache_resource decorators
    (identity). Any other st.* access returns a callable/usable no-op so nothing
    crashes even if a refresh path touches one.
    """
    class _Noop:
        def __init__(self, *a, **k):
            pass

        def __call__(self, *a, **k):
            # @st.cache_data  -> used directly as a decorator: a == (fn,)
            if len(a) == 1 and callable(a[0]) and not k:
                return a[0]
            # @st.cache_data(ttl=...) -> returns a decorator
            def _deco(fn):
                return fn
            return _deco

        def __getattr__(self, name):
            return _Noop()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __getitem__(self, k):
            return _Noop()

        def __setitem__(self, k, v):
            pass

        def __bool__(self):
            return False

    st = types.ModuleType("streamlit")
    # explicit names the backend references at import time
    st.set_page_config = lambda *a, **k: None
    st.cache_data = _Noop()
    st.cache_resource = _Noop()
    st.session_state = _Noop()
    st.secrets = _Noop()
    # catch-all for anything else (st.error, st.warning, st.spinner, …)
    st.__getattr__ = lambda name: _Noop()
    sys.modules["streamlit"] = st


def _load_backend():
    """Exec the backend half of optimizer.py once; return its namespace."""
    global _backend
    if _backend is not None:
        return _backend
    if not os.path.exists(OPT):
        raise FileNotFoundError(f"optimizer.py not found at {OPT}")
    _install_streamlit_shim()
    src = open(OPT, encoding="utf-8").read()
    mk = src.index(_UI_MARKER)
    cut = src.rfind("\n", 0, mk)            # start of the marker's line
    cut = src.rfind("\n", 0, cut) + 1       # include the box-rule line above it
    backend_src = src[:cut]
    ns = {"__name__": "augur_opt_backend", "__file__": OPT, "__builtins__": __builtins__}
    # Suppress the legacy optimizer.py startup banner during exec — it prints its OWN engine
    # version (5.8.103), confusing now that EDGELOG reports a single website version. We only
    # want optimizer's data-refresh helpers, not its console noise.
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(backend_src, OPT, "exec"), ns)
    _backend = ns
    return ns


def run_auto_refresh(progress_cb=None):
    """Run optimizer.py's auto_refresh_masters() (Yahoo + watch-folder ingest).
    Returns the list of human-readable change strings (empty if nothing changed)."""
    ns = _load_backend()
    fn = ns.get("auto_refresh_masters")
    if not callable(fn):
        raise RuntimeError("auto_refresh_masters not found in optimizer backend")
    try:
        return fn(progress_cb=progress_cb) or []
    except TypeError:
        return fn() or []


# ---------------------------------------------------------------- the coarse masters
#
# WHY THIS IS SEPARATE (2026-09-30, owner GO via MANAGER). auto_refresh_masters() only knows
# how to pull 1m and 5m from Yahoo. The masters resampled ON TOP of those -- 2m, 15m, 30m and
# 60m, both roots -- were a one-time build and nothing ever topped them up, so they drifted
# months behind their own parents without anything noticing. They are now refreshed here.
#
# ONCE AN EVENING, NOT EVERY PASS. Nothing reads a 30m or 60m bar intraday: the paper legs
# and the backtests want them after the close. Rebuilding them on every 30-minute pass would
# rewrite millions of rows for no reader, so this self-gates to one run per ET day, after
# the 17:20 ET data refresh -- plus one at runner start, so a fresh fleet is never serving
# a stale coarse master.
COARSE_AFTER_ET = (17, 25)        # just behind the 17:20 ET refresh + push
COARSE_STATE = os.path.join(os.environ.get("EDGELOG_STATE_DIR", r"C:\EdgeLog"),
                            "coarse_refresh_state.json")


def _et_now():
    import pandas as pd
    return pd.Timestamp.now(tz="US/Eastern")


def coarse_refresh_due(now=None, state_path=None):
    """True when the coarse masters have not been refreshed yet on this ET day and the
    evening cutoff has passed. Reading the state must never raise: an unreadable state file
    means 'not run today', which costs one extra refresh and loses nothing."""
    now = now or _et_now()
    if (now.hour, now.minute) < COARSE_AFTER_ET:
        return False
    try:
        with open(state_path or COARSE_STATE, encoding="utf-8") as fh:
            return json.load(fh).get("last_et_date") != str(now.date())
    except Exception:
        return True


def _mark_coarse_done(now=None, state_path=None):
    now = now or _et_now()
    try:
        path = state_path or COARSE_STATE
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"last_et_date": str(now.date()), "at": now.isoformat()}, fh)
    except Exception:
        pass          # a state file we cannot write means we retry; that is the safe way round


def run_coarse_refresh(force=False, now=None, state_path=None):
    """Top up the resampled masters. Returns the report lines, empty when not due.

    It reuses tools/refresh_resampled_masters.py unchanged, so the runner and a human at a
    prompt get byte-identical behaviour -- including its strict reproduction check, which
    refuses to append to a master it cannot rebuild from its own parent.
    """
    if not force and not coarse_refresh_due(now, state_path):
        return []
    import subprocess
    tool = os.path.join(ROOT, "tools", "refresh_resampled_masters.py")
    out = subprocess.run([sys.executable, tool, "--apply"], cwd=ROOT,
                         capture_output=True, text=True, timeout=1800)
    lines = [ln.strip() for ln in (out.stdout or "").splitlines()
             if ln.strip().startswith(("NOADJ_", "REPAIRED", "WARNING", "STOPPING"))
             or ": backed up ->" in ln]
    _mark_coarse_done(now, state_path)
    return lines


# ------------------------------------------------ the roll-corrected (ADJ_/FADJ_) masters
#
# WHY THIS IS HERE TOO (2026-09-30). The 19 ADJ_/FADJ_ masters are rebuilt from the no-adjust
# ones, and NOTHING scheduled that rebuild - it had been run by hand exactly once, on 09-28, so
# by 09-30 anything pinned to them was reading two-day-old bars while the no-adjust masters
# were current. Frontier's vol-target shadow signal and any ES book run past 09-14 were both
# affected. No guard refused them; nobody ran the tool.
#
# THEY GO LAST. The chain is Yahoo (1m/5m) -> coarse resample (2m..60m) -> adjusted rebuild,
# because each step reads what the step before it wrote. Rebuilding the adjusted twins first
# would bake yesterday's tail into today's corrected bars.
#
# The rebuild is a FULL rewrite of all 19 files rather than an append, which is why it shares
# the coarse masters' once-an-evening gate instead of running every pass.
ADJUSTED_STATE = os.path.join(os.environ.get("EDGELOG_STATE_DIR", r"C:\EdgeLog"),
                              "adjusted_refresh_state.json")


def adjusted_refresh_due(now=None, state_path=None):
    """Same rule as the coarse masters: once per ET day, after the evening cutoff."""
    return coarse_refresh_due(now, state_path or ADJUSTED_STATE)


def run_adjusted_refresh(force=False, now=None, state_path=None):
    """Rebuild the ADJ_/FADJ_ masters from the current no-adjust parents.

    Reuses tools/build_adjusted_masters.py --apply unchanged, so a human at a prompt and the
    runner get identical results - including the write guard, which refuses a rebuild that
    would leave any adjusted master with fewer rows than it already has.
    """
    state_path = state_path or ADJUSTED_STATE
    if not force and not coarse_refresh_due(now, state_path):
        return []
    import subprocess
    tool = os.path.join(ROOT, "tools", "build_adjusted_masters.py")
    out = subprocess.run([sys.executable, tool, "--apply"], cwd=ROOT,
                         capture_output=True, text=True, timeout=3600)
    lines = [ln.strip() for ln in (out.stdout or "").splitlines()
             if "-> ADJ_" in ln or "-> FADJ_" in ln or "refusing" in ln.lower()
             or ln.strip().startswith(("NOTE:", "ERROR"))]
    _mark_coarse_done(now, state_path)
    return lines


if __name__ == "__main__":
    print("running auto-refresh (Yahoo + watch-folder ingest)…")
    for line in run_auto_refresh(progress_cb=lambda m: print("  ·", m)):
        print("   ", line)
    print("coarse masters (2m-60m):")
    for line in run_coarse_refresh(force="--coarse-force" in sys.argv) or ["  not due yet"]:
        print("   ", line)
    print("roll-corrected masters (ADJ_/FADJ_):")
    for line in run_adjusted_refresh(force="--coarse-force" in sys.argv) or ["  not due yet"]:
        print("   ", line)
    print("done.")
