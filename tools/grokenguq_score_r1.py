"""GROK-ENGUQ SCORE FILTER r1 - the frozen harness for docs/PREREG_grokenguq_score_r1_2026-10-28.md.

MANAGER #123, owner GO 10-28. Job 1 of two: tag every ENGU-Q #335 trade with the GROK quality score at
its ENTRY SIGNAL BAR and ask whether a score floor lifts the four numbers. Nothing is optimised and no
new strategy is run - this is a filter applied after the fact to one fixed, existing trade list.

THE SCORE, ported from the owner's Pine at its own defaults (maxScore 15):
  +1 opposite-momentum pass, +1 ATR expansion, +1 volume, +1 trend side
  +1 each: body is the session's largest / the largest since the day's low / the largest of 20 bars
  +1 each: the same three for volume
  + min(S/D supply levels broken, 5)

TWO QUIRKS OF THE PINE THAT ARE REPRODUCED DELIBERATELY, not cleaned up:
  1. The opposite-momentum loop runs only `if useOppFilter and breakoutBodyValid`. On a bar whose body
     is NOT bigger than 0.7x the prior 20-bar range the loop never runs, so oppFilterPass stays TRUE
     and the bar is GIVEN that point. A port that "fixed" this would not be the owner's indicator.
  2. The score is direction-gated on `isBull` / `isBear`, which are only true where GROK's own breakout
     fires. ENGU-Q is long only, so every signal bar is scored on the BULL side (isBull forced true)
     and the GROK-breakout coincidence is a separate arm. The prereg says why.

LOOK-AHEAD. S/D levels come from `ta.pivothigh(high, 20, 20)`, confirmed 20 bars late: a pivot at bar p
only enters the array at bar p+20, and the harness asserts that lag. Every other reading uses closed
bars up to and including the signal bar and nothing after it.

    python tools/grokenguq_score_r1.py selftest   the score on hand-made bars, no data
    python tools/grokenguq_score_r1.py run        the report
"""
import hashlib
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
OUT = r"C:\EdgeLog\_anatomy_cache\grokenguq_score_r1"
PINE = r"C:\EdgeLog\_research_cache\tv_scalp\grok_engu\grok_engu_ii.pine.txt"
PREREG = "docs/PREREG_grokenguq_score_r1_2026-10-28.md"
PREREG_SHA = "b7b0ccfbf1f38e75bf9d688bd2b8baec2874984d3cb5c57400f6e659982e828a"

D0, D1 = "2010-06-07", "2026-06-30"
FOLDS = [(1, "2016-10-12", "2017-11-23"), (2, "2017-11-23", "2018-12-30"), (3, "2018-12-30", "2020-02-03"),
         (4, "2020-02-03", "2021-03-08"), (5, "2021-03-08", "2022-04-04"), (6, "2022-04-04", "2023-05-02"),
         (7, "2023-05-02", "2024-05-29"), (8, "2024-05-29", "2025-06-27")]
WF0, WF1 = FOLDS[0][1], FOLDS[-1][2]

# the indicator's own defaults
LOOKBACK, BODY_MULT = 20, 0.7
ATR_LEN, ATR_MULT = 20, 1.7
VOL_LEN, VOL_MULT = 20, 1.3
EMA_LEN = 20
OPP_LOOK, OPP_TH = 20, 0.6
PIVOT_LEN, SD_KEEP, SD_CAP = 20, 30, 5
MAX_SCORE = 15

import numpy as np   # noqa: E402

lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


# ---------------------------------------------------------------- pure pieces (selftested)
def rma(x, n):
    """Wilder's moving average, which is what Pine's ta.atr smooths with."""
    out = np.empty(len(x))
    out[:] = np.nan
    if len(x) < n:
        return out
    a = 1.0 / n
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def ema(x, n):
    out = np.empty(len(x))
    out[:] = np.nan
    if len(x) < n:
        return out
    a = 2.0 / (n + 1.0)
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def true_range(h, l, c):
    tr = np.empty(len(c))
    tr[0] = h[0] - l[0]
    pc = c[:-1]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    return tr


def roll_max(x, n):
    """max of the last n values INCLUDING the current one (Pine's ta.highest)."""
    out = np.empty(len(x))
    out[:] = np.nan
    if len(x) < n:
        return out
    from numpy.lib.stride_tricks import sliding_window_view
    out[n - 1:] = sliding_window_view(x, n).max(axis=1)
    return out


def roll_min(x, n):
    out = np.empty(len(x))
    out[:] = np.nan
    if len(x) < n:
        return out
    from numpy.lib.stride_tricks import sliding_window_view
    out[n - 1:] = sliding_window_view(x, n).min(axis=1)
    return out


def pivot_highs(high, n):
    """Pine's ta.pivothigh(high, n, n): bar p is a pivot high when its high is >= the n bars either
    side, and it is CONFIRMED at bar p + n. Returns (pivot_index, confirm_index, level)."""
    m = len(high)
    if m < 2 * n + 1:
        return []
    rm = roll_max(high, n)                 # rm[i] = max(high[i-n+1 .. i])
    prev_max = np.full(m, -np.inf)
    prev_max[1:] = rm[:-1]                 # max of the n bars BEFORE p
    next_max = np.full(m, -np.inf)
    next_max[:m - n] = rm[n:]              # max of the n bars AFTER p
    idx = np.flatnonzero((np.arange(m) >= n) & (np.arange(m) < m - n)
                         & (high >= prev_max) & (high >= next_max))
    return [(int(p), int(p) + n, float(high[p])) for p in idx]


def opp_pass_bull(open_, close, body, lookback, th, body_valid):
    """The Pine's opposite-momentum filter, INCLUDING its quirk: the scan runs only when the body is
    already big enough to be a breakout body, so a small-body bar passes by default."""
    bad = np.zeros(len(body), bool)
    for k in range(1, lookback + 1):
        pb = np.full(len(body), np.nan)
        pb[k:] = np.abs(close[:-k] - open_[:-k])
        bear = np.zeros(len(body), bool)
        bear[k:] = close[:-k] < open_[:-k]
        bad |= bear & (pb > body * th)
    return ~(body_valid & bad)


def day_running(body, volume, low, high, day_id):
    """The session-quality state the Pine keeps: the day's largest body and volume so far, and the
    largest since the day's running LOW (the bull-side reading). Resets on each new session."""
    n = len(body)
    max_body_day = np.empty(n)
    max_vol_day = np.empty(n)
    max_body_since_low = np.empty(n)
    max_vol_since_low = np.empty(n)
    cur_low = np.inf
    mbd = mvd = mbl = mvl = 0.0
    prev = None
    for i in range(n):
        d = day_id[i]
        if d != prev:
            mbd = mvd = mbl = mvl = 0.0
            cur_low = low[i]
            prev = d
        mbd = max(mbd, body[i])
        mvd = max(mvd, volume[i])
        if low[i] <= cur_low:
            cur_low = low[i]
            mbl = body[i]
            mvl = volume[i]
        else:
            mbl = max(mbl, body[i])
            mvl = max(mvl, volume[i])
        max_body_day[i] = mbd
        max_vol_day[i] = mvd
        max_body_since_low[i] = mbl
        max_vol_since_low[i] = mvl
    return max_body_day, max_vol_day, max_body_since_low, max_vol_since_low


def sd_points_bull(piv, upto_bar, highest_high, close_px, keep=SD_KEEP, cap=SD_CAP):
    """Supply levels the breakout cleared: a confirmed pivot high at or above the prior 20-bar high and
    at or below this bar's close. Only pivots CONFIRMED on or before this bar are in the array, and the
    array holds the most recent `keep`."""
    levels = [lvl for (_p, c, lvl) in piv if c <= upto_bar][-keep:]
    return min(sum(1 for lvl in levels if highest_high <= lvl <= close_px), cap)


def selftest():
    x = np.array([1.0, 2, 3, 4, 5, 6])
    assert np.allclose(roll_max(x, 3)[2:], [3, 4, 5, 6]) and np.isnan(roll_max(x, 3)[1])
    assert np.allclose(roll_min(x, 3)[2:], [1, 2, 3, 4])
    r = rma(np.ones(10), 3)
    assert abs(r[-1] - 1.0) < 1e-12, "a constant series smooths to itself"
    e = ema(np.ones(10), 3)
    assert abs(e[-1] - 1.0) < 1e-12

    # the pivot lag: a pivot at bar p is only visible from bar p + n
    h = np.array([1.0, 1, 1, 5, 1, 1, 1])
    piv = pivot_highs(h, 2)
    assert piv == [(3, 5, 5.0)], piv
    assert sd_points_bull(piv, 4, 0.0, 10.0) == 0, "a pivot is invisible before it is confirmed"
    assert sd_points_bull(piv, 5, 0.0, 10.0) == 1, "and visible from its confirmation bar"
    assert sd_points_bull(piv, 9, 6.0, 10.0) == 0, "a level below the prior high is not cleared"
    assert sd_points_bull(piv, 9, 0.0, 4.0) == 0, "a level above the close is not cleared"

    # the opposite-momentum quirk: a small body passes because the scan never runs
    o = np.array([10.0, 10, 10]); c = np.array([5.0, 10, 10.2]); b = np.abs(c - o)
    valid = np.array([False, False, False])
    assert opp_pass_bull(o, c, b, 2, 0.6, valid).all(), "the scan must not run when the body is small"
    valid = np.array([False, False, True])
    got = opp_pass_bull(o, c, b, 2, 0.6, valid)
    assert not got[2], "a big opposite body two bars back must veto a valid breakout body"

    # the session state resets and tracks from the day's running low
    body = np.array([1.0, 3, 2, 5])
    vol = np.array([10.0, 30, 20, 50])
    low = np.array([5.0, 6, 4, 7])
    high = np.array([6.0, 7, 5, 8])
    day = np.array([0, 0, 0, 1])
    mbd, mvd, mbl, mvl = day_running(body, vol, low, high, day)
    assert list(mbd) == [1, 3, 3, 5] and list(mvd) == [10, 30, 30, 50]
    assert list(mbl) == [1, 3, 2, 5], "a new day low restarts the since-low body max"
    assert list(mvl) == [10, 30, 20, 50]
    print("selftest PASS (rolling max/min, RMA, EMA, pivot confirmation lag, S/D window, "
          "the opposite-momentum quirk, the session reset)")


# ---------------------------------------------------------------- the report
def run():
    sys.path.insert(0, REPO)
    os.chdir(REPO)
    import pandas as pd
    from api.book_shadow import BOOK463_LEGS
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.drawdowns import four_numbers
    from augur_engine.engine import run_backtest

    pre = os.path.join(REPO, PREREG)
    if not os.path.exists(pre):
        pre = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), PREREG)
    pins = {"prereg_lf": lf(pre), "harness_lf": lf(os.path.abspath(__file__)), "pine_lf": lf(PINE)}
    print("PINS: prereg LF %s" % pins["prereg_lf"])
    print("PINS: harness LF %s" % pins["harness_lf"])
    print("PINS: pine LF %s" % pins["pine_lf"])
    if pins["prereg_lf"] != PREREG_SHA:
        raise SystemExit("refused: the prereg is not the frozen one (nothing computed)")
    os.makedirs(OUT, exist_ok=True)

    leg = [l for l in BOOK463_LEGS if l["strategy"].startswith("ENGUQ")][0]
    m = find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"])
    arr = load_master_arrays(m, date_from=D0, date_to=D1)
    n = len(arr["close"])
    print("MASTER PINNED: %s | registry rows %s | bars loaded %d" % (m["filename"], m.get("rows"), n))
    pins["master"] = {"filename": m["filename"], "registry_rows": m.get("rows"), "bars_loaded": n}

    res = run_backtest(leg["strategy"], arrays=arr, params=leg["params"],
                       cost_pts=float(leg["cost_pts"]), return_trades=True)
    trades = sorted((int(t[0]), int(t[1]), float(t[2])) for t in res["trades"])
    assert all(int(t[3]) == 1 for t in res["trades"]), "ENGU-Q is long only - the bull-side score applies"
    print("leg trades: %d" % len(trades))

    o = np.asarray(arr["open"], float)
    h = np.asarray(arr["high"], float)
    lo = np.asarray(arr["low"], float)
    c = np.asarray(arr["close"], float)
    v = np.asarray(arr["volume"], float)
    day_id = np.asarray(arr["day_id"])
    body = np.abs(c - o)

    prev_hh = np.full(n, np.nan); prev_hh[1:] = roll_max(h, LOOKBACK)[:-1]
    prev_ll = np.full(n, np.nan); prev_ll[1:] = roll_min(lo, LOOKBACK)[:-1]
    range_prev = prev_hh - prev_ll
    body_valid = body > range_prev * BODY_MULT
    atr = rma(true_range(h, lo, c), ATR_LEN)
    avg_vol = np.full(n, np.nan)
    avg_vol[VOL_LEN - 1:] = np.convolve(v, np.ones(VOL_LEN) / VOL_LEN, "valid")
    em = ema(c, EMA_LEN)
    opp_ok = opp_pass_bull(o, c, body, OPP_LOOK, OPP_TH, body_valid)
    atr_ok = body > atr * ATR_MULT
    vol_ok = v > avg_vol * VOL_MULT
    trend_bull = c > em
    body_sw = body >= roll_max(body, LOOKBACK)
    vol_sw = v >= roll_max(v, LOOKBACK)
    mbd, mvd, mbl, mvl = day_running(body, v, lo, h, day_id)
    piv = pivot_highs(h, PIVOT_LEN)
    print("pivot highs found: %d (each visible only from %d bars after it)" % (len(piv), PIVOT_LEN))

    grok_bull = (c > o) & (c > prev_hh) & body_valid & opp_ok & atr_ok & vol_ok & trend_bull

    rows = []
    for ei, xi, pts in trades:
        s = (int(bool(opp_ok[ei])) + int(bool(atr_ok[ei])) + int(bool(vol_ok[ei])) + int(bool(trend_bull[ei]))
             + int(body[ei] >= mbd[ei]) + int(body[ei] >= mbl[ei]) + int(bool(body_sw[ei]))
             + int(v[ei] >= mvd[ei]) + int(v[ei] >= mvl[ei]) + int(bool(vol_sw[ei]))
             + sd_points_bull(piv, ei, prev_hh[ei], c[ei]))
        rows.append({"ei": ei, "xi": xi, "pts": pts, "score": int(s), "grok": bool(grok_bull[ei])})
    sc = np.array([r["score"] for r in rows])
    print("score over all %d trades: min %d max %d mean %.2f | GROK bull breakout also fired on %d (%.1f%%)"
          % (len(rows), sc.min(), sc.max(), sc.mean(), sum(r["grok"] for r in rows),
             100.0 * sum(r["grok"] for r in rows) / len(rows)))
    print("score histogram:", {int(k): int((sc == k).sum()) for k in range(0, MAX_SCORE + 1) if (sc == k).sum()})

    # ---- daily mark-to-market, per arm --------------------------------------------------------
    sess = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(np.asarray(arr["index"], dtype="datetime64[D]")))))
    bd = pd.DatetimeIndex(np.asarray(arr["index"], dtype="datetime64[D]"))
    last_bar = pd.Series(np.arange(n), index=bd).groupby(level=0).max()
    marks = last_bar.to_numpy()
    md = pd.DatetimeIndex(last_bar.index)

    def daily_of(sel):
        eq = np.zeros(len(marks))
        for r in sel:
            i0, i1, pnl = r["ei"], r["xi"], r["pts"] * 20.0
            x0 = float(c[min(i0, n - 1)])
            om = (marks > i0) & (marks < i1)
            eq[om] += (c[marks[om]] - x0) * 20.0            # long only
            eq[marks >= i1] += pnl
        s = pd.Series(eq, index=md).diff()
        s.iloc[0] = eq[0]
        return s

    ARMS = [("LEG", lambda r: True), ("S4", lambda r: r["score"] >= 4), ("S6", lambda r: r["score"] >= 6),
            ("S8", lambda r: r["score"] >= 8), ("S10", lambda r: r["score"] >= 10),
            ("GB", lambda r: r["grok"]), ("GB+S", lambda r: r["grok"] and r["score"] >= 8)]
    wf_mask = (md >= pd.Timestamp(WF0)) & (md <= pd.Timestamp(WF1))
    yrs = (pd.Timestamp(WF1) - pd.Timestamp(WF0)).days / 365.25
    out = {"pins": pins, "arms": {}, "folds": {}}
    base = None
    print("\n%-6s %7s %7s | %s" % ("arm", "trades", "tr/yr", "the four numbers, WF 2016-10-12..2025-06-27"))
    series = {}
    for name, f in ARMS:
        sel = [r for r in rows if f(r)]
        d = daily_of(sel)[wf_mask]
        series[name] = d
        kept = sum(1 for r in sel if pd.Timestamp(WF0) <= bd[r["ei"]] <= pd.Timestamp(WF1))
        fn = four_numbers(list(d), years=yrs)
        out["arms"][name] = dict(fn, trades=kept, trades_per_year=kept / yrs,
                                 dropped_net=float(sum(r["pts"] for r in rows if not f(r)) * 20.0))
        if name == "LEG":
            base = fn
        print("%-6s %7d %7.0f | ROC@30k %7.2f | DD5 %10s | DD%% %6.2f | Sortino %6.3f | one_ep %-5s | %+.2f"
              % (name, kept, kept / yrs, fn["roc30"] or 0.0, format(fn["dd5_usd"], ",.0f"),
                 fn["dd_pct_peak"], fn["sortino"] or 0.0, fn["one_episode"],
                 (fn["roc30"] or 0.0) - (base["roc30"] or 0.0)))

    print("\nFOLD BY FOLD - wins against the bare leg (bar: >= 7 of 8)")
    print("  %-6s %s" % ("arm", "  ".join("f%d" % f for f, _a, _b in FOLDS)))
    for name, _f in ARMS:
        if name == "LEG":
            continue
        wins, diffs = 0, []
        for fno, a, b in FOLDS:
            last = fno == len(FOLDS)
            mm = (series[name].index >= a) & ((series[name].index <= b) if last else (series[name].index < b))
            fy = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
            ra = four_numbers(list(series[name][mm]), years=fy)["roc30"] or 0.0
            rl = four_numbers(list(series["LEG"][mm]), years=fy)["roc30"] or 0.0
            diffs.append(ra - rl)
            wins += ra > rl
        out["folds"][name] = {"wins": wins, "diffs": diffs}
        print("  %-6s %s  -> %d of 8  (mean %+.2f, sd %.2f)"
              % (name, "  ".join("%+5.1f" % d for d in diffs), wins,
                 float(np.mean(diffs)), float(np.std(diffs, ddof=1))))

    print("\nTHE BAR (prereg section 3): beats the leg on the stretch AND >= 7 of 8 folds AND not one "
          "episode AND >= 50 trades a year")
    for name, _f in ARMS:
        if name == "LEG":
            continue
        a = out["arms"][name]
        cond = {"1 beats the leg": (a["roc30"] or 0) > (base["roc30"] or 0),
                "2 >= 7 of 8 folds": out["folds"][name]["wins"] >= 7,
                "3 not one episode": not a["one_episode"],
                "4 >= 50 trades/yr": a["trades_per_year"] >= 50}
        print("  %-6s %s -> %s" % (name, "  ".join("%s %s" % (k, "PASS" if v else "FAIL")
                                                   for k, v in cond.items()),
                                   "LIFTS" if all(cond.values()) else "NO LIFT"))
        out["arms"][name]["bar"] = cond
        out["arms"][name]["lifts"] = all(cond.values())

    json.dump(out, open(os.path.join(OUT, "grokenguq_score_r1.json"), "w"), indent=1, default=str)
    json.dump([{k: (int(x) if isinstance(x, (bool, np.integer)) else x) for k, x in r.items()} for r in rows],
              open(os.path.join(OUT, "scored_trades.json"), "w"))
    print("\nwrote %s" % os.path.join(OUT, "grokenguq_score_r1.json"))
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
    elif len(sys.argv) > 1 and sys.argv[1] == "run":
        run()
    else:
        raise SystemExit("usage: grokenguq_score_r1.py selftest | run")
