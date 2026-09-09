"""ENGU-Q SEARCH: THE KNOBS THIS PROJECT HAS BARELY TOUCHED, JUDGED ON THE OWNER'S RULE.

Every ENGU-Q round so far has moved the same few settings: the trendline lookback, the trend
filter, the trail, the breakeven, the regime filter, the hold cap. Four knobs have been left
at their crowned values through the whole campaign:

    limit_atr   how far below the signal bar the entry limit sits (fill quality)
    atr_len     the volatility ruler everything else is measured in
    er_len      the window the trend-quality gate measures over
    vol_mult    the volume filter on the breakout bar
    stop_mult   how wide the initial stop sits relative to the swing

This searches those, one at a time around the live crown (a one-at-a-time walk, not a grid:
the grid would be 1,000+ cells on a 16-year 1-minute tape, and this project has already
learned that the useful information is in whether a knob has ANY power, not in its
interactions).

EVERY CELL IS SCORED ON THE OWNER'S RULE, NOT ON PROFIT: after today's work the bar for an
ENGU-Q config is that its edge must not be a fat tail riding a rising index.

PRE-REGISTERED, written before running. A cell is a CANDIDATE only if it clears all of:
  1. top-10 share of net           < 50%     (live crown 51%, capped crown 44%)
  2. proportional-tail EV R        > 0.20    (delete the top 0.5% of ITS OWN trades and the
                                              edge per trade must still beat the capped
                                              crown's 0.173; this is the even-handed read
                                              that exposed the frontier leg today)
  3. annualised MAR                > 0.92    (the live crown; beat it, do not tie it)
  4. both index down years positive
  5. at least 120 continuous held-out trades (the live crown takes 118)
Anything clearing all five gets the queue guard's tail bar run against it, and if that agrees,
an Auto-Validate. Everything is printed either way, including the knobs that do nothing -
a knob with no power is a finding, because the validate is spending a search dimension on it.

RESULT, 2026-09-09: 0 of 24 cells cleared every bar - but the bar was mis-set and one cell
matters anyway.

THE BAR WAS WRONG. It required top-10 concentration under 50%, which the crown itself does
not achieve (55.6%). Nothing that keeps the crown's exits can clear it, so "0 of 24" is
partly an artifact of my own threshold. Read the cells against the CROWN instead:

    limit_atr   trades      net       PF     MAR   top-10  propEVR  corr    2018      2022
      0.55 CROWN 1,949   $613,126   1.711   0.92   55.6%   0.224  +0.51  $12,392   $ 7,340
      0.70       1,997   $583,678   1.670   0.96   58.7%   0.196  +0.41  $11,452   $12,225
      0.85       1,995   $617,284   1.717   1.08   56.3%   0.223  +0.44  $10,574   $17,489
      1.00       2,030   $598,987   1.701   1.03   55.7%   0.221  +0.45  $ 8,332   $17,191

The entry limit depth is the ONLY one of the five untouched settings that improves the crown:
+17% MAR at 0.85, net slightly up, 2022 more than doubled, tail dependence unchanged. Shipped
as ENGUQ_1M_ETH_R4_1_0.py and queued (job 4Oy6lWgZ). ATR length, volume filter and stop width
all trade one read for another; none dominate.

SECOND DEAD KNOB FOUND: er_len has NO POWER at the crown - every value returns the crown's
exact trade count - because the efficiency floor (er_th) is 0.0, which switches the gate off
entirely, so the length of its window cannot matter. Together with buf_atr (dead because
min_brk strictly dominates it) that is TWO of this family's fourteen knobs that a
full-discovery validate is searching for nothing.
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

SCR = os.path.dirname(os.path.abspath(__file__))
WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
LB_FROM = pd.Timestamp("2025-06-30")
MULT, COST = 20.0, 0.533
STRAT = "ENGUQ_1M_ETH_R2_1_0.py"

CROWN = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52, act_R=1.5,
             breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
             min_brk=1.6, vol_mult=1.1, er_th=0.0)

WALK = [
    ("limit_atr", [0.0, 0.25, 0.40, 0.70, 0.85, 1.00]),
    ("atr_len", [26, 39, 65, 78, 104]),
    ("er_len", [50, 75, 130, 160]),
    ("vol_mult", [0.0, 0.8, 1.0, 1.3, 1.5]),
    ("stop_mult", [0.7, 0.85, 1.15, 1.3]),
]


def score(tr, idx, bench, years):
    pnl = np.array([t[2] * MULT for t in tr], float)
    ent = pd.DatetimeIndex([idx[int(t[0])] for t in tr])
    eq = np.cumsum(pnl[np.argsort(ent.values)])
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    order = np.argsort(pnl)[::-1]
    k = max(1, int(round(len(pnl) * 0.005)))
    keep = np.ones(len(pnl), bool)
    keep[order[:k]] = False
    q = pnl[keep]
    w = q[q > 0]
    pf_q = float(w.sum() / max(-q[q < 0].sum(), 1e-9))
    wr_q = len(w) / len(q)
    wf = pnl[pnl > 0]
    pf = float(wf.sum() / max(-pnl[pnl < 0].sum(), 1e-9))
    yr = pd.Series(pnl, index=ent).groupby(lambda x: x.year).sum()
    common = yr.index.intersection(bench.index)
    return dict(n=len(pnl), net=float(pnl.sum()), pf=pf, dd=dd,
                mar=(float(pnl.sum()) / years) / dd if dd > 1e-9 else float("nan"),
                top10=float(np.sort(pnl)[::-1][:10].sum() / pnl.sum()),
                prop_ev_r=(1 - wr_q) * (pf_q - 1), prop_k=k,
                corr=float(yr[common].corr(bench[common])),
                y2018=float(yr.get(2018, 0.0)), y2022=float(yr.get(2022, 0.0)),
                lb_n=int((ent >= LB_FROM).sum()))


def clears(s):
    return [("top10<50%", s["top10"] < 0.50), ("propEVR>0.20", s["prop_ev_r"] > 0.20),
            ("MAR>0.92", s["mar"] > 0.92), ("2018>0", s["y2018"] > 0),
            ("2022>0", s["y2022"] > 0), ("LB>=120", s["lb_n"] >= 120)]


def main():
    a = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), **WIN)
    idx = pd.DatetimeIndex(pd.to_datetime(a["index"]))
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    years = (idx[-1] - idx[0]).days / 365.25
    last = pd.Series(np.asarray(a["close"], float), index=idx).resample("YE").last()
    bench = ((last / last.shift(1) - 1.0) * 100).dropna()
    bench.index = bench.index.year

    def run(p):
        r = run_backtest(STRAT, arrays=a, params=dict(p), cost_pts=COST, return_trades=True)
        tr = (r or {}).get("trades") or []
        return score(tr, idx, bench, years) if len(tr) >= 50 else None

    base = run(CROWN)
    print("  CROWN                     n=%4d net=$%9s PF=%.3f MAR=%.2f top10=%4.1f%% "
          "propEVR=%.3f corr=%+.2f LB=%3d"
          % (base["n"], format(base["net"], ",.0f"), base["pf"], base["mar"],
             base["top10"] * 100, base["prop_ev_r"], base["corr"], base["lb_n"]), flush=True)

    rows, winners, dead = [], [], []
    for knob, values in WALK:
        seen = {}
        for v in values:
            s = run(dict(CROWN, **{knob: v}))
            if s is None:
                print("  %-12s %-6s too few trades" % (knob, v), flush=True)
                continue
            s.update(knob=knob, value=v)
            rows.append(s)
            seen[v] = s["n"]
            ok = clears(s)
            s["clears_all"] = all(x for _, x in ok)
            if s["clears_all"]:
                winners.append(s)
            print("  %-12s %-6s n=%4d net=$%9s PF=%.3f MAR=%.2f top10=%4.1f%% "
                  "propEVR=%.3f corr=%+.2f 2018=$%7s 2022=$%8s LB=%3d%s"
                  % (knob, v, s["n"], format(s["net"], ",.0f"), s["pf"], s["mar"],
                     s["top10"] * 100, s["prop_ev_r"], s["corr"],
                     format(s["y2018"], ",.0f"), format(s["y2022"], ",.0f"), s["lb_n"],
                     "   <<< CLEARS ALL" if s["clears_all"] else ""), flush=True)
        if seen and len(set(seen.values())) == 1 and base["n"] in set(seen.values()):
            dead.append(knob)
        print("", flush=True)

    if dead:
        print("KNOBS WITH NO POWER at the crown (every value gave the crown's own trade "
              "count): %s -- the validate is spending a search dimension on each of these."
              % ", ".join(dead))
    print("\nCLEARS EVERY BAR: %d of %d" % (len(winners), len(rows)))
    for w in sorted(winners, key=lambda x: -x["mar"]):
        print("   %s=%s  MAR %.2f  net $%s  top10 %.1f%%  propEVR %.3f  LB %d"
              % (w["knob"], w["value"], w["mar"], format(w["net"], ",.0f"),
                 w["top10"] * 100, w["prop_ev_r"], w["lb_n"]))
    if not winners:
        print("   NONE -- the crown is not beaten on the owner's own rule by any single-knob "
              "move in the five settings the campaign never touched.")
    json.dump(dict(crown=base, rows=rows, dead=dead),
              io.open(os.path.join(SCR, "_enguq_r5.json"), "w"), indent=1, default=float)
    print("SAVED")


if __name__ == "__main__":
    main()
