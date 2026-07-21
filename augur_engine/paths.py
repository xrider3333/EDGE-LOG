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
TRIAL_CACHE_DB = os.environ.get("AUGUR_TRIAL_CACHE_DB") or os.path.join(ROOT, "trial_cache.db")
