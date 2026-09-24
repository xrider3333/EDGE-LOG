"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
SCAN (daily bars, approximate fills) - crash-regime short on NQ as a HEDGE LEG for frontier book #397.
Regime known at day d close: close < SMA(L) AND SMA(L) below its value 5 days ago AND RV20 > k * median(RV20 over prior 252d).
Enter short next open. Exit: chandelier stop (lowest low since entry + m*ATR20, checked on daily highs, fill at max(open, stop))
or regime off at close -> next open. Seam jumps crossed while short are ADDED BACK (a roll, not a loss) + 0.533 roll cost.
Cost 0.533 pts/RT. $20/pt. Window pre-LB 2010-06-07..2025-06-30 for selection; LB reported separately (NOT for choosing)."""
import os, numpy as np, pandas as pd, itertools
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
D = pd.read_csv(os.path.join(CACHE, "NQ_daily_rth.csv"), index_col=0, parse_dates=True)
X = pd.read_csv(r"C:\EdgeLog\_anatomy_cache\book56\leg_dailies.csv", index_col="date", parse_dates=True)
B = X["ORB297"] + X["ENGUQ335"] + 3 * X["TTM369"] + X["NOISE304"]
o, h, l, c = D.o.values, D.h.values, D.l.values, D.c.values
n = len(D); dates = D.index
gap = np.r_[np.nan, o[1:] - c[:-1]]
seam = D.seam.values
lr = np.r_[np.nan, np.diff(np.log(c))]
tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
tr = np.r_[h[0] - l[0], tr]
atr = pd.Series(tr).rolling(20).mean().values
rv = pd.Series(lr).rolling(20).std().values
rvmed = pd.Series(rv).rolling(252, min_periods=120).median().shift(1).values
def run(L, k, m, cost=0.533):
    sma = pd.Series(c).rolling(L).mean().values
    reg = (c < sma) & (sma < np.r_[np.full(5, np.nan), sma[:-5]]) & (rv > k * rvmed)
    pos = 0; ent = 0.0; lo = 0.0; adj = 0.0; trades = []; daily = np.zeros(n); ent_i = 0
    for t in range(1, n):
        if pos == 0:
            if reg[t - 1] and not np.isnan(atr[t - 1]):
                pos = -1; ent = o[t]; lo = l[t]; adj = 0.0; ent_i = t
                stop = lo + m * atr[t - 1]
                # same-day stop check (conservative: if high >= stop on the entry day, stopped at stop)
                if h[t] >= ent + m * atr[t - 1]:
                    px = max(o[t], ent + m * atr[t - 1]); pnl = ent - px - cost
                    trades.append((ent_i, t, pnl)); daily[t] += pnl; pos = 0
                continue
        else:
            if seam[t]:
                adj += gap[t] - cost          # roll: add the stitch back, pay a round trip
            stop = lo + m * atr[t - 1]
            ex = None
            if o[t] >= stop: ex = o[t]
            elif h[t] >= stop: ex = stop
            elif not reg[t - 1]: ex = o[t]
            if ex is not None:
                pnl = ent - ex + adj - cost
                trades.append((ent_i, t, pnl)); daily[t] += pnl; pos = 0
                continue
            lo = min(lo, l[t])
    return trades, daily
def dd(x):
    cc = np.cumsum(x); return float((np.maximum.accumulate(cc) - cc).max())
pre = dates < "2025-06-30"; lbm = dates >= "2025-06-30"
yrs = (pd.Timestamp("2025-06-30") - pd.Timestamp("2010-06-07")).days / 365.25
Bd = B.reindex(dates).fillna(0.0).values
print("book #397 pre-LB: net $%.0f DD $%.0f MAR %.2f" % (Bd[pre].sum(), dd(Bd[pre]), Bd[pre].sum() / yrs / dd(Bd[pre])))
rows = []
for L, k, m in itertools.product((20, 50, 100), (1.0, 1.25, 1.5), (2.0, 3.0)):
    tr_, dly = run(L, k, m)
    usd = dly * 20
    pn = [p * 20 for (i, j, p) in tr_ if dates[i] < pd.Timestamp("2025-06-30")]
    if not pn: continue
    pn = np.array(pn); gw = pn[pn > 0].sum(); gl = -pn[pn < 0].sum()
    top10 = np.sort(pn)[::-1][:10].sum() / pn.sum() if pn.sum() > 0 else np.nan
    yy = pd.Series(usd[pre], index=dates[pre]).groupby(dates[pre].year).sum()
    comb = Bd + usd
    s20 = usd[(dates >= "2020-02-26") & (dates <= "2020-03-27")].sum(); s22 = usd[(dates >= "2022-04-27") & (dates <= "2022-05-03")].sum()
    corr = np.corrcoef(usd[pre], Bd[pre])[0, 1]
    rows.append((L, k, m, len(pn), pn.sum(), gw / gl if gl else np.inf, dd(usd[pre]), pn.sum() / yrs / max(dd(usd[pre]), 1),
                 int((yy > 0).sum()), len(yy), top10, s20, s22, corr, comb[pre].sum() / yrs / dd(comb[pre]), dd(comb[pre]),
                 usd[lbm].sum(), comb[lbm].sum() / dd(comb[lbm])))
print("%3s %4s %3s %4s %9s %5s %7s %5s %5s %5s %8s %8s %5s | %6s %7s | %8s %6s" % ("L", "k", "m", "n", "net", "PF", "DD", "MAR", "yr+", "top10", "2020str", "2022str", "corr", "bkMAR", "bkDD", "LBnet", "bkLBr"))
for r in rows:
    print("%3d %4.2f %3.1f %4d %9.0f %5.2f %7.0f %5.2f %2d/%2d %5.2f %8.0f %8.0f %5.2f | %6.2f %7.0f | %8.0f %6.2f" % r)
