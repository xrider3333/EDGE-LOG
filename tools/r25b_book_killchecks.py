"""
ROUND 25b — adversarial kill-checks on the weak-edge book (the round-25 pass).

The r25 result (equal-risk book MAR 8.08; stacked onto the champion book MAR
8.44 -> 10.92) has one obvious way to be a lie: the 11 legs were SELECTED for
profit factor >= 1.40 measured on the SAME window the book is then scored on.
That is selection on the test set - the same class of self-deception as the
round-18 harness foresight. These checks are pre-registered here and run once.

K1  NO SELECTION AT ALL. Pool all 20 candidate legs, including the 9 the rule
    rejected. If the book only works when the winners are known in advance, this
    collapses. PASS = still clears PF 1.25 / MAR 8.
K2  OUT-OF-SAMPLE SELECTION. Rank legs by profit factor on 2010-06-07..2017-12-31
    ONLY (>= 1.40, n >= 30 in that stretch), then score the resulting book on
    2018-01-01..2025-06-29 exclusively. This is the honest version of what a
    trader could actually have done. PASS = PF >= 1.25 and MAR >= 8 out of sample.
K3  CAUSAL SIZING. Replace full-sample equal-risk sizing with an EXPANDING-WINDOW
    estimate: each trade is scaled by the median-leg volatility divided by that
    leg's volatility computed from its OWN trades strictly BEFORE that trade
    (minimum 20 prior trades; before that, weight 1.0). No future volatility.
K4  YEAR SPREAD of the K3 book: yearly nets, post-2021 profit share, and the count
    of positive years.
K5  STACK TEST redone with the K3 (causal) book and causal risk-matching against
    the champion book, using an expanding-window volatility ratio.
Window 2010-06-07 -> 2025-06-29 throughout; lockbox never loaded.
"""
import os, sys, csv
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("r25", os.path.join(ROOT, "tools", "r25_weak_edge_book.py"))
r25 = _ilu.module_from_spec(_sp); _sp.loader.exec_module(r25)

WIN_FROM, WIN_TO = "2010-06-07", "2025-06-29"
SPLIT = pd.Timestamp("2018-01-01").date()


def stats(series, label):
    s = sorted(series, key=lambda z: z[0])
    p = np.array([z[1] for z in s], float)
    if len(p) == 0:
        return dict(book=label, n=0, net=0, pf=0, dd=0, mar=0)
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum())
    return dict(book=label, n=len(p), net=round(net), pf=round(gw / gl if gl > 0 else 99, 3),
                dd=round(-dd), mar=round(net / -dd if dd < 0 else 99, 2))


def causal_scaled(legs):
    """expanding-window equal-risk: scale each trade by (running median leg vol) /
    (that leg's vol over its OWN prior trades). No future information."""
    hist = defaultdict(list)
    events = sorted(((dt, k, v) for k, ser in legs.items() for dt, v in ser), key=lambda z: z[0])
    out = []
    for dt, k, v in events:
        vols = [np.std(h) for h in hist.values() if len(h) >= 20]
        own = np.std(hist[k]) if len(hist[k]) >= 20 else None
        if own and own > 0 and vols:
            w = float(np.median(vols)) / own
        else:
            w = 1.0
        out.append((dt, v * w))
        hist[k].append(v)
    return out


def main():
    legs = r25_build_legs()
    rows = []

    # K1 - no selection
    allser = [z for v in legs.values() for z in v]
    rows.append(stats(allser, "K1 all 20 legs, equal notional, no selection"))
    rows.append(stats(causal_scaled(legs), "K1 all 20 legs, causal equal risk"))

    # K2 - out-of-sample selection
    picked = {}
    for k, v in legs.items():
        tr = [z for z in v if z[0] < SPLIT]
        p = np.array([z[1] for z in tr], float)
        if len(p) >= 30:
            gw = p[p > 0].sum(); gl = -p[p < 0].sum()
            if (gw / gl if gl > 0 else 99) >= 1.40 and p.sum() > 0:
                picked[k] = [z for z in v if z[0] >= SPLIT]
    print(f"K2 selected on 2010-2017: {sorted(picked)}")
    rows.append(stats([z for v in picked.values() for z in v],
                      f"K2 OOS book 2018-2025 ({len(picked)} legs picked on 2010-17)"))
    rows.append(stats(causal_scaled(picked), "K2 OOS book, causal equal risk"))

    # K3 - the r25 selection but with causal sizing
    sel = {}
    for k, v in legs.items():
        p = np.array([z[1] for z in v], float)
        if len(p) >= 100:
            gw = p[p > 0].sum(); gl = -p[p < 0].sum()
            if (gw / gl if gl > 0 else 99) >= 1.40 and p.sum() > 0:
                sel[k] = v
    k3 = causal_scaled(sel)
    rows.append(stats(k3, f"K3 r25 selection ({len(sel)} legs), CAUSAL equal risk"))

    # K4 - year spread of K3
    yr = defaultdict(float)
    for dt, v in k3:
        yr[dt.year] += v
    tot = sum(yr.values()); post = sum(v for y, v in yr.items() if y >= 2022)
    pos = sum(1 for v in yr.values() if v > 0)
    print(f"\nK4 year spread (K3 book): {pos}/{len(yr)} positive years, "
          f"post-2021 share {100*post/tot:.0f}%")
    for y in sorted(yr):
        print(f"   {y}: {yr[y]:>12,.0f}")

    # K5 - stack with causal risk matching
    champ = defaultdict(float)
    csvp = os.path.join(ROOT, "tools", "r13_results", "legal_legs_daily.csv")
    for r in csv.DictReader(open(csvp)):
        d = pd.Timestamp(r["date"][:10]).date()
        if pd.Timestamp(WIN_FROM).date() <= d <= pd.Timestamp(WIN_TO).date():
            champ[d] += float(r["c2"]) + float(r["engq_eth"])
    rows.append(stats(list(champ.items()), "CHAMPION BOOK alone (reference)"))
    wk = defaultdict(float)
    for dt, v in k3:
        wk[dt] += v
    alld = sorted(set(champ) | set(wk))
    ch, wh, stacked = [], [], {}
    for d in alld:
        cv = champ.get(d, 0.0); wv = wk.get(d, 0.0)
        sc = (np.std(ch) / np.std(wh)) if (len(ch) >= 250 and len(wh) >= 250 and np.std(wh) > 0) else 1.0
        stacked[d] = cv + wv * sc
        ch.append(cv); wh.append(wv)
    rows.append(stats(list(stacked.items()), "K5 CHAMPION + K3 weak-edge (causal risk match)"))
    cd = np.array([champ.get(d, 0.0) for d in alld]); wd = np.array([wk.get(d, 0.0) for d in alld])
    print(f"\nK5 champion vs causal weak-edge daily correlation: {np.corrcoef(cd, wd)[0,1]:.3f}")

    print(f"\n{'book':52}{'n':>6}{'net$':>12}{'PF':>7}{'DD$':>11}{'MAR':>7}  gate")
    for r_ in rows:
        g = "PASS" if (r_['pf'] >= 1.25 and r_['mar'] >= 8 and r_['n'] >= 300) else "fail"
        print(f"{r_['book']:52}{r_['n']:>6}{r_['net']:>12,}{r_['pf']:>7.3f}{r_['dd']:>11,}{r_['mar']:>7.2f}  {g}")
    with open(os.path.join(ROOT, "tools", "r16_results", "r25b_killchecks.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print("saved tools/r16_results/r25b_killchecks.csv")


def r25_build_legs():
    """rebuild the same 20 candidate legs r25 built (same code path, no selection)."""
    from augur_engine.data import find_master, load_master_arrays
    import yfinance as yf
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
    seams = set(r25.detect_roll_seams(ndo, ndc, [idx5[x] for x, y in sess]))
    legs = {}
    for cell in ("PB20L", "DBL7L", "RSI2L", "CAP5"):
        legs[f"NQ/{cell}"] = r25.run_cell(ndo, ndh, ndl, ndc, ndates, cell,
                                          shares_fn=lambda d: r25.MULT,
                                          cost_fn=lambda de, dx: (r25.RT_D if dx == de else r25.RT_ON),
                                          seams=seams)
    for tk in ("GLD", "TLT", "IWM", "QQQ"):
        df = yf.download(tk, start="2009-06-01", end="2025-06-30", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close"]].dropna()
        do_, dh_, dl_, dc_ = (df[c].values.astype(float) for c in ["Open", "High", "Low", "Close"])
        dts = [d.date() for d in df.index]
        for cell in ("RSI2L", "RSI2B", "DBL7L", "PB20L"):
            legs[f"{tk}/{cell}"] = [z for z in r25.run_cell(
                do_, dh_, dl_, dc_, dts, cell,
                shares_fn=lambda de, o=do_: r25.NOTIONAL / o[de],
                cost_fn=lambda de, dx, o=do_: r25.ETF_COST / (r25.NOTIONAL / o[de]))
                if z[0] >= pd.Timestamp(WIN_FROM).date()]
    return legs


if __name__ == "__main__":
    main()
