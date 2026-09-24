"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
Does the month-end rebalancing leg lift frontier #397 at matched drawdown? Daily MARKED-TO-MARKET for both.
#397 MTM = ORB297 + ENGUQ335 (MTM, sister session's enguq_mtm_daily.csv) + 3 x TTM369 + NOISE304, parity-checked
against the sister session's published MTM figures (pre DD $34,449, LB DD $49,855)."""
import os, numpy as np, pandas as pd, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
X = pd.read_csv(r"C:\EdgeLog\_anatomy_cache\book56\leg_dailies.csv", index_col="date", parse_dates=True).sort_index()
M = pd.read_csv(r"C:\EdgeLog\_anatomy_cache\book56\enguq_mtm_daily.csv", index_col="date", parse_dates=True).sort_index()
idx = X.index.union(M.index)
X = X.reindex(idx).fillna(0.0); M = M.reindex(idx).fillna(0.0)
book = X["ORB297"] + M["ENGUQ335_mtm"] + 3 * X["TTM369"] + X["NOISE304"]
def dd(s):
    c = s.cumsum(); return float((c.cummax() - c).max())
def stats(s, lab):
    pre = s[s.index < "2025-06-30"]; lb = s[s.index >= "2025-06-30"]
    yp = 15.06; yl = 1.0
    return "%-40s pre net $%9.0f DD $%6.0f ROC %5.1f%% MAR %.2f | LB net $%8.0f DD $%6.0f MAR %.2f" % (
        lab, pre.sum(), dd(pre), 100 * pre.sum() / yp / 1e5, pre.sum() / yp / dd(pre), lb.sum(), dd(lb), lb.sum() / yl / dd(lb))
print(stats(book, "#397 MTM (rebuilt)"))
import rebal_scan as R                          # reuses the scan's run() with its data
def leg_daily(DD, mult, K, th, cost=0.533):
    T = R.run(DD, mult, K, th, 0, cost)
    c = DD.c; gap = DD.o - DD.c.shift(1); seam = DD.seam; dates = DD.index
    s = pd.Series(0.0, index=dates)
    pos = pd.Series(0.0, index=dates)
    for _, t in T.iterrows():
        di = dates.get_loc(t.entry); xi = dates.get_loc(t.exit)
        s.iloc[di] -= cost * mult                              # cost booked at entry
        for j in range(di + 1, xi + 1):
            ch = c.iloc[j] - c.iloc[j - 1]
            if seam.iloc[j]: ch -= gap.iloc[j]; s.iloc[j] -= cost * mult
            s.iloc[j] += t.side * ch * mult
    return s, T
for inst, DD, mult, K, th in (("ES", R.E, 50, 5, 0.02), ("ES", R.E, 50, 3, 0.02), ("NQ", R.D, 20, 3, 0.02), ("NQ", R.D, 20, 5, 0.02)):
    s, T = leg_daily(DD, mult, K, th)
    # union of the book's dates AND the leg's own dates: reindexing the leg onto the book's dates alone
    # silently dropped leg P&L on days no book leg traded (first run read ES K=5 as $98,932, truly $115,168)
    s = s[s.index <= "2026-06-30"]            # the book's own window ends 2026-06-30
    ix2 = idx.union(s.index)
    s = s.reindex(ix2).fillna(0.0)
    book = (X.reindex(ix2).fillna(0.0)["ORB297"] + M.reindex(ix2).fillna(0.0)["ENGUQ335_mtm"]
            + 3 * X.reindex(ix2).fillna(0.0)["TTM369"] + X.reindex(ix2).fillna(0.0)["NOISE304"])
    print(stats(s, "leg %s K=%d th=%.2f x1 (alone)" % (inst, K, th)), " corr w/ book %.3f" % np.corrcoef(s[s.index < "2025-06-30"], book[book.index < "2025-06-30"])[0, 1])
    for w in (1, 2, 3, 4, 6):
        print(stats(book + w * s, "  #397 + %s K=%d x%d" % (inst, K, w)))
