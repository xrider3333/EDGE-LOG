"""The walk-forward chain's DAILY curve must rebuild EXACTLY from the stored block.

WHY THIS TEST EXISTS. `validate.wf_oos` stored the chain's per-trade P&L but not the trades' BAR
INDICES, so the chain had no time axis, so no daily equity curve could be built from it, so a
walk-forward chain carried NO DD5 and NO "DD% from peak" - two of the four numbers every house
result must report. Runs #489 and #491 were both reported with '-' in those columns.

WHY A REBUILD WAS NOT ENOUGH, and why the assertion below is EXACT rather than tolerant. Rebuilding
the chain by re-running each fold needs its bar bounds, its scored params and the warm convention,
and even with all three it did not reproduce: a master refill inserted 740 bars inside run #491's
optimize window, so every bar index after the insertion pointed at a different bar. Masking the
inserted bars made all 8 folds reproduce bit-exact. The conclusion was to stop re-deriving the chain
and store it - which is only worth anything if "stored" means the curve comes back EXACTLY.

So: no tolerance on the curve. The stored integers either reproduce the series they were taken from
or the feature has failed.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine.analytics import wf_oos_block          # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak       # noqa: E402

MULT = 20.0
BARS_PER_DAY = 10          # a tiny synthetic tape: 10 bars a session


def _trades(fold_no):
    """(ei, xi, pnl) per fold, slice-local. Deliberately includes a trade that spans
    several sessions (the ENGU-Q shape - the money is in multi-day survivors) and a
    losing one, so the daily curve is not trivially flat."""
    return {
        1: [(1, 3, 12.5), (14, 41, -8.25), (52, 55, 3.0)],
        2: [(0, 2, -4.5), (23, 67, 31.75)],
        3: [(5, 9, 2.25), (30, 34, -1.5), (60, 61, 0.5), (70, 95, 18.0)],
    }[fold_no]


def _bounds(fold_no):
    """Each fold's test slice [a, b), contiguous and advancing - the rolling shape, where
    the old derivation (test_start == train_bars) is wrong."""
    a = 1000 + (fold_no - 1) * 100
    return a, a + 100


def _index(n):
    """Synthetic bar timestamps, BARS_PER_DAY to a session."""
    import datetime
    base = datetime.datetime(2020, 1, 1)
    return [str(base + datetime.timedelta(days=i // BARS_PER_DAY, minutes=i % BARS_PER_DAY))
            for i in range(n)]


def _fold_dicts(trim=None):
    out = []
    for f in (1, 2, 3):
        tr = _trades(f)
        a, b = _bounds(f)
        ei = [t[0] for t in tr]
        xi = [t[1] for t in tr]
        pn = [t[2] for t in tr]
        if trim == f:                      # one fold with a SHORT index array
            ei = ei[:-1]
        out.append({"fold": f, "pnls": pn, "oos_pnl": sum(pn), "oos_trades": len(pn),
                    "oos_wins": sum(1 for x in pn if x > 0), "oos_pf": 1.0,
                    "from": "2020-01-01", "to": "2020-12-31",
                    "ei": ei, "xi": xi, "a": a, "b": b,
                    "a_ts": "2020-01-01 00:00:00", "b_ts": "2020-12-31 00:00:00"})
    return out


def _daily_from(trade_rows):
    """The ONE definition of the daily curve used by both sides of the comparison: a trade's
    P&L lands on the session its EXIT bar falls in. Absolute bar = a + slice-local index."""
    by_day = {}
    for a, ei, xi, pnl in trade_rows:
        day = (a + xi) // BARS_PER_DAY
        by_day[day] = by_day.get(day, 0.0) + pnl * MULT
    return [by_day[k] for k in sorted(by_day)]


@pytest.fixture(scope="module")
def block():
    b = wf_oos_block(_fold_dicts(), mode="rolling", src="validate",
                     arrays={"index": _index(2000)})
    assert b is not None, "the block refused to build on valid input"
    return b


def test_the_block_stores_the_trades_and_the_bounds(block):
    """Without these five fields there is no time axis and no DD5."""
    assert len(block["folds"]) == 3
    for row, f in zip(block["folds"], (1, 2, 3)):
        a, b = _bounds(f)
        assert row["a"] == a and row["b"] == b, "the slice bounds must be stored, not derived"
        assert row["a_ts"] and row["b_ts"], "bound timestamps survive a refill; indices do not"
        assert row["ei"] == [t[0] for t in _trades(f)]
        assert row["xi"] == [t[1] for t in _trades(f)]
        assert len(row["ei"]) == row["trades"] == len(row["xi"])


def test_the_tape_fingerprint_is_recorded(block):
    """A bar index only means something against the exact array it was measured in."""
    fp = block["fp"]
    assert fp and fp["n"] == 2000 and fp["first"] and fp["last"]


def test_the_daily_curve_rebuilds_EXACTLY_from_the_stored_block(block):
    """The point of the whole change. Exact equality, not a tolerance."""
    source = _daily_from([(a, ei, xi, pnl)
                          for f in (1, 2, 3)
                          for (a, _b), (ei, xi, pnl) in
                          [(_bounds(f), t) for t in _trades(f)]])
    stored = _daily_from([(row["a"], ei, xi, pnl)
                          for row in block["folds"]
                          for ei, xi, pnl in zip(row["ei"], row["xi"],
                                                 _pnls_of(block, row))])
    assert stored == source, "the stored block does not reproduce its own daily curve"


def _pnls_of(block, row):
    """This fold's slice of the stitched per-trade series, via the block's own fold_idx."""
    i = block["folds"].index(row)
    start = block["fold_idx"][i]
    return [p / 1.0 for p in _ALL_PNLS[start:start + row["trades"]]]


_ALL_PNLS = [t[2] for f in (1, 2, 3) for t in _trades(f)]


def test_dd5_and_dd_pct_from_peak_come_out_of_the_stored_block(block):
    """The two numbers that were '-' on every chain before this change."""
    import pandas as pd
    daily = _daily_from([(row["a"], ei, xi, pnl)
                         for row in block["folds"]
                         for ei, xi, pnl in zip(row["ei"], row["xi"], _pnls_of(block, row))])
    s = pd.Series(daily, index=pd.date_range("2020-01-01", periods=len(daily), freq="D"))
    r5 = dd5(s)
    assert r5 and r5["dd5_usd"] >= 0.0 and math.isfinite(r5["dd5_usd"])
    pct = dd_pct_peak(s, start=100_000)
    assert math.isfinite(pct) and pct >= 0.0


def test_a_short_index_array_REFUSES_the_block():
    """Silently wrong is the one outcome the guard exists to prevent: a short ei would map
    trades to the wrong bars while every other figure still reconciled."""
    assert wf_oos_block(_fold_dicts(trim=2), mode="rolling", src="validate") is None


def test_the_budget_drops_only_the_indices_and_says_so():
    """Over budget the block must stay correct and keep its bounds - it loses DD5, not truth."""
    b = wf_oos_block(_fold_dicts(), mode="rolling", src="validate", trade_budget=2)
    assert b is not None and b["chain_trimmed"] is True
    assert all("ei" not in r and "xi" not in r for r in b["folds"])
    assert all(r["a"] and r["b"] for r in b["folds"]), "bounds must survive a trim"
    assert b["trades"] == len(_ALL_PNLS)
    # net is rounded to `dp` (1 by default) by the block's own contract, so compare at dp.
    assert b["net"] == pytest.approx(round(sum(_ALL_PNLS), 1), abs=0.05)


def test_old_callers_without_the_new_fields_still_work():
    """Every pre-existing caller passes no ei/xi; the block must build exactly as before."""
    rows = [{k: v for k, v in d.items() if k not in ("ei", "xi", "a", "b", "a_ts", "b_ts")}
            for d in _fold_dicts()]
    b = wf_oos_block(rows, mode="anchored", src="backfill")
    assert b is not None and b["chain_trimmed"] is False
    assert all("ei" not in r for r in b["folds"])
    assert b["trades"] == len(_ALL_PNLS)
