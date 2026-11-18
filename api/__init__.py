"""AUGUR HTTP API — FastAPI surface over augur_engine (streamlit-free).

Step 2 of the EDGELOG split (docs/EDGELOG_ARCHITECTURE.md): the local runner and
the EDGELOG web frontend call these endpoints; the compute stays on this PC.
Run:  uvicorn api.server:app --reload --port 8787
"""

# Per-caller Firestore read/write counters (MANAGER 11-18, after the 11-13 quota 429) -- api/fs_usage.py.
try:
    from . import fs_usage as _fs_usage
    _fs_usage.enable()
except Exception:  # never let a counter break an import
    pass
