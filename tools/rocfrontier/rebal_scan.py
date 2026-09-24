"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
SCAN (daily bars) - month-end pension REBALANCING (Harvey/Mazzoleni/Melone 2025): when equities beat bonds
month-to-date, rebalancers SELL equities into month-end (and buy after they lag).
Signal at the RTH close of the day K trading days before the month's last trading day:
  spread = MTD return of SPY (yahoo adj daily close) - MTD return of TLT, both measured from the prior month's last close.
Trade NQ: position = -sign(spread) if |spread| >= th, entered at that day's close (MOC), exited at the close of
the month's last trading day (or the first day of the next month: variant X1). Cost 0.533/RT (two RTH prints).
Seam days inside the hold: the stitch is removed from the P&L (roll) + one extra cost.
Pre-lockbox 2010-06..2025-06 for choosing; LB (2025-06-30+) printed for info only."""
import os, numpy as np, pandas as pd, itertools, sys
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
from augur_engine.data import find_master, load_master_arrays
def yahoo(sym):
    m = find_master(sym, "1d", "rth", "yahoo_adj"); A = load_master_arrays(m)
    s = pd.Series(A["close"], index=pd.DatetimeIndex(A["index"]).tz_localize(None).normalize()); return s
SPY, TLT = yahoo("SPY"), yahoo("TLT")
D = pd.read_csv(os.path.join(CACHE, "NQ_daily_rth.csv"), index_col=0, parse_dates=True)
E = pd.read_csv(os.path.join(CACHE, "ES_daily_rth.csv"), index_col=0, parse_dates=True)
def run(DD, mult, K, th, hold_extra=0, cost=0.533):
    c = DD.c; o = DD.o; seam = DD.seam; gap = (DD.o - DD.c.shift(1))
    dates = DD.index
    ym = dates.to_period("M")
    last_idx = pd.Series(np.arange(len(dates)), index=dates).groupby(ym).max()     # last trading day of each month (index)
    trades = []
    for per, li in last_idx.items():
        di = li - K                                    # signal/entry day
        if di < 1: continue
        dsig = dates[di]
        # MTD returns up to the signal close, from the prior month's last close
        prev_month_end = dates[last_idx.get(per - 1, -1)] if (per - 1) in last_idx.index else None
        if prev_month_end is None: continue
        try:
            s0, s1 = SPY.asof(prev_month_end), SPY.asof(dsig)
            t0, t1 = TLT.asof(prev_month_end), TLT.asof(dsig)
        except Exception: continue
        if any(pd.isna(x) for x in (s0, s1, t0, t1)): continue
        spread = (s1 / s0 - 1) - (t1 / t0 - 1)
        if abs(spread) < th: continue
        side = -np.sign(spread)
        xi = min(li + hold_extra, len(dates) - 1)
        if xi <= di: continue
        pnl = side * (c.iloc[xi] - c.iloc[di]) - cost
        for j in range(di + 1, xi + 1):
            if seam.iloc[j]: pnl -= side * gap.iloc[j] + cost
        trades.append((dates[di], dates[xi], side, spread, pnl * mult))
    return pd.DataFrame(trades, columns=["entry", "exit", "side", "spread", "usd"])
def summ(T, lab):
    pre = T[T.entry < "2025-06-30"]; lb = T[T.entry >= "2025-06-30"]
    if len(pre) == 0: return
    yrs = 15.06; cc = pre.usd.cumsum(); dd = float((cc.cummax() - cc).max())
    by = pre.groupby(pre.entry.dt.year).usd.sum()
    w = pre.usd
    print("%-34s n=%3d net $%8.0f PF %4.2f win %2.0f%% DD $%6.0f MAR %5.2f yrs+ %2d/%2d  2016+ $%8.0f | L $%7.0f S $%7.0f | LB n=%d $%.0f" % (
        lab, len(pre), w.sum(), w[w > 0].sum() / max(-w[w < 0].sum(), 1), 100 * (w > 0).mean(), dd, w.sum() / yrs / max(dd, 1),
        int((by > 0).sum()), len(by), pre[pre.entry >= "2016-01-01"].usd.sum(), pre[pre.side > 0].usd.sum(), pre[pre.side < 0].usd.sum(), len(lb), lb.usd.sum()))
for inst, DD, mult in (("NQ", D, 20), ("ES", E, 50)):
    for K, th, X in itertools.product((2, 3, 5), (0.0, 0.02, 0.04), (0, 1)):
        summ(run(DD, mult, K, th, X), "%s K=%d th=%.2f +%dd" % (inst, K, th, X))
