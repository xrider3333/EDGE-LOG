"""
WFO — the Nasdaq dip family with an OVER-SAMPLED in-sample grid (owner: "oversample
the crap out of the IS section ... until you find something that excels at the WF").

Why Nasdaq: in the first WFO pass QQQ was the standout on all four mechanisms
(7-day-low buy OOS MAR 9.19, capitulation 7.88, 2-day dip PF 2.41) and NQ carried
the same edge in PF terms. Prior: bookmark B4 (QQQ dip MAR 7.67 in round 19).

What is bigger here:
- grid ~6x denser per mechanism (lookbacks, thresholds, trend lengths, exits)
- 12 folds instead of 8 (the IS is re-searched 12 times; OOS windows are ~1 year)
- both QQQ ($100k notional, 2 bps) and NQ at constant $100k notional (micros)
- the JOINT search picks mechanism AND parameters per fold
Everything reported is OOS-only. Lockbox never loaded. Window 2010-06-07 -> 2025-06-29.

Grids (whole grid, fixed):
  RSI : len {2,3,4,5} x thr {5,8,10,12,15,20,25,30} x sma {50,100,150,200,250,300}
        x exit {sma3,sma5,sma8,sma10}                                  = 768
  DBL : n {3,4,5,6,7,8,10,12,15} x sma {50,100,150,200,250,300}         = 54
  PB  : ema {5,8,10,15,20,30,50} x sma {50,100,150,200,250,300} x hold {3,5,8,10,15,20} = 252
  CAP : rng_mult {1.0,1.25,1.5,1.75,2.0,2.5} x close_q {0.15,0.2,0.25,0.33,0.4}
        x hold {1,2,3,4,5,8}                                            = 180
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
_sp2 = _ilu.spec_from_file_location("wfb", os.path.join(ROOT, "tools", "wfo_daily_dips_books.py"))
wfb = _ilu.module_from_spec(_sp2); _sp2.loader.exec_module(wfb)
stats = wfd.stats
OUT = os.path.join(ROOT, "tools", "r16_results")
FOLDS = 12

GRIDS = {
    "RSI": [dict(rsi_len=a, thr=b, sma=c, exit=e) for a in (2, 3, 4, 5) for b in (5, 8, 10, 12, 15, 20, 25, 30)
            for c in (50, 100, 150, 200, 250, 300) for e in (3, 5, 8, 10)],
    "DBL": [dict(n=a, sma=c) for a in (3, 4, 5, 6, 7, 8, 10, 12, 15) for c in (50, 100, 150, 200, 250, 300)],
    "PB": [dict(ema=a, sma=c, hold=h) for a in (5, 8, 10, 15, 20, 30, 50) for c in (50, 100, 150, 200, 250, 300)
           for h in (3, 5, 8, 10, 15, 20)],
    "CAP": [dict(rng_mult=a, close_q=b, hold=h) for a in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5)
            for b in (0.15, 0.2, 0.25, 0.33, 0.4) for h in (1, 2, 3, 4, 5, 8)],
}


class FineTape(wfd.Tape):
    def __init__(self, base):
        self.__dict__.update(base.__dict__)
        dc = self.dc
        for L in (50, 300, 3, 8):
            k = np.concatenate([[0.0], np.cumsum(dc)]); s = np.full(self.nd, np.nan)
            for d in range(L - 1, self.nd):
                s[d] = (k[d + 1] - k[d + 1 - L]) / L
            self.sma[L] = s
        for L in (5, 8, 15, 30):
            e = np.full(self.nd, np.nan); e[L - 1] = dc[:L].mean(); kk = 2 / (L + 1)
            for d in range(L, self.nd):
                e[d] = e[d - 1] + kk * (dc[d] - e[d - 1])
            self.ema[L] = e
        self.rsi[5] = wfd.wilder_rsi(dc, 5)


def fold_edges(dates):
    d0 = pd.Timestamp(dates[0]); d1 = pd.Timestamp(dates[-1])
    start = d0 + pd.Timedelta(days=730)
    edges = [start + (d1 - start) * i / FOLDS for i in range(FOLDS + 1)]
    return [(e.date(), edges[i + 1].date()) for i, e in enumerate(edges[:-1])]


def wfo12(all_trades, dates, min_n=40):
    oos = []; chosen = []; fold_nets = []; is_avg = []
    for (a, b) in fold_edges(dates):
        best = None; best_key = None
        for ci, tr in all_trades.items():
            p = [t[2] for t in tr if t[0] < a]
            if len(p) < min_n:
                continue
            st = stats(p)
            if best is None or st["mar"] > best_key:
                best, best_key = ci, st["mar"]
        if best is None:
            fold_nets.append(0.0); chosen.append(None); continue
        tr = all_trades[best]
        seg = [t for t in tr if a <= t[1] < b]
        oos.extend((t[0], t[2]) for t in seg); chosen.append(best)
        fold_nets.append(sum(t[2] for t in seg))
        isp = [t[2] for t in tr if t[0] < a]; is_avg.append(np.mean(isp) if isp else 0.0)
    oos.sort(key=lambda z: z[0])
    return oos, chosen, fold_nets, is_avg


def main():
    wmask = pd.Timestamp(wfd.WIN_FROM).date()
    tapes = [FineTape(wfd.load_etf("QQQ")), FineTape(wfd.load_futures("NQ"))]
    rows = []; legs = {}
    for tp in tapes:
        conv = wfb.const_notional(tp)
        joint = {}
        for mech, grid in GRIDS.items():
            all_tr = {ci: conv([t for t in tp.trades(mech, p) if t[1] >= wmask]) for ci, p in enumerate(grid)}
            oos, chosen, fold_nets, is_avg = wfo12(all_tr, [d for d in tp.dates if d >= wmask])
            st = stats([z[1] for z in oos]); pos = sum(1 for f in fold_nets if f > 0)
            oos_avg = (st["net"] / st["n"]) if st["n"] else 0.0
            wfe = (oos_avg / np.mean(is_avg)) if is_avg and np.mean(is_avg) > 0 else 0.0
            legs[f"{tp.name}/{mech}"] = oos
            rows.append(dict(inst=tp.name, mech=mech, n=st["n"], net=round(st["net"]), pf=round(st["pf"], 3),
                             dd=round(st["dd"]), mar=round(st["mar"], 2), folds_pos=f"{pos}/{FOLDS}",
                             wfe=round(wfe, 2), cfg_last=str(grid[chosen[-1]]) if chosen[-1] is not None else ""))
            print(f"{tp.name:4} {mech:4} OOS n={st['n']:4} net=${st['net']:>10,.0f} PF={st['pf']:.3f} "
                  f"DD=${st['dd']:>9,.0f} MAR={st['mar']:>6.2f} folds+ {pos}/{FOLDS} WFE {wfe:.2f}  "
                  f"last cfg {grid[chosen[-1]] if chosen[-1] is not None else '-'}", flush=True)
            for ci, tr in all_tr.items():
                joint[(mech, ci)] = tr
        oos, chosen, fold_nets, is_avg = wfo12(joint, [d for d in tp.dates if d >= wmask])
        st = stats([z[1] for z in oos]); pos = sum(1 for f in fold_nets if f > 0)
        legs[f"{tp.name}/JOINT"] = oos
        rows.append(dict(inst=tp.name, mech="JOINT", n=st["n"], net=round(st["net"]), pf=round(st["pf"], 3),
                         dd=round(st["dd"]), mar=round(st["mar"], 2), folds_pos=f"{pos}/{FOLDS}", wfe=0,
                         cfg_last=str(chosen[-1])))
        print(f"{tp.name:4} JOINT OOS n={st['n']:4} net=${st['net']:>10,.0f} PF={st['pf']:.3f} "
              f"DD=${st['dd']:>9,.0f} MAR={st['mar']:>6.2f} folds+ {pos}/{FOLDS}", flush=True)

    # pooled books (causal equal risk): QQQ 4 mechs / NQ 4 mechs / both
    for name, keys in (("QQQ 4 mechanisms", [k for k in legs if k.startswith("QQQ/") and "JOINT" not in k]),
                       ("NQ 4 mechanisms (const notional)", [k for k in legs if k.startswith("NQ/") and "JOINT" not in k]),
                       ("QQQ + NQ, 8 legs", [k for k in legs if "JOINT" not in k])):
        ser = wfb.causal_scaled({k: legs[k] for k in keys}); st = stats([z[1] for z in ser])
        y = wfb.yearly(ser); pos = sum(1 for v in y.values() if v > 0)
        g = "PASS" if (st["pf"] >= 1.25 and st["mar"] >= 8 and st["n"] >= 300) else "fail"
        rows.append(dict(inst="BOOK", mech=name, n=st["n"], net=round(st["net"]), pf=round(st["pf"], 3),
                         dd=round(st["dd"]), mar=round(st["mar"], 2), folds_pos=f"{pos}/{len(y)} yrs", wfe=0, cfg_last=g))
        print(f"BOOK {name:34} n={st['n']:4} net=${st['net']:>10,.0f} PF={st['pf']:.3f} DD=${st['dd']:>9,.0f} "
              f"MAR={st['mar']:>6.2f} yrs+ {pos}/{len(y)}  {g}", flush=True)
    with open(os.path.join(OUT, "wfo_nasdaq_fine.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, "wfo_nasdaq_fine_oos.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["leg", "date", "pnl"])
        for k, ser in legs.items():
            for dt, v in ser:
                w.writerow([k, dt.isoformat(), round(v, 2)])
    print("saved tools/r16_results/wfo_nasdaq_fine.csv")


if __name__ == "__main__":
    main()
