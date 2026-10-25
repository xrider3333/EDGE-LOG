"""Owner item 51 - DD% from peak + the worst $ drawdown per stretch on a VALUED daily series
(augur_engine/stretch_dd.py; design C:/EdgeLog/_research_cache/item51/ENGINE_DESIGN.md + Critic C1-C7,
DECISIONS_1020.md).

What is pinned here, by the design's test ids:
  T1  intraday only: the valued curve IS the closed-trade daily curve.
  T2  THE OVERNIGHT HOLDER: closed-trade daily DD $0, valued DD $600 = 0.5988% of $100,200.
  T3  a multi-day trade with no side / entry price -> the stretch is null with the count, never 0.
  T4  IS / WF boundary: entry membership, the IS series runs on to the trade's exit, both cent-checked.
  T5  wf_lb = the WF chain then the lockbox as ONE daily series; a shared boundary day sums.
  T6  a one-day stretch -> null (FEW_DAYS), no exception.
  T7  gate_validate with mtm=None vs mtm=ctx: every old key identical, only the three keys added.
  T8  the per-trade (vectorized) path == one direct whole-array book._mtm_increments call, to the cent.
  T9  a PNL_UNITS="usd" file is UNSIZED (decision 5 overrides the body's plugin-mark plan).
  T10 no _oos_side / _oos_px / _oos_pnlf anywhere in a saved validate result.
  T11 the trial-cache key and ENGINE_CACHE_EPOCH are pinned (item 51 touches neither).
  T12 a fold whose test_start bar timestamp moved -> wf and wf_lb null, is / lb / full unaffected.
  T13 UNSIZED: QQQ, yahoo_adj, alpaca; a job multiplier of 20 on QQQ is still UNSIZED.
  T15 (C1) ETH: a Fri 15:00 -> Mon 10:00 long across the Sunday 18:00 open on a DST Sunday has exactly
      ONE mark (the Fri 16:59 session close) and no Sunday row; an 18:30 -> 10:00 trade is same-day.
  T16 (C2) a long held across a contract switch with a +200 step: no mark carries the step; a ratio
      plan is refused (RATIO_ROLL).
  plus: the cent check refuses a $0.01 miss; a member-count mismatch refuses; C7 out-of-frame refuses;
  C3 a folded size scales the marks; and a synthetic run_validate whose existing keys are
  byte-identical with item 51 on and off, the new keys where the decisions put them and nowhere else.
"""
import json
import math
import types

import numpy as np
import pandas as pd
import pytest

from augur_engine import stretch_dd as S
from augur_engine import book as B
from augur_engine.drawdowns import four_numbers


def _rth_frame(closes, dates=None, times=("10:00", "15:55"), meta=None):
    """Two bars a day by default; closes in bar order."""
    n_days = (len(closes) + len(times) - 1) // len(times)
    dates = dates or [str(d.date()) for d in pd.bdate_range("2024-01-02", periods=n_days)]
    stamps = [f"{d} {t}" for d in dates for t in times][:len(closes)]
    idx = pd.DatetimeIndex(stamps).tz_localize("US/Eastern")
    return {"index": idx, "close": np.asarray(closes, dtype=float),
            "meta": meta or {"instrument": "NQ", "session": "rth", "source": "db_adj_rth",
                             "timeframe": "5m"}}


# ── T2: the overnight holder ────────────────────────────────────────────────────────────────────────
def test_overnight_holder_closed_dd_zero_valued_dd_600():
    """NQ x 20, long at 100 on day 1 (day-1 close 110), day-2 close 80, exit day 3 at 105 (+5 pts)."""
    arr = _rth_frame([100, 110, 90, 80, 105, 106])
    fr = S.Frame(arr)
    v = S.Valuation(fr, [(0, 4, 5.0, 1, 100.0)], 20.0)
    r, why = S.reading(v, [True], 0, fr.n - 1, 5.0 * 20)
    assert why is None
    assert r == {"dd_pct_peak": 0.5988, "dd_usd": 600.0, "marked": 1}
    assert r["dd_pct_peak"] == round(600 / 100200 * 100, 4)
    assert list(v.row_usd) == [200.0, -600.0, 500.0]                  # +200, -600, +500
    assert math.fsum(v.row_usd) == pytest.approx(100.0, abs=1e-9)     # = 5 pts x 20
    # the closed-trade daily curve of the same stretch: one winning trade, no drawdown at all
    closed = four_numbers([0.0, 0.0, 100.0], dates=["2024-01-02", "2024-01-03", "2024-01-04"])
    assert closed["max_dd"] == 0.0 and closed["dd_pct_peak"] == 0.0


# ── T1: intraday only ───────────────────────────────────────────────────────────────────────────────
def test_intraday_only_equals_the_closed_trade_daily_curve():
    arr = _rth_frame([100, 101, 102, 103, 104, 105])
    fr = S.Frame(arr)
    trades = [(0, 1, -3.0, 1, 100.0), (2, 3, 1.0, -1, 102.0), (4, 5, -4.0, 1, 104.0)]
    v = S.Valuation(fr, trades, 20.0)
    r, why = S.reading(v, [True] * 3, 0, fr.n - 1, -6.0 * 20)
    assert why is None and r["marked"] == 0
    daily = [-60.0, 20.0, -80.0]
    f = four_numbers(daily, dates=["2024-01-02", "2024-01-03", "2024-01-04"])
    assert r["dd_usd"] == f["max_dd"] == 120.0
    assert r["dd_pct_peak"] == f["dd_pct_peak"]
    # C5 sanity (non-overlapping intraday trades): the daily DD never exceeds the per-trade DD
    assert r["dd_usd"] <= 140.0 + 0.01


# ── T3: an open position that cannot be valued ─────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [(0, 4, 5.0, 0, 100.0), (0, 4, 5.0, 1, float("nan")), (0, 4, 5.0)])
def test_unmarked_multi_day_trade_makes_the_stretch_null_with_its_count(bad):
    fr = S.Frame(_rth_frame([100, 110, 90, 80, 105, 106]))
    v = S.Valuation(fr, [bad, (5, 5, 1.0, 1, 106.0)], 20.0)
    r, why = S.reading(v, [True, True], 0, fr.n - 1, 6.0 * 20)
    assert r is None
    assert why[0] == "UNMARKED" and why[1] == 1                       # null + count, never 0


def test_unmarked_shows_up_as_null_plus_count_at_run_level():
    arr = _rth_frame([100, 110, 90, 80, 105, 106])
    full = {"trades": [(0, 4, 5.0, 0, 100.0)], "total_pnl": 5.0, "num_trades": 1}
    money, _ = S.money_ctx(None, "NQ")
    dd, src = S.validate_dd(money, arr, full=full, log=None)
    assert dd["full"] is None
    assert src["reasons"]["full"].startswith("UNMARKED")
    assert src["unmarked"] == {"full": 1}


# ── the cent check, membership, C7 ─────────────────────────────────────────────────────────────────
def test_the_cent_check_refuses_a_one_cent_miss():
    fr = S.Frame(_rth_frame([100, 110, 90, 80, 105, 106]))
    v = S.Valuation(fr, [(0, 4, 5.0, 1, 100.0)], 20.0)
    assert S.reading(v, [True], 0, fr.n - 1, 100.0)[0] is not None
    assert S.reading(v, [True], 0, fr.n - 1, 100.004)[0] is not None   # under half a cent: fine
    r, why = S.reading(v, [True], 0, fr.n - 1, 100.01)
    assert r is None and why[0] == "NET_MISMATCH"


def test_member_count_must_equal_the_blocks_trade_count():
    fr = S.Frame(_rth_frame([100, 110, 90, 80, 105, 106]))
    v = S.Valuation(fr, [(0, 4, 5.0, 1, 100.0)], 20.0)
    r, why = S.reading(v, [True], 0, fr.n - 1, 100.0, expect_n=2)
    assert r is None and why[0] == "MEMBERSHIP"


@pytest.mark.parametrize("t", [(0, 6, 5.0, 1, 100.0), (-1, 2, 5.0, 1, 100.0), (3, 2, 5.0, 1, 100.0)])
def test_out_of_frame_indices_are_refused_never_clamped(t):
    """C7: _mtm_increments would clamp an index past the last bar; the stretch is refused instead."""
    fr = S.Frame(_rth_frame([100, 110, 90, 80, 105, 106]))
    v = S.Valuation(fr, [t], 20.0)
    r, why = S.reading(v, [True], 0, fr.n - 1, 100.0)
    assert r is None and why[0] == "OUT_OF_FRAME"


# ── T6: a one-day stretch ───────────────────────────────────────────────────────────────────────────
def test_one_day_stretch_is_null_not_an_exception():
    fr = S.Frame(_rth_frame([100, 101, 102, 103]))
    v = S.Valuation(fr, [(0, 1, 1.0, 1, 100.0)], 20.0)
    r, why = S.reading(v, [True], 0, 1, 20.0)
    assert r is None and why[0] == "FEW_DAYS"


# ── T8: the per-trade path == the direct whole-array call ──────────────────────────────────────────
def test_vectorized_equals_direct_mtm_increments_to_the_cent():
    rng = np.random.default_rng(3)
    n = 400
    close = 1000 + np.cumsum(rng.normal(0, 2.0, n))
    arr = _rth_frame(close, times=("09:30", "11:00", "13:00", "15:55"))
    fr = S.Frame(arr)
    trades, w = [], []
    for k in range(60):
        e = int(rng.integers(0, n - 30))
        x = e + int(rng.integers(0, 25))
        side = 1 if k % 2 else -1
        trades.append((e, x, side * (close[x] - close[e]) - 0.25, side, float(close[e])))
        w.append(float(np.linspace(0.25, 3.0, 60)[k]))
    v = S.Valuation(fr, trades, 20.0)
    m = np.ones(len(trades), dtype=bool)
    m[::7] = False
    sel = m[v.row_trade]
    mine = np.bincount(v.row_pos[sel], weights=v.row_usd[sel] * np.asarray(w)[v.row_trade[sel]],
                       minlength=len(fr.days))
    direct, mk, um = B._mtm_increments(S.day_stamps(arr["index"], arr["meta"]), close,
                                       [(t, wt) for t, wt, keep in zip(trades, w, m) if keep], 20.0, 1.0)
    assert um == 0 and mk > 0
    dd = np.asarray([d for d, _ in direct], dtype="datetime64[D]")
    ref = np.bincount(np.searchsorted(fr.days, dd), weights=[u for _, u in direct], minlength=len(fr.days))
    assert np.max(np.abs(mine - ref)) < 0.005
    exp = math.fsum(t[2] * wt * 20.0 for t, wt, keep in zip(trades, w, m) if keep)
    r, why = S.reading(v, m, 0, fr.n - 1, exp, weights=w)
    assert why is None
    f = four_numbers(list(ref), dates=[str(d) for d in fr.days])
    assert r["dd_usd"] == f["max_dd"] and r["dd_pct_peak"] == f["dd_pct_peak"]


# ── C3: a size the strategy folded into t[2] ────────────────────────────────────────────────────────
def test_folded_size_scales_the_marks_and_unknown_sizes_refuse():
    fr = S.Frame(_rth_frame([100, 110, 90, 80, 105, 106]))
    v = S.Valuation(fr, [(0, 4, 10.0, 1, 100.0)], 20.0, sizes=[2.0], sized_file=True)
    r, why = S.reading(v, [True], 0, fr.n - 1, 200.0)
    assert why is None and r["dd_usd"] == 1200.0                    # 2 contracts: twice the holder
    v2 = S.Valuation(fr, [(0, 4, 10.0, 1, 100.0)], 20.0, sizes=None, sized_file=True)
    assert S.reading(v2, [True], 0, fr.n - 1, 200.0)[1][0] == "SIZE_UNKNOWN"


# ── T13 / T9: money ─────────────────────────────────────────────────────────────────────────────────
def test_money_ctx_sizes_futures_and_refuses_everything_else():
    assert S.money_ctx(None, "NQ")[0] == {"mult": 20.0, "mult_src": "table", "instrument": "NQ"}
    assert S.money_ctx(2, "NQ")[0]["mult"] == 2.0 and S.money_ctx(2, "NQ")[0]["mult_src"] == "job"
    assert S.money_ctx(None, "MNQ")[0]["mult"] == 2.0
    assert S.money_ctx(None, "ES")[0]["mult"] == 50.0
    for inst, src in (("QQQ", "alpaca_split_rth"), ("QQQ", "yahoo_adj"), ("GLD", None), (None, None)):
        ctx, why = S.money_ctx(20, inst, source=src)          # the runner's default 20 is no evidence
        assert ctx is None and why.startswith("UNSIZED")
    usd = types.SimpleNamespace(run_backtest=lambda *a, **k: None, PNL_UNITS="usd")
    ctx, why = S.money_ctx(None, "NQ", strategy=usd)
    assert ctx is None and "PNL_UNITS" in why


def test_unsized_run_level_is_null_with_the_reason():
    dd, src = S.validate_dd(None, None, unsized="UNSIZED: 'QQQ' is not a futures root", log=None)
    assert dd is None and src["status"] == "UNSIZED" and "QQQ" in src["reason"]


# ── T15 (C1): the ETH day ───────────────────────────────────────────────────────────────────────────
def _eth_index():
    fri = pd.date_range("2024-03-08 15:00", "2024-03-08 16:59", freq="1min")
    sun = pd.date_range("2024-03-10 18:00", "2024-03-10 23:59", freq="1min")    # DST began 02:00 that day
    mon = pd.date_range("2024-03-11 00:00", "2024-03-11 10:00", freq="1min")
    mon_eve = pd.date_range("2024-03-11 18:00", "2024-03-11 18:59", freq="1min")
    tue = pd.date_range("2024-03-12 00:00", "2024-03-12 10:00", freq="1min")
    return pd.DatetimeIndex(fri.append([sun, mon, mon_eve, tue])).tz_localize("US/Eastern")


_ETH_META = {"instrument": "NQ", "session": "eth", "source": "db_noadj_eth", "timeframe": "1m"}


def test_eth_trading_day_rolls_at_1800_and_weekends_collapse():
    idx = _eth_index()
    d = S.day_stamps(idx, _ETH_META)
    assert sorted(set(str(x) for x in d)) == ["2024-03-08", "2024-03-11", "2024-03-12"]   # no Sunday row
    # the book's UTC truncation would have given the DST Sunday evening its own row (design Q3 / C1)
    utc = set(str(x) for x in np.asarray(idx, dtype="datetime64[D]"))
    assert "2024-03-10" in utc
    # RTH / unlabelled masters keep the ET calendar date
    assert S.day_rule({"session": "rth"}) == "et_date" and S.day_rule(None) == "et_date"
    assert S.day_rule({"session": "eth", "source": "alpaca_split_eth"}) == "et_date"


def test_eth_weekend_hold_has_exactly_one_mark_at_the_friday_close():
    idx = _eth_index()
    n = len(idx)
    close = 18000.0 + np.arange(n, dtype=float) * 0.1
    arr = {"index": idx, "close": close, "meta": _ETH_META}
    fr = S.Frame(arr)
    mon10 = int(np.flatnonzero(idx == pd.Timestamp("2024-03-11 10:00", tz="US/Eastern"))[0])
    fri_close = int(np.flatnonzero(idx == pd.Timestamp("2024-03-08 16:59", tz="US/Eastern"))[0])
    pnl = float(close[mon10] - close[0])
    v = S.Valuation(fr, [(0, mon10, pnl, 1, float(close[0]))], 20.0)
    assert v.marked[0] and len(v.row_usd) == 2                     # one mark + the exit remainder
    assert v.row_usd[0] == pytest.approx((close[fri_close] - close[0]) * 20.0)
    assert [str(fr.days[p]) for p in v.row_pos] == ["2024-03-08", "2024-03-11"]
    assert math.fsum(v.row_usd) == pytest.approx(pnl * 20.0, abs=1e-6)
    # an evening entry held to the next morning is ONE trading day: booked whole, no mark
    e = int(np.flatnonzero(idx == pd.Timestamp("2024-03-11 18:30", tz="US/Eastern"))[0])
    x = int(np.flatnonzero(idx == pd.Timestamp("2024-03-12 10:00", tz="US/Eastern"))[0])
    v2 = S.Valuation(fr, [(e, x, 3.0, 1, float(close[e]))], 20.0)
    assert not v2.marked[0] and len(v2.row_usd) == 1 and str(fr.days[v2.row_pos[0]]) == "2024-03-12"


# ── T16 (C2): roll seams ────────────────────────────────────────────────────────────────────────────
def _roll_table(tmp_path, switch_et, offset):
    ts = pd.Timestamp(switch_et, tz="US/Eastern")
    (tmp_path / "rolls_NQ.csv").write_text(
        "root,old,new,switch_sec,switch_et,offset_pts,offset_ci_pts,offset_sec,kind,source,status,note\n"
        "NQ,NQH4,NQM4,%d,%s,%.2f,,,mid_session,databento_raw,exact,\n"
        % (int(ts.tz_convert("UTC").value // 10 ** 9), switch_et, offset), encoding="utf-8")
    return str(tmp_path)


_NOADJ_META = {"instrument": "NQ", "session": "rth", "source": "db_noadj_rth", "timeframe": "5m"}


def test_marks_across_a_contract_switch_carry_no_roll_step(tmp_path):
    """Raw tape: the old contract to day 1, then the new one 200 points higher. The long is entered at
    raw 100 (repriced fill) and its P&L, the adjusted series' 305 - 300, is +5 with the step out."""
    td = _roll_table(tmp_path, "2024-01-02 20:00", 200.0)
    arr = _rth_frame([100, 110, 290, 280, 305, 306], meta=_NOADJ_META)
    fr = S.Frame(arr)
    trade = (0, 4, 5.0, 1, 100.0)
    roll = {"root": "NQ", "kind": S.DIFF_KIND, "table_dir": td}
    v = S.Valuation(fr, [trade], 20.0, roll=roll)
    assert v.roll_corrected == 1
    assert list(v.row_usd) == [200.0, -600.0, 500.0]               # the holder's own path: no +3,400 jump
    r, why = S.reading(v, [True], 0, fr.n - 1, 100.0)
    assert why is None and r["dd_usd"] == 600.0
    # the naive mark on the raw close books the step and passes the cent check - the C2 trap
    naive = S.Valuation(fr, [trade], 20.0)
    assert max(naive.row_usd) > 3000 and math.fsum(naive.row_usd) == pytest.approx(100.0)
    # a ratio plan is refused until its maths is designed; an unknown plan is refused too
    for kind, code in ((S.RATIO_KIND, "RATIO_ROLL"), (None, "ROLL_SEAM"), ("raw (declared)", "ROLL_SEAM")):
        vv = S.Valuation(fr, [trade], 20.0, roll={"root": "NQ", "kind": kind, "table_dir": td})
        assert S.reading(vv, [True], 0, fr.n - 1, 100.0)[1][0] == code
    # a trade that does not span the switch is marked on raw prices as before
    vv = S.Valuation(fr, [(2, 5, 26.0, 1, 280.0)], 20.0, roll={"root": "NQ", "kind": S.RATIO_KIND,
                                                              "table_dir": td})
    assert vv.marked[0] and vv.roll_corrected == 0


def test_roll_info_reads_the_plan_kind_and_skips_adjusted_masters():
    st = {"_meta": {"roll_stamp": {"calendar": S.DIFF_KIND, "signal_method": "difference"}}}
    assert S.roll_info(_NOADJ_META, st)["kind"] == S.DIFF_KIND
    assert S.roll_info({"instrument": "NQ", "source": "db_adj_rth"}, st) is None
    assert S.roll_info({"instrument": "QQQ", "source": "alpaca_split_rth"}, st) is None


# ── T4 / T5 / T12: run-level stretches on one frame ─────────────────────────────────────────────────
def _eth_chain_frame():
    """Two bars per date (10:00 and 19:00); under the 18:00 roll the 19:00 bar is the NEXT trading day."""
    dates = [str(d.date()) for d in pd.date_range("2024-01-01", periods=6)]
    stamps = [f"{d} {t}" for d in dates for t in ("10:00", "19:00")]
    idx = pd.DatetimeIndex(stamps).tz_localize("US/Eastern")
    close = np.array([100, 102, 99, 97, 101, 104, 103, 100, 98, 95, 99, 101], dtype=float)
    return {"index": idx, "close": close, "meta": {"session": "eth", "source": "db_noadj_eth"}}


def _fold(arr, f, a, b, trades):
    idx = arr["index"]
    return {"fold": f, "a": a, "b": b, "a_ts": str(idx[a]), "b_ts": str(idx[b - 1]),
            "oos_pnl": float(sum(t[2] for t in trades)), "oos_trades": len(trades),
            "ei": [t[0] for t in trades], "xi": [t[1] for t in trades], "pnl": [t[2] for t in trades],
            "side": [t[3] for t in trades], "px": [t[4] for t in trades]}


def _chain_run(arr, a_ts_override=None):
    c = arr["close"]
    f1 = [(0, 2, 3.0, 1, float(c[0]) - 1.0)]                 # global 0 -> 2: held over a session close
    f2 = [(3, 3, -2.0, -1, float(c[7]))]                     # global 7 = 01-04 19:00 -> trading day 01-05
    lbt = [(0, 2, 4.0, -1, float(c[8]) + 1.0)]               # global 8 -> 10, opens trading day 01-05
    chain = [_fold(arr, 1, 0, 4, f1), _fold(arr, 2, 4, 8, f2)]
    if a_ts_override:
        chain[1]["a_ts"] = a_ts_override
    lb = {"trades": lbt, "total_pnl": 4.0, "num_trades": 1}
    money, _ = S.money_ctx(None, "NQ")
    dd, src = S.validate_dd(money, arr, chain=chain, lb=lb, lb_from="2024-01-05", log=None)
    glob = [(0, 2) + f1[0][2:], (7, 7) + f2[0][2:], (8, 10) + lbt[0][2:]]
    return dd, src, glob


def test_wf_lb_is_the_chain_then_the_lockbox_as_one_daily_series():
    arr = _eth_chain_frame()
    dd, src, glob = _chain_run(arr)
    assert dd["wf"] is not None and dd["lb"] is not None and dd["wf_lb"] is not None
    assert src["day_rule"] == "cme_1800_roll"
    # hand-built: ONE direct _mtm_increments call over the global trades, summed by day
    days = S.day_stamps(arr["index"], arr["meta"])
    inc, mk, um = B._mtm_increments(days, arr["close"], [(t, 1.0) for t in glob], 20.0, 1.0)
    grid = np.unique(days)
    ser = np.zeros(len(grid))
    for d, u in inc:
        ser[np.searchsorted(grid, d)] += u
    assert math.fsum(ser) == pytest.approx((3.0 - 2.0 + 4.0) * 20.0, abs=1e-9)
    f = four_numbers(list(ser), dates=[str(d) for d in grid])
    assert dd["wf_lb"] == {"dd_pct_peak": f["dd_pct_peak"], "dd_usd": f["max_dd"], "marked": 2}
    # the shared boundary day (trading day 01-05) carries fold 2's close AND the lockbox's first mark
    k = int(np.searchsorted(grid, np.datetime64("2024-01-05")))
    lb_mark = -1 * (arr["close"][8] - (arr["close"][8] + 1.0)) * 20.0
    assert ser[k] == pytest.approx(-2.0 * 20.0 + lb_mark)


def test_a_moved_fold_bound_drops_wf_and_wf_lb_only():
    """T12: the tape moved under fold 2's bar index (a fill) - the chain cannot be placed."""
    arr = _eth_chain_frame()
    dd, src, _ = _chain_run(arr, a_ts_override="2024-01-03 10:05:00-05:00")
    assert dd["wf"] is None and dd["wf_lb"] is None and dd["lb"] is not None
    assert src["reasons"]["wf"].startswith("FOLD_TS")
    assert src["reasons"]["wf_lb"].startswith("NEEDS_WF_AND_LB")


def test_is_wf_boundary_trade_stays_in_is_and_both_reconcile():
    """T4: a trade entering before the WF split and exiting after it is IS's; the IS series runs to
    its exit; IS and FULL each sum to their stored block net."""
    arr = _rth_frame([100, 101, 103, 99, 98, 104, 105, 107, 106, 108])
    idx = arr["index"]
    trades = [(0, 1, 1.0, 1, 100.0),          # IS, intraday
              (1, 6, 4.0, 1, 101.0),          # IS by entry, exits 3 days into WF
              (6, 7, 2.0, 1, 105.0),          # WF
              (8, 9, 2.0, 1, 106.0)]          # WF
    full = {"trades": trades, "total_pnl": 9.0, "num_trades": 4}
    gate = {"ungated_is": {"total_pnl": 5.0, "num_trades": 2},
            "ungated_full": {"total_pnl": 9.0, "num_trades": 4}}
    money, _ = S.money_ctx(None, "NQ")
    dd, src = S.validate_dd(money, arr, full=full, gate=gate, wf_split=idx[4], log=None)
    assert dd["is"] is not None and dd["full"] is not None
    assert dd["is"]["marked"] == 1
    assert src["net_ref"] == {"full": "gate_validate.ungated_full", "is": "gate_validate.ungated_is"}
    # the stored IS net is what the series must reach: a wrong one refuses
    gate_bad = dict(gate, ungated_is={"total_pnl": 5.1, "num_trades": 2})
    dd2, src2 = S.validate_dd(money, arr, full=full, gate=gate_bad, wf_split=idx[4], log=None)
    assert dd2["is"] is None and src2["reasons"]["is"].startswith("NET_MISMATCH")
    assert dd2["full"] == dd["full"]


# ── T7: gate_validate, legacy vs mtm ────────────────────────────────────────────────────────────────
def golden_diff(old, new, allowed, path=()):
    """Every path where `new` differs from `old`. A key new adds is allowed only when allowed(path)."""
    bad = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in old:
            if k not in new:
                bad.append((path + (k,), "MISSING IN NEW"))
            else:
                bad += golden_diff(old[k], new[k], allowed, path + (k,))
        for k in new:
            if k not in old and not allowed(path + (k,)):
                bad.append((path + (k,), "ADDED"))
        if [k for k in new if k in old] != list(old):
            bad.append((path, "KEY ORDER"))
        return bad
    if isinstance(old, (list, tuple)) and isinstance(new, (list, tuple)):
        if len(old) != len(new):
            return [(path, "LENGTH %d != %d" % (len(old), len(new)))]
        for i, (a, b) in enumerate(zip(old, new)):
            bad += golden_diff(a, b, allowed, path + (i,))
        return bad
    if isinstance(old, np.ndarray) or isinstance(new, np.ndarray):
        same = (np.shape(old) == np.shape(new)
                and np.array_equal(np.asarray(old), np.asarray(new), equal_nan=True))
        return [] if same else [(path, "ARRAY")]
    if isinstance(old, float) and isinstance(new, float) and math.isnan(old) and math.isnan(new):
        return []
    if type(old) is not type(new) and not (isinstance(old, (int, float)) and isinstance(new, (int, float))):
        return [(path, "TYPE %s -> %s" % (type(old).__name__, type(new).__name__))]
    return [] if old == new else [(path, "VALUE %r -> %r" % (old, new))]


def _gate_fixture():
    rng = np.random.default_rng(11)
    idx = pd.date_range(pd.Timestamp("2020-01-01", tz="US/Eastern"),
                        pd.Timestamp("2020-02-20", tz="US/Eastern"), freq="30min", tz="US/Eastern")
    n = len(idx)
    close = 9000.0 + np.cumsum(rng.normal(0, 3.0, n))
    day_id = pd.factorize(pd.Series(idx).dt.date)[0].astype("int64")
    arrays = {"open": close.copy(), "high": close + 2.0, "low": close - 2.0, "close": close.copy(),
              "volume": np.full(n, 1000.0), "day_id": day_id, "index": idx,
              "meta": {"instrument": "NQ", "session": "rth", "source": "db_adj_rth", "timeframe": "30m"}}
    trades = []
    for k, e in enumerate(range(20, n - 80, 9)):
        hold = int(rng.integers(1, 70))                      # many held over one or more nights
        x = e + hold
        side = 1 if k % 3 else -1
        trades.append((e, x, float(side * (close[x] - close[e]) - 0.3), side, float(close[e])))
    return arrays, trades


_GKW = dict(gates=("logistic", "tree"), thresholds=(0.5, 0.55), min_kept=1, min_keep_frac=0.0,
            lb_from="2020-02-05", wf_from="2020-01-15", wf_to="2020-02-05", keel=False)


@pytest.fixture(scope="module")
def gate_pair():
    from augur_engine.ml_gate import gate_validate
    arrays, trades = _gate_fixture()
    old = gate_validate(arrays, trades, **_GKW)
    money, _ = S.money_ctx(None, "NQ")
    ctx = S.gate_ctx(money)
    new = gate_validate(arrays, trades, mtm=ctx, **_GKW)
    return arrays, trades, old, new, ctx


def test_gate_old_keys_identical_only_dd_keys_added(gate_pair):
    arrays, trades, old, new, ctx = gate_pair
    assert old is not None and new is not None
    bad = golden_diff(old, new, lambda p: p[-1] in S.DD_KEYS)
    assert bad == [], bad[:10]
    assert json.dumps(S.strip_keys(new), sort_keys=True, default=str) == \
        json.dumps(old, sort_keys=True, default=str)
    rep = ctx["report"]
    assert rep and rep.get("blocks", 0) >= 20 and "error" not in rep, rep


def test_gate_blocks_carry_the_keys_and_match_an_independent_reading(gate_pair):
    arrays, trades, old, new, ctx = gate_pair
    for k in ("ungated_pre", "ungated_lockbox", "ungated_full", "ungated_is", "ungated_wf", "ungated_wf_lb"):
        assert set(S.DD_KEYS) <= set(new[k]), k
    assert any(set(S.DD_KEYS) <= set(c.get("full") or {}) for c in new["candidates"])
    assert all(set(S.DD_KEYS) <= set(t["full"]) for t in new["tilts"])
    # ungated_full by hand: one direct _mtm_increments call over every trade, the whole window's days
    days = S.day_stamps(arrays["index"], arrays["meta"])
    inc, mk, um = B._mtm_increments(days, arrays["close"], [(t, 1.0) for t in trades], 20.0, 1.0)
    grid = np.unique(days)
    ser = np.zeros(len(grid))
    for d, u in inc:
        ser[np.searchsorted(grid, d)] += u
    f = four_numbers(list(ser), dates=[str(d) for d in grid])
    assert new["ungated_full"]["dd_usd"] == f["max_dd"]
    assert new["ungated_full"]["dd_pct_peak"] == f["dd_pct_peak"]
    assert new["ungated_full"]["dd_marked"] == mk > 0
    # a tilt row by hand: the same call with the row's weights as sizes (T8 on real gate output)
    t0 = new["tilts"][0]
    assert t0["full"]["dd_usd"] >= 0


def test_gate_without_mtm_registers_nothing(gate_pair):
    arrays, trades, old, new, ctx = gate_pair
    blob = json.dumps(old, default=str)
    assert not any(k in blob for k in S.DD_KEYS)


# ── T11: the cache key is untouched ─────────────────────────────────────────────────────────────────
def test_trial_cache_key_and_epoch_pinned():
    import augur_engine
    from augur_engine import trial_cache as TC
    assert augur_engine.ENGINE_CACHE_EPOCH == 1
    ctx = {"strategy_file_sha": "f" * 64, "engine_epoch": 1, "master_id": "NQ|5m|db_noadj_rth",
           "data_fingerprint": "abc", "date_from": "2020-01-01", "date_to": "2024-12-31",
           "cost_pts": 0.283, "session": "rth"}
    assert TC.make_key(ctx, {"a": 1, "b": 2.5}, 10, 500) == "da6d8523a0f8ec56caa8763f1d3b35be5d120ab4"
    assert TC.make_key(ctx, {"a": 1, "b": 2.5}, 10, 500, tag="warm:v1|300") == \
        "a26e2122a4e20c06664a3faa9c0bc32a94a2ffc1"


# ── a synthetic run_validate: old keys byte-identical, new keys only where the decisions put them ──
_LO = pd.Timestamp("2020-01-01", tz="US/Eastern")
_HI = pd.Timestamp("2020-02-15", tz="US/Eastern")
_IDX = pd.date_range(_LO, _HI, freq="5min", tz="US/Eastern")
_CLOSE = 1000.0 + np.cumsum(np.random.default_rng(5).normal(0, 0.8, len(_IDX)))
_MASTER = {"filename": "SYN_STRETCHDD.csv", "instrument": "SYN_DD", "timeframe": "5m",
           "date_from": _LO.date().isoformat(), "date_to": _HI.date().isoformat(), "name": "SYN_DD"}


def _fake_find_master(instrument, timeframe, session=None, source=None):
    return dict(_MASTER)


def _fake_load_master_arrays(master, date_from=None, date_to=None):
    mask = np.ones(len(_IDX), dtype=bool)
    if date_from:
        mask &= (_IDX >= pd.Timestamp(date_from, tz="US/Eastern"))
    if date_to:
        mask &= (_IDX < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
    si, sc = _IDX[mask], _CLOSE[mask]
    n = len(sc)
    day_id = (pd.factorize(pd.Series(si).dt.date)[0].astype("int64") if n else np.array([], dtype="int64"))
    return {"open": sc.copy(), "high": sc + 1.0, "low": sc - 1.0, "close": sc.copy(),
            "volume": np.full(n, 1000.0), "day_id": day_id, "index": si, "meta": master}


def _holder_strategy():
    """Overlapping longs and shorts held ~25 hours (300 five-minute bars): every one is marked."""
    mod = types.ModuleType("fake_stretch_dd_strategy")
    mod.STRATEGY_NAME = "SYN STRETCH DD TEST"
    mod.DEFAULT_PARAMS = {"knob": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0}}

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        c = np.asarray(c, dtype=float)
        n = len(c)
        edge = 0.2 * (5.0 - abs(float(knob or 0.0) - 3.0))
        trades = []
        for k, e in enumerate(range(5, n - 301, 150)):
            x = e + 300
            side = 1 if k % 2 == 0 else -1
            trades.append((e, x, float(side * (c[x] - c[e]) + edge), side, float(c[e])))
        pnls = [t[2] for t in trades]
        tot = float(sum(pnls))
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        cum = np.cumsum(pnls) if pnls else np.zeros(1)
        peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
        out = {"total_pnl": tot, "num_trades": len(trades),
               "win_rate": 100.0 * len(wins) / len(trades) if trades else 0.0,
               "profit_factor": (sum(wins) / -sum(losses)) if losses else 9.0,
               "max_drawdown": float((cum - peak).min()) if pnls else 0.0,
               "avg_pnl": tot / len(trades) if trades else 0.0,
               "wins": len(wins), "losses": len(losses)}
        if return_trades:
            out["trades"] = trades
        return out

    mod.run_backtest = run_backtest
    return mod


_VKW = dict(instrument="SYN_DD", timeframe="5m", session="rth", source=None, cost_pts=0.0,
            min_trades=1, n_trials=4, wf_folds=3, seed=42, lockbox_months=0.33, equity_points=200,
            discover="auto", warm_days=0, compute_pills=False)
_NONDETERMINISTIC = ("timings", "code_stamps")


@pytest.fixture(scope="module")
def validate_pair():
    import augur_engine.auto as auto_mod
    import augur_engine.engine as engine_mod
    import augur_engine.optimize as optimize_mod
    import augur_engine.validate as validate_mod
    from augur_engine.validate import run_validate
    mp = pytest.MonkeyPatch()
    for m in (validate_mod, auto_mod, engine_mod, optimize_mod):
        mp.setattr(m, "find_master", _fake_find_master)
        mp.setattr(m, "load_master_arrays", _fake_load_master_arrays)
    mp.setitem(B._MULT, "SYN_DD", 20)
    try:
        mp.setenv("AUGUR_STRETCH_DD", "0")
        off = run_validate(_holder_strategy(), **_VKW)
        mp.setenv("AUGUR_STRETCH_DD", "1")
        on = run_validate(_holder_strategy(), **_VKW)
    finally:
        mp.undo()
    for r in (off, on):
        for k in _NONDETERMINISTIC:
            r.pop(k, None)
    return off, on


def _allowed_validate_path(p):
    if p in (("validate", "dd_pct"), ("validate", "dd_pct_src")):
        return True
    return p[0] == "gate_validate" and p[-1] in S.DD_KEYS


def test_validate_old_keys_byte_identical_new_keys_only_where_decided(validate_pair):
    off, on = validate_pair
    bad = golden_diff(off, on, _allowed_validate_path)
    assert bad == [], bad[:10]
    assert "dd_pct" not in off["validate"] and "dd_pct_src" not in off["validate"]
    assert "dd_pct" not in on and "dd_pct_src" not in on                      # validate.* only (decision 2)


def test_validate_dd_pct_has_all_five_stretches_valued(validate_pair):
    off, on = validate_pair
    dd, src = on["validate"]["dd_pct"], on["validate"]["dd_pct_src"]
    assert set(dd) == set(S.STRETCHES)
    assert src["status"] == "OK", src
    for k in S.STRETCHES:
        assert set(dd[k]) == {"dd_pct_peak", "dd_usd", "marked"}, k
        assert dd[k]["marked"] > 0, k                       # every trade here is held overnight
        assert dd[k]["dd_usd"] >= 0 and dd[k]["dd_pct_peak"] >= 0
    assert src["day_rule"] == "et_date" and src["mult"] == 20.0 and src["mult_src"] == "table"
    assert src["start"] == 100000.0 and src["v"] == S.VERSION and src["src"] == "validate"
    assert src["net_ref"]["lb"] == "validate.lockbox.pnl"
    assert (src.get("gate") or {}).get("blocks", 0) > 0, src.get("gate")


def test_gate_keys_on_top_level_copy_only_not_on_the_mirror(validate_pair):
    off, on = validate_pair
    top = json.dumps(on["gate_validate"], default=str)
    mirror = json.dumps(on["validate"]["gate_bakeoff"], default=str)
    assert "dd_usd" in top
    assert not any(k in mirror for k in S.DD_KEYS)
    assert mirror == json.dumps(off["validate"]["gate_bakeoff"], default=str)


def test_no_transient_trade_arrays_reach_the_saved_result(validate_pair):
    """T10: _oos_side / _oos_px / _oos_pnlf are popped like every other _oos_* array."""
    off, on = validate_pair
    blob = json.dumps(on, default=str)
    for k in ("_oos_side", "_oos_px", "_oos_pnlf", "_oos_pnls", "_oos_ei", "_oos_xi"):
        assert k not in blob, k


def test_unsized_validate_writes_the_reason_and_no_gate_keys(monkeypatch):
    """T13 end to end: an instrument with no point value - dd_pct null, UNSIZED, no per-block key."""
    import augur_engine.auto as auto_mod
    import augur_engine.engine as engine_mod
    import augur_engine.optimize as optimize_mod
    import augur_engine.validate as validate_mod
    from augur_engine.validate import run_validate
    for m in (validate_mod, auto_mod, engine_mod, optimize_mod):
        monkeypatch.setattr(m, "find_master", _fake_find_master)
        monkeypatch.setattr(m, "load_master_arrays", _fake_load_master_arrays)
    monkeypatch.setenv("AUGUR_STRETCH_DD", "1")
    kw = dict(_VKW, n_trials=2, wf_folds=2)
    r = run_validate(_holder_strategy(), **kw)
    v = r["validate"]
    assert v["dd_pct"] is None and v["dd_pct_src"]["status"] == "UNSIZED"
    assert not any(k in json.dumps(r.get("gate_validate"), default=str) for k in S.DD_KEYS)


def test_gate_validate_job_gets_block_keys_and_nothing_else(monkeypatch):
    """Decision 9: Gate-Validate jobs (engine.run_gate_validate) are in scope - block keys only."""
    from augur_engine.engine import run_gate_validate
    arrays = _fake_load_master_arrays(_MASTER, None, None)
    kw = dict(arrays=arrays, gates=("logistic",), thresholds=(0.5,), lockbox_months=0.33)
    monkeypatch.setitem(B._MULT, "SYN_DD", 20)
    monkeypatch.setenv("AUGUR_STRETCH_DD", "0")
    off = run_gate_validate(_holder_strategy(), **kw)
    monkeypatch.setenv("AUGUR_STRETCH_DD", "1")
    on = run_gate_validate(_holder_strategy(), **kw)
    bad = golden_diff(off, on, lambda p: p[0] == "gate_validate" and p[-1] in S.DD_KEYS)
    assert bad == [], bad[:10]
    assert set(S.DD_KEYS) <= set(on["gate_validate"]["ungated_full"])
    monkeypatch.delitem(B._MULT, "SYN_DD")
    unsized = run_gate_validate(_holder_strategy(), **kw)
    assert golden_diff(off, unsized, lambda p: False) == []


def test_run_auto_default_leaves_walk_forward_rows_unchanged():
    """keep_oos_detail defaults False: an Auto-Optimize walk-forward result gains no key."""
    from augur_engine.auto import run_auto
    arrays = _fake_load_master_arrays(_MASTER, None, None)
    kw = dict(arrays=arrays, method="walkforward", oos=True, wf_folds=2, n_trials=2, min_trades=1,
              top_n=5, seed=1)
    plain = run_auto(_holder_strategy(), **kw)
    asked = run_auto(_holder_strategy(), keep_oos_detail=True, **kw)
    assert plain.get("wf") and plain.get("top")
    assert not any(k in r for r in plain["top"] for k in ("_oos_side", "_oos_px", "_oos_pnlf"))
    assert all("_oos_side" in r and "_oos_pnlf" in r for r in asked["top"])
    strip = [{k: v for k, v in r.items() if k not in ("_oos_side", "_oos_px", "_oos_pnlf")}
             for r in asked["top"]]
    assert golden_diff(plain["top"], strip, lambda p: False) == []
