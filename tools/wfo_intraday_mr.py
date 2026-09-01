"""
WALK-FORWARD OPTIMIZATION — intraday mean-reversion family on 30m / 60m bars (NEW).

Nothing in the library has tested hourly-scale mean reversion (every intraday family
so far was 1m/5m; every mean-reversion family was daily). Same WFO discipline as
tools/wfo_daily_dips.py: greedy grid search on the anchored in-sample of each of 8
folds, chosen config traded on the OOS window, only OOS numbers reported.

Instruments/bars: NQ and ES, 30m and 60m RTH masters (db_noadj_rth, 2010 -> 2025-06-29).
Costs: NQ 0.533 same-day / 0.783 overnight-held; ES 0.363 / 0.613; + 0.25 per roll
seam crossed (house calendar detector, computed on the daily aggregation).

Mechanisms (long-only, trend-filtered; the fade/short side of everything has died):
  RSI-MR : RSI(len) of bar closes < thr, while close > SMA(trend) of bar closes ->
           buy next bar open. Exit: RSI > exit_thr, or hold >= max_bars, or (if
           flat_eod) the session's last bar close.
  BB-MR  : close < lower Bollinger(len, k) with the same trend filter -> buy next
           open; exit when close >= middle band, or max_bars, or flat_eod.
Grids (whole grid, fixed):
  RSI-MR: len {2,3,5} x thr {10,20,30} x trend {100,200,400} x exit_thr {50,70}
          x max_bars {8,24} x flat_eod {True, False}            = 216
  BB-MR : len {10,20} x k {2.0,2.5} x trend {100,200,400} x max_bars {8,24}
          x flat_eod {True, False}                              = 48
A hold that crosses a session boundary carries the real close->open gap; if the
next day is a roll seam, the seam jump is removed and 0.25 pts charged instead.
"""
import os, sys, csv
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("ond", os.path.join(ROOT, "augur_strategies", "ONDRIFT_1_0.py"))
_ond = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ond)
detect_roll_seams = _ond.detect_roll_seams
_sp2 = _ilu.spec_from_file_location("wfd", os.path.join(ROOT, "tools", "wfo_daily_dips.py"))
wfd = _ilu.module_from_spec(_sp2); _sp2.loader.exec_module(wfd)
wilder_rsi, stats, wfo = wfd.wilder_rsi, wfd.stats, wfd.wfo

WIN_FROM, WIN_TO = "2010-06-07", "2025-06-29"
FUT = {"NQ": (20.0, 0.533, 0.783), "ES": (50.0, 0.363, 0.613)}
OUT = os.path.join(ROOT, "tools", "r16_results")

GRIDS = {
    "RSIMR": [dict(len=a, thr=b, trend=c, exit_thr=e, max_bars=m, flat=f)
              for a in (2, 3, 5) for b in (10, 20, 30) for c in (100, 200, 400)
              for e in (50, 70) for m in (8, 24) for f in (True, False)],
    "BBMR": [dict(len=a, k=b, trend=c, max_bars=m, flat=f)
             for a in (10, 20) for b in (2.0, 2.5) for c in (100, 200, 400)
             for m in (8, 24) for f in (True, False)],
}


class IntraTape:
    def __init__(self, sym, tf):
        self.sym, self.tf = sym, tf
        self.mult, self.cost_day, self.cost_on = FUT[sym]
        m = find_master(sym, tf, "rth", "db_noadj_rth")
        R = load_master_arrays(m, date_from=WIN_FROM, date_to=WIN_TO)
        self.o, self.h, self.l, self.c, did = R["open"], R["high"], R["low"], R["close"], R["day_id"]
        self.idx = R["index"]; self.n = len(self.c)
        sess = []; a = 0
        while a < self.n:
            b = a
            while b < self.n and did[b] == did[a]:
                b += 1
            sess.append((a, b)); a = b
        self.sess = sess
        self.bar_day = np.zeros(self.n, int)
        for i, (a, b) in enumerate(sess):
            self.bar_day[a:b] = i
        self.is_last = np.zeros(self.n, bool)
        for a, b in sess:
            self.is_last[b - 1] = True
        do = np.array([self.o[a] for a, b in sess]); dc = np.array([self.c[b - 1] for a, b in sess])
        self.seam_days = set(detect_roll_seams(do, dc, [self.idx[a] for a, b in sess]))
        self.dates = [self.idx[i].date() for i in range(self.n)]
        self.sma = {}
        for L in (100, 200, 400):
            k = np.concatenate([[0.0], np.cumsum(self.c)]); s = np.full(self.n, np.nan)
            for i in range(L - 1, self.n):
                s[i] = (k[i + 1] - k[i + 1 - L]) / L
            self.sma[L] = s
        self.rsi = {L: wilder_rsi(self.c, L) for L in (2, 3, 5)}
        self.bb = {}
        for L in (10, 20):
            ser = pd.Series(self.c)
            mid = ser.rolling(L).mean().values; sd = ser.rolling(L).std(ddof=0).values
            self.bb[L] = (mid, sd)

    def trades(self, mech, p):
        o, c = self.o, self.c; n = self.n; out = []
        trend = self.sma[p["trend"]]
        i = 400; pos = 0; ei = 0
        while i < n - 1:
            if pos == 0:
                sig = False
                if mech == "RSIMR":
                    sig = (c[i] > trend[i]) and (self.rsi[p["len"]][i] < p["thr"])
                else:
                    mid, sd = self.bb[p["len"]]
                    sig = (c[i] > trend[i]) and (c[i] < mid[i] - p["k"] * sd[i])
                if sig and not (self.is_last[i] and p["flat"]):
                    nd = self.bar_day[i + 1]
                    if nd != self.bar_day[i] and nd in self.seam_days:
                        i += 1; continue
                    pos = 1; ei = i + 1
                i += 1; continue
            # in position, evaluate exit on bar i close (i >= ei)
            ex = False
            if mech == "RSIMR":
                ex = self.rsi[p["len"]][i] > p["exit_thr"]
            else:
                mid, sd = self.bb[p["len"]]
                ex = c[i] >= mid[i]
            if (i - ei + 1) >= p["max_bars"]:
                ex = True
            if p["flat"] and self.is_last[i]:
                ex = True
            if ex:
                xi = i + 1 if not (p["flat"] and self.is_last[i]) else i
                exit_px = o[xi] if xi > i else c[i]
                # pnl over the hold with seam handling at day boundaries
                pnl = 0.0; cost = self.cost_day; crossed_night = False
                cur = o[ei]
                for j in range(ei, (xi if xi > i else i + 1)):
                    if j > ei and self.bar_day[j] != self.bar_day[j - 1]:
                        crossed_night = True
                        gap = o[j] - c[j - 1]
                        if self.bar_day[j] in self.seam_days:
                            cost += 0.25
                        else:
                            pnl += gap
                    if j == ei:
                        pnl += (c[j] - o[j]) if j < (xi if xi > i else i + 1) else 0.0
                    else:
                        pnl += c[j] - o[j]
                if xi > i:
                    # exit at next bar's open: add the transition from c[i] to o[xi]
                    if self.bar_day[xi] != self.bar_day[i]:
                        crossed_night = True
                        if self.bar_day[xi] in self.seam_days:
                            cost += 0.25
                        else:
                            pnl += o[xi] - c[i]
                    else:
                        pnl += o[xi] - c[i]
                if crossed_night:
                    cost = max(cost, self.cost_on + (cost - self.cost_day))
                out.append((self.dates[xi], self.dates[ei], (pnl - cost) * self.mult))
                pos = 0; i = xi if xi > i else i + 1
                continue
            i += 1
        return out


def main():
    rows = []; book = []
    for sym in ("NQ", "ES"):
        for tf in ("30m", "60m"):
            tp = IntraTape(sym, tf)
            print(f"loaded {sym} {tf}: {tp.n} bars, {len(tp.seam_days)} seams", flush=True)
            joint = {}
            for mech, grid in GRIDS.items():
                all_tr = {ci: tp.trades(mech, p) for ci, p in enumerate(grid)}
                oos, chosen, is_avg, fold_nets = wfo(all_tr, sorted(set(tp.dates)))
                st = stats([z[1] for z in oos]); pos = sum(1 for f in fold_nets if f > 0)
                oos_avg = (st["net"] / st["n"]) if st["n"] else 0.0
                wfe = (oos_avg / np.mean(is_avg)) if is_avg and np.mean(is_avg) > 0 else 0.0
                rows.append(dict(inst=f"{sym}-{tf}", mech=mech, n=st["n"], net=round(st["net"]),
                                 pf=round(st["pf"], 3), dd=round(st["dd"]), mar=round(st["mar"], 2),
                                 folds_pos=pos, wfe=round(wfe, 2),
                                 cfg_last=str(grid[chosen[-1]]) if chosen and chosen[-1] is not None else ""))
                print(f"{sym}-{tf} {mech:5} OOS n={st['n']:4} net=${st['net']:>10,.0f} PF={st['pf']:.3f} "
                      f"DD=${st['dd']:>9,.0f} MAR={st['mar']:>6.2f} folds+ {pos}/8 WFE {wfe:.2f}", flush=True)
                book.extend(oos)
                for ci, tr in all_tr.items():
                    joint[(mech, ci)] = tr
            oos, chosen, is_avg, fold_nets = wfo(joint, sorted(set(tp.dates)))
            st = stats([z[1] for z in oos]); pos = sum(1 for f in fold_nets if f > 0)
            rows.append(dict(inst=f"{sym}-{tf}", mech="JOINT", n=st["n"], net=round(st["net"]),
                             pf=round(st["pf"], 3), dd=round(st["dd"]), mar=round(st["mar"], 2),
                             folds_pos=pos, wfe=0, cfg_last=str(chosen[-1])))
            print(f"{sym}-{tf} JOINT OOS n={st['n']:4} net=${st['net']:>10,.0f} PF={st['pf']:.3f} "
                  f"DD=${st['dd']:>9,.0f} MAR={st['mar']:>6.2f} folds+ {pos}/8", flush=True)
    book.sort(key=lambda z: z[0]); st = stats([z[1] for z in book])
    print(f"\nPOOLED OOS (all 4 tapes x 2 mechanisms): n={st['n']} net=${st['net']:,.0f} "
          f"PF={st['pf']:.3f} DD=${st['dd']:,.0f} MAR={st['mar']:.2f}")
    rows.append(dict(inst="ALL", mech="POOLED-OOS", n=st["n"], net=round(st["net"]), pf=round(st["pf"], 3),
                     dd=round(st["dd"]), mar=round(st["mar"], 2), folds_pos=-1, wfe=0, cfg_last=""))
    with open(os.path.join(OUT, "wfo_intraday_mr.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("saved tools/r16_results/wfo_intraday_mr.csv")


if __name__ == "__main__":
    main()
