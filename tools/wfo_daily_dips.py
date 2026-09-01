"""
WALK-FORWARD OPTIMIZATION of the dip-buy family across instruments.

Owner 2026-08-25: "oversample the crap out of the IS section if you have to until you
find something that excels at the WF section. idk what time frame or instrument."

This is the honest way to do that: for each of 8 chronological out-of-sample (OOS)
windows, search the WHOLE parameter grid on everything BEFORE that window (anchored
in-sample), pick the best config by MAR (n >= 40), then trade THAT config on the OOS
window. Concatenate the 8 OOS windows -> the walk-forward equity. Only OOS numbers
are reported as results. The IS search is allowed to be as greedy as it likes.

Instruments: NQ and ES (daily bars from the 5m RTH masters, house roll detector,
futures costs), plus GLD, TLT, IWM, QQQ, SPY, EEM, USO daily via Yahoo
(total-return, $100k notional, 2 bps/RT).

Mechanisms and grids (the whole grid, fixed here):
  RSI  : rsi_len {2,3,4} x thr {5,10,15,20,25} x sma {100,150,200,250} x exit {5,10}
  DBL  : n {5,7,10} x sma {100,150,200,250}
  PB   : ema {10,20,50} x sma {100,150,200,250} x hold {5,10,20}
  CAP  : rng_mult {1.25,1.5,2.0} x close_q {0.2,0.25,0.33} x hold {2,3,5}
All long-only (the short mirrors died in triage, and the pooled book's short cells
added nothing). Entry next open after the close signal; exit next open after the
exit signal; no stop (the dip edge lives in the hold).

Outputs per (instrument, mechanism): OOS n / net / PF / DD / MAR, folds positive,
walk-forward efficiency (OOS avg trade / IS avg trade of the chosen configs).
Also the per-instrument "best mechanism chosen per fold" variant, and the pooled
WF book of all (instrument, mechanism) OOS series.
Window 2010-06-07 -> 2025-06-29. Lockbox never loaded.
"""
import os, sys, csv, itertools
from collections import defaultdict

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

WIN_FROM, WIN_TO = "2010-06-07", "2025-06-29"
FOLDS = 8
NOTIONAL, ETF_COST = 100_000.0, 20.0
FUT = {"NQ": (20.0, 0.533, 0.783), "ES": (50.0, 0.363, 0.613)}
OUT = os.path.join(ROOT, "tools", "r16_results")


def wilder_rsi(x, per):
    d = np.diff(x, prepend=x[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = np.zeros_like(x); ad = np.zeros_like(x)
    au[per] = up[1:per + 1].mean(); ad[per] = dn[1:per + 1].mean()
    for i in range(per + 1, len(x)):
        au[i] = (au[i - 1] * (per - 1) + up[i]) / per
        ad[i] = (ad[i - 1] * (per - 1) + dn[i]) / per
    rs = np.divide(au, ad, out=np.full_like(x, np.inf), where=ad > 1e-12)
    return 100 - 100 / (1 + rs)


class Tape:
    def __init__(self, name, do, dh, dl, dc, dates, seams, mult, cost_day, cost_on, etf):
        self.name = name; self.do, self.dh, self.dl, self.dc = do, dh, dl, dc
        self.dates = dates; self.seams = seams; self.nd = len(dc)
        self.mult, self.cost_day, self.cost_on, self.etf = mult, cost_day, cost_on, etf
        self.sma = {}; self.ema = {}; self.rsi = {}
        for L in (100, 150, 200, 250):
            s = np.full(self.nd, np.nan); k = np.concatenate([[0.0], np.cumsum(dc)])
            for d in range(L - 1, self.nd):
                s[d] = (k[d + 1] - k[d + 1 - L]) / L
            self.sma[L] = s
        for L in (5, 10):
            s = np.full(self.nd, np.nan); k = np.concatenate([[0.0], np.cumsum(dc)])
            for d in range(L - 1, self.nd):
                s[d] = (k[d + 1] - k[d + 1 - L]) / L
            self.sma[L] = s
        for L in (10, 20, 50):
            e = np.full(self.nd, np.nan); e[L - 1] = dc[:L].mean(); kk = 2 / (L + 1)
            for d in range(L, self.nd):
                e[d] = e[d - 1] + kk * (dc[d] - e[d - 1])
            self.ema[L] = e
        for L in (2, 3, 4):
            self.rsi[L] = wilder_rsi(dc, L)
        self.atr20 = np.full(self.nd, np.nan)
        for d in range(20, self.nd):
            self.atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()

    def trades(self, mech, p):
        """returns list of (exit_date, entry_date, pnl_dollars)"""
        do, dh, dl, dc = self.do, self.dh, self.dl, self.dc
        nd = self.nd; out = []; pos = 0; de = 0; d = 260
        sma = self.sma[p.get("sma", 200)] if mech != "CAP" else None
        while d < nd - 1:
            if pos == 0:
                s = 0
                if mech == "RSI":
                    if dc[d] > sma[d] and self.rsi[p["rsi_len"]][d] < p["thr"]: s = 1
                elif mech == "DBL":
                    n = p["n"]
                    if d >= n and dc[d] > sma[d] and dc[d] == dc[d - n + 1:d + 1].min(): s = 1
                elif mech == "PB":
                    e = self.ema[p["ema"]]
                    if dc[d] > sma[d] and dl[d] <= e[d] and dc[d - 1] > e[d - 1]: s = 1
                elif mech == "CAP":
                    rng = dh[d] - dl[d]; atr = self.atr20[d]
                    if (dc[d] < do[d] and rng > 0 and not np.isnan(atr) and rng >= p["rng_mult"] * atr
                            and (dc[d] - dl[d]) / rng <= p["close_q"]): s = 1
                if s and not ((d + 1) in self.seams):
                    pos, de = 1, d + 1; d += 1; continue
            else:
                ex = False
                if mech == "RSI": ex = dc[d] > self.sma[p["exit"]][d]
                elif mech == "DBL": n = p["n"]; ex = dc[d] == dc[d - n + 1:d + 1].max()
                elif mech == "PB": ex = (dc[d] > dh[de - 1]) or (d - de >= p["hold"])
                elif mech == "CAP": ex = (d - de >= p["hold"])
                if d >= de and ex and not ((d + 1) in self.seams):
                    raw = dc[de] - do[de]
                    cost = self.cost_day if (d + 1) == de else self.cost_on
                    for dd_ in range(de + 1, d + 2):
                        g = do[dd_] - dc[dd_ - 1]
                        if dd_ in self.seams:
                            cost += 0.25
                        else:
                            raw += g
                        if dd_ <= d:
                            raw += dc[dd_] - do[dd_]
                    if self.etf:
                        sh = NOTIONAL / do[de]
                        out.append((self.dates[d + 1], self.dates[de], (raw * sh) - ETF_COST))
                    else:
                        out.append((self.dates[d + 1], self.dates[de], (raw - cost) * self.mult))
                    pos = 0
            d += 1
        return out


GRIDS = {
    "RSI": [dict(rsi_len=a, thr=b, sma=c, exit=e) for a in (2, 3, 4) for b in (5, 10, 15, 20, 25)
            for c in (100, 150, 200, 250) for e in (5, 10)],
    "DBL": [dict(n=a, sma=c) for a in (5, 7, 10) for c in (100, 150, 200, 250)],
    "PB": [dict(ema=a, sma=c, hold=h) for a in (10, 20, 50) for c in (100, 150, 200, 250) for h in (5, 10, 20)],
    "CAP": [dict(rng_mult=a, close_q=b, hold=h) for a in (1.25, 1.5, 2.0) for b in (0.2, 0.25, 0.33) for h in (2, 3, 5)],
}


def stats(p):
    p = np.asarray(p, float)
    if len(p) == 0:
        return dict(n=0, net=0, pf=0, dd=0, mar=0)
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum())
    return dict(n=len(p), net=net, pf=(gw / gl if gl > 0 else 99.0), dd=-dd,
                mar=(net / -dd if dd < 0 else 99.0))


def fold_edges(dates):
    d0 = pd.Timestamp(dates[0]); d1 = pd.Timestamp(dates[-1])
    # first OOS window starts after 2 years of warm-up training
    start = d0 + pd.Timedelta(days=730)
    edges = [start + (d1 - start) * i / FOLDS for i in range(FOLDS + 1)]
    return [(e.date(), edges[i + 1].date()) for i, e in enumerate(edges[:-1])]


def wfo(all_trades, dates, objective="mar", min_n=40):
    """all_trades: {cfg_idx: [(exit_date, entry_date, pnl)]}.  Returns OOS series,
    chosen cfg per fold, and IS avg-trade of chosen cfgs (for WFE)."""
    edges = fold_edges(dates)
    oos = []; chosen = []; is_avg = []; fold_nets = []
    for (a, b) in edges:
        best = None; best_key = None
        for ci, tr in all_trades.items():
            p = [t[2] for t in tr if t[0] < a]           # exit strictly before OOS start
            if len(p) < min_n:
                continue
            st = stats(p)
            key = st[objective] if objective == "mar" else st["pf"]
            if best is None or key > best_key:
                best, best_key = ci, key
        if best is None:
            fold_nets.append(0.0); chosen.append(None); continue
        tr = all_trades[best]
        seg = [t for t in tr if a <= t[1] < b]           # entered inside the OOS window
        oos.extend((t[0], t[2]) for t in seg)
        chosen.append(best)
        isp = [t[2] for t in tr if t[0] < a]
        is_avg.append(np.mean(isp) if isp else 0.0)
        fold_nets.append(sum(t[2] for t in seg))
    oos.sort(key=lambda z: z[0])
    return oos, chosen, is_avg, fold_nets


def load_futures(sym):
    mult, cd, co = FUT[sym]
    m5 = find_master(sym, "5m", "rth", "db_noadj_rth")
    R = load_master_arrays(m5, date_from=WIN_FROM, date_to=WIN_TO)
    o5, h5, l5, c5, did5 = R["open"], R["high"], R["low"], R["close"], R["day_id"]
    idx5 = R["index"]
    sess = []; a = 0; n5 = len(c5)
    while a < n5:
        b = a
        while b < n5 and did5[b] == did5[a]:
            b += 1
        sess.append((a, b)); a = b
    do = np.array([o5[x] for x, y in sess]); dh = np.array([h5[x:y].max() for x, y in sess])
    dl = np.array([l5[x:y].min() for x, y in sess]); dc = np.array([c5[y - 1] for x, y in sess])
    dates = [idx5[x].date() for x, y in sess]
    seams = set(detect_roll_seams(do, dc, [idx5[x] for x, y in sess]))
    return Tape(sym, do, dh, dl, dc, dates, seams, mult, cd, co, etf=False)


def load_etf(tk):
    import yfinance as yf
    df = yf.download(tk, start="2009-01-01", end="2025-06-30", interval="1d",
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    do, dh, dl, dc = (df[c].values.astype(float) for c in ["Open", "High", "Low", "Close"])
    dates = [d.date() for d in df.index]
    return Tape(tk, do, dh, dl, dc, dates, set(), 1.0, 0.0, 0.0, etf=True)


def main():
    tapes = [load_futures("NQ"), load_futures("ES")] + [load_etf(t) for t in
             ("GLD", "TLT", "IWM", "QQQ", "SPY", "EEM", "USO")]
    rows = []; book_oos = []; per_inst_best = {}
    for tp in tapes:
        wmask = pd.Timestamp(WIN_FROM).date()
        per_mech_trades = {}
        for mech, grid in GRIDS.items():
            all_tr = {}
            for ci, p in enumerate(grid):
                tr = [t for t in tp.trades(mech, p) if t[1] >= wmask]
                all_tr[ci] = tr
            per_mech_trades[mech] = all_tr
            oos, chosen, is_avg, fold_nets = wfo(all_tr, [d for d in tp.dates if d >= wmask])
            st = stats([z[1] for z in oos])
            pos = sum(1 for f in fold_nets if f > 0)
            oos_avg = (st["net"] / st["n"]) if st["n"] else 0.0
            wfe = (oos_avg / np.mean(is_avg)) if is_avg and np.mean(is_avg) > 0 else 0.0
            rows.append(dict(inst=tp.name, mech=mech, n=st["n"], net=round(st["net"]),
                             pf=round(st["pf"], 3), dd=round(st["dd"]), mar=round(st["mar"], 2),
                             folds_pos=pos, wfe=round(wfe, 2),
                             cfg_last=str(grid[chosen[-1]]) if chosen and chosen[-1] is not None else ""))
            book_oos.extend(oos)
            print(f"{tp.name:4} {mech:4} OOS n={st['n']:4} net=${st['net']:>10,.0f} PF={st['pf']:.3f} "
                  f"DD=${st['dd']:>9,.0f} MAR={st['mar']:>6.2f} folds+ {pos}/8 WFE {wfe:.2f}", flush=True)
        # per-instrument: choose the best (mechanism, cfg) jointly on each fold's IS
        joint = {}
        for mech, all_tr in per_mech_trades.items():
            for ci, tr in all_tr.items():
                joint[(mech, ci)] = tr
        oos, chosen, is_avg, fold_nets = wfo(joint, [d for d in tp.dates if d >= wmask])
        st = stats([z[1] for z in oos]); pos = sum(1 for f in fold_nets if f > 0)
        oos_avg = (st["net"] / st["n"]) if st["n"] else 0.0
        wfe = (oos_avg / np.mean(is_avg)) if is_avg and np.mean(is_avg) > 0 else 0.0
        rows.append(dict(inst=tp.name, mech="JOINT", n=st["n"], net=round(st["net"]), pf=round(st["pf"], 3),
                         dd=round(st["dd"]), mar=round(st["mar"], 2), folds_pos=pos, wfe=round(wfe, 2),
                         cfg_last=str(chosen[-1]) if chosen and chosen[-1] is not None else ""))
        print(f"{tp.name:4} JOINT OOS n={st['n']:4} net=${st['net']:>10,.0f} PF={st['pf']:.3f} "
              f"DD=${st['dd']:>9,.0f} MAR={st['mar']:>6.2f} folds+ {pos}/8 WFE {wfe:.2f}", flush=True)

    # pooled WF book of all (instrument, mechanism) OOS series, causal equal-risk
    book_oos.sort(key=lambda z: z[0])
    st = stats([z[1] for z in book_oos])
    print(f"\nPOOLED WF BOOK (all instruments x mechanisms, OOS only, equal notional): "
          f"n={st['n']} net=${st['net']:,.0f} PF={st['pf']:.3f} DD=${st['dd']:,.0f} MAR={st['mar']:.2f}")
    rows.append(dict(inst="ALL", mech="POOLED-OOS", n=st["n"], net=round(st["net"]), pf=round(st["pf"], 3),
                     dd=round(st["dd"]), mar=round(st["mar"], 2), folds_pos=-1, wfe=0, cfg_last=""))
    with open(os.path.join(OUT, "wfo_daily_dips.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, "wfo_daily_dips_book_oos.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "pnl"]); w.writerows([(z[0].isoformat(), z[1]) for z in book_oos])
    print("saved tools/r16_results/wfo_daily_dips.csv")


if __name__ == "__main__":
    main()
