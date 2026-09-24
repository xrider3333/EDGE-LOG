r"""
TREND round 1 - time-series momentum on the markets where dip-buying fails (2026-09-24).

WHY. NON-EQUITY DIP r1 (tools/secdip2_nonequity_dip_triage.py) showed dip-buying is harvesting an asset's upward
drift: it pays on stocks, bonds and gold and dies on currencies and commodities, which have no drift. What those
markets DO have in the literature is trend (Moskowitz-Ooi-Pedersen 2012 time-series momentum; "crisis alpha" in
2008 and 2022). ROTATION r1 tested cross-sectional ranking of five funds against equal-weight; it never tested
trend as a LONG/SHORT return stream judged by what it adds to the DIP book - that is this round.

UNIVERSE, fixed before any run: IEF TIP SLV DBC USO UUP FXE FXY FXA (non-equity, cached in
C:\EdgeLog\_research_cache\nonequity_*.csv) + GLD TLT (library masters).
RULE: on each month's last close, sign of the last L months' return -> long (+) or short (-) from the next open,
held a month. RISK-MATCHED: notional = $100,000 x (median trailing-60-day vol of the DIP funds GLD TLT IWM QQQ /
the fund's trailing-60-day vol), capped 4x, set at the signal. 2 bp per side on every change of dollars.
GRID: L in {1, 3, 6, 12} months = 4 cells. No other knobs.

DIP pool A = GLD TLT IWM QQQ x (RSI2, DBL7) at $100,000, exactly as secdip1/secdip2.
BOOK B = A + T x k, where k scales the trend pool to A's daily PnL volatility over the window (equal risk).
SELECTION WINDOW 2008-01-01 .. 2025-06-30; the last 15 months are not read.

PRE-REGISTERED BAR - TREND is PROMISING only if ALL hold:
  1. plateau: at least 3 of the 4 lookbacks have standalone Sharpe >= 0.30;
  2. it widens the book: for those cells, B's Sharpe >= 1.10 x A's, AND B beats A on Sharpe in all three eras
     2008-2013, 2014-2019, 2020-2025H1;
  3. not one year: the scaled trend pool is still net positive after removing its best calendar year.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.argv = sys.argv[:1]
import importlib.util
spec = importlib.util.spec_from_file_location("sd2", os.path.join(ROOT, "tools", "secdip2_nonequity_dip_triage.py"))
sd2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(sd2)   # data, DIP legs, helpers (no main)
DATA, DAYS, VOL, REFVOL = sd2.DATA, sd2.DAYS, sd2.VOL, sd2.REFVOL
win, sharpe, dd = sd2.win, sd2.sharpe, sd2.dd
NOTIONAL, COST = sd2.NOTIONAL, sd2.COST
UNIV = ["IEF", "TIP", "SLV", "DBC", "USO", "UUP", "FXE", "FXY", "FXA", "GLD", "TLT"]
SEL0, SEL1 = "2008-01-01", "2025-06-30"
ERAS = [("2008-01-01", "2013-12-31"), ("2014-01-01", "2019-12-31"), ("2020-01-01", SEL1)]
ME = set(pd.Series(DAYS, index=DAYS).groupby([DAYS.year, DAYS.month]).tail(1).index)


def notional(sym, t):
    v, r = VOL[sym].iloc[t], REFVOL.iloc[t]
    return NOTIONAL * min(4.0, r / v) if (v > 0 and r > 0) else 0.0


def trend_leg(sym, L):
    df = DATA[sym].reindex(DAYS); o, c = df.o.values, df.c.values
    pnl = np.zeros(len(c)); sh = 0.0; pend = None
    for t in range(1, len(c)):
        if np.isnan(c[t]) or np.isnan(c[t - 1]) or np.isnan(o[t]):
            continue
        if pend is not None:
            pnl[t] += sh * (o[t] - c[t - 1])
            pnl[t] -= abs(pend - sh) * o[t] * COST / 2
            sh = pend; pend = None
            pnl[t] += sh * (c[t] - o[t])
        else:
            pnl[t] += sh * (c[t] - c[t - 1])
        if DAYS[t] in ME:
            a = t - 21 * L
            if a >= 0 and not np.isnan(c[a]):
                s = 1.0 if c[t] > c[a] else -1.0
                pend = s * notional(sym, t) / c[t]
    return pd.Series(pnl, index=DAYS)


if __name__ == "__main__":
    A = sum(sd2.leg(s, r)[0] for s in sd2.ETFS for r in ("RSI2", "DBL7"))
    Aw = win(A, SEL0, SEL1)
    print(f"DIP pool A: net ${Aw.sum():,.0f}  Sharpe {sharpe(Aw):.2f}  DD ${dd(Aw):,.0f}  | eras "
          + " ".join(f"{sharpe(win(Aw, *e)):.2f}" for e in ERAS))
    rows = []
    for L in (1, 3, 6, 12):
        legs = {s: win(trend_leg(s, L), SEL0, SEL1) for s in UNIV}
        T = sum(legs.values())
        k = Aw.std() / T.std()
        Ts = T * k; B = Aw + Ts
        yr = Ts.groupby(Ts.index.year).sum()
        eras = [(sharpe(win(Aw, *e)), sharpe(win(B, *e))) for e in ERAS]
        c1 = sharpe(T) >= 0.30
        c2 = sharpe(B) >= 1.10 * sharpe(Aw) and all(b > a for a, b in eras)
        c3 = (yr.sum() - yr.max()) > 0
        rows.append(dict(L=L, sharpe_T=round(sharpe(T), 2), corr=round(T.corr(Aw), 2), sharpe_B=round(sharpe(B), 2),
                         c1=c1, c2=c2, c3=c3))
        print(f"\nL={L:2}m  trend pool Sharpe {sharpe(T):.2f}  DD ${dd(Ts):,.0f} (scaled x{k:.2f})  corr to A {T.corr(Aw):.2f}"
              f"  -> book B Sharpe {sharpe(B):.2f} vs A {sharpe(Aw):.2f}")
        print("   eras A->B: " + "  ".join(f"{a:.2f}->{b:.2f}" for a, b in eras))
        print("   per fund Sharpe: " + " ".join(f"{s}:{sharpe(p):+.2f}" for s, p in legs.items()))
        print("   scaled trend $ by year: " + " ".join(f"{y % 100:02d}:{v / 1000:+.0f}k" for y, v in yr.items()))
        print(f"   C1 {'PASS' if c1 else 'fail'}  C2 {'PASS' if c2 else 'fail'}  C3 {'PASS' if c3 else 'fail'}")
    R = pd.DataFrame(rows)
    plat = int(R.c1.sum())
    prom = R[R.c1 & R.c2 & R.c3] if plat >= 3 else R.iloc[0:0]
    print(f"\nplateau {plat}/4 lookbacks with Sharpe >= 0.30 (needs 3); PROMISING: "
          + ("none" if prom.empty else ", ".join(f"L{l}m" for l in prom.L)))
    os.makedirs("tools/r16_results", exist_ok=True)
    R.to_csv("tools/r16_results/tsm1_trend_triage.csv", index=False)
