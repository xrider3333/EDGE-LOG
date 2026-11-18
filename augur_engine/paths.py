"""Shared filesystem paths. The AUGUR project root is the parent of this package,
so the engine finds the same data/strategies/DB the Streamlit app uses."""
import os

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS   = os.path.join(ROOT, "augur_uploads")
STRAT_DIR = os.path.join(ROOT, "augur_strategies")
PINE_DIR  = os.path.join(ROOT, "pine")
DB_PATH   = os.path.join(ROOT, "optimizer_history.db")
CONFIG    = os.path.join(ROOT, "augur_config.json")
# Sidecar DB for the trial-level backtest result cache (docs/INCREMENTAL_BACKTEST_
# REUSE.md). Same directory as DB_PATH. Overridable via env so tests (and any other
# caller that wants an isolated cache) can point at a temp file; augur_engine.
# trial_cache re-reads the env var live on every connection (not just this
# import-time default) so a test's monkeypatch.setenv takes effect immediately.
#
# DEFAULT LIVES OUTSIDE THE REPO (2026-11-15). The repo root sits under
#   OneDrive/Desktop; runners rewrite trial_cache.db (+ -wal, -shm) about 30x a
#   second, and Windows Explorer - which watches everything under Desktop - burned
#   a whole core on the change notices until the taskbar froze. The sidecar is
#   scratch, never committed, so it belongs in EDGELOG_HOME (C:/EdgeLog) whenever
#   that directory exists. Falls back to the repo root only when it does not (CI,
#   a clone on another machine). AUGUR_TRIAL_CACHE_DB still wins over both.
def _trial_cache_default():
    home = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
    try:
        if os.path.isdir(home):
            return os.path.join(home, "trial_cache.db")
    except OSError:
        pass
    return os.path.join(ROOT, "trial_cache.db")


TRIAL_CACHE_DB = os.environ.get("AUGUR_TRIAL_CACHE_DB") or _trial_cache_default()


# Per-trade blotter CSVs, one per saved run (api/runner.py writes them after a run
# lands in Runs history). Same reason as the trial cache above: the repo root sits
# under OneDrive/Desktop, and every Auto-Validate / grid run dropping a fresh CSV
# into a watched Desktop folder is exactly the write pattern that froze Explorer and
# the taskbar on 2026-11-15. Blotters are regenerable scratch, never committed, so
# the default lives in EDGELOG_HOME (C:/EdgeLog/blotters) whenever that directory
# exists, and falls back to the repo root only when it does not (CI, a fresh clone).
# AUGUR_BLOTTER_DIR wins over both. Read through blotter_dir(), never cached at
# import time, so a test's monkeypatch.setenv takes effect immediately.
def _blotter_default():
    home = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
    try:
        if os.path.isdir(home):
            return os.path.join(home, "blotters")
    except OSError:
        pass
    return os.path.join(ROOT, "blotters")


def blotter_dir():
    """Directory the per-run trade blotters are written to (created on demand)."""
    d = os.environ.get("AUGUR_BLOTTER_DIR") or _blotter_default()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d
