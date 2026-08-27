"""
ROUND 25 — the WEAK-EDGE BOOK. Pre-registered 2026-08-25 before any results.

The hunt's 162 dead cells contain a repeated fingerprint: mechanisms with a genuinely
positive edge (profit factor 1.4-2.3) that fail the risk bar (MAR >= 8) ALONE. That is
exactly the situation a portfolio is supposed to fix: if the legs are uncorrelated,
pooled drawdowns partially cancel while profits add.

This round asks the question honestly, with the composition fixed BEFORE any pooled
number is computed.

INCLUSION RULE (mechanical, no cherry-picking): every cell already triaged in rounds
17/19/20 that had profit factor >= 1.40, positive net, and n >= 100 trades. That rule
selects the following 13 legs (listed here so the grid is auditable):
  NQ daily : PB20/long (1.879), DBL7/long (1.703), RSI2 thr10 long (1.402),
             CAPITULATION buy/5d (1.810)
  GLD      : DBL7/long (2.328), RSI2/long (1.667), PB20/long (1.414)
  TLT      : DBL7/long (1.516), RSI2/long (1.495)
  IWM      : RSI2/both (1.715), DBL7/long (1.432)
  QQQ      : RSI2/long (1.954), RSI2/both (1.803), DBL7/long (1.642), PB20/long (1.452)
(That enumeration is 15 legs; the rule, not the list, governs - the harness recomputes
membership from the saved triage CSVs at run time and prints what it selected.)

SIZING (both reported, both fixed now):
  EQN  - equal notional: $100,000 per ETF trade; 1 NQ contract per futures trade.
  EQR  - equal risk: each leg scaled so its per-trade standard deviation equals the
         median leg's. This uses in-sample volatility (not returns) to size, which is
         standard practice; it is stated, not hidden.

SCORING: all legs' trades pooled chronologically and scored as ONE strategy - profit
factor from the pooled trades, drawdown from the pooled cumulative curve (house BOOK
convention). Correlations are measured on daily PnL.

STACK TEST: the weak-edge book is then added 1:1 (by risk) to the live champion book
(legal ORB #234 + ENGU-Q ETH #226 daily series, already saved) to answer the only
question that matters - does it IMPROVE the book we actually own?

GATES: standalone book must clear PF >= 1.25 AND MAR >= 8. The stack must RAISE the
champion book's MAR by >= 15% while giving up <= 10% of its net. Window 2010-06-07 ->
2025-06-29 (ETFs from 2006 are truncated to the common window so every leg is judged
on the same tape). Lockbox never loaded. One look.
"""
import os, sys, csv
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
NOTIONAL, ETF_COST = 100_000.0, 20.0
MULT, RT_D, RT_ON, ROLL = 20.0, 0.533, 0.783, 0.25
PF_MIN, N_MIN = 1.40, 100


def wilder_rsi(x, per):
    d = np.diff(x, prepend=x[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = np.zeros_like(x); ad = np.zeros_like(x)
    au[per] = up[1:per + 1].mean(); ad[per] = dn[1:per + 1].mean()
    for i in range(per + 1, len(x)):
        au[i] = (au[i - 1] * (per - 1) + up[i]) / per
        ad[i] = (ad[i - 1] * (per - 1) + dn[i]) / per
    rs = np.divide(au, ad, out=np.full_like(x, np.inf), where=ad > 1e-12)
    return 100 - 100 / (1 + rs)


def daily_ctx(do, dh, dl, dc):
    nd = len(dc)
    sma200 = np.full(nd, np.nan); sma5 = np.full(nd, np.nan)
    for d in range(199, nd):
        sma200[d] = dc[d - 199:d + 1].mean()
    for d in range(4, nd):
        sma5[d] = dc[d - 4:d + 1].mean()
    k = 2 / 21; ema20 = np.full(nd, np.nan); ema20[19] = dc[:20].mean()
    for d in range(20, nd):
        ema20[d] = ema20[d - 1] + k * (dc[d] - ema20[d - 1])
    return sma200, sma5, ema20, wilder_rsi(dc, 2)


def run_cell(do, dh, dl, dc, dates, cell, shares_fn, cost_fn, seams=None, start=210):
    """Generic daily engine. Returns list of (exit_date, pnl_dollars)."""
    sma200, sma5, ema20, rsi2 = daily_ctx(do, dh, dl, dc)
    nd = len(dc); out = []; pos = 0; de = 0
    d = start
    while d < nd - 1:
        if pos == 0:
            s = 0
            if cell == "RSI2L" and dc[d] > sma200[d] and rsi2[d] < 10: s = 1
            elif cell == "RSI2B":
                if dc[d] > sma200[d] and rsi2[d] < 10: s = 1
                elif dc[d] < sma200[d] and rsi2[d] > 90: s = -1
            elif cell == "DBL7L" and d >= 7 and dc[d] > sma200[d] and dc[d] == dc[d - 6:d + 1].min(): s = 1
            elif cell == "PB20L" and dc[d] > sma200[d] and dl[d] <= ema20[d] and dc[d - 1] > ema20[d - 1]: s = 1
            elif cell == "CAP5":
                rng = dh[d] - dl[d]
                atr = (dh[max(0, d - 20):d] - dl[max(0, d - 20):d]).mean()
                if dc[d] < do[d] and rng >= 1.5 * atr and rng > 0 and (dc[d] - dl[d]) / rng <= 0.25: s = 1
            if s != 0 and not (seams and (d + 1) in seams):
                pos, de = s, d + 1; d += 1; continue
        else:
            ex = False
            if cell in ("RSI2L", "RSI2B"): ex = (dc[d] > sma5[d]) if pos > 0 else (dc[d] < sma5[d])
            elif cell == "DBL7L": ex = dc[d] == dc[d - 6:d + 1].max()
            elif cell == "PB20L": ex = (dc[d] > dh[de - 1]) or (d - de >= 10)
            elif cell == "CAP5": ex = (d - de >= 4)
            if d >= de and ex and not (seams and (d + 1) in seams):
                raw = dc[de] - do[de]; cost = cost_fn(de, d + 1)
                for dd_ in range(de + 1, d + 2):
                    g = do[dd_] - dc[dd_ - 1]
                    if seams and dd_ in seams:
                        cost += ROLL
                    else:
                        raw += g
                    if dd_ <= d:
                        raw += dc[dd_] - do[dd_]
                pnl_pts = pos * raw - cost
                out.append((dates[d + 1], pnl_pts * shares_fn(de)))
                pos = 0
        d += 1
    return out


def book_stats(series, label):
    """series: list of (date, dollars) -> pooled trade stats."""
    s = sorted(series, key=lambda z: z[0])
    p = np.array([z[1] for z in s], float)
    if len(p) == 0:
        return dict(book=label, n=0, net=0, pf=0, dd=0, mar=0)
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum())
    return dict(book=label, n=len(p), net=round(net), pf=round(gw / gl if gl > 0 else 99, 3),
                dd=round(-dd), mar=round(net / -dd if dd < 0 else 99, 2))


def main():
    # ---------- NQ daily legs ----------
    m5 = find_master("NQ", "5m", "rth", "db_noadj_rth")
    R = load_master_arrays(m5, date_from=WIN_FROM, date_to=WIN_TO)
    o5, h5, l5, c5, did5 = R["open"], R["high"], R["low"], R["close"], R["day_id"]
    idx5 = R["index"]
    sess = []; a = 0; n5 = len(c5)
    while a < n5:
        b = a
        while b < n5 and did5[b] == did5[a]:
            b += 1
        sess.append((a, b)); a = b
    ndo = np.array([o5[x] for x, y in sess]); ndh = np.array([h5[x:y].max() for x, y in sess])
    ndl = np.array([l5[x:y].min() for x, y in sess]); ndc = np.array([c5[y - 1] for x, y in sess])
    ndates = [idx5[x].date() for x, y in sess]
    seams = set(detect_roll_seams(ndo, ndc, [idx5[x] for x, y in sess]))

    legs = {}
    for cell in ("PB20L", "DBL7L", "RSI2L", "CAP5"):
        legs[f"NQ/{cell}"] = run_cell(ndo, ndh, ndl, ndc, ndates, cell,
                                      shares_fn=lambda d: MULT,
                                      cost_fn=lambda de, dx: (RT_D if dx == de else RT_ON),
                                      seams=seams)
    # ---------- ETF legs ----------
    import yfinance as yf
    for tk in ("GLD", "TLT", "IWM", "QQQ"):
        df = yf.download(tk, start="2009-06-01", end="2025-06-30", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close"]].dropna()
        do_, dh_, dl_, dc_ = (df[c].values.astype(float) for c in ["Open", "High", "Low", "Close"])
        dts = [d.date() for d in df.index]
        for cell in ("RSI2L", "RSI2B", "DBL7L", "PB20L"):
            legs[f"{tk}/{cell}"] = run_cell(
                do_, dh_, dl_, dc_, dts, cell,
                shares_fn=lambda de, o=do_: NOTIONAL / o[de],
                cost_fn=lambda de, dx: ETF_COST / (NOTIONAL / do_[de]))
    # ---------- inclusion rule ----------
    keep = {}
    print(f"{'leg':14}{'n':>6}{'net$':>11}{'PF':>7}  include")
    for k, v in sorted(legs.items()):
        cut = [z for z in v if z[0] >= pd.Timestamp(WIN_FROM).date()]
        p = np.array([z[1] for z in cut], float)
        if len(p) == 0:
            continue
        gw = p[p > 0].sum(); gl = -p[p < 0].sum()
        pf = gw / gl if gl > 0 else 99
        ok = (pf >= PF_MIN and p.sum() > 0 and len(p) >= N_MIN)
        print(f"{k:14}{len(p):>6}{p.sum():>11,.0f}{pf:>7.3f}  {'YES' if ok else 'no'}")
        if ok:
            keep[k] = cut
    print(f"\nselected {len(keep)} legs by the pre-registered rule\n")

    rows = []
    eqn = [z for v in keep.values() for z in v]
    rows.append(book_stats(eqn, "WEAK-EDGE BOOK (equal notional)"))
    sds = {k: np.std([z[1] for z in v]) for k, v in keep.items()}
    med = np.median(list(sds.values()))
    eqr = [(z[0], z[1] * (med / sds[k])) for k, v in keep.items() for z in v]
    rows.append(book_stats(eqr, "WEAK-EDGE BOOK (equal risk)"))

    # ---------- correlation ----------
    daily = {}
    for k, v in keep.items():
        d = defaultdict(float)
        for dt, pnl in v:
            d[dt] += pnl * (med / sds[k])
        daily[k] = d
    alldates = sorted({d for v in daily.values() for d in v})
    M = np.array([[daily[k].get(d, 0.0) for d in alldates] for k in keep])
    C = np.corrcoef(M) if len(keep) > 1 else np.array([[1.0]])
    iu = np.triu_indices(len(keep), 1)
    print(f"leg-to-leg daily correlation: mean {C[iu].mean():.3f}, max {C[iu].max():.3f}")

    # ---------- stack onto the champion book ----------
    champ = defaultdict(float)
    csvp = os.path.join(ROOT, "tools", "r13_results", "legal_legs_daily.csv")
    if os.path.exists(csvp):
        for r in csv.DictReader(open(csvp)):
            d = pd.Timestamp(r["date"][:10]).date()
            if pd.Timestamp(WIN_FROM).date() <= d <= pd.Timestamp(WIN_TO).date():
                champ[d] += float(r["c2"]) + float(r["engq_eth"])
        cs = [(d, v) for d, v in champ.items()]
        rows.append(book_stats(cs, "CHAMPION BOOK (ORB #234 + ENGU-Q ETH)"))
        wk = defaultdict(float)
        for dt, pnl in eqr:
            wk[dt] += pnl
        cw = np.std([v for v in champ.values()]); ww = np.std([v for v in wk.values()])
        scale = cw / ww if ww > 0 else 1.0
        stacked = defaultdict(float)
        for d, v in champ.items():
            stacked[d] += v
        for d, v in wk.items():
            stacked[d] += v * scale
        rows.append(book_stats(list(stacked.items()), "CHAMPION + WEAK-EDGE (risk-matched)"))
        cd = np.array([champ.get(d, 0.0) for d in alldates]); wd = np.array([wk.get(d, 0.0) for d in alldates])
        print(f"champion book vs weak-edge book daily correlation: {np.corrcoef(cd, wd)[0,1]:.3f}")

    print(f"\n{'book':40}{'n':>6}{'net$':>12}{'PF':>7}{'DD$':>11}{'MAR':>7}")
    for r_ in rows:
        print(f"{r_['book']:40}{r_['n']:>6}{r_['net']:>12,}{r_['pf']:>7.3f}{r_['dd']:>11,}{r_['mar']:>7.2f}")
    with open(os.path.join(ROOT, "tools", "r16_results", "r25_book.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print("saved tools/r16_results/r25_book.csv")


if __name__ == "__main__":
    main()
