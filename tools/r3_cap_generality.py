"""IS THE HOLD CAP A GENERAL MECHANISM ON NQ, OR IS IT FITTED TO THE CROWN'S EXACT ENTRY?

The cap was measured at ONE entry configuration - the crown's - and it looked like a clean
fix: top-10 share 56% -> 44%, index correlation +0.51 -> +0.38, both down years positive, a
third more held-out trades, for about 8% of headline profit. Then tools/r3_es_travel.py
showed the cap does NOT travel to ES, where the uncapped config beats it on every read. That
raises the obvious question about the tape it DOES work on: is "capping the hold fixes the
tail" a property of the mechanism, or a property of that one entry setting?

THE TEST: hold the exit knobs fixed at the crown's (trail 2.5, breakeven 2.0, stop 1.0) and
walk the ENTRY side - the trendline lookback, the trend filter length, the breakout buffer,
the regime filter and the efficiency-ratio threshold - one knob at a time around the crown.
Each entry variant is run TWICE, once uncapped and once at the shipped 8,280-bar cap, and
what is scored is the DIFFERENCE the cap makes, variant by variant.

PRE-REGISTERED, written before running. The cap is a GENERAL mechanism on NQ only if, across
the entry variants:
  1. it lowers the top-10 concentration share in at least 80% of them
  2. it lowers the correlation of yearly net with the index's yearly return in at least 70%
  3. it does not cost more than 15% of annualised MAR on the median variant
  4. it raises the continuous held-out trade count in at least 70%
If it clears those, the cap earns its place on NQ as a mechanism rather than a fitted knob.
If it only helps at the crown's own entry, it is a fitted knob and the honest label changes,
whatever the crown's numbers say. Every variant is printed either way.

RESULT, 2026-09-09 - THE CAP CLEARS ALL FOUR BARS over 19 entry variants:
    lowers concentration in 95% of them          (bar 80%)
    lowers index correlation in 89%              (bar 70%)
    median MAR cost -5.5%                        (bar -15%)
    raises the held-out sample in 100%           (bar 70%)
So on NQ the hold cap is a MECHANISM, not a knob fitted to the crown's entry: it does the
same thing - shorter holds, profit spread wider, less index correlation, more held-out
evidence - wherever the entry is put. Note this stands ALONGSIDE tools/r3_es_travel.py, which
found the cap does NOT travel to ES. Both are true: general across entries on the Nasdaq tape,
absent (worse than useless) on the S&P tape.

TWO THINGS THIS RUN TURNED UP THAT WERE NOT WHAT IT WAS LOOKING FOR.

1. `buf_atr` IS A DEAD KNOB at the crown. buf_atr 0.2 / 0.4 / 0.5 produce byte-identical
   results (55.6% -> 43.8%, corr +0.51 -> +0.38, same trade counts). The entry applies two
   gates in series - close must clear the trendline by buf_atr * ATR, and then
   (close - trendline) / ATR must be >= min_brk - and since min_brk is 1.6 while buf_atr is
   fenced 0.0-1.0, the second gate strictly dominates and the first can NEVER bind. buf_atr
   only comes alive if a search drives min_brk below 1.0. Consequences: any "plateau across
   buf_atr" in this family's history is illusory breadth, and a full-discovery validate is
   spending one of its search dimensions on a setting that cannot change anything. Not fixed
   here - narrowing or removing the knob changes the search space and is an owner call.

2. THE EFFICIENCY-RATIO GATE is the strongest correlation reducer found so far, and it is
   still not usable. er_th 0.15 reads corr +0.19 uncapped (crown: +0.51) - by far the lowest
   on this family - but in absolute terms it is weak everywhere else: n 1,064, net $396,100,
   MAR 0.40, top-10 70.3%, 77 held-out trades. Capped it improves to MAR 0.53 / top-10 61.3%
   / corr +0.25 / 90 held-out, which is still well below the capped crown (MAR 0.87, top-10
   43.8%, 155 held-out). er_th 0.25 is an outright artifact (top-10 100.7% - it loses money
   once its ten best trades are removed). Recorded so the next session does not re-discover
   the low correlation and mistake it for a candidate.
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
STRAT = "ENGUQ_1M_ETH_R3_1_0.py"
CAP = 8280

CROWN = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52, act_R=1.5,
             breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
             min_brk=1.6, vol_mult=1.1, er_th=0.0)

VARIANTS = [("crown", {})]
for v in (150, 180, 240, 280):
    VARIANTS.append(("tl_len %d" % v, dict(tl_len=v)))
for v in (140, 180, 300, 400):
    VARIANTS.append(("ema_len %d" % v, dict(ema_len=v)))
for v in (0.2, 0.4, 0.5):
    VARIANTS.append(("buf_atr %.1f" % v, dict(buf_atr=v)))
for v in (0, 5, 20):
    VARIANTS.append(("regime_len %d" % v, dict(regime_len=v)))
for v in (0.15, 0.25):
    VARIANTS.append(("er_th %.2f" % v, dict(er_th=v)))
for v in (1.3, 1.9):
    VARIANTS.append(("min_brk %.1f" % v, dict(min_brk=v)))


def score(tr, idx, bench, years):
    d = np.array([t[2] * MULT for t in tr], float)
    ent = pd.DatetimeIndex([idx[int(t[0])] for t in tr])
    eq = np.cumsum(d[np.argsort(ent.values)])
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    yr = pd.Series(d, index=ent).groupby(lambda x: x.year).sum()
    common = yr.index.intersection(bench.index)
    return dict(n=len(d), net=float(d.sum()), dd=dd,
                mar=(float(d.sum()) / years) / dd if dd > 1e-9 else float("nan"),
                top10=float(np.sort(d)[::-1][:10].sum() / d.sum()),
                corr=float(yr[common].corr(bench[common])),
                lb_n=int((ent >= LB_FROM).sum()))


def main():
    arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), **WIN)
    idx = pd.DatetimeIndex(pd.to_datetime(arr["index"]))
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    years = (idx[-1] - idx[0]).days / 365.25
    last = pd.Series(np.asarray(arr["close"], float), index=idx).resample("YE").last()
    bench = ((last / last.shift(1) - 1.0) * 100).dropna()
    bench.index = bench.index.year

    print("%d entry variants x {uncapped, cap %d}. Negative deltas on top10 and corr are the "
          "cap working." % (len(VARIANTS), CAP), flush=True)
    print("  %-14s %7s %7s %7s   %6s %6s %6s   %5s %5s"
          % ("entry variant", "top10", "top10", "delta", "corr", "corr", "delta",
             "dMAR", "dLB"), flush=True)
    print("  %-14s %7s %7s %7s   %6s %6s %6s   %5s %5s"
          % ("", "off", "cap", "", "off", "cap", "", "%", ""), flush=True)

    rows = []
    for name, over in VARIANTS:
        p = dict(CROWN, **over)
        pair = {}
        for tag, cap in (("off", 0), ("cap", CAP)):
            r = run_backtest(STRAT, arrays=arr, params=dict(p, max_hold_bars=cap),
                             cost_pts=COST, return_trades=True)
            tr = (r or {}).get("trades") or []
            pair[tag] = score(tr, idx, bench, years) if len(tr) >= 50 else None
        if not pair["off"] or not pair["cap"]:
            print("  %-14s too few trades, skipped" % name, flush=True)
            continue
        a, b = pair["off"], pair["cap"]
        row = dict(name=name, off=a, cap=b,
                   d_top10=b["top10"] - a["top10"], d_corr=b["corr"] - a["corr"],
                   d_mar_pct=(b["mar"] - a["mar"]) / abs(a["mar"]) * 100 if a["mar"] else float("nan"),
                   d_lb=b["lb_n"] - a["lb_n"])
        rows.append(row)
        print("  %-14s %6.1f%% %6.1f%% %+6.1f%%   %+5.2f %+5.2f %+6.2f   %+5.1f %+5d"
              % (name, a["top10"] * 100, b["top10"] * 100, row["d_top10"] * 100,
                 a["corr"], b["corr"], row["d_corr"], row["d_mar_pct"], row["d_lb"]),
              flush=True)

    n = len(rows)
    f_top = sum(1 for r in rows if r["d_top10"] < 0) / n
    f_corr = sum(1 for r in rows if r["d_corr"] < 0) / n
    med_mar = float(np.median([r["d_mar_pct"] for r in rows]))
    f_lb = sum(1 for r in rows if r["d_lb"] > 0) / n
    checks = [("lowers concentration in >=80%", f_top >= 0.80, "%.0f%%" % (f_top * 100)),
              ("lowers index correlation in >=70%", f_corr >= 0.70, "%.0f%%" % (f_corr * 100)),
              ("median MAR cost <=15%", med_mar >= -15.0, "%+.1f%%" % med_mar),
              ("raises held-out sample in >=70%", f_lb >= 0.70, "%.0f%%" % (f_lb * 100))]
    print("\nPRE-REGISTERED VERDICT over %d entry variants:" % n)
    for label, ok, val in checks:
        print("   %-36s %-8s %s" % (label, val, "PASS" if ok else "FAIL"))
    print("\n%s" % ("THE CAP IS A GENERAL MECHANISM ON NQ - it is not fitted to the crown's entry."
                    if all(ok for _, ok, _ in checks) else
                    "THE CAP IS NOT GENERAL - it does not do on other entries what it does on "
                    "the crown's, so it is a fitted knob and must be labelled as one."))
    json.dump(rows, io.open(os.path.join(SCR, "_cap_generality.json"), "w"), indent=1,
              default=float)
    print("SAVED")


if __name__ == "__main__":
    main()
