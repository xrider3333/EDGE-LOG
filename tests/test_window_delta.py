"""THE GATE for the PR4 window-extension delta (augur_engine.window_delta,
docs/INCREMENTAL_BACKTEST_REUSE.md §2(c)).

Recipe (per the hand-off spec): build a TEST EOD-flat strategy
(STATELESS_AT_EOD=True, always flat by each day's own last bar) on synthetic
multi-day data. Compute a FULL reference backtest over the whole window with
the cache OFF. Then, with the cache ON, compute a SHORT prefix window
(populates the window-cache) and request the FULL window again -- this must
take the delta path (verified via window_delta.get_stats(), never just
inferred from a matching number) and produce a result byte-identical to the
uncached reference: every headline metric (through the real, wired-in
engine.run_backtest path) AND every trade tuple (via a direct, low-level call
to window_delta.try_extend, compared against an independent gross-trade
reference -- engine.run_backtest never returns trades on the cached/delta
path, so this is the only way to inspect them directly).

A companion NEGATIVE test proves a strategy that does NOT set
STATELESS_AT_EOD never deltas -- even though its trade logic is IDENTICAL
(genuinely day-independent under the hood) -- because the FLAG, not an
inferred runtime property, is what gates activation. Further tests cover the
other declared preconditions (cost_pts>0, matching date_from, an unrevised
prefix) each falling back to a correct full recompute rather than a wrong
reuse.
"""
import os

import numpy as np
import pandas as pd
import pytest

import augur_engine.data as D
from augur_engine import trial_cache as TC
from augur_engine import window_delta as WD
from augur_engine.engine import run_backtest
from augur_engine.strategies import load_strategy


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Every test gets its OWN fresh sqlite sidecar (PR1's scalar table AND
    PR4's window table live in the same file, different tables -- see
    window_delta._db_path) so nothing here ever touches the real repo's
    trial_cache.db, starts with the cache OFF, and empties every in-process
    bit of state (trial_cache stats, window_delta stats, PR3's data-prep
    memo) so tests can never leak into one another."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE_DB", str(tmp_path / "trial_cache_test.db"))
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    TC.reset_stats()
    WD.reset_stats()
    D._memo_clear()
    yield


# ─────────────────────────────────────────────────────────────────────────
# Synthetic EOD-flat strategy + data
# ─────────────────────────────────────────────────────────────────────────

_OR_BARS = 2
_PER_DAY = 8
_N_DAYS = 24

# A simple daily-open-range strategy: for EACH day (segmented purely by
# day_id equality-runs, mirroring ORB_1_0.py's real day-loop), take the
# opening range of the first `or_bars` bars, enter at the next bar's open in
# the direction of the range midpoint, and exit at THAT SAME DAY's own last
# close -- always flat by end of day BY CONSTRUCTION, and a PURE function of
# that day's own o/h/l/c slice (no cross-day state of any kind whatsoever) --
# the literal property STATELESS_AT_EOD asserts.
_EOD_STRATEGY_SRC = f'''
import numpy as np

STRATEGY_NAME = "SYN EOD-FLAT ORB (TEST)"
STATELESS_AT_EOD = True
DEFAULT_PARAMS = {{"or_bars": {{"type": "int", "min": 1, "max": 6, "step": 1, "default": {_OR_BARS}}}}}

def run_backtest(opens, highs, lows, closes, day_id=None, or_bars={_OR_BARS},
                 return_trades=False, **kw):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    did = np.asarray(day_id) if day_id is not None else None
    if did is None or n == 0:
        return None
    trades = []
    i = 0
    while i < n:
        j = i
        while j < n and did[j] == did[i]:
            j += 1
        so, sh, sl, sc = o[i:j], h[i:j], l[i:j], c[i:j]
        m = j - i
        if m > or_bars:
            or_hi = float(sh[:or_bars].max())
            or_lo = float(sl[:or_bars].min())
            entry_k = or_bars
            entry_px = float(so[entry_k])
            direction = 1 if entry_px >= (or_hi + or_lo) / 2.0 else -1
            exit_px = float(sc[-1])
            pnl = (exit_px - entry_px) if direction > 0 else (entry_px - exit_px)
            trades.append((i + entry_k, j - 1, pnl, direction, entry_px))
        i = j
    if not trades:
        return None
    pnls = [t[2] for t in trades]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    total = float(sum(pnls))
    out = {{
        "total_pnl": total, "num_trades": len(pnls),
        "win_rate": (100.0 * len(wins) / len(pnls)) if pnls else 0.0,
        "profit_factor": (sum(wins) / -sum(losses)) if losses and -sum(losses) > 1e-9
                          else (float("inf") if wins else 0.0),
        "max_drawdown": 0.0, "avg_pnl": total / len(pnls) if pnls else 0.0,
        "wins": len(wins), "losses": len(losses),
    }}
    if return_trades:
        out["trades"] = trades
    return out
'''

# NEGATIVE control: BYTE-FOR-BYTE the same day-independent logic, just
# without the STATELESS_AT_EOD opt-in -- proves the FLAG (not an inferred
# runtime property) is what gates activation.
_NOT_OPTED_IN_SRC = _EOD_STRATEGY_SRC.replace("STATELESS_AT_EOD = True\n", "")


def _write_strategy(tmp_path, src, name="syn_eod_strategy.py"):
    p = tmp_path / name
    p.write_text(src, encoding="utf-8")
    return str(p)


def _make_eod_csv(path, n_days=_N_DAYS, per_day=_PER_DAY, seed=7):
    """n_days consecutive calendar days, per_day 5-min bars each, a seeded
    random walk with enough range that the opening-range breakout direction
    varies day to day (both long and short trades occur)."""
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2026-01-05", tz="US/Eastern")
    price = 100.0
    rows = []
    dates = []
    for d in range(n_days):
        day = base + pd.Timedelta(days=d)
        dates.append(day.strftime("%Y-%m-%d"))
        for b in range(per_day):
            ts = day + pd.Timedelta(minutes=5 * b)
            drift = float(rng.normal(0, 0.6))
            o = price
            c = price + drift
            h = max(o, c) + abs(float(rng.normal(0, 0.15)))
            l = min(o, c) - abs(float(rng.normal(0, 0.15)))
            rows.append((int(ts.timestamp()), o, h, l, c, 100.0))
            price = c
    pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]
                ).to_csv(path, index=False)
    return dates


@pytest.fixture
def eod_master(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    dates = _make_eod_csv(tmp_path / "eod.csv")
    master = {"filename": "eod.csv", "name": "SYN_EOD", "instrument": "SYNEOD",
              "timeframe": "5m", "source": "test"}
    return master, dates


# ─────────────────────────────────────────────────────────────────────────
# THE GATE
# ─────────────────────────────────────────────────────────────────────────

def test_delta_headline_metrics_byte_identical_through_public_api(tmp_path, eod_master, monkeypatch):
    master, dates = eod_master
    strat_path = _write_strategy(tmp_path, _EOD_STRATEGY_SRC)
    d0, dN, dK = dates[0], dates[-1], dates[len(dates) // 2]
    params = {"or_bars": _OR_BARS}
    kw = dict(master=master, params=params, cost_pts=0.05, session="rth")

    # 1) Reference: FULL window [d0..dN], cache OFF entirely.
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    full = run_backtest(strat_path, date_from=d0, date_to=dN, **kw)
    assert full is not None and full["num_trades"] > 0

    # 2) Cache ON: populate a SHORT prefix window [d0..dK] first...
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats(); WD.reset_stats()
    prefix = run_backtest(strat_path, date_from=d0, date_to=dK, **kw)
    assert prefix is not None

    # ...then request the FULL window again. A fresh DB has never seen
    # date_to=dN before, so this MUST miss PR1's scalar cache and instead
    # take the PR4 delta path -- assert that explicitly, not just infer it
    # from the numbers matching (a bug that always fell back to a full
    # recompute would ALSO pass a numbers-only check).
    WD.reset_stats()
    extended = run_backtest(strat_path, date_from=d0, date_to=dN, **kw)
    stats = WD.get_stats()
    assert stats == {"hits": 1, "misses": 0}, (
        f"delta path did not genuinely fire ({stats}) -- a numbers match here would prove nothing")

    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor",
              "max_drawdown", "avg_pnl", "wins", "losses"):
        assert extended[k] == full[k], k


def test_delta_trades_byte_identical_to_full_gross_trades(tmp_path, eod_master, monkeypatch):
    """THE core trade-level proof. engine.run_backtest never returns trades on
    the cached/delta path (return_trades=True disables PR1+PR4 both, by
    design), so this calls window_delta.try_extend directly and compares
    against an INDEPENDENT gross-trade reference: the strategy's own
    run_backtest, called directly with no engine.py/caching machinery
    whatsoever, on the full window."""
    master, dates = eod_master
    strat_path = _write_strategy(tmp_path, _EOD_STRATEGY_SRC)
    mod = load_strategy(strat_path)
    d0, dN, dK = dates[0], dates[-1], dates[len(dates) // 2]
    params = {"or_bars": _OR_BARS}

    full_arrays = D.load_master_arrays(master, date_from=d0, date_to=dN)
    ref = mod.run_backtest(full_arrays["open"], full_arrays["high"], full_arrays["low"],
                           full_arrays["close"], day_id=full_arrays["day_id"],
                           or_bars=_OR_BARS, return_trades=True)
    assert ref and ref["trades"]

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats(); WD.reset_stats()
    run_backtest(strat_path, master=master, date_from=d0, date_to=dK,
                params=params, cost_pts=0.05, session="rth")   # populates [d0..dK]

    WD.reset_stats()
    delta_trades = WD.try_extend(mod, full_arrays, params, cost_pts=0.05, session="rth",
                                 date_from=d0, date_to=dN, master=master)
    assert delta_trades is not None
    assert WD.get_stats() == {"hits": 1, "misses": 0}

    assert delta_trades == ref["trades"], "delta trade list diverged from an independent full gross recompute"


def test_extension_chains_a_second_time(tmp_path, eod_master, monkeypatch):
    """A delta result is itself persisted (engine.run_backtest calls
    record_full after a delta, same as after a from-scratch compute) so a
    SECOND, further extension chains off the newly-extended window rather
    than re-deriving the tail from the original short prefix every time."""
    master, dates = eod_master
    strat_path = _write_strategy(tmp_path, _EOD_STRATEGY_SRC)
    d0 = dates[0]
    dK1, dK2, dN = dates[8], dates[16], dates[-1]
    params = {"or_bars": _OR_BARS}
    kw = dict(master=master, params=params, cost_pts=0.05, session="rth")

    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    full = run_backtest(strat_path, date_from=d0, date_to=dN, **kw)

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats(); WD.reset_stats()
    run_backtest(strat_path, date_from=d0, date_to=dK1, **kw)          # populate [d0..dK1]
    WD.reset_stats()
    run_backtest(strat_path, date_from=d0, date_to=dK2, **kw)          # extend to [d0..dK2] (delta #1)
    assert WD.get_stats()["hits"] == 1
    WD.reset_stats()
    extended2 = run_backtest(strat_path, date_from=d0, date_to=dN, **kw)   # extend to [d0..dN] (delta #2)
    assert WD.get_stats() == {"hits": 1, "misses": 0}

    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor",
              "max_drawdown", "avg_pnl", "wins", "losses"):
        assert extended2[k] == full[k], k


# ─────────────────────────────────────────────────────────────────────────
# NEGATIVE — the required non-opted-in test
# ─────────────────────────────────────────────────────────────────────────

def test_strategy_without_flag_never_deltas(tmp_path, eod_master, monkeypatch):
    master, dates = eod_master
    strat_path = _write_strategy(tmp_path, _NOT_OPTED_IN_SRC, name="syn_not_opted_in.py")
    mod = load_strategy(strat_path)
    assert getattr(mod, "STATELESS_AT_EOD", False) is False   # sanity: the flag really is absent
    d0, dN, dK = dates[0], dates[-1], dates[len(dates) // 2]
    params = {"or_bars": _OR_BARS}
    kw = dict(master=master, params=params, cost_pts=0.05, session="rth")

    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    full = run_backtest(strat_path, date_from=d0, date_to=dN, **kw)

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats(); WD.reset_stats()
    run_backtest(strat_path, date_from=d0, date_to=dK, **kw)
    WD.reset_stats()
    extended = run_backtest(strat_path, date_from=d0, date_to=dN, **kw)

    assert WD.get_stats() == {"hits": 0, "misses": 0}, "delta must never even ATTEMPT without the flag"
    # the FALLBACK (full recompute) path must still be correct
    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor",
              "max_drawdown", "avg_pnl", "wins", "losses"):
        assert extended[k] == full[k], k


# ─────────────────────────────────────────────────────────────────────────
# Other declared preconditions — each must fall back to a correct full
# recompute, never a wrong reuse.
# ─────────────────────────────────────────────────────────────────────────

def test_cost_pts_zero_never_deltas(tmp_path, eod_master, monkeypatch):
    """See window_delta.py's module docstring: cost_pts > 0 is required
    because it's what makes the merge provably identical to a full recompute
    (both route through _apply_costs). At cost_pts == 0 PR4 must decline."""
    master, dates = eod_master
    strat_path = _write_strategy(tmp_path, _EOD_STRATEGY_SRC)
    d0, dN, dK = dates[0], dates[-1], dates[len(dates) // 2]
    params = {"or_bars": _OR_BARS}
    kw = dict(master=master, params=params, cost_pts=0.0, session="rth")

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats(); WD.reset_stats()
    run_backtest(strat_path, date_from=d0, date_to=dK, **kw)
    WD.reset_stats()
    run_backtest(strat_path, date_from=d0, date_to=dN, **kw)
    assert WD.get_stats() == {"hits": 0, "misses": 0}


def test_mismatched_date_from_never_deltas(tmp_path, eod_master, monkeypatch):
    master, dates = eod_master
    strat_path = _write_strategy(tmp_path, _EOD_STRATEGY_SRC)
    d0, d1, dN = dates[0], dates[1], dates[-1]
    params = {"or_bars": _OR_BARS}
    kw = dict(master=master, params=params, cost_pts=0.05, session="rth")

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats(); WD.reset_stats()
    run_backtest(strat_path, date_from=d0, date_to=dates[len(dates) // 2], **kw)   # cached under date_from=d0
    WD.reset_stats()
    run_backtest(strat_path, date_from=d1, date_to=dN, **kw)   # a DIFFERENT date_from -- not an extension of the above
    assert WD.get_stats() == {"hits": 0, "misses": 1}   # eligible, but genuinely no matching prior window


def test_data_revision_in_prefix_declines_delta(tmp_path, eod_master, monkeypatch):
    """The invalidation case docs/INCREMENTAL_BACKTEST_REUSE.md §3 calls "the
    hard part": if the underlying master file's ALREADY-cached days were
    revised (a correction), the stored trades for that stretch may no longer
    be correct -- the fresh fingerprint re-slice at use time must catch this
    and decline (fall back to a full recompute), never silently splice in the
    now-stale prefix trades."""
    master, dates = eod_master
    strat_path = _write_strategy(tmp_path, _EOD_STRATEGY_SRC)
    d0, dN, dK = dates[0], dates[-1], dates[len(dates) // 2]
    params = {"or_bars": _OR_BARS}
    kw = dict(master=master, params=params, cost_pts=0.05, session="rth")

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats(); WD.reset_stats()
    run_backtest(strat_path, date_from=d0, date_to=dK, **kw)   # populate [d0..dK]

    # Revise a bar WELL INSIDE the already-cached prefix window (day 2) and
    # force a distinct mtime -- the exact "a correction landed on an
    # already-cached historical day" scenario.
    csv_path = tmp_path / master["filename"]
    df = pd.read_csv(csv_path)
    df.loc[_PER_DAY + 1, "close"] = df.loc[_PER_DAY + 1, "close"] + 5.0
    df.to_csv(csv_path, index=False)
    st = os.stat(csv_path)
    os.utime(csv_path, (st.st_mtime + 5.0, st.st_mtime + 5.0))
    D._memo_clear()   # PR3 memo would otherwise still be OFF here anyway (only reads the file when enabled)

    WD.reset_stats()
    extended = run_backtest(strat_path, date_from=d0, date_to=dN, **kw)
    assert WD.get_stats() == {"hits": 0, "misses": 1}   # declined, not a silent stale reuse

    # and the FALLBACK full recompute must reflect the REVISED data, not the
    # original -- an independent uncached reference over the (now-revised)
    # full window must match exactly.
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    D._memo_clear()
    true_full = run_backtest(strat_path, date_from=d0, date_to=dN, **kw)
    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor",
              "max_drawdown", "avg_pnl", "wins", "losses"):
        assert extended[k] == true_full[k], k


def test_disabled_cache_window_delta_is_a_pure_noop(tmp_path, eod_master, monkeypatch):
    master, dates = eod_master
    strat_path = _write_strategy(tmp_path, _EOD_STRATEGY_SRC)
    d0, dN, dK = dates[0], dates[-1], dates[len(dates) // 2]
    params = {"or_bars": _OR_BARS}
    kw = dict(master=master, params=params, cost_pts=0.05, session="rth")

    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    run_backtest(strat_path, date_from=d0, date_to=dK, **kw)
    run_backtest(strat_path, date_from=d0, date_to=dN, **kw)
    assert WD.get_stats() == {"hits": 0, "misses": 0}
