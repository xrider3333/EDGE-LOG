"""Warm starts for every SCORED out-of-sample stretch (RESEARCH.md item 7).

THE DEFECT. A walk-forward test fold and the lockbox used to be run on their own bars
only. A strategy with a long look-back therefore spent the opening part of every such
stretch unable to trade at all: measured on 2026-09-15 (tools/wf_coldstart_audit.py), a
250-day trend filter lost 86% of its fold trades and its whole family then failed on
walk-forward efficiency for a reason that was an artifact of the measurement, not of the
strategy. The intraday control lost 0%.

THE FIX. Run the same fixed config from `warm_days` trading sessions BEFORE the stretch
opens, then keep only the trades that ENTER inside the stretch. Nothing after the
stretch's own end is read, so no look-ahead is introduced.

WHAT THESE TESTS PIN.
  1. warm_days=0 is a no-op — the old numbers, exactly.
  2. The re-derived metrics match the engine's own cost arithmetic.
  3. A long-look-back strategy recovers its trades, and the warmed stretch's trades are
     exactly the entries of a full-history run that fall inside it.
  4. Warming reads nothing from beyond the stretch end.
  5. Trade bar indices come back in the stretch's own coordinates.
  6. The session counter warms over sessions, not bars.
"""
import types

import numpy as np
import pandas as pd
import pytest

from augur_engine.engine import _apply_costs, keep_trades_entering_at_or_after
from augur_engine.auto import make_slice_evaluator, score_candidates_on_folds


# ─────────────────────────────────────────────────────────────────────────────
# fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _session_arrays(n_days=40, bars_per_day=10, start="2020-01-01"):
    """Bars carrying a real day_id, so warm-up can be counted in SESSIONS."""
    n = n_days * bars_per_day
    close = 100.0 + np.arange(n, dtype=float)
    day_id = np.repeat(np.arange(n_days), bars_per_day).astype("int64")
    idx = pd.date_range(start, periods=n, freq="30min", tz="US/Eastern")
    return {"open": close.copy(), "high": close + 1.0, "low": close - 1.0,
            "close": close.copy(), "volume": None, "day_id": day_id, "index": idx}


def _warmup_strategy(lookback=120):
    """Stands in for a long-look-back leg: it cannot trade until `lookback` bars of the
    slice it was handed have gone by, which is exactly what a 250-day trend filter does
    to a fold that starts cold. One trade per bar after that, +1 point each."""
    mod = types.ModuleType("fake_warmup_strategy")
    mod.STRATEGY_NAME = "SYN WARMUP"

    def run_backtest(o, h, l, c, knob=1.0, return_trades=False, **kw):
        n = len(c)
        entries = list(range(int(lookback), n))
        pnl = float(knob) * len(entries)
        out = {"total_pnl": pnl, "num_trades": len(entries),
               "win_rate": 100.0 if entries else 0.0,
               "profit_factor": 3.0 if entries else 0.0,
               "max_drawdown": -1.0, "avg_pnl": (pnl / len(entries)) if entries else 0.0,
               "wins": len(entries), "losses": 0}
        if return_trades:
            out["trades"] = [(i, i, float(knob), 1, float(c[i])) for i in entries]
        return out

    mod.run_backtest = run_backtest
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# 1. the flag off changes nothing
# ─────────────────────────────────────────────────────────────────────────────

def test_warm_days_zero_is_byte_identical_to_the_old_evaluator():
    """warm_days=0, and warm=True on top of it, both return exactly the cold result."""
    mod = _warmup_strategy(lookback=50)
    arrays = _session_arrays()
    cold = make_slice_evaluator(mod, arrays, 0.0)
    off = make_slice_evaluator(mod, arrays, 0.0, warm_days=0)
    a, b = 200, 300
    base = cold(a, b, {"knob": 1.0})
    assert off(a, b, {"knob": 1.0}) == base
    assert off(a, b, {"knob": 1.0}, warm=True) == base


def test_warm_flag_off_on_a_warm_capable_evaluator_is_still_cold():
    """An evaluator built WITH warm_days still evaluates cold unless the call asks."""
    mod = _warmup_strategy(lookback=50)
    arrays = _session_arrays()
    ev = make_slice_evaluator(mod, arrays, 0.0, warm_days=10)
    a, b = 200, 300
    assert ev(a, b, {"knob": 1.0}) == make_slice_evaluator(mod, arrays, 0.0)(a, b, {"knob": 1.0})


# ─────────────────────────────────────────────────────────────────────────────
# 2. the re-derived metrics are the engine's own arithmetic
# ─────────────────────────────────────────────────────────────────────────────

def test_metrics_match_apply_costs_on_the_same_surviving_trades():
    """Keeping every trade (first_idx=0) must reproduce _apply_costs at zero cost —
    the two re-derivations are the same math, so they can never drift."""
    trades = [(0, 1, 5.0, 1, 100.0), (2, 3, -2.0, -1, 101.0), (4, 5, 7.5, 1, 102.0),
              (6, 7, -1.5, 1, 103.0)]
    m = {"trades": trades, "total_pnl": 0.0, "num_trades": 0}
    a = _apply_costs(dict(m), 0.0)
    b = keep_trades_entering_at_or_after(dict(m), 0)
    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown",
              "avg_pnl", "wins", "losses"):
        assert a[k] == pytest.approx(b[k]), k


def test_drawdown_is_recomputed_over_the_surviving_trades_only():
    """A deep loss BEFORE the stretch must not appear in the stretch's drawdown."""
    trades = [(0, 1, -100.0, 1, 100.0), (5, 6, 2.0, 1, 100.0), (6, 7, -3.0, 1, 100.0),
              (7, 8, 4.0, 1, 100.0)]
    out = keep_trades_entering_at_or_after({"trades": trades}, 5)
    assert out["num_trades"] == 3
    assert out["total_pnl"] == pytest.approx(3.0)
    assert out["max_drawdown"] == pytest.approx(-3.0)   # not -100


# ─────────────────────────────────────────────────────────────────────────────
# 3. the defect itself: a long look-back recovers its trades
# ─────────────────────────────────────────────────────────────────────────────

def test_long_lookback_leg_recovers_the_trades_a_cold_fold_lost():
    mod = _warmup_strategy(lookback=120)
    arrays = _session_arrays(n_days=40, bars_per_day=10)   # 400 bars, 10 bars/session
    a, b = 300, 400                                        # a 100-bar test fold
    cold = make_slice_evaluator(mod, arrays, 0.0)(a, b, {"knob": 1.0})
    warm = make_slice_evaluator(mod, arrays, 0.0, warm_days=20)(a, b, {"knob": 1.0},
                                                                warm=True)
    assert cold["num_trades"] == 0          # 100-bar fold, 120-bar look-back: silent
    assert warm["num_trades"] == 100        # every bar of the fold trades once
    assert warm["total_pnl"] == pytest.approx(100.0)


def test_warm_stretch_is_exactly_the_full_run_entries_that_fall_inside_it():
    """The warmed stretch's trades are the SUBSET of a full-history run entering inside
    it — same trades, same pnls, nothing invented and nothing from before the open."""
    mod = _warmup_strategy(lookback=120)
    arrays = _session_arrays(n_days=40, bars_per_day=10)
    a, b = 300, 400
    full = make_slice_evaluator(mod, arrays, 0.0)(0, b, {"knob": 1.0}, keep_trades=True)
    warm = make_slice_evaluator(mod, arrays, 0.0, warm_days=40)(a, b, {"knob": 1.0},
                                                                keep_trades=True, warm=True)
    expect = [t for t in full["trades"] if t[0] >= a]
    assert len(warm["trades"]) == len(expect)
    assert [t[2] for t in warm["trades"]] == [t[2] for t in expect]
    assert warm["total_pnl"] == pytest.approx(sum(t[2] for t in expect))


# ─────────────────────────────────────────────────────────────────────────────
# 4. no look-ahead
# ─────────────────────────────────────────────────────────────────────────────

def test_warming_reads_nothing_from_after_the_stretch_end():
    """Change every bar AFTER the stretch and the warmed result must not move."""
    mod = _warmup_strategy(lookback=60)
    arrays = _session_arrays(n_days=40, bars_per_day=10)
    a, b = 250, 300
    first = make_slice_evaluator(mod, arrays, 0.0, warm_days=20)(a, b, {"knob": 1.0},
                                                                 keep_trades=True, warm=True)
    tampered = {k: (v.copy() if isinstance(v, np.ndarray) else v)
                for k, v in arrays.items()}
    for k in ("open", "high", "low", "close"):
        tampered[k][b:] = tampered[k][b:] * 7.0 + 1000.0
    second = make_slice_evaluator(mod, tampered, 0.0, warm_days=20)(a, b, {"knob": 1.0},
                                                                    keep_trades=True, warm=True)
    assert first["total_pnl"] == pytest.approx(second["total_pnl"])
    assert [t[2] for t in first["trades"]] == [t[2] for t in second["trades"]]


def test_a_stretch_starting_at_bar_zero_cannot_warm_up():
    mod = _warmup_strategy(lookback=10)
    arrays = _session_arrays()
    ev = make_slice_evaluator(mod, arrays, 0.0, warm_days=20)
    assert ev(0, 200, {"knob": 1.0}, warm=True) == ev(0, 200, {"knob": 1.0})


# ─────────────────────────────────────────────────────────────────────────────
# 5. trade coordinates
# ─────────────────────────────────────────────────────────────────────────────

def test_trade_indices_come_back_in_the_stretch_coordinates():
    """Callers index bar arrays sliced from the stretch start (mae_mfe does), so a
    warmed trade's entry/exit indices must be relative to the stretch, not the warm-up."""
    mod = _warmup_strategy(lookback=120)
    arrays = _session_arrays(n_days=40, bars_per_day=10)
    a, b = 300, 400
    warm = make_slice_evaluator(mod, arrays, 0.0, warm_days=40)(a, b, {"knob": 1.0},
                                                                keep_trades=True, warm=True)
    idxs = [t[0] for t in warm["trades"]]
    assert min(idxs) == 0
    assert max(idxs) == (b - a) - 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. the warm-up is counted in SESSIONS
# ─────────────────────────────────────────────────────────────────────────────

def test_warm_up_is_counted_in_sessions_not_bars():
    """10 bars per session: warming 5 sessions must reach back 50 bars, no further."""
    mod = _warmup_strategy(lookback=45)
    arrays = _session_arrays(n_days=40, bars_per_day=10)
    a, b = 300, 320
    five = make_slice_evaluator(mod, arrays, 0.0, warm_days=5)(a, b, {"knob": 1.0}, warm=True)
    four = make_slice_evaluator(mod, arrays, 0.0, warm_days=4)(a, b, {"knob": 1.0}, warm=True)
    # 5 sessions = 50 warm-up bars, so the 45-bar look-back is filled 5 bars before the
    # stretch opens and every one of its 20 bars trades; 4 sessions = 40 bars is not
    # enough, so the first 5 bars of the stretch stay silent.
    assert five["num_trades"] == 20
    assert four["num_trades"] == 15


def test_no_day_index_means_no_warm_up_rather_than_a_wrong_one():
    mod = _warmup_strategy(lookback=10)
    arrays = _session_arrays()
    arrays = dict(arrays, day_id=None)
    ev = make_slice_evaluator(mod, arrays, 0.0, warm_days=20)
    assert ev(200, 300, {"knob": 1.0}, warm=True) == ev(200, 300, {"knob": 1.0})


# ─────────────────────────────────────────────────────────────────────────────
# 7. the candidate scorer carries it
# ─────────────────────────────────────────────────────────────────────────────

def test_score_candidates_on_folds_warms_every_fold():
    mod = _warmup_strategy(lookback=120)
    arrays = _session_arrays(n_days=60, bars_per_day=10)
    bounds = [(200, 300), (300, 400), (400, 500)]
    cold = score_candidates_on_folds(mod, arrays, [{"knob": 1.0}], bounds)[0]
    warm = score_candidates_on_folds(mod, arrays, [{"knob": 1.0}], bounds,
                                     warm_days=20)[0]
    assert [r["oos_trades"] for r in cold] == [0, 0, 0]
    assert [r["oos_trades"] for r in warm] == [100, 100, 100]
    assert sum(r["oos_pnl"] for r in warm) == pytest.approx(300.0)
