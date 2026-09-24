"""
SECTOR round 1 - cross-sectional sector trading, a family the library has never tested (2026-09-24).

ROTATION round 1 (tools/rot1_rotation_triage.py) closed cross-ASSET dual momentum over the five ETFs here: 0 of
16 cells beat plain equal-weight on Sharpe and drawdown. The other textbook cross-sectional effect lives one
level down - between the nine S&P sectors (XLK XLF XLE XLV XLY XLP XLI XLU XLB, all trading since Dec 1998,
so no survivorship bias - the universe is fixed and complete). Two opposite published effects, tested together
so neither can be cherry-picked:
  MOMENTUM (monthly): hold the top N sectors by the last L months' return (skip the last month or not).
  REVERSAL (weekly):  hold the bottom N sectors by the last W weeks' return - short-term losers bounce.
Long-only, constant $100,000 split evenly, decided on the last close of the period, filled at the next open,
2 bp cost on every buy and sell. Data: Yahoo daily, dividend-adjusted (cached in C:\\EdgeLog\\_research_cache).

CONTROL: all nine sectors equal-weight, rebalanced monthly, same costs. (SPY is reported for reference.)
SELECTION WINDOW 2000-01-01 .. 2025-06-30; the last 15 months are not read.

PRE-REGISTERED BAR, per side (momentum and reversal judged separately):
  1. Sharpe above the equal-weight control AND max drawdown no deeper;
  2. Sharpe above the control in all three eras 2000-2008, 2009-2016, 2017-2025H1;
  3. plateau: at least two thirds of that side's cells meet clause 1;
  4. excess return over the control is not one year: remove the best calendar year of excess and the cell
     must still beat the control on total return.
A side that clears 1-3 on its plateau is PROMISING and gets a plugin file and a proper validate.
"""
import os, sys, itertools
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
CACHE = r"C:\EdgeLog\_research_cache"
SECT = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB"]
SEL0, SEL1 = "2000-01-01", "2025-06-30"
ERAS = [("2000-01-01", "2008-12-31"), ("2009-01-01", "2016-12-31"), ("2017-01-01", SEL1)]
NOTIONAL, COST = 100000.0, 0.0002

O = pd.read_csv(os.path.join(CACHE, "sector_open.csv"), index_col=0, parse_dates=True)[SECT].dropna()
C = pd.read_csv(os.path.join(CACHE, "sector_close.csv"), index_col=0, parse_dates=True)[SECT].reindex(O.index).dropna()
O = O.reindex(C.index)
SPYC = pd.read_csv(os.path.join(CACHE, "sector_close.csv"), index_col=0, parse_dates=True)["SPY"].reindex(C.index)
month_end = set(C.groupby([C.index.year, C.index.month]).tail(1).index)
week_end = set(C.groupby([C.index.isocalendar().year, C.index.isocalendar().week]).tail(1).index)


def run(decide, when):
    """decide(end_loc) -> weight Series or None; applied from the next open."""
    w = pd.Series(0.0, index=SECT); pending = None
    pnl = np.zeros(len(C.index))
    Cv, Ov = C.values, O.values
    for t in range(1, len(C.index)):
        if pending is not None:
            pnl[t] += float((w.values * (Ov[t] / Cv[t - 1] - 1)).sum() * NOTIONAL)
            pnl[t] -= float((pending - w).abs().sum()) * NOTIONAL * COST
            w = pending; pending = None
            pnl[t] += float((w.values * (Cv[t] / Ov[t] - 1)).sum() * NOTIONAL)
        else:
            pnl[t] += float((w.values * (Cv[t] / Cv[t - 1] - 1)).sum() * NOTIONAL)
        if C.index[t] in when:
            nw = decide(t)
            if nw is not None:
                pending = nw
    return pd.Series(pnl, index=C.index)


def top_by(t, look, skip, n, lowest):
    a, b = t - look - skip, t - skip
    if a < 0:
        return None
    sc = C.iloc[b] / C.iloc[a] - 1.0
    pick = sc.sort_values(ascending=lowest).index[:n]
    return pd.Series([1.0 / n if s in pick else 0.0 for s in SECT], index=SECT)


def st(p, lo, hi):
    z = p[(p.index >= pd.Timestamp(lo)) & (p.index <= pd.Timestamp(hi))]
    r = z / NOTIONAL
    cum = z.cumsum()
    return dict(net=float(z.sum()), sh=float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0,
                dd=float(-(cum - cum.cummax()).min()))


if __name__ == "__main__":
    eq = run(lambda t: pd.Series(1.0 / 9, index=SECT), month_end)
    E = st(eq, SEL0, SEL1); EE = [st(eq, *e) for e in ERAS]
    spy = (SPYC.pct_change().fillna(0) * NOTIONAL)
    S = st(spy, SEL0, SEL1)
    print(f"CONTROL equal-weight 9 sectors: net ${E['net']:,.0f} Sharpe {E['sh']:.2f} DD ${E['dd']:,.0f} | eras "
          + " ".join(f"{e['sh']:.2f}" for e in EE))
    print(f"reference SPY buy-hold:          net ${S['net']:,.0f} Sharpe {S['sh']:.2f} DD ${S['dd']:,.0f}\n")
    rows = []
    sides = {
        "MOMENTUM": [(L, sk, n, month_end, (lambda L=L, sk=sk, n=n: (lambda t: top_by(t, 21 * L, 21 * sk, n, False)))())
                     for L, sk, n in itertools.product((3, 6, 9, 12), (0, 1), (1, 2, 3))],
        "REVERSAL": [(W, 0, n, week_end, (lambda W=W, n=n: (lambda t: top_by(t, 5 * W, 0, n, True)))())
                     for W, n in itertools.product((1, 2, 4), (1, 2, 3))],
    }
    ex_eq = eq[(eq.index >= SEL0) & (eq.index <= SEL1)]
    for side, cells in sides.items():
        print(side)
        for a, sk, n, when, dec in cells:
            p = run(dec, when)
            s = st(p, SEL0, SEL1); es = [st(p, *e) for e in ERAS]
            c1 = s["sh"] > E["sh"] and s["dd"] <= E["dd"]
            c2 = all(es[i]["sh"] > EE[i]["sh"] for i in range(3))
            z = p[(p.index >= SEL0) & (p.index <= SEL1)]
            exc = (z - ex_eq).groupby(z.index.year).sum()
            c4 = (exc.sum() - exc.max()) > 0
            lab = (f"L{a}m skip{sk}" if side == "MOMENTUM" else f"W{a}wk") + f" n{n}"
            rows.append(dict(side=side, cell=lab, net=round(s["net"]), sharpe=round(s["sh"], 2), dd=round(s["dd"]),
                             eras=" ".join(f"{e['sh']:.2f}" for e in es), c1=c1, c2=c2, c4=c4))
            print(f"  {lab:16} net ${s['net']:>9,.0f} Sharpe {s['sh']:.2f} DD ${s['dd']:>7,.0f} | eras "
                  + " ".join(f"{e['sh']:.2f}" for e in es) + f"  {'C1' if c1 else '--'} {'C2' if c2 else '--'} {'C4' if c4 else '--'}", flush=True)
    R = pd.DataFrame(rows)
    for side in ("MOMENTUM", "REVERSAL"):
        r = R[R.side == side]
        plat = int(r.c1.sum())
        need = int(np.ceil(len(r) * 2 / 3))
        prom = r[r.c1 & r.c2 & r.c4] if plat >= need else r.iloc[0:0]
        print(f"\n{side}: clause-1 plateau {plat} of {len(r)} (needs {need}); PROMISING cells: "
              + ("none" if prom.empty else ", ".join(prom.cell)))
    os.makedirs("tools/r16_results", exist_ok=True)
    R.to_csv("tools/r16_results/sec1_sector_triage.csv", index=False)
