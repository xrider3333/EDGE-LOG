# -*- coding: utf-8 -*-
"""NOISE ROUND 61 - the live NOISE #382 leg's two known gaps, and NOISE #422 on the same tape.

MANAGER dispatch 2026-09-26 (owner GO): judge #422 against #382's warm re-run #410, size the live fill-timing gap
the Paper: WB audit found (live NOISE orders go out a full bar after the backtest fill, as market orders), and say
whether commit 307a128 closed the live volatility-skip look-back gap (live ranks against ~70 sessions, backtest 252).

  PART 1  #304 raw, #382's cell (the live base), #422's crowned cell, one continuous tape, the validates' stretches:
          WF 2016-06-30 .. 2025-07-16, LB 2025-07-16 .. 2026-07-16, fresh tail 2026-07-16 .. 2026-09-16 (last Databento
          bar). Net, drawdown, ROC %/yr on $100k, return per drawdown, engine Sortino, PF.
  PART 2  FILL TIMING. Each trade re-priced from the bars themselves: (a) entry one bar late (the next bar's open),
          (b) entry AND exit one bar late. A stop or VWAP exit that the backtest filled at bar k goes out at the open
          of k+1 in (b); an exit on the session's last bar stays at that close (nothing later exists). A delay of zero
          must reproduce every trade to the cent - checked, or the script stops.
  PART 3  VOL-SKIP WINDOW. The skip ranks yesterday's volatility against up to 252 prior sessions in the backtest;
          live, 307a128 hands the strategy 70 sessions, so it ranks against ~68. Run with the reference capped at
          68 and compare which days are skipped and what it costs.

  python tools/r61_noise_382_live_gaps.py   -> tools/r37_results/r61_382_live_gaps.txt
"""
import os
import sys
import types

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import importlib.util as ilu                                          # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

COST, M, ACCT = 0.533, 20.0, 100000.0
LAST = pd.Timestamp("2026-09-16").date()
WF0, LB0, LB1 = (pd.Timestamp(x).date() for x in ("2016-06-30", "2025-07-16", "2026-07-16"))
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=str(LAST))
IDX = pd.DatetimeIndex(A["index"])
O, C, DAY = np.asarray(A["open"], float), np.asarray(A["close"], float), np.asarray(A["day_id"])
N = len(O)


def mod(fn):
    sp = ilu.spec_from_file_location(fn[:-3] + "_r61", os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
ROWS = [("NOISE #304 raw (crown)", "NOISE_1_0.py", CROWN),
        ("NOISE #382 cell (live base; #410 = its warm re-run)", "NOISE_1_8_CT304.py",
         dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=2.0)),
        ("NOISE #422 crowned (hourly 20/1.15 at 1.75x)", "NOISE_1_8_CT304H.py",
         dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75))]
STRETCH = [("WF", WF0, LB0), ("LB", LB0, LB1), ("tail", LB1, None)]


def yrs(a, b):
    return (pd.Timestamp(b or LAST) - pd.Timestamp(a)).days / 365.25


def run(fn, params, module=None):
    m = module or mod(fn)
    r = run_backtest(m, arrays=A, params=params, cost_pts=COST, return_trades=True)
    t = r["trades"]
    s = r.get("trade_sizes")
    s = np.asarray(s, float) if s is not None and len(s) == len(t) else np.ones(len(t))
    order = np.argsort([int(x[0]) for x in t], kind="stable")
    return [t[i] for i in order], s[order]


def reprice(trades, sizes, late_entry, late_exit):
    """Per-trade net points (sized, cost included) with entry / exit moved one bar later."""
    out, dropped = [], 0
    for (ke, kx, pnl, side, epx), s in zip(trades, sizes):
        ke, kx, side = int(ke), int(kx), int(np.sign(side))
        raw = pnl / s + COST                               # engine: pnl = s * (raw - cost)
        xpx = epx + side * raw
        e2, x2 = epx, xpx
        if late_entry:
            if ke + 1 >= N or DAY[ke + 1] != DAY[ke] or ke + 1 > kx + (1 if late_exit else 0):
                dropped += 1
                continue
            e2 = O[ke + 1]
        if late_exit:
            last_bar = (kx + 1 >= N) or (DAY[kx + 1] != DAY[kx])
            if not (last_bar and abs(xpx - C[kx]) < 1e-9):     # a session-close exit cannot move later
                x2 = C[kx] if last_bar else O[kx + 1]
        out.append((ke, s * (side * (x2 - e2) - COST)))
    return out, dropped


def stats(pairs, a, b):
    k = np.array([p[0] for p in pairs]); v = np.array([p[1] for p in pairs], float) * M
    d = np.array([IDX[max(x - 1, 0)].date() for x in k]) if len(k) else np.array([])
    m = np.ones(len(v), bool)
    if a is not None:
        m &= d >= a
    if b is not None:
        m &= d < b
    q = v[m]
    if not len(q):
        return dict(n=0, net=0, dd=0, roc=0, mar=0, so=0, pf=0)
    y = yrs(a, b)
    cum = np.cumsum(q)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    down = np.sqrt(np.mean(np.minimum(q, 0.0) ** 2))
    gw, gl = q[q > 0].sum(), -q[q < 0].sum()
    return dict(n=len(q), net=float(q.sum()), dd=dd, roc=100 * q.sum() / y / ACCT,
                mar=(q.sum() / y / dd) if dd > 0 else 0.0,
                so=(q.mean() / down) * np.sqrt(len(q) / y) if down > 0 else 0.0,
                pf=(gw / gl) if gl > 0 else 99.0)


def line(label, pairs):
    print("  " + label)
    for nm, a, b in STRETCH:
        s = stats(pairs, a, b)
        print("    %-4s %4d tr  $%9s  DD $%7s  ROC %5.1f%%/yr  MAR %4.2f  Sortino %4.2f  PF %4.2f" % (
            nm, s["n"], format(int(s["net"]), ","), format(int(s["dd"]), ","), s["roc"], s["mar"], s["so"], s["pf"]))


print("tape 2010-06-07 .. %s, cost %.3f, $%d per point, ROC on $%d" % (IDX[-1].date(), COST, M, ACCT))
print("\nPART 1 + PART 2 - as backtested, then one bar late")
base_cache = {}
for name, fn, params in ROWS:
    t, s = run(fn, params)
    base_cache[name] = (fn, params)
    same, _ = reprice(t, s, False, False)
    worst = max(abs(a[1] - float(x[2])) for a, x in zip(same, t))
    assert worst < 1e-6, "re-pricing at zero delay does not reproduce %s (%.6f)" % (name, worst)
    print("\n%s  (%d trades; zero-delay re-price reproduces every trade)" % (name, len(t)))
    line("as backtested (fill at next bar's open)", same)
    late_e, dr1 = reprice(t, s, True, False)
    line("entry one bar late (%d trades lost)" % dr1, late_e)
    late_ex, dr2 = reprice(t, s, True, True)
    line("entry AND exit one bar late (%d lost)" % dr2, late_ex)
    tot = lambda p: sum(x[1] for x in p) * M
    n_ = len(t)
    print("    whole tape: $%s -> $%s (entry late) -> $%s (both late); per trade %+.2f / %+.2f points vs as-backtested"
          % (format(int(tot(same)), ","), format(int(tot(late_e)), ","), format(int(tot(late_ex)), ","),
             (tot(late_e) - tot(same)) / M / n_, (tot(late_ex) - tot(same)) / M / n_))

print("\nPART 3 - volatility-skip reference window: 252 prior sessions (backtest) vs 68 (live after 307a128)")


def patch_ref(module, ref_n, seen=None):
    seen = seen if seen is not None else set()
    if id(module) in seen:
        return 0
    seen.add(id(module))
    hit = 0
    fn = getattr(module, "_vol_percentile", None)
    if callable(fn) and fn.__defaults__:
        d = list(fn.__defaults__)
        d[0] = ref_n
        fn.__defaults__ = tuple(d)
        hit += 1
    for v in list(vars(module).values()):
        if isinstance(v, types.ModuleType) and getattr(v, "__file__", "") and "augur_strategies" in v.__file__:
            hit += patch_ref(v, ref_n, seen)
    return hit


for name in ("NOISE #304 raw (crown)", "NOISE #382 cell (live base; #410 = its warm re-run)"):
    fn, params = base_cache[name]
    m252 = mod(fn)
    m68 = mod(fn)
    n_patched = patch_ref(m68, 68)
    t1, s1 = run(fn, params, m252)
    t2, s2 = run(fn, params, m68)
    d1 = {IDX[int(x[0])].date() for x in t1}
    d2 = {IDX[int(x[0])].date() for x in t2}
    print("\n%s  (vol-skip function patched in %d module(s))" % (name, n_patched))
    line("reference 252 sessions (backtest)", [(int(x[0]), float(x[2])) for x in t1])
    line("reference 68 sessions (live)", [(int(x[0]), float(x[2])) for x in t2])
    print("    trading days only in the 252 run: %d, only in the 68 run: %d, of %d / %d"
          % (len(d1 - d2), len(d2 - d1), len(d1), len(d2)))
