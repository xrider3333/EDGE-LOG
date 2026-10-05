# -*- coding: utf-8 -*-
"""NOISE ROUND 69 STAGE A - walk-forward ONLY (docs/PREREG_noise_r69_tiltdepth_2026-10-04.md).

Is NOISE #422's compression size-up too small? 2.25x (neighbours 2.0x / 2.75x) vs #422's 1.75x on the same trades.
Nothing in this file reads the lockbox (entries on or after 2025-07-16) or the tail. Stage B was dropped (amendment
#28): a pass on EVERY bar makes the frozen 2.25x cell a no-order forward shadow beside #422 (paired sequential stop,
judged at 50 closed trades); a fail is recorded dead.

  PARITY  round 68's harness must reproduce stored run #422 (WF 2,805 tr, ROC@30k 84.6, Sortino 4.49) or abort
  A1      2.25x beats #422 on WF ROC@30k AND Sortino, >= 100 trades
  A2      both neighbours beat #422's WF ROC@30k
  A3      stationary block bootstrap (mean block 20 sessions, 1,000 draws, seed 20261004) of both daily P&L series
          resampled TOGETHER: 5th percentile of (2.25x - 1.75x) WF ROC@30k > 0
  A4      2.25x beats 1.75x on ROC@30k in >= 6 of the 9 WF years
  A5      INFORMATION ONLY (amendment #28): the book lane reads BOOK #463 with this NOISE leg against WF 93.8 / 3.82
          on the exported walk-forward leg (C:\\EdgeLog\\book_legs\\NOISE422_t225_*)
  sanity  1,000 shuffles of the 2.25x sizes across WF trades (not a bar)

  python tools/r69_noise_stageA.py   (from the shared checkout's python path; writes r37_results/r69_stageA.txt by tee)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

GATE = (60, 20, 1.15)
SEED, DRAWS, BLOCK = 20261004, 1000, 20
LEGDIR = os.environ.get("EDGELOG_BOOK_LEGS", r"C:\EdgeLog\book_legs")


def leg(tr, tilt):
    return R.sized(tr, GATE + (tilt,))


def wf_only(pairs):
    return [(k, v) for k, v in pairs if R.WF0 <= R.DATE[k - 1] < R.LB0]


def wf_line(label, pairs):
    s = R.stats(pairs, R.WF0, R.LB0)
    print("  %-22s WF %4d tr  ROC@30k %5.1f%%  Sortino %4.2f  (%5.1f%%/yr, DD $%s)" % (
        label, s["n"], s["r30"], s["so"], s["roc"], format(int(s["dd"]), ",")))
    return s


SESS = np.array(sorted(set(R.DATE[(R.DATE >= R.WF0) & (R.DATE < R.LB0)])))
YEARS = (pd.Timestamp(R.LB0) - pd.Timestamp(R.WF0)).days / 365.25


def daily(pairs):
    k = np.array([p[0] for p in pairs], int)
    v = np.array([p[1] for p in pairs], float) * R.M
    d = R.DATE[k - 1]
    m = (d >= R.WF0) & (d < R.LB0)
    return pd.Series(v[m]).groupby(d[m]).sum().reindex(SESS, fill_value=0.0).to_numpy()


def roc30(x, years):
    cum = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    return 30 * (x.sum() / years) / dd if dd > 0 else np.inf


def stationary_index(n, rng):
    idx = np.empty(n, int)
    i = rng.integers(n)
    p = 1.0 / BLOCK
    for t in range(n):
        if t > 0:
            i = rng.integers(n) if rng.random() < p else (i + 1) % n
        idx[t] = i
    return idx


def export(pairs, tr, name):
    """WF and IS rows only (entry before 2025-07-16), the book_legs format, for the book lane's A5 read."""
    os.makedirs(LEGDIR, exist_ok=True)
    comp = R.SQ._compression(R.H, R.L, R.C, np.asarray(R.A["day_id"]), R.A["index"], *GATE)
    rows = []
    for x, (k, v) in zip(tr, pairs):
        if R.DATE[k - 1] >= R.LB0:
            continue
        s = 2.25 if bool(comp[k - 1]) else 1.0
        rows.append(dict(entry_time=str(R.IDX[k].tz_convert("US/Eastern").tz_localize(None)),
                         exit_time=str(R.IDX[int(x[1])].tz_convert("US/Eastern").tz_localize(None)),
                         side="long" if x[3] > 0 else "short", pnl_usd=round(v * R.M, 2), size=s,
                         stage="IS" if R.DATE[k - 1] < R.WF0 else "WF", date=str(R.DATE[k - 1])))
    t = pd.DataFrame(rows)
    t.drop(columns="date").to_csv(os.path.join(LEGDIR, name + "_trades.csv"), index=False)
    g = t.groupby("date")
    pd.DataFrame({"date": list(g.groups.keys()), "pnl_usd": g.pnl_usd.sum().round(2).to_numpy(),
                  "trades": g.size().to_numpy(), "size": g["size"].max().to_numpy(),
                  "stage": g.stage.first().to_numpy()}).to_csv(os.path.join(LEGDIR, name + "_daily.csv"), index=False)
    print("  exported %s_trades.csv / _daily.csv (%d trades, IS + WF only - no lockbox rows)" % (name, len(t)))


if __name__ == "__main__":
    print("NOISE round 69 STAGE A - walk-forward only, %s .. %s, cost %.3f, $%d/pt" % (R.WF0, R.LB0, R.COST, R.M))
    tr = R.trades(R.build())
    ct = R.load("NOISE_1_8_CT304H.py")
    ref = run_backtest(ct, arrays=R.A, params=dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75), cost_pts=R.COST,
                       return_trades=True)["trades"]
    twin_pairs = leg(tr, 1.75)
    assert sorted((int(x[0]), round(float(x[2]), 9)) for x in ref) == sorted((k, round(v, 9)) for k, v in twin_pairs), \
        "rebuilt #422 does not reproduce NOISE_1_8_CT304H"
    print("")
    twin = wf_line("NOISE #422 (1.75x)", twin_pairs)
    assert twin["n"] == 2805 and round(twin["r30"], 1) == 84.6 and round(twin["so"], 2) == 4.49, "PARITY FAILED - abort"
    print("  parity: reproduces stored run #422 (WF 2,805 trades, 84.6, 4.49)")
    cells = {t: leg(tr, t) for t in (2.25, 2.0, 2.75)}
    s = {t: wf_line("%.2fx%s" % (t, "" if t == 2.25 else " (neighbour)"), cells[t]) for t in (2.25, 2.0, 2.75)}

    a1 = s[2.25]["r30"] > twin["r30"] and s[2.25]["so"] > twin["so"] and s[2.25]["n"] >= 100
    a2 = s[2.0]["r30"] > twin["r30"] and s[2.75]["r30"] > twin["r30"]
    shape = [twin["r30"], s[2.0]["r30"], s[2.25]["r30"], s[2.75]["r30"]]
    mono = all(b > a for a, b in zip(shape, shape[1:]))

    x1, x2 = daily(twin_pairs), daily(cells[2.25])
    rng = np.random.default_rng(SEED)
    diffs = np.empty(DRAWS)
    for i in range(DRAWS):
        idx = stationary_index(len(SESS), rng)
        diffs[i] = roc30(x2[idx], YEARS) - roc30(x1[idx], YEARS)
    p5 = float(np.percentile(diffs, 5))
    a3 = p5 > 0

    wins = []
    for y in range(9):
        a = (pd.Timestamp(R.WF0) + pd.DateOffset(years=y)).date()
        b = R.LB0 if y == 8 else (pd.Timestamp(R.WF0) + pd.DateOffset(years=y + 1)).date()
        m = (SESS >= a) & (SESS < b)
        yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
        r1, r2 = roc30(x1[m], yrs), roc30(x2[m], yrs)
        wins.append(r2 > r1)
        print("    year %d (%s .. %s): 1.75x %6.1f  2.25x %6.1f  %s" % (y + 1, a, b, r1, r2, "2.25x" if r2 > r1 else "1.75x"))
    a4 = sum(wins) >= 6

    comp = R.SQ._compression(R.H, R.L, R.C, np.asarray(R.A["day_id"]), R.A["index"], *GATE)
    kk = np.array([k for k, _ in cells[2.25]])
    sizes = np.where(comp[kk - 1].astype(bool), 2.25, 1.0)
    base = np.array([v0 for _, v0 in leg(tr, 1.0)])                   # 1x net per trade, same order
    wfm = (R.DATE[kk - 1] >= R.WF0) & (R.DATE[kk - 1] < R.LB0)
    real = s[2.25]["r30"]
    sh = []
    for _ in range(DRAWS):
        perm = sizes.copy()
        perm[wfm] = rng.permutation(sizes[wfm])
        sh.append(R.stats(list(zip(kk, perm * base)), R.WF0, R.LB0)["r30"])
    pct = 100 * np.mean(np.array(sh) < real)

    print("")
    print("  A1 2.25x beats #422 on WF ROC@30k and Sortino, >=100 trades : %s" % ("PASS" if a1 else "FAIL"))
    print("  A2 both neighbours beat #422's WF ROC@30k                   : %s" % ("PASS" if a2 else "FAIL"))
    print("     shape 1.75 / 2.0 / 2.25 / 2.75 = %s%s" % (" / ".join("%.1f" % v for v in shape),
                                                       "  -> 'top edge again' (monotone; not a stronger pass)" if mono else ""))
    print("  A3 paired block bootstrap, 5th pct of WF ROC@30k difference  : %+.1f -> %s" % (p5, "PASS" if a3 else "FAIL"))
    print("  A4 2.25x wins %d of 9 WF years (need 6)                      : %s" % (sum(wins), "PASS" if a4 else "FAIL"))
    print("  sanity: 2.25x WF ROC@30k beats %.0f%% of 1,000 shuffles of its own sizes" % pct)
    ok = a1 and a2 and a3 and a4
    if ok:
        export(cells[2.25], tr, "NOISE422_t225")
    print("")
    print("STAGE A (own conditions A1-A4): %s" % ("PASS -> frozen 2.25x becomes a no-order forward shadow beside #422 (paired sequential stop, 50 trades); A5 book read = info"
                                               if ok else "FAIL - recorded dead, #422 stays at 1.75x"))
