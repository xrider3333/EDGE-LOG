"""Root conftest — makes the streamlit-free engine importable from tests.

Puts the repo root on sys.path so `import augur_engine`, `import augur_mp_worker`
resolve without installing the package, and exposes a couple of small shared
fixtures. Deliberately imports NO streamlit and touches NO real data files, so the
suite runs anywhere (CI included) with only requirements-dev.txt.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def trades_from_pnls():
    """Build an engine-shaped trade list from a list of per-trade PnLs (points).

    The engine's trade tuples are (entry_idx, exit_idx, pnl[, side, entry_px]); the
    net-metrics helpers only read t[2] (the PnL), so a minimal 3-tuple is enough to
    exercise them exactly as a real backtest would.
    """
    def _build(pnls):
        return [(i, i + 1, float(p)) for i, p in enumerate(pnls)]
    return _build
