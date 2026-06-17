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


if __name__ == "__main__":
    print("running auto-refresh (Yahoo + watch-folder ingest)…")
    for line in run_auto_refresh(progress_cb=lambda m: print("  ·", m)):
        print("   ", line)
    print("done.")
