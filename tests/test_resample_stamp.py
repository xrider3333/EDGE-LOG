"""The NinjaTrader 10s export stamps each row at the bar END. api/paper.py::_resample
(and tools/backfill_1m_from_10s.py::aggregate) must read it that way by default so the
paper tail, the candle window and the LIVE gate bouncer all rebuild the bars the
Databento masters hold. Found 2026-09-08; measured by tools/diag_10s_stamp.py."""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Test the tree these tests live in. `tools/queue_guard.py` inserts the shared desktop
# checkout at sys.path[0] when it is imported (it needs that checkout's
# optimizer_history.db, which a git worktree does not carry), so once any test touches
# it, a later `import api.x` can resolve to the OTHER checkout's code -- this file then
# checked the SHIPPED `_resample` instead of the edited one and failed with "unexpected
# keyword argument 'stamp'" (2026-09-09, the pre-push engine gate). Put this checkout
# first and drop any api/tools module already bound outside it.
sys.path.insert(0, ROOT)
for _name, _mod in list(sys.modules.items()):
    if _name == "api" or _name.startswith("api.") or _name == "tools" or _name.startswith("tools."):
        _where = list(getattr(_mod, "__path__", None) or [getattr(_mod, "__file__", "") or ""])
        if not all(os.path.abspath(str(w)).startswith(ROOT) for w in _where):
            del sys.modules[_name]

from api import bars as barsmod                          # noqa: E402
from api import paper                                    # noqa: E402
from tools import backfill_1m_from_10s as backfill       # noqa: E402

assert os.path.abspath(paper.__file__).startswith(ROOT), paper.__file__

T0 = 1_788_000_000 - (1_788_000_000 % 300)   # an exact 5-minute boundary


def _ticks(n_bars=2, tf_sec=300):
    """END-stamped 10s rows covering n_bars whole bars from T0. Row i covers
    [T0+10i, T0+10(i+1)) and is stamped at its END, T0+10(i+1). Prices encode the row
    number so open/close pick-up is checkable to the row."""
    rows = []
    for i in range(n_bars * tf_sec // 10):
        rows.append({"time": T0 + 10 * (i + 1), "open": float(i), "high": float(i) + 0.5,
                     "low": float(i) - 0.5, "close": float(i) + 0.25, "volume": 1})
    return pd.DataFrame(rows)


def test_default_reads_stamp_as_bar_end_5m():
    bars = paper._resample(_ticks(2, 300), 5)
    assert list(bars["time"]) == [T0, T0 + 300]
    # first bar = rows 0..29 (the row stamped exactly T0+300 is row 29, it CLOSES the bar)
    assert bars.loc[0, "open"] == 0.0 and bars.loc[0, "close"] == 29.25
    assert bars.loc[0, "high"] == 29.5 and bars.loc[0, "low"] == -0.5
    # second bar = rows 30..59 -- opens on the FIRST row after the boundary, not the last
    # row before it (the old off-by-10s open)
    assert bars.loc[1, "open"] == 30.0 and bars.loc[1, "close"] == 59.25
    assert int(bars["volume"].sum()) == 60 and list(bars["volume"]) == [30, 30]


def test_start_stamp_reproduces_the_old_bucketing():
    ticks = _ticks(2, 300)
    old = paper._resample(ticks, 5, stamp="start")
    # the old way pushes the boundary row (stamped T0+300) into the next bar and opens a
    # third, one-row bar at T0+600
    assert list(old["time"]) == [T0, T0 + 300, T0 + 600]
    assert old.loc[1, "open"] == 29.0          # previous 10 s leaked in as the open
    assert old.loc[0, "close"] == 28.25        # last 10 s lost to the next bar


def test_1m_and_bad_stamp():
    bars = paper._resample(_ticks(3, 60), 1)
    assert list(bars["time"]) == [T0, T0 + 60, T0 + 120]
    assert list(bars["open"]) == [0.0, 6.0, 12.0]
    assert list(bars["close"]) == [5.25, 11.25, 17.25]
    try:
        paper._resample(_ticks(1, 60), 1, stamp="middle")
    except ValueError:
        pass
    else:
        raise AssertionError("stamp='middle' must be rejected")


def test_backfill_aggregate_matches_resample():
    ticks = _ticks(3, 60)
    ticks["delta"] = 1
    a = backfill.aggregate(ticks)
    r = paper._resample(ticks, 1)
    assert list(a["time"]) == list(r["time"])
    for c in ("open", "high", "low", "close", "volume"):
        assert list(a[c]) == list(r[c]), c
    assert list(a["_n"]) == [6, 6, 6]
    assert list(a["delta"]) == [6, 6, 6]
    old = backfill.aggregate(ticks, stamp="start")
    assert list(old["open"]) == [0.0, 5.0, 11.0, 17.0]   # the shifted minutes the master got


def test_fresh_tail_passes_instrument(monkeypatch):
    seen = {}

    def fake_load(instrument="NQ"):
        seen["inst"] = instrument
        return _ticks(2, 300), "x"
    monkeypatch.setattr(paper, "_load_fresh_ticks", fake_load)
    out = barsmod._fresh_tail("5m", "eth", pd.Timestamp("2000-01-01", tz="US/Eastern"),
                              lambda *_: None, instrument="ES")
    assert seen["inst"] == "ES"
    assert out is not None and list(out["time"]) == [T0, T0 + 300]
    assert out.loc[1, "open"] == 30.0
