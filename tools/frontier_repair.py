"""REPAIR THE FRONTIER BOOK: ITS SECOND LEG HAS ALMOST NO EDGE ONCE THE TAIL IS REMOVED.

Runs #323 (pair) and #324 (trio) both carry NOISE_1_2_RYR beside the ENGU-Q R2 crown. Today's
even-handed tail read (tools/tail_adjusted_board.py) found that leg goes from $146,392 to
$2,331 - profit factor 1.325 to 1.005 - once the top 0.5% of its OWN trades are deleted (28 of
5,548). It passed the house fixed-ten concentration check only because it trades three times
as often as the legs it was compared against.

So the pair's second slot is open, and this asks which available leg should hold it. Every
candidate is pooled 1:1 with the SAME ENGU-Q R2 leg, day by day, and scored the same way -
including the incumbent, so the comparison is like for like rather than against a memory.

WHAT EACH CANDIDATE IS SCORED ON
  * pooled annualised MAR (the read that decides), pooled net and drawdown
  * pooled concentration on trading DAYS (a pooled "trade" does not exist when legs overlap)
  * the candidate's OWN proportional tail read - EV R after deleting its top 0.5% of trades -
    which is the specific failure being repaired
  * daily correlation with the ENGU-Q leg (low is the point of a book)
  * both index down years on the pooled series

PRE-REGISTERED, written before running. A candidate REPLACES the incumbent only if:
  1. pooled MAR beats the incumbent pair's pooled MAR
  2. its own proportional-tail EV R  >  0.05   (the incumbent's is 0.004 - this is the bar the
     incumbent fails, and it is set low on purpose: the job is to clear the floor, not to win)
  3. daily correlation with the ENGU-Q leg  < 0.50
  4. both index down years positive on the pooled series
A winner gets an Auto-Validate as a BOOK job. If nothing clears, the honest outcome is that
the pair should be a single leg until a real second leg exists, and nothing is queued.

NOTE ON THE ORB CANDIDATE: the look-ahead audit voided ORB 3.0/3.1, not this file (the #234
crown), but the ORB family is the one where a leak was found, so a win here would need its own
execution-feasibility check before anything is queued. Flagged, not excluded.

RESULT, 2026-09-09. Both replacements cleared; ORB won and was queued (job LUxH9euN).

    pair                              net $     maxDD $   MAR   day-top10  index corr  leg corr
    incumbent (NOISE R/YR frontier)   786,889    35,399   1.38     43.3%      +0.34      -0.00
    + NOISE crown                     892,764    34,026   1.63     40.7%      +0.16      +0.03
    + ORB #234 crown                  986,430    36,360   1.69     38.3%      +0.04      +0.01
    ENGU-Q R2 alone                   613,126    39,200   0.97       n/a      +0.48        n/a

The incumbent leg is WORSE than the morning read suggested: on the full window it does not
merely lose its edge under proportional treatment, it goes NEGATIVE (-$6,317, EV R -0.010,
30 of 5,969 trades deleted). The ORB pair takes the pooled index correlation to +0.04 and
makes money in both index down years. But see tools/frontier_trio.py before concluding that
the incumbent leg should be thrown away - it should not.
"""
import io
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from augur_engine.engine import run_backtest                      # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402
import importlib.util as ilu                                       # noqa: E402

SCR = os.path.dirname(os.path.abspath(__file__))
WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
R2 = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52, act_R=1.5,
          breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
          min_brk=1.6, vol_mult=1.1, er_th=0.0)

ANCHOR = ("ENGU-Q R2 crown", "ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", "db_noadj_eth",
          0.533, 20.0, dict(R2))
CANDIDATES = [
    ("NOISE R/YR frontier (incumbent)", "NOISE_1_2_RYR.py", "NQ", "5m", "rth",
     "db_noadj_rth", 0.533, 20.0, {}),
    ("NOISE crown", "NOISE_1_0.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, 20.0, None),
    ("ORB crown (#234)", "ORB_3_6_C2.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, 20.0,
     None),
    ("ENGU-Q capped (R3)", "ENGUQ_1M_ETH_R3_1_0.py", "NQ", "1m", "eth", "db_noadj_eth",
     0.533, 20.0, dict(R2, max_hold_bars=8280)),
]

_ARR = {}


def arr_for(inst, tf, sess, src):
    k = (inst, tf, sess, src)
    if k not in _ARR:
        a = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
        idx = pd.DatetimeIndex(pd.to_datetime(a["index"]))
        try:
            idx = idx.tz_localize(None)
        except (TypeError, AttributeError):
            pass
        _ARR[k] = (a, idx)
    return _ARR[k]


def defaults(fn):
    sp = ilu.spec_from_file_location("m", os.path.join("augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


def build(fn, inst, tf, sess, src, cost, mult, params):
    a, idx = arr_for(inst, tf, sess, src)
    p = defaults(fn) if params is None else params
    r = run_backtest(fn, arrays=a, params=dict(p), cost_pts=cost, return_trades=True)
    tr = (r or {}).get("trades") or []
    pnl = np.array([t[2] * mult for t in tr], float)
    ex = pd.DatetimeIndex([idx[int(t[1])] for t in tr]).normalize()
    daily = pd.Series(pnl, index=ex).groupby(level=0).sum()
    order = np.argsort(pnl)[::-1]
    k = max(1, int(round(len(pnl) * 0.005)))
    keep = np.ones(len(pnl), bool)
    keep[order[:k]] = False
    q = pnl[keep]
    w = q[q > 0]
    pf = float(w.sum() / max(-q[q < 0].sum(), 1e-9))
    wr = len(w) / len(q)
    return daily, pnl, dict(n=len(pnl), net=float(pnl.sum()), prop_k=k,
                            prop_ev_r=(1 - wr) * (pf - 1), prop_net=float(q.sum()))


def pooled_read(daily, bench, years):
    eq = daily.cumsum()
    dd = float((eq.cummax() - eq).max())
    d = daily.values
    yr = daily.groupby(daily.index.year).sum()
    common = yr.index.intersection(bench.index)
    return dict(net=float(d.sum()), dd=dd,
                mar=(float(d.sum()) / years) / dd if dd > 1e-9 else float("nan"),
                day_top10=float(np.sort(d)[::-1][:10].sum() / d.sum()),
                corr=float(yr[common].corr(bench[common])),
                y2018=float(yr.get(2018, 0.0)), y2022=float(yr.get(2022, 0.0)),
                pos_years=int((yr > 0).sum()), n_years=int(len(yr)))


def main():
    a_nq, idx_nq = arr_for("NQ", "1m", "eth", "db_noadj_eth")
    years = (idx_nq[-1] - idx_nq[0]).days / 365.25
    last = pd.Series(np.asarray(a_nq["close"], float), index=idx_nq).resample("YE").last()
    bench = ((last / last.shift(1) - 1.0) * 100).dropna()
    bench.index = bench.index.year

    anchor_daily, _, anchor_stats = build(*ANCHOR[1:])
    print("  anchor %-30s n=%d net $%s   proportional-tail EV R %.3f"
          % (ANCHOR[0], anchor_stats["n"], format(anchor_stats["net"], ",.0f"),
             anchor_stats["prop_ev_r"]), flush=True)
    solo = pooled_read(anchor_daily, bench, years)
    print("  anchor ALONE: MAR %.2f  net $%s  DD $%s\n"
          % (solo["mar"], format(solo["net"], ",.0f"), format(solo["dd"], ",.0f")), flush=True)

    print("  %-32s %11s %10s %6s %6s %6s %7s %9s %9s"
          % ("pair = anchor + candidate", "net $", "maxDD $", "MAR", "dayT10", "corr",
             "legCorr", "2018", "2022"), flush=True)
    rows = []
    for label, fn, inst, tf, sess, src, cost, mult, params in CANDIDATES:
        daily, pnl, st = build(fn, inst, tf, sess, src, cost, mult, params)
        both = pd.concat([anchor_daily, daily], axis=1).fillna(0.0)
        assert abs(both.sum().sum() - (anchor_daily.sum() + daily.sum())) < 1.0
        pool = both.sum(axis=1).sort_index()
        pr = pooled_read(pool, bench, years)
        lc = float(both.iloc[:, 0].corr(both.iloc[:, 1]))
        rows.append(dict(label=label, leg=st, pair=pr, leg_corr=lc))
        print("  %-32s %11s %10s %6.2f %5.1f%% %+6.2f %+7.2f %9s %9s"
              % (label, format(pr["net"], ",.0f"), format(pr["dd"], ",.0f"), pr["mar"],
                 pr["day_top10"] * 100, pr["corr"], lc, format(pr["y2018"], ",.0f"),
                 format(pr["y2022"], ",.0f")), flush=True)
        print("       leg alone: n=%5d  net $%-10s  proportional-tail EV R %.3f "
              "(deleted %d, net left $%s)"
              % (st["n"], format(st["net"], ",.0f"), st["prop_ev_r"], st["prop_k"],
                 format(st["prop_net"], ",.0f")), flush=True)

    inc = next(r for r in rows if "incumbent" in r["label"])
    print("\nPRE-REGISTERED VERDICT (beat incumbent pooled MAR %.2f; own proportional-tail "
          "EV R > 0.05; leg correlation < 0.50; both down years positive)" % inc["pair"]["mar"])
    winners = []
    for r in rows:
        if "incumbent" in r["label"]:
            continue
        c = [("MAR", r["pair"]["mar"] > inc["pair"]["mar"], "%.2f" % r["pair"]["mar"]),
             ("tail floor", r["leg"]["prop_ev_r"] > 0.05, "%.3f" % r["leg"]["prop_ev_r"]),
             ("leg corr", r["leg_corr"] < 0.50, "%+.2f" % r["leg_corr"]),
             ("down years", r["pair"]["y2018"] > 0 and r["pair"]["y2022"] > 0,
              "%.0f/%.0f" % (r["pair"]["y2018"], r["pair"]["y2022"]))]
        ok = all(x for _, x, _ in c)
        print("   %-32s " % r["label"] + "  ".join(
            "%s %s %s" % (n, v, "OK" if x else "no") for n, x, v in c)
            + ("   <<< CLEARS" if ok else ""))
        if ok:
            winners.append(r)
    print("\n%s" % ("CLEARS: " + ", ".join(w["label"] for w in winners)
                    if winners else
                    "NOTHING CLEARS. The frontier pair has no available second leg that both "
                    "survives an even-handed tail read and improves the pooled risk-adjusted "
                    "return - it should stand as a single leg until one exists."))
    json.dump(rows, io.open(os.path.join(SCR, "_frontier_repair.json"), "w"), indent=1,
              default=float)
    print("SAVED")


if __name__ == "__main__":
    main()
