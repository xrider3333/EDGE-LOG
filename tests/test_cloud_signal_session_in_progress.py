"""api/cloud_signal.py -- the `session_in_progress` pass-through (WEBULL_PAPER_TODO.md
item 15). See augur_strategies/ORB_3_6.py's own "LIVE-ENGINE ADDITION" note and
tests/test_orb_session_in_progress.py for the strategy-side half of this fix.

GENERIC BY DESIGN: this module never mentions ORB by name for this feature.
_leg_accepts_session_in_progress detects support purely by reflecting on whatever
run_backtest a leg's cfg["strategy"] resolves to, and _session_in_progress decides
purely off `arrays`' own last bar date vs `now` and the market calendar -- so every
test below uses a synthetic stub strategy, never a real one, to prove the mechanism
itself rather than ORB's particular fix.
"""
import datetime
import types

import pandas as pd
import pytest

import api.cloud_signal as cs


# ── _leg_accepts_session_in_progress: reflection, explicit declaration only ─────────────
def test_explicit_declaration_is_detected():
    mod = types.ModuleType("stub_declares_sip")
    mod.run_backtest = lambda o, h, l, c, day_id=None, session_in_progress=False, **kw: None
    assert cs._leg_accepts_session_in_progress(mod) is True


def test_bare_kwargs_catchall_does_not_count_as_support():
    """Unlike volumes/day_id (conventions every plugin tolerates via **kw), a bare
    catch-all must NOT be treated as opting in to a live-only correctness decision."""
    mod = types.ModuleType("stub_catchall_only")
    mod.run_backtest = lambda o, h, l, c, day_id=None, **kw: None
    assert cs._leg_accepts_session_in_progress(mod) is False


def test_no_declaration_at_all_is_not_support():
    mod = types.ModuleType("stub_plain")
    mod.run_backtest = lambda o, h, l, c, day_id=None: None
    assert cs._leg_accepts_session_in_progress(mod) is False


def test_unresolvable_strategy_string_is_best_effort_false():
    assert cs._leg_accepts_session_in_progress("NOT_A_REAL_FILE_xyz.py") is False


# ── _session_in_progress: last-session-date-vs-today + calendar check ───────────────────
def _arrays_ending(last_ts):
    idx = pd.DatetimeIndex([last_ts - pd.Timedelta(minutes=5), last_ts])
    return {"index": idx}


def test_true_when_last_session_is_today_and_not_a_half_day():
    now = pd.Timestamp("2026-09-18 10:15:00", tz=cs.TZ)
    arrays = _arrays_ending(pd.Timestamp("2026-09-18 10:10:00", tz=cs.TZ))
    assert cs._session_in_progress(arrays, now.to_pydatetime()) is True


def test_false_when_last_session_is_not_today():
    now = pd.Timestamp("2026-09-18 10:15:00", tz=cs.TZ)
    arrays = _arrays_ending(pd.Timestamp("2026-09-17 15:55:00", tz=cs.TZ))   # yesterday
    assert cs._session_in_progress(arrays, now.to_pydatetime()) is False


def test_false_on_a_real_recognised_half_day():
    """A GENUINE half day (day after Thanksgiving) must NOT be exempted even though the
    last session shares today's date -- only skip_holidays' own length test, unchanged,
    should fire there."""
    now = pd.Timestamp("2026-11-27 10:15:00", tz=cs.TZ)
    arrays = _arrays_ending(pd.Timestamp("2026-11-27 10:10:00", tz=cs.TZ))
    assert cs._session_in_progress(arrays, now.to_pydatetime()) is False


def test_false_and_never_raises_on_missing_or_bad_inputs():
    assert cs._session_in_progress({"index": pd.DatetimeIndex([])}, datetime.datetime.now()) is False
    assert cs._session_in_progress({}, datetime.datetime.now()) is False
    arrays = _arrays_ending(pd.Timestamp("2026-09-18 10:10:00", tz=cs.TZ))
    assert cs._session_in_progress(arrays, None) is False


# ── run_leg_trades: the actual pass-through into a leg's params ─────────────────────────
def _spy_stub(declares_param=True):
    seen = {}
    if declares_param:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                         session_in_progress=False, return_trades=False, **kw):
            seen["session_in_progress"] = session_in_progress
            seen["kwargs"] = dict(kw)
            return {"trades": [], "num_trades": 0, "total_pnl": 0, "win_rate": 0,
                   "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}
    else:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                         return_trades=False, **kw):
            seen["kwargs"] = dict(kw)
            seen["session_in_progress" ] = ("session_in_progress" in kw)
            return {"trades": [], "num_trades": 0, "total_pnl": 0, "win_rate": 0,
                   "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}
    mod = types.ModuleType(f"stub_spy_{declares_param}")
    mod.run_backtest = run_backtest
    return mod, seen


def _today_arrays():
    now = pd.Timestamp("2026-09-18 10:15:00", tz=cs.TZ)
    idx = pd.DatetimeIndex([now - pd.Timedelta(minutes=5), now - pd.Timedelta(minutes=0)])
    arrays = {"index": idx, "open": [100.0, 100.5], "high": [100.5, 101.0],
             "low": [99.5, 100.0], "close": [100.0, 100.5], "day_id": [0, 0]}
    return arrays, now


def test_run_leg_trades_sets_the_flag_when_supported_and_last_session_is_today():
    mod, seen = _spy_stub(declares_param=True)
    arrays, now = _today_arrays()
    cs.run_leg_trades({"strategy": mod, "params": {}}, arrays, now=now.to_pydatetime())
    assert seen["session_in_progress"] is True


def test_run_leg_trades_leaves_the_flag_off_when_now_is_omitted():
    """No `now` (every pre-existing call site) must reproduce today's behaviour exactly
    -- cfg["params"] untouched, the leg's own default used."""
    mod, seen = _spy_stub(declares_param=True)
    arrays, _ = _today_arrays()
    cs.run_leg_trades({"strategy": mod, "params": {}}, arrays)   # now defaults to None
    assert seen["session_in_progress"] is False


def test_run_leg_trades_leaves_the_flag_off_when_last_session_is_not_today():
    mod, seen = _spy_stub(declares_param=True)
    arrays, now = _today_arrays()
    stale_now = now + pd.Timedelta(days=1)
    cs.run_leg_trades({"strategy": mod, "params": {}}, arrays, now=stale_now.to_pydatetime())
    assert seen["session_in_progress"] is False


def test_run_leg_trades_never_hands_the_flag_to_a_strategy_that_did_not_opt_in():
    mod, seen = _spy_stub(declares_param=False)
    arrays, now = _today_arrays()
    cs.run_leg_trades({"strategy": mod, "params": {}}, arrays, now=now.to_pydatetime())
    assert seen["session_in_progress"] is False   # never appeared in kw at all


def test_run_leg_trades_does_not_mutate_cfg_params():
    """A per-call copy only -- cfg["params"] itself must be the SAME dict, untouched,
    so the next call (a different `now`) recomputes the flag fresh rather than
    inheriting a stale True from a previous tick."""
    mod, seen = _spy_stub(declares_param=True)
    params = {}
    cfg = {"strategy": mod, "params": params}
    arrays, now = _today_arrays()
    cs.run_leg_trades(cfg, arrays, now=now.to_pydatetime())
    assert params == {}
    assert cfg["params"] is params


# ── step(): end-to-end, a leg that opts in gets the flag on its own live tick ────────────
def test_step_passes_now_through_to_a_session_in_progress_leg(tmp_path):
    mod, seen = _spy_stub(declares_param=True)
    base = pd.Timestamp("2026-09-18 09:30:00", tz=cs.TZ)
    times = [base + pd.Timedelta(minutes=5 * i) for i in range(4)]
    epoch = [int(t.tz_convert("UTC").timestamp()) for t in times]
    epoch_df = pd.DataFrame({
        "time": epoch, "open": [100.0] * 4, "high": [100.5] * 4,
        "low": [99.5] * 4, "close": [100.0] * 4, "volume": [1000.0] * 4,
    })
    paths = cs._paths(home=str(tmp_path / "sip_home"))
    import os
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(cs._cache_path("5m", paths), index=False)

    legs = {"SIP": {"strategy": mod, "timeframe": "5m", "params": {}, "warmup_sessions": 5}}
    now = (times[-1] + pd.Timedelta(minutes=1)).to_pydatetime()
    cs.step(now=now, legs=legs, paths=paths, fetch=False)

    assert seen.get("session_in_progress") is True
