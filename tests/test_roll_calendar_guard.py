"""ENGINE ROLL GUARD (owner ask 2026-10-08 via MANAGER #54) - the one seam calendar, the run-time guard,
the roll stamp, and the plumbing around them. Synthetic bar grids on the committed roll table
(tools/data/rolls_NQ.csv), so nothing here needs a price master.

What is pinned:
  * seam_days answers from the table: the first session on the new contract (RTH), the session that
    contains the switch (24h / in-bar), no warm-up, nothing outside the series.
  * outside a roll context it refuses; with root None (adjusted / non-futures) it returns no seams.
  * MANAGER #58: on an UNADJUSTED NQ master signals run on a jump-free series - difference-adjusted
    for point logic, ratio-adjusted for % logic, declared (ROLL_SIGNAL, checked) or found by test - and
    fills / P&L come back at raw contract prices with the roll step out, on every engine path
    (run_backtest, the slice evaluator, the sweep, its process pool); TTM's flat gap exploit is gone.
  * a file that reads levels keeps raw prices and is refused when it holds across a switch; arrays
    that do not say what market they are are refused; the same run on an adjusted master passes and
    is stamped; report mode and live/paper callers never raise.
  * the 25 retired copies now ARE rolls.seam_days, and files without a detector are untouched.
"""
import os
import sys
import textwrap

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from augur_engine import rolls as R                         # noqa: E402

ET = "America/New_York"


def _rth_grid(d0, d1, step_min=5):
    """5-minute RTH bars 09:30..15:55 ET on business days, as a tz-aware index + day_id."""
    idx, did = [], []
    for j, d in enumerate(pd.bdate_range(d0, d1)):
        for k in range(0, 390, step_min):
            idx.append(pd.Timestamp(d.date(), tz=ET) + pd.Timedelta(hours=9, minutes=30 + k))
            did.append(j)
    return pd.DatetimeIndex(idx), np.asarray(did)


def _sessions(idx, did):
    starts = np.r_[0, np.flatnonzero(np.diff(did) != 0) + 1]
    return starts, idx[starts]


# ── 1. the calendar ──────────────────────────────────────────────────────────────────────────
def test_rth_switch_between_sessions_marks_the_next_session():
    idx, did = _rth_grid("2016-02-01", "2016-04-29")
    starts, day_ts = _sessions(idx, did)
    with R.roll_context("NQ", idx, 300):
        seams = R.seam_days(None, None, day_ts, ratio_th=2.5, abs_th=15.0)
    # NQH6 -> NQM6 switched 2016-03-10 19:00 ET (Thursday evening): Friday 03-11 opens on June
    assert [str(day_ts[s].date()) for s in seams] == ["2016-03-11"]


def test_weekday_evening_switch_is_not_put_a_day_early():
    idx, did = _rth_grid("2016-03-07", "2016-03-18")
    starts, day_ts = _sessions(idx, did)
    seams = R.seam_days_for(day_ts, "NQ", R.epoch_seconds(idx), 300)
    assert [str(day_ts[s].date()) for s in seams] == ["2016-03-11"]      # not Thursday 03-10


def test_in_bar_splice_marks_its_own_session():
    idx, did = _rth_grid("2026-09-08", "2026-09-18")
    starts, day_ts = _sessions(idx, did)
    seams = R.seam_days_for(day_ts, "NQ", R.epoch_seconds(idx), 300)
    # the 2026-09-14 11:30 ET switch happened INSIDE that session's 11:30 bar
    assert [str(day_ts[s].date()) for s in seams] == ["2026-09-14"]


def test_24h_session_containing_the_switch_is_the_seam():
    # 30-minute bars around the clock, sessions = ET calendar days (the house day_id)
    idx = pd.date_range("2016-03-07 00:00", "2016-03-14 23:30", freq="30min", tz=ET)
    idx = idx[idx.dayofweek < 5]
    did = np.asarray(pd.factorize(idx.date)[0])
    starts, day_ts = _sessions(idx, did)
    seams = R.seam_days_for(day_ts, "NQ", R.epoch_seconds(idx), 1800)
    assert [str(day_ts[s].date()) for s in seams] == ["2016-03-10"]      # the 19:00 switch is inside it


def test_short_window_sees_its_first_roll_and_nothing_outside_it():
    idx, did = _rth_grid("2016-03-09", "2016-03-14")                     # five sessions, no warm-up
    starts, day_ts = _sessions(idx, did)
    assert len(R.seam_days_for(day_ts, "NQ", R.epoch_seconds(idx), 300)) == 1
    idx2, did2 = _rth_grid("2016-04-04", "2016-05-27")                   # no switch inside
    s2, ts2 = _sessions(idx2, did2)
    assert R.seam_days_for(ts2, "NQ", R.epoch_seconds(idx2), 300) == []


def test_not_a_roll_rows_never_mark_a_seam():
    idx, did = _rth_grid("2026-08-03", "2026-09-11")                     # hole end + Labor Day rows
    s, ts = _sessions(idx, did)
    assert R.seam_days_for(ts, "NQ", R.epoch_seconds(idx), 300) == []


def test_no_context_refuses_and_root_none_has_no_seams():
    idx, did = _rth_grid("2016-03-07", "2016-03-18")
    s, ts = _sessions(idx, did)
    with pytest.raises(R.RollContextMissing):
        R.seam_days(None, None, ts)
    with R.roll_context(None, idx, 300):
        assert R.seam_days(None, None, ts) == []


def test_context_is_thread_local():
    import threading
    idx, did = _rth_grid("2016-03-07", "2016-03-18")
    s, ts = _sessions(idx, did)
    seen = {}

    def other():
        try:
            R.seam_days(None, None, ts)
            seen["other"] = "answered"
        except R.RollContextMissing:
            seen["other"] = "refused"

    with R.roll_context("NQ", idx, 300):
        th = threading.Thread(target=other)
        th.start()
        th.join(timeout=30)
        assert len(R.seam_days(None, None, ts)) == 1
    assert seen["other"] == "refused"


# ── 2. the plan and the guard, through every engine path (v4, MANAGER #58) ──────────────────────
STRATS = textwrap.dedent('''
    STRATEGY_NAME = "test strategies"
    def _res(trades, return_trades):
        res = dict(total_pnl=sum(t[2] for t in trades), num_trades=len(trades),
                   win_rate=0.0, profit_factor=1.0, max_drawdown=0.0)
        if return_trades:
            res["trades"] = trades
        return res

    def run_backtest(open_, high, low, close, return_trades=False, mode="hold", level=0.0, gap=40.0,
                     pct=0.0, **kw):
        n = len(close)
        hold = [(0, n - 1, float(close[-1] - close[0]), 1, float(close[0]))]
        if mode == "hold":          # one long, first bar to last: across every switch, reads no price
            trades = hold
        elif mode == "flat":        # one long per 78-bar session, never overnight, reads no price
            trades = [(a, a + 77, float(close[a + 77] - close[a]), 1, float(close[a]))
                      for a in range(0, n - 77, 78)]
        elif mode == "level":       # holds only while the first close is below a LEVEL: level-reading
            trades = hold if close[0] < level else []
        elif mode == "pct":         # holds only when the first bar's range is over pct of its close: % logic
            trades = hold if (high[0] - low[0]) / close[0] > pct else []
        elif mode == "none":        # never trades
            trades = []
        elif mode == "gap":         # TTM's exploit: buy a session that OPENS >= gap away from the
            trades = []             # prior session's close, out at that session's close - flat overnight
            for a in range(78, n - 77, 78):
                if abs(open_[a] - close[a - 1]) >= gap:
                    trades.append((a, a + 77, float(close[a + 77] - open_[a]), 1, float(open_[a])))
        return _res(trades, return_trades)
''')


@pytest.fixture()
def make(tmp_path):
    """One strategy FILE per behaviour (the plan classifies files), its mode baked in as the default;
    `declare` writes ROLL_SIGNAL into the file."""
    from augur_engine.strategies import load_strategy

    def _make(mode, declare=None, **defaults):
        name = "ROLL%s%s_9_9.py" % (mode.upper(), ("_" + declare.upper()) if declare else "")
        src = STRATS.replace('mode="hold", level=0.0, gap=40.0,\n                 pct=0.0',
                             'mode=%r, level=%r, gap=%r,\n                 pct=%r'
                             % (mode, defaults.get("level", 4405.0), defaults.get("gap", 5.0),
                                defaults.get("pct", 0.00043)))
        assert src != STRATS
        if declare:
            src = src.replace('STRATEGY_NAME = "test strategies"',
                              'STRATEGY_NAME = "test strategies"\nROLL_SIGNAL = %r' % declare)
        p = tmp_path / name
        p.write_text(src, encoding="utf-8")
        return load_strategy(str(p)), str(p)
    return _make


@pytest.fixture()
def strat(make):
    return make("hold")[0]


STEP = -9.50          # NQH6 -> NQM6 offset in tools/data/rolls_NQ.csv (NEW minus OLD)


def _arrays(source, d0="2016-02-29", d1="2016-03-18", instrument="NQ", provenance=None):
    """A flat-drifting NQ tape that, on an UNADJUSTED source, carries the real NQH6 -> NQM6 step
    (-9.50 points at 2016-03-10 19:00 ET) - as the raw master does; back-adjusting removes it."""
    idx, did = _rth_grid(d0, d1)
    n = len(idx)
    c = 4400.0 + np.cumsum(np.full(n, 0.01))
    if source and not str(source).startswith(("db_adj", "db_fadj")):
        sw = R.epoch_seconds([pd.Timestamp("2016-03-10 19:00", tz=ET)])[0]
        c = c + np.where(R.epoch_seconds(idx) > sw, STEP, 0.0)              # the real -9.50 step
    meta = dict(instrument=instrument, source=source, timeframe="5m", name="NQ 5m test " + str(source))
    if provenance is not None:
        meta.update(provenance=provenance, date_from=str(d0))
    return dict(open=c.copy(), high=c + 1, low=c - 1, close=c, volume=np.ones(n), day_id=did,
                index=idx, meta=meta)


def _raw_hold_pnl(a=0):
    raw = _arrays("db_noadj_rth")
    return float(raw["close"][-1] - raw["close"][a]) - STEP, float(raw["close"][a])


def test_point_logic_file_gets_difference_adjusted_signals_and_raw_fills(strat):
    import augur_engine as ae
    r = ae.run_backtest(strat, arrays=_arrays("db_noadj_rth"), return_trades=True)
    st = r["_meta"]["roll_stamp"]
    assert st["calendar"] == "difference-adjusted signals"
    assert st["signal_method"] == "difference" and st["method_source"] == "test"
    assert st["master_type"] == "unadjusted, signals difference-adjusted on the fly, fills raw"
    assert st["trades_crossing"] == 1 and st["usd_roll_step"] == 0.0      # held across, booked no step
    pnl, entry = _raw_hold_pnl()
    assert r["total_pnl"] == pytest.approx(pnl, abs=1e-6)                 # raw close-to-close, step out
    assert r["trades"][0][4] == pytest.approx(entry, abs=1e-9)            # the fill at the RAW price
    adj = ae.run_backtest(strat, arrays=_arrays("db_adj_rth"))            # = the adjusted master's P&L
    assert r["total_pnl"] == pytest.approx(adj["total_pnl"], abs=1e-6)


def test_percent_logic_file_gets_ratio_adjusted_signals_and_raw_fills(make):
    """#58: % logic is ratio-adjusted (a difference back-adjust would change its threshold), and its
    fills and P&L are re-priced to raw contract prices with the roll step taken out."""
    import augur_engine as ae
    pct = make("pct")[0]
    r = ae.run_backtest(pct, arrays=_arrays("db_noadj_rth"), return_trades=True)
    st = r["_meta"]["roll_stamp"]
    assert st["calendar"] == "ratio-adjusted signals" and st["signal_method"] == "ratio"
    assert st["method_tests"]["shift"] < 1.0 and st["method_tests"]["scale"] == 1.0
    assert "ratio-adjusted" in st["master_type"]
    pnl, entry = _raw_hold_pnl()
    assert r["num_trades"] == 1
    assert r["total_pnl"] == pytest.approx(pnl, abs=1e-6)
    assert r["trades"][0][4] == pytest.approx(entry, abs=1e-6)
    no_trades = ae.run_backtest(pct, arrays=_arrays("db_noadj_rth"))     # ratio path without trades asked
    assert no_trades["total_pnl"] == pytest.approx(pnl, abs=1e-6) and "trades" not in no_trades


def test_declared_method_is_used_and_checked(make):
    import augur_engine as ae
    r = ae.run_backtest(make("pct", declare="ratio")[0], arrays=_arrays("db_noadj_rth"))
    st = r["_meta"]["roll_stamp"]
    assert st["signal_method"] == "ratio" and st["method_source"] == "declared"
    with pytest.raises(R.RollGuardError) as e:                            # % logic declared as points
        ae.run_backtest(make("pct", declare="difference")[0], arrays=_arrays("db_noadj_rth"))
    assert "declares ROLL_SIGNAL = 'difference'" in str(e.value)
    with pytest.raises(R.RollGuardError):                                 # declared raw + held across
        ae.run_backtest(make("hold", declare="raw")[0], arrays=_arrays("db_noadj_rth"))
    r = ae.run_backtest(make("flat", declare="raw")[0], arrays=_arrays("db_noadj_rth"))
    assert r["_meta"]["roll_stamp"]["calendar"] == "raw (declared)"


def test_ttm_exploit_a_flat_gap_trader_no_longer_trades_the_roll_step(make):
    """MANAGER #57 / TTM #56 point 1: flat across the switch, yet its SIGNAL read the step. On the
    planned (adjusted) series the switch-session gap is gone, so the fake entry is gone - and the
    stamp's raw-vs-adjusted check shows the one trade that only raw prices made, next to the switch."""
    import augur_engine as ae
    gapper = make("gap")[0]
    planned = ae.run_backtest(gapper, arrays=_arrays("db_noadj_rth"), return_trades=True, roll_diff=True)
    raw = ae.run_backtest(gapper, arrays=_arrays("db_noadj_rth"), params=dict(roll_treatment="raw"),
                          return_trades=True)
    assert raw["num_trades"] == 1                    # raw prices: it traded the -9.50 roll step
    assert planned["num_trades"] == 0                # adjusted signals: nothing to trade
    st = planned["_meta"]["roll_stamp"]
    assert st["calendar"] == "difference-adjusted signals"
    d = st["raw_vs_adjusted"]
    assert d["only_raw"] == 1 and d["only_adjusted"] == 0 and d["price_moves_near_switch"] == 1
    assert d["price_moves_elsewhere"] == 0 and d["verdict"].startswith("differs near switches")


def test_raw_vs_adjusted_is_identical_for_a_file_the_roll_never_reaches(strat):
    import augur_engine as ae
    r = ae.run_backtest(strat, arrays=_arrays("db_noadj_rth"), roll_diff=True)
    d = r["_meta"]["roll_stamp"]["raw_vs_adjusted"]
    assert d["verdict"] == "identical" and d["same"] == 1
    assert "raw_vs_adjusted" not in ae.run_backtest(strat, arrays=_arrays("db_noadj_rth"))["_meta"]["roll_stamp"]


def test_level_reading_file_keeps_raw_prices_and_is_refused_when_it_crosses(make):
    import augur_engine as ae
    lvl = make("level")[0]
    with pytest.raises(R.RollGuardError) as e:
        ae.run_backtest(lvl, arrays=_arrays("db_noadj_rth"))
    msg = str(e.value)
    assert "contract switch" in msg and "adjusted master" in msg and "ROLLLEVEL_9_9.py" in msg
    plan = R.plan_for(lvl, _arrays("db_noadj_rth"), lvl.__file__, {})
    assert plan["kind"] == "raw: level-dependent" and plan["tests"]["scale"] < 1.0


def test_a_file_with_no_trades_in_the_test_sample_is_not_trusted(make):
    m = make("none")[0]
    plan = R.plan_for(m, _arrays("db_noadj_rth"), m.__file__, {})
    assert plan["kind"].startswith("raw: untested") and plan["refuse_crossings"]


def test_raw_opt_out_is_refused_when_it_crosses_and_stamped_when_it_does_not(strat, make):
    import augur_engine as ae
    with pytest.raises(R.RollGuardError):
        ae.run_backtest(strat, arrays=_arrays("db_noadj_rth"), params=dict(roll_treatment="raw"))
    r = ae.run_backtest(make("flat")[0], arrays=_arrays("db_noadj_rth"), params=dict(roll_treatment="raw"))
    assert r["_meta"]["roll_stamp"]["calendar"] == "raw (opted out)"
    assert r["_meta"]["roll_stamp"]["trades_crossing"] == 0


def test_adjusted_master_passes_and_is_stamped(strat, make):
    import augur_engine as ae
    r = ae.run_backtest(strat, arrays=_arrays("db_adj_rth"))
    st = r["_meta"]["roll_stamp"]
    assert st["master_type"] == "adjusted" and st["calendar"] == "adjusted master"
    assert st["trades_crossing"] == 1 and st["usd_roll_step"] == 0.0 and not st["warning"]
    # #58: a %-reading file on a difference-adjusted master is warned in the stamp
    r = ae.run_backtest(make("pct")[0], arrays=_arrays("db_adj_rth"))
    assert "difference-adjusted" in (r["_meta"]["roll_stamp"]["warning"] or "")


def test_stale_adjusted_master_is_refused_past_its_last_applied_switch(strat):
    import augur_engine as ae
    ok = _arrays("db_adj_rth", provenance='{"switches_applied": 999}')
    ae.run_backtest(strat, arrays=ok)
    stale = _arrays("db_adj_rth", provenance='{"switches_applied": 0}')
    with pytest.raises(R.RollGuardError) as e:
        ae.run_backtest(strat, arrays=stale)
    assert "Rebuild the adjusted masters" in str(e.value)


def test_futures_root_without_a_roll_table_is_refused(strat):
    import augur_engine as ae
    with pytest.raises(R.RollGuardError) as e:
        ae.run_backtest(strat, arrays=_arrays("db_noadj_rth", instrument="CL"))
    assert "no roll table" in str(e.value)


def test_mnq_tv_and_blank_sources_count_as_unadjusted():
    for inst, src in (("MNQ", "db_noadj_rth"), ("NQ", "tv"), ("NQ", "yahoo"), ("ES", ""), ("MES", "x")):
        assert R.unadjusted_futures_root(dict(instrument=inst, source=src)) in ("NQ", "ES")
    assert R.unadjusted_futures_root(dict(instrument="NQ", source="db_adj_eth")) is None
    assert R.unadjusted_futures_root(dict(instrument="QQQ", source="alpaca_split_rth")) is None


def test_arrays_that_do_not_say_what_they_are_are_refused(strat):
    """#58 (A): fail closed. No instrument -> refused, unless the caller declares roll_mode='none'."""
    import augur_engine as ae
    arr = _arrays("db_noadj_rth")
    arr["meta"] = {"name": "SYN"}
    with pytest.raises(R.RollGuardError) as e:
        ae.run_backtest(strat, arrays=arr)
    assert "roll_mode" in str(e.value)
    bare = {k: v for k, v in _arrays("db_noadj_rth").items() if k != "meta"}
    with pytest.raises(R.RollGuardError):
        ae.run_backtest(strat, arrays=bare)
    arr["meta"] = {"name": "SYN", "roll_mode": "none"}
    r = ae.run_backtest(strat, arrays=arr)
    assert "roll_stamp" not in r["_meta"]
    with R.guard_mode("report"):                                         # live / paper: warned only
        assert R.plan_for(strat, dict(arr, meta={"name": "SYN"}), "x.py", {})["kind"] == "undeclared"
    live = R.plan_for(strat, dict(arr, meta={"roll_mode": "live"}), "x.py", {})   # the live bar builder
    assert live["kind"].startswith("live bar builder") and not live["adjust"]


def test_planning_twice_is_a_no_op(make):
    pct = make("pct")[0]
    arr = _arrays("db_noadj_rth")
    p1 = R.plan_for(pct, arr, pct.__file__, {})
    a1 = R.apply_plan(arr, p1)
    p2 = R.plan_for(pct, a1, pct.__file__, {})
    a2 = R.apply_plan(a1, p2)
    assert p2 is p1 and "times" in p2 and np.array_equal(a2["close"], a1["close"])
    assert a2["meta"]["source"] == "db_adj_otf_ratio:db_noadj_rth"


def test_planned_arrays_cut_afterwards_keep_raw_fills(make):
    """An in-sample / out-of-sample split (a boolean mask that keeps the meta) of planned arrays:
    the plan follows the bars that are left, so fills still come back at raw prices."""
    import augur_engine as ae
    pct = make("pct")[0]
    arr = _arrays("db_noadj_rth")
    planned = R.apply_plan(arr, R.plan_for(pct, arr, pct.__file__, {}))
    keep = np.arange(len(arr["close"])) >= 78
    cut = {k: (v[keep] if hasattr(v, "shape") else v) for k, v in planned.items()}
    r = ae.run_backtest(pct, arrays=cut)
    pnl, _e = _raw_hold_pnl(78)
    assert r["total_pnl"] == pytest.approx(pnl, abs=1e-6)
    assert np.allclose(R.raw_view(planned)["close"], arr["close"])
    assert np.allclose(R.raw_view(cut)["close"], arr["close"][keep])


def test_report_mode_and_live_callers_never_raise(make):
    import augur_engine as ae
    lvl = make("level")[0]
    with R.guard_mode("report"):
        r = ae.run_backtest(lvl, arrays=_arrays("db_noadj_rth"))
    st = r["_meta"]["roll_stamp"]
    assert st["trades_crossing"] == 1 and st["usd_roll_step"] != 0.0      # the step it booked
    # report mode from a research script only WAIVES the refusal; the plan is the research plan and
    # the stamp says the result is not a research result (TTM attack 8)
    assert st["calendar"] == "raw: level-dependent" and st["guard"].startswith("report mode")
    with R.guard_mode("report"):                                          # a point file is still adjusted
        p = ae.run_backtest(make("hold")[0], arrays=_arrays("db_noadj_rth"))
    assert p["_meta"]["roll_stamp"]["calendar"] == "difference-adjusted signals"
    g = {"__file__": os.path.join(ROOT, "api", "paper.py"), "ae": ae, "strat": lvl,
         "arr": _arrays("db_noadj_rth")}
    exec("res = ae.run_backtest(strat, arrays=arr)", g)
    assert g["res"]["_meta"]["roll_stamp"]["trades_crossing"] == 1
    assert g["res"]["_meta"]["roll_stamp"]["calendar"] == "raw (live/paper path)"
    # the live KEEL state builder (tools/keel_live_state.py) fits live sizing on these trades:
    # a planned run there would change live sizing, so it is report-only too
    g2 = dict(g, __file__=os.path.join(ROOT, "tools", "keel_live_state.py"), arr=_arrays("db_noadj_rth"))
    exec("res = ae.run_backtest(strat, arrays=arr)", g2)
    assert g2["res"]["_meta"]["roll_stamp"]["calendar"] == "raw (live/paper path)"
    g3 = dict(g, __file__=os.path.join(ROOT, "tools", "some_research.py"), arr=_arrays("db_noadj_rth"))
    with pytest.raises(R.RollGuardError):                                   # a research tool is not
        exec("res = ae.run_backtest(strat, arrays=arr)", g3)


def test_slice_evaluator_reraises_the_refusal_and_reprices_a_slice(make):
    from augur_engine.auto import make_slice_evaluator
    arr = _arrays("db_noadj_rth")
    ev = make_slice_evaluator(make("level")[0], arr, 0.0)
    with pytest.raises(R.RollGuardError):
        ev(0, len(arr["close"]), {})
    ev2 = make_slice_evaluator(make("flat")[0], arr, 0.0)
    assert ev2(0, len(arr["close"]), {}) is not None
    ev3 = make_slice_evaluator(make("pct")[0], arr, 0.0)                 # ratio, a slice from bar 78
    pnl, _e = _raw_hold_pnl(78)
    m = ev3(78, len(arr["close"]), {}, keep_trades=True)
    assert m["total_pnl"] == pytest.approx(pnl, abs=1e-6)


@pytest.mark.parametrize("workers", [1, 2])
def test_sweep_refuses_at_the_first_crossing_trial(make, workers):
    from augur_engine.optimize import run_grid
    _mod, path = make("level")
    with pytest.raises(R.RollGuardError):
        run_grid(path, arrays=_arrays("db_noadj_rth"), grid={"level": [4405.0, 4410.0]},
                 min_trades=1, workers=workers)


@pytest.mark.parametrize("workers", [1, 2])
def test_sweep_reprices_ratio_fills_like_the_engine(make, workers):
    from augur_engine.optimize import run_grid
    _mod, path = make("pct")
    out = run_grid(path, arrays=_arrays("db_noadj_rth"), grid={"pct": [0.00043, 0.00044]},
                   min_trades=1, workers=workers)
    pnl, _e = _raw_hold_pnl()
    assert out["best"]["total_pnl"] == pytest.approx(pnl, abs=1e-6)


# ── TTM's attack on v4 (2026-10-08): the holes, closed ──────────────────────────────────────────
def test_ttm7_a_module_rebuilt_in_memory_under_a_roll_aware_name_is_not_trusted():
    import types
    from augur_engine.strategies import load_strategy
    real_path = os.path.join(ROOT, "augur_strategies", "NQDIP_1_3.py")
    real = load_strategy(real_path)
    assert R.is_roll_aware(real_path, real)                                # the real file, as loaded
    fake = types.ModuleType("augur_engine_strat_NQDIP_1_3_py_rebuilt")
    fake.__file__ = real_path
    exec(compile(STRATS, real_path, "exec"), fake.__dict__)               # other code, same __file__
    assert not R.is_roll_aware(real_path, fake)
    plan = R.plan_for(fake, _arrays("db_noadj_rth"), real_path, {})
    assert plan["kind"] != "roll-aware strategy"
    edited = types.ModuleType("augur_engine_strat_NQDIP_1_3_py_edited")    # same code, one constant changed
    edited.__file__ = real_path
    exec(compile(open(real_path, encoding="utf-8").read(), real_path, "exec"), edited.__dict__)
    consts = [k for k, v in vars(edited).items() if isinstance(v, (int, float)) and not k.startswith("_")
              and not isinstance(v, bool)]
    if consts:
        setattr(edited, consts[0], getattr(edited, consts[0]) + 1)
        assert not R.is_roll_aware(real_path, edited)


@pytest.mark.parametrize("alias", ["NQ1!", "/NQ", "NQZ6", "NQ=F", "nq", "MNQH2026"])
def test_ttm4_instrument_aliases_are_the_root(strat, alias):
    import augur_engine as ae
    r = ae.run_backtest(strat, arrays=_arrays("db_noadj_rth", instrument=alias))
    assert r["_meta"]["roll_stamp"]["calendar"] == "difference-adjusted signals"


@pytest.mark.parametrize("alias", ["CL1!", "/GC", "CLZ6", "GC=F", "RTY1!"])
def test_ttm4_futures_aliases_without_a_table_are_refused(strat, alias):
    import augur_engine as ae
    with pytest.raises(R.RollGuardError):
        ae.run_backtest(strat, arrays=_arrays("db_noadj_rth", instrument=alias))


def _stepped(source, steps):
    """A 5m RTH tape 2021-01 .. 2026-09 whose prices carry (or not) every real NQ switch's step."""
    idx, did = _rth_grid("2021-01-04", "2026-09-30")
    n = len(idx)
    c = 15000.0 + np.cumsum(np.full(n, 0.001))
    if steps:
        t = R.epoch_seconds(idx)
        for r in R.real_switches("NQ"):
            c = c + np.where(t >= r["switch_sec"], float(r["offset_pts"]), 0.0)
    meta = dict(instrument="NQ", source=source, timeframe="5m", name="NQ 5m " + source)
    return dict(open=c.copy(), high=c + 1, low=c - 1, close=c, volume=np.ones(n), day_id=did, index=idx, meta=meta)


def test_ttm5_a_label_the_prices_contradict_is_refused(strat):
    hold = _stepped("db_adj_rth", steps=True)                             # raw prices labelled adjusted
    lc = R.label_check(R.epoch_seconds(hold["index"]), hold["open"], hold["close"], "NQ", 300)
    assert lc["eligible"] >= R.LABEL_MIN_SWITCHES and lc["raw_like"] == lc["eligible"]
    with pytest.raises(R.RollGuardError) as e:
        R.plan_for(strat, hold, strat.__file__, {})
    assert "label is wrong" in str(e.value)
    with pytest.raises(R.RollGuardError):                                 # adjusted prices labelled raw
        R.plan_for(strat, _stepped("db_noadj_rth", steps=False), strat.__file__, {})
    ok = R.plan_for(strat, _stepped("db_adj_rth", steps=False), strat.__file__, {})   # honest labels pass
    assert ok["kind"] == "adjusted master"
    ok2 = R.plan_for(strat, _stepped("db_noadj_rth", steps=True), strat.__file__, {})
    assert ok2["kind"] == "difference-adjusted signals"


def test_ttm8_report_mode_is_for_the_audit_tool_and_tests_only(tmp_path):
    import subprocess
    script = tmp_path / "my_research.py"                                  # a research script, run on its own
    script.write_text("import sys\nsys.path.insert(0, %r)\nfrom augur_engine import rolls as R\n"
                      "try:\n    R.guard_mode('report').__enter__()\n    print('ALLOWED')\n"
                      "except R.RollGuardError:\n    print('REFUSED')\n" % ROOT, encoding="utf-8")
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "REFUSED", out.stdout + out.stderr
    g2 ={"__file__": os.path.join(ROOT, "tools", "roll_guard_probe.py"), "R": R}
    exec("with R.guard_mode('report'):\n    ok = R.current_guard_mode()\n", g2)
    assert g2["ok"] == "report"


def test_ttm11_a_borrowed_live_file_name_is_not_report_only(tmp_path, make):
    import augur_engine as ae
    lvl = make("level")[0]
    fake = tmp_path / "api" / "paper.py"
    g = {"__file__": str(fake), "ae": ae, "strat": lvl, "arr": _arrays("db_noadj_rth")}
    with pytest.raises(R.RollGuardError):
        exec("res = ae.run_backtest(strat, arrays=arr)", g)


def test_ttm2c_two_in_memory_modules_never_share_a_method_test():
    import types
    pt = types.ModuleType("mem_point")
    exec(STRATS, pt.__dict__)
    lv = types.ModuleType("mem_level")
    exec(STRATS.replace('mode="hold"', 'mode="level"').replace("level=0.0", "level=4405.0"), lv.__dict__)
    arr = _arrays("db_noadj_rth")
    p1 = R.plan_for(pt, arr, None, {})
    p2 = R.plan_for(lv, _arrays("db_noadj_rth"), None, {})
    assert p1["kind"] == "difference-adjusted signals" and p2["kind"] == "raw: level-dependent"


def test_ttm6b_a_forged_roll_plan_is_ignored_or_refused(strat, make):
    import augur_engine as ae
    arr = _arrays("db_noadj_rth")
    arr["meta"] = dict(arr["meta"], roll_plan=dict(kind="declared: no contract rolls", adjust=False,
                                                    refuse_crossings=False, root=None, ctx_root=None,
                                                    times=R.epoch_seconds(arr["index"]), tf=300))
    with pytest.raises(R.RollGuardError):                                 # re-planned: the level file is refused
        ae.run_backtest(make("level")[0], arrays=arr)
    planned = R.apply_plan(_arrays("db_noadj_rth"), R.plan_for(strat, _arrays("db_noadj_rth"), strat.__file__, {}))
    forged = dict(planned, meta=dict(planned["meta"], roll_plan=dict(planned["meta"]["roll_plan"],
                                                                     sc=np.zeros(len(planned["close"])))))
    with pytest.raises(R.RollGuardError):                                 # adjusted plan with wrong factors
        ae.run_backtest(strat, arrays=forged)


def test_roll_aware_list_is_keyed_by_content(tmp_path):
    real = os.path.join(ROOT, "augur_strategies", "NQDIP_1_2.py")
    assert R.is_roll_aware(real)
    spoof = tmp_path / "NQDIP_1_2.py"                                       # same name, other content
    spoof.write_text(open(real, encoding="utf-8").read() + "\n# edited\n", encoding="utf-8")
    assert not R.is_roll_aware(str(spoof))
    for name, sha in R.ROLL_AWARE_SHA.items():                              # pins match the files
        assert R.file_sha(os.path.join(ROOT, "augur_strategies", name)) == sha, name


def test_assert_no_crossings_for_self_simulating_harnesses():
    a = [pd.Timestamp("2016-03-10 10:00", tz=ET)]
    b = [pd.Timestamp("2016-03-11 15:55", tz=ET)]
    with pytest.raises(R.RollGuardError):
        R.assert_no_crossings(a, b, "NQ", "db_noadj_rth", label="tools/x_stageA.py")
    assert R.assert_no_crossings(a, b, "NQ", "db_adj_rth") == 0
    assert R.assert_no_crossings(a, [pd.Timestamp("2016-03-10 15:55", tz=ET)], "NQ", "db_noadj_rth") == 0


# ── 3. the redirect and the cache key ──────────────────────────────────────────────────────
RETIRED = ["AOSTOCH_1_0", "BBRSI_1_0", "EMAX_1_0", "FLAWLESS_1_0", "GAPFADE_1_0", "GAPGO_1_0",
           "GAPGO_TRAVEL_1_0", "GOLDX_1_0", "HULL_1_0", "ICHIHULL_1_0", "MACD200_1_0", "MACDRSI_1_0",
           "NQDIP_1_0", "NQDIP_1_1", "NQDIP_1_2", "NQDIP_1_3", "NQDIP_1_4", "ONDRIFT_1_0", "PMAX_1_0",
           "RSIDIV_1_0", "SUPERTREND_3_0", "TTIBS_1_0", "TTIBS_1_1", "TTIBS_1_2", "TTIBS_1_3"]


@pytest.mark.parametrize("name", RETIRED)
def test_every_retired_copy_is_the_audited_function(name):
    from augur_engine.strategies import load_strategy
    mod = load_strategy(name + ".py")
    assert mod.detect_roll_seams is R.seam_days


def test_cache_key_changes_only_for_guarded_jobs():
    from augur_engine import trial_cache as TC
    base = dict(strategy_file_sha="x", engine_epoch=1, master_id="m", data_fingerprint="f")
    k0 = TC.make_key(base, {"a": 1})
    assert TC.make_key(dict(base, roll_guard=None), {"a": 1}) == k0       # unguarded: unchanged
    assert TC.make_key(dict(base, roll_guard="v3|difference-adjusted signals|abc"), {"a": 1}) != k0


def test_combine_stamps_sums_the_legs():
    a = dict(master_type="unadjusted", source="s1", calendar="true roll table", roll_source="r",
             switches_in_window=2, switches_estimated=0, trades_crossing=0, usd_crossing_trades=0.0,
             usd_roll_step=0.0, usd_switch_sessions=10.0)
    b = dict(a, master_type="adjusted", trades_crossing=3, usd_switch_sessions=-4.0)
    c = R.combine_stamps([a, None, b])
    assert c["legs_stamped"] == 2 and c["trades_crossing"] == 3 and c["usd_switch_sessions"] == 6.0
    assert c["master_type"] == ["adjusted", "unadjusted"]
    assert R.combine_stamps([None]) is None
