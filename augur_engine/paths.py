"""Shared filesystem paths. The AUGUR project root is the parent of this package,
so the engine finds the same data/strategies/DB the Streamlit app uses."""
import os

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS   = os.path.join(ROOT, "augur_uploads")
STRAT_DIR = os.path.join(ROOT, "augur_strategies")
PINE_DIR  = os.path.join(ROOT, "pine")
DB_PATH   = os.path.join(ROOT, "optimizer_history.db")
CONFIG    = os.path.join(ROOT, "augur_config.json")
