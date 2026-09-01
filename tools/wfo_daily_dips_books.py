"""
Companion to wfo_daily_dips.py: re-derives every (instrument, mechanism) walk-forward
OOS series with tags, then scores the pooled BOOKS honestly.

Two things the first pass could not answer:
1. Equal-NOTIONAL pooling let the futures legs (1 contract = a notional that grew
   5x over the window) dominate the drawdown. Here every leg is sized at a
   constant $100,000 notional - futures included (fractional contracts; in live
   trading MNQ/MES micros at $2/$5 per point make this realistic) - and then
   pooled at CAUSAL equal risk (each trade scaled by the leg's OWN prior-trade
   volatility only).
2. Which pooled books clear the bar. Reported, in this order and with the
   selection honesty stated on each:
     ALL      - every instrument x mechanism (36 series). No selection at all.
     EQIDX    - the equity-index ETFs (QQQ, SPY, IWM, EEM) - a definable group.
     ETF      - all 7 ETFs.  FUT - NQ + ES.
     QQQ      - QQQ's 4 mechanisms only. POST-HOC (QQQ was picked after seeing
                the WFO table; its prior is bookmark B4, MAR 7.67 in r19).
Window 2010-06-07 -> 2025-06-29, OOS only, lockbox never loaded.
"""
import os, sys, csv
from collections import defaultdict
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("wfd", os.path.join(ROOT, "tools", "wfo_daily_dips.py"))
wfd = _ilu.module_from_spec(_sp); _sp.loader.exec_module(wfd)
stats, wfo, GRIDS = wfd.stats, wfd.wfo, wfd.GRIDS
OUT = os.path.join(ROOT, "tools", "r16_results")
NOTIONAL = 100_000.0


def const_notional(tape):
    """re-express a futures tape's trades at $100k notional (fractional contracts)."""
    if tape.etf:
        return lambda tr: tr
    mult = tape.mult
    dates = tape.dates; do = tape.do
    d2i = {d: i for i, d in enumerate(dates)}

    def conv(tr):
        out = []
        for ex_d, en_d, pnl in tr:
            px = do[d2i[en_d]]
            contracts = NOTIONAL / (px * mult)
            out.append((ex_d, en_d, pnl * contracts))
        return out
    return conv


def causal_scaled(series_by_leg):
    hist = defaultdict(list)
    events = sorted(((dt, k, v) for k, ser in series_by_leg.items() for dt, v in ser), key=lambda z: z[0])
    out = []
    for dt, k, v in events:
        vols = [np.std(h) for h in hist.values() if len(h) >= 20]
        own = np.std(hist[k]) if len(hist[k]) >= 20 else None
        w = (float(np.median(vols)) / own) if (own and own > 0 and vols) else 1.0
        out.append((dt, v * w)); hist[k].append(v)
    return out


def yearly(series):
    y = defaultdict(float)
    for dt, v in series:
        y[dt.year] += v
    return y


def main():
    tapes = [wfd.load_futures("NQ"), wfd.load_futures("ES")] + [wfd.load_etf(t) for t in
             ("GLD", "TLT", "IWM", "QQQ", "SPY", "EEM", "USO")]
    wmask = pd.Timestamp(wfd.WIN_FROM).date()
    oos_by_leg = {}
    for tp in tapes:
        conv = const_notional(tp)
        for mech, grid in GRIDS.items():
            all_tr = {ci: conv([t for t in tp.trades(mech, p) if t[1] >= wmask]) for ci, p in enumerate(grid)}
            oos, chosen, is_avg, fold_nets = wfo(all_tr, [d for d in tp.dates if d >= wmask])
            oos_by_leg[f"{tp.name}/{mech}"] = oos
            st = stats([z[1] for z in oos])
            print(f"{tp.name:4} {mech:4} const-notional OOS n={st['n']:4} net=${st['net']:>9,.0f} "
                  f"PF={st['pf']:.3f} DD=${st['dd']:>8,.0f} MAR={st['mar']:>6.2f}", flush=True)
    with open(os.path.join(OUT, "wfo_daily_dips_oos_tagged.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["leg", "date", "pnl"])
        for k, ser in oos_by_leg.items():
            for dt, v in ser:
                w.writerow([k, dt.isoformat(), round(v, 2)])

    groups = {
        "ALL 36 series (no selection)": list(oos_by_leg),
        "EQIDX (QQQ,SPY,IWM,EEM)": [k for k in oos_by_leg if k.split("/")[0] in ("QQQ", "SPY", "IWM", "EEM")],
        "ETF (7)": [k for k in oos_by_leg if k.split("/")[0] not in ("NQ", "ES")],
        "FUT (NQ,ES) const-notional": [k for k in oos_by_leg if k.split("/")[0] in ("NQ", "ES")],
        "QQQ only (POST-HOC)": [k for k in oos_by_leg if k.startswith("QQQ/")],
        "NQ+QQQ (the Nasdaq pair)": [k for k in oos_by_leg if k.split("/")[0] in ("NQ", "QQQ")],
    }
    rows = []
    print(f"\n{'book':34}{'n':>6}{'net$':>12}{'PF':>7}{'DD$':>10}{'MAR':>7}{'yrs+':>6}{'post21':>8}  gate")
    for name, legs in groups.items():
        ser = causal_scaled({k: oos_by_leg[k] for k in legs})
        st = stats([z[1] for z in ser])
        y = yearly(ser); pos = sum(1 for v in y.values() if v > 0)
        post = 100 * sum(v for yy, v in y.items() if yy >= 2022) / st["net"] if st["net"] > 0 else 0
        g = "PASS" if (st["pf"] >= 1.25 and st["mar"] >= 8 and st["n"] >= 300) else "fail"
        rows.append(dict(book=name, n=st["n"], net=round(st["net"]), pf=round(st["pf"], 3),
                         dd=round(st["dd"]), mar=round(st["mar"], 2), yrs_pos=f"{pos}/{len(y)}",
                         post2021=round(post), gate=g))
        print(f"{name:34}{st['n']:>6}{st['net']:>12,.0f}{st['pf']:>7.3f}{st['dd']:>10,.0f}{st['mar']:>7.2f}"
              f"{pos:>3}/{len(y):<2}{post:>7.0f}%  {g}")
    with open(os.path.join(OUT, "wfo_daily_dips_books.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("saved tools/r16_results/wfo_daily_dips_books.csv")


if __name__ == "__main__":
    main()
