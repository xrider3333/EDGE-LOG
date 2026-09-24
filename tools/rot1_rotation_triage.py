"""
ROTATION round 1 - a family this library has never tested: CROSS-ASSET ROTATION (2026-09-24, owner: "continue
searching for new strategies").

WHY THIS AND NOT ANOTHER NQ TIMING RULE. Every family on the board times ONE market: ORB, NOISE, ENGU-Q, TTM,
DIP, GAPGO, TTIBS - and the MISC hunts (rounds 16-25), the family seeds (rounds 32-42), the scalpers and the
ideas round closed ~300 more single-market cells. What has never been asked is WHICH market to hold. Dual
momentum (relative strength across asset classes plus an absolute-momentum cash switch) is the textbook
version; it trades once a month, holds bonds and gold when stocks fall, and so should be close to uncorrelated
with an intraday NQ/ES book.

DATA: the five daily ETF masters already here (QQQ, SPY, IWM, TLT, GLD; yahoo_adj = dividend-adjusted closes),
2006-01-03 onward. The first year is lookback warm-up only.

RULE (all decisions on a month's LAST close, filled at the next session's open - no same-bar fill):
  score_i = total return over the last L months, skipping the most recent month when skip=1
  hold the top N by score, each at 1/N of $100,000, but only those whose score > 0 (absolute momentum);
  the rest of the book sits in cash at 0%. Cost 2 bp of notional on every buy and every sell.
GRID, pre-registered: L in {3, 6, 9, 12} months x skip in {0, 1} x N in {1, 2} = 16 cells.
CONTROLS: equal-weight all five, monthly rebalanced (same costs) and buy-and-hold QQQ.
SELECTION WINDOW 2007-01-01 .. 2025-06-30. The last 14 months (2025-07-01 .. data end) are NOT read here.

PRE-REGISTERED BAR - a cell is PROMISING only if ALL hold on the selection window:
  1. Sharpe above the equal-weight control's AND max drawdown below it;
  2. positive in both halves (2007-2015 and 2016-2025H1) with Sharpe above equal-weight in both;
  3. a plateau: at least 12 of the 16 cells meet clause 1 (one lucky lookback is not a family);
  4. monthly-return correlation to QQQ below 0.6 (otherwise it is QQQ with extra steps).
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays

SYMS = ["QQQ", "SPY", "IWM", "TLT", "GLD"]
SEL0, SEL1, MID = "2007-01-01", "2025-06-30", "2016-01-01"
NOTIONAL, COST = 100000.0, 0.0002


def load(sym):
    m = find_master(sym, "1d", "rth", "yahoo_adj") or find_master(sym, "1d", None, "yahoo_adj")
    A = load_master_arrays(m)
    idx = pd.DatetimeIndex(A["index"]).tz_localize(None).normalize()
    return pd.DataFrame({"o": A["open"], "c": A["close"]}, index=idx)


D = {s: load(s) for s in SYMS}
days = sorted(set.intersection(*[set(d.index) for d in D.values()]))
O = pd.DataFrame({s: D[s].o.reindex(days) for s in SYMS})
C = pd.DataFrame({s: D[s].c.reindex(days) for s in SYMS})
month_end = C.groupby([C.index.year, C.index.month]).tail(1).index      # last session of each month


def run(L, skip, N, eqw=False, only=None):
    """Daily dollar PnL of the book. Weights set on a month-end close, applied from the NEXT open."""
    w_now = pd.Series(0.0, index=SYMS)
    pnl = pd.Series(0.0, index=C.index)
    pending = None
    me = set(month_end)
    di = C.index
    for t in range(1, len(di)):
        d, p = di[t], di[t - 1]
        # 1) a pending rebalance fills at today's open: close-to-open for old weights already booked
        if pending is not None:
            gap = (O.loc[d] / C.loc[p] - 1.0)
            pnl[d] += float((w_now * gap).sum() * NOTIONAL)
            turn = float((pending - w_now).abs().sum())
            pnl[d] -= turn * NOTIONAL * COST
            w_now = pending; pending = None
            intraday = (C.loc[d] / O.loc[d] - 1.0)
            pnl[d] += float((w_now * intraday).sum() * NOTIONAL)
        else:
            pnl[d] += float((w_now * (C.loc[d] / C.loc[p] - 1.0)).sum() * NOTIONAL)
        # 2) on a month-end close, decide next month's weights
        if d in me:
            if only:
                pending = pd.Series({s: (1.0 if s == only else 0.0) for s in SYMS})
            elif eqw:
                pending = pd.Series(1.0 / len(SYMS), index=SYMS)
            else:
                end = C.index.get_loc(d)
                look = int(round(21 * L)); sk = 21 * skip
                if end - look - sk < 0:
                    continue
                a, b = end - look - sk, end - sk
                score = C.iloc[b] / C.iloc[a] - 1.0
                top = score.sort_values(ascending=False).index[:N]
                pending = pd.Series(0.0, index=SYMS)
                for s in top:
                    if score[s] > 0:
                        pending[s] = 1.0 / N
    return pnl


def stats(p, lo, hi):
    z = p[(p.index >= pd.Timestamp(lo)) & (p.index <= pd.Timestamp(hi))]
    r = z / NOTIONAL
    sh = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
    cum = z.cumsum(); dd = float(-(cum - cum.cummax()).min())
    return dict(net=float(z.sum()), sharpe=sh, dd=dd, cagr_pct=100 * float(z.sum()) / NOTIONAL / ((z.index[-1] - z.index[0]).days / 365.25))


if __name__ == "__main__":
    eq = run(0, 0, 0, eqw=True); qqq = run(0, 0, 0, only="QQQ")
    E = {k: stats(eq, *w) for k, w in (("all", (SEL0, SEL1)), ("h1", (SEL0, "2015-12-31")), ("h2", (MID, SEL1)))}
    Q = stats(qqq, SEL0, SEL1)
    print(f"CONTROL equal-weight five: net ${E['all']['net']:,.0f}  Sharpe {E['all']['sharpe']:.2f}  DD ${E['all']['dd']:,.0f}"
          f"  | h1 Sharpe {E['h1']['sharpe']:.2f}  h2 {E['h2']['sharpe']:.2f}")
    print(f"CONTROL buy-hold QQQ:      net ${Q['net']:,.0f}  Sharpe {Q['sharpe']:.2f}  DD ${Q['dd']:,.0f}\n")
    mq = qqq.resample("ME").sum()
    rows = []
    for L in (3, 6, 9, 12):
        for skip in (0, 1):
            for N in (1, 2):
                p = run(L, skip, N)
                a, h1, h2 = stats(p, SEL0, SEL1), stats(p, SEL0, "2015-12-31"), stats(p, MID, SEL1)
                corr = float(p.resample("ME").sum().corr(mq))
                c1 = a["sharpe"] > E["all"]["sharpe"] and a["dd"] < E["all"]["dd"]
                c2 = h1["net"] > 0 and h2["net"] > 0 and h1["sharpe"] > E["h1"]["sharpe"] and h2["sharpe"] > E["h2"]["sharpe"]
                c4 = corr < 0.6
                rows.append(dict(L=L, skip=skip, N=N, net=round(a["net"]), sharpe=round(a["sharpe"], 2), dd=round(a["dd"]),
                                 cagr=round(a["cagr_pct"], 1), h1_sh=round(h1["sharpe"], 2), h2_sh=round(h2["sharpe"], 2),
                                 corr_qqq=round(corr, 2), c1=c1, c2=c2, c4=c4))
                print(f"  L{L:2} skip{skip} top{N}  net ${a['net']:>9,.0f}  CAGR {a['cagr_pct']:5.1f}%  Sharpe {a['sharpe']:.2f}  DD ${a['dd']:>7,.0f}"
                      f"  | h1 {h1['sharpe']:.2f} h2 {h2['sharpe']:.2f}  corrQQQ {corr:.2f}  {'C1' if c1 else '--'} {'C2' if c2 else '--'} {'C4' if c4 else '--'}",
                      flush=True)
    R = pd.DataFrame(rows)
    plateau = int(R.c1.sum())
    print(f"\nclause 3 plateau: {plateau} of 16 cells beat equal-weight on Sharpe AND drawdown (needs 12)")
    prom = R[R.c1 & R.c2 & R.c4] if plateau >= 12 else R.iloc[0:0]
    print("PROMISING cells:", "none" if prom.empty else "\n" + prom.to_string(index=False))
    os.makedirs("tools/r16_results", exist_ok=True)
    R.to_csv("tools/r16_results/rot1_rotation_triage.csv", index=False)
