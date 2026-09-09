"""DOES A THIRD LEG BEAT THE REPAIRED PAIR, OR IS TWO ENOUGH?

The repaired frontier pair (ENGU-Q R2 crown + ORB #234) measured pooled MAR 1.69 against the
incumbent pair's 1.38, and the NOISE crown ALSO cleared the audition (1.63) - so both
survivors are available and the obvious question is whether running all three beats running
the best two.

This is the same machinery as tools/frontier_repair.py: legs pooled day by day, one contract
each, nothing tuned, every book scored the same way. The incumbent trio (run #324, which
carries the disqualified NOISE R/YR frontier leg) is scored alongside so the comparison is
against what exists rather than against a memory.

PRE-REGISTERED, written before running. The trio is queued only if:
  1. pooled MAR beats the repaired PAIR's 1.69          (a third leg must earn its slot)
  2. pooled day-level top-10 concentration < the pair's 38.3%
  3. both index down years positive
  4. every leg's own proportional-tail EV R > 0.05      (no passenger legs - the rule that
                                                         disqualified the incumbent's leg)
A third leg that merely adds size without improving the risk-adjusted return is leverage, and
this project already measured that trap on the two-horizon book. If the trio does not clear,
the pair stands and nothing further is queued.

RESULT, 2026-09-09 - AND IT OVERTURNS THE "REPAIR" NARRATIVE.

    book                          net $     maxDD $   MAR   dayTop10  index corr   2018      2022
    PAIR repaired (queued)       986,430    36,360   1.69     38.3%     +0.04    42,831   115,649
    PAIR alt (NOISE crown)       892,764    34,026   1.63     40.7%     +0.16    45,475    73,969
    TRIO new (no bad leg)      1,266,068    49,894   1.58     34.3%     -0.10    78,903   183,362
    TRIO incumbent (#324)      1,066,527    36,011   1.84     35.1%     +0.10    56,567   108,658
    QUAD (all four)            1,439,831    49,894   1.80     31.3%     -0.11    89,996   218,051

The new trio FAILS its own bar (MAR 1.58 < the pair's 1.69), so it was not queued. But the
INCUMBENT trio - the one carrying the leg disqualified as a standalone edge - has the best
pooled MAR measured anywhere (1.84). A leg can be fragile alone and still earn a book slot,
because a book wants UNCORRELATED P&L, not a standalone edge; the "no passenger legs" rule
written into this file assumed those were the same thing and they are not.

What was queued instead is the QUAD (tools/queue_quad_book.py): against run #324 it is +35%
net, lower concentration (31.3% vs 35.1%), a NEGATIVE index correlation (-0.11 vs +0.10) and
far stronger down years, for 2% less MAR and a deeper drawdown. Stated as a trade-off, not
sold as a free win.
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
from augur_engine.engine import run_backtest                      # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402
import importlib.util as ilu                                       # noqa: E402

SCR = os.path.dirname(os.path.abspath(__file__))
WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
R2 = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52, act_R=1.5,
          breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
          min_brk=1.6, vol_mult=1.1, er_th=0.0)

LEGS = {
    "ENGU-Q R2": ("ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", "db_noadj_eth", 0.533, 20.0,
                  dict(R2)),
    "ORB #234": ("ORB_3_6_C2.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, 20.0, None),
    "NOISE crown": ("NOISE_1_0.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, 20.0, None),
    "NOISE R/YR (bad)": ("NOISE_1_2_RYR.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, 20.0,
                         {}),
}
BOOKS = [
    ("PAIR repaired (queued)", ["ENGU-Q R2", "ORB #234"]),
    ("PAIR alt (NOISE crown)", ["ENGU-Q R2", "NOISE crown"]),
    ("TRIO new", ["ENGU-Q R2", "ORB #234", "NOISE crown"]),
    ("TRIO incumbent (#324)", ["ENGU-Q R2", "NOISE R/YR (bad)", "NOISE crown"]),
    ("QUAD (all four)", ["ENGU-Q R2", "ORB #234", "NOISE crown", "NOISE R/YR (bad)"]),
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


def build(name):
    fn, inst, tf, sess, src, cost, mult, params = LEGS[name]
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
    return daily, dict(n=len(pnl), net=float(pnl.sum()), prop_ev_r=(1 - wr) * (pf - 1))


def read(daily, bench, years):
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

    built = {}
    for name in LEGS:
        d, st = build(name)
        built[name] = (d, st)
        print("  leg %-18s n=%5d net $%-10s proportional-tail EV R %+.3f"
              % (name, st["n"], format(st["net"], ",.0f"), st["prop_ev_r"]), flush=True)

    print("\n  %-24s %11s %10s %6s %7s %6s %9s %9s %6s"
          % ("book", "net $", "maxDD $", "MAR", "dayT10", "corr", "2018", "2022", "yrs+"),
          flush=True)
    out = {}
    for label, names in BOOKS:
        frame = pd.concat([built[n][0] for n in names], axis=1).fillna(0.0)
        assert abs(frame.sum().sum() - sum(built[n][0].sum() for n in names)) < 1.0
        r = read(frame.sum(axis=1).sort_index(), bench, years)
        r["legs"] = names
        r["min_leg_tail"] = min(built[n][1]["prop_ev_r"] for n in names)
        out[label] = r
        print("  %-24s %11s %10s %6.2f %6.1f%% %+6.2f %9s %9s %3d/%d"
              % (label, format(r["net"], ",.0f"), format(r["dd"], ",.0f"), r["mar"],
                 r["day_top10"] * 100, r["corr"], format(r["y2018"], ",.0f"),
                 format(r["y2022"], ",.0f"), r["pos_years"], r["n_years"]), flush=True)

    pair = out["PAIR repaired (queued)"]
    trio = out["TRIO new"]
    checks = [("MAR beats the pair (%.2f)" % pair["mar"], trio["mar"] > pair["mar"],
               "%.2f" % trio["mar"]),
              ("concentration below the pair (%.1f%%)" % (pair["day_top10"] * 100),
               trio["day_top10"] < pair["day_top10"], "%.1f%%" % (trio["day_top10"] * 100)),
              ("both down years positive", trio["y2018"] > 0 and trio["y2022"] > 0,
               "%.0f / %.0f" % (trio["y2018"], trio["y2022"])),
              ("no passenger leg (min tail EV R > 0.05)", trio["min_leg_tail"] > 0.05,
               "%.3f" % trio["min_leg_tail"])]
    print("\nPRE-REGISTERED VERDICT for the new trio:")
    for label, ok, val in checks:
        print("   %-44s %-10s %s" % (label, val, "PASS" if ok else "FAIL"))
    ok = all(o for _, o, _ in checks)
    print("\n%s" % ("TRIO CLEARS -- queue it as a BOOK Auto-Validate beside the pair."
                    if ok else
                    "TRIO DOES NOT CLEAR -- the repaired PAIR stands as the frontier book; "
                    "a third leg adds size, not risk-adjusted return."))
    json.dump(out, io.open(os.path.join(SCR, "_frontier_trio.json"), "w"), indent=1,
              default=float)
    print("SAVED")


if __name__ == "__main__":
    main()
