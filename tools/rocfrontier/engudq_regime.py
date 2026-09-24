"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
Regime-gated ENGU-Q SHORT mirror (ENGUDQ_1M_ETH_1_0.py, frozen defaults) on NQ 1m ETH, PRE-LOCKBOX ONLY
(2010-06-07..2025-06-30; nothing after is loaded). regime_len N = short only while close < SMA(N*390 one-minute bars).
Roll stitches crossed while short are ADDED BACK (they are the calendar spread, not a market loss).
Screen: standalone, and #397 (MTM, rebuilt from the sister session's dailies) + leg at x1 by exit day."""
import os, sys, numpy as np, pandas as pd
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, os.getcwd())
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
import importlib.util
if __name__ == "__main__":
    arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), date_from="2010-06-07", date_to="2025-06-30")
    idx = pd.DatetimeIndex(arr["index"]).tz_localize(None); o = arr["open"]; c = arr["close"]
    day = np.asarray(arr["index"], dtype="datetime64[D]")
    Dd = pd.read_csv(os.path.join(CACHE, "NQ_daily_rth.csv"), index_col=0, parse_dates=True)
    jmp = np.r_[0.0, o[1:] - c[:-1]]; st = []
    for sd in Dd.index[Dd.seam.values]:
        a = np.searchsorted(idx, sd - pd.Timedelta(days=4)); b = np.searchsorted(idx, sd + pd.Timedelta(days=1))
        if b > a:
            k = a + int(np.argmax(np.abs(jmp[a:b]))); st.append((k, jmp[k]))
    X = pd.read_csv(r"C:\EdgeLog\_anatomy_cache\book56\leg_dailies.csv", index_col="date", parse_dates=True).sort_index()
    M = pd.read_csv(r"C:\EdgeLog\_anatomy_cache\book56\enguq_mtm_daily.csv", index_col="date", parse_dates=True).sort_index()
    ix = X.index.union(M.index); X = X.reindex(ix).fillna(0); M = M.reindex(ix).fillna(0)
    book = (X["ORB297"] + M["ENGUQ335_mtm"] + 3 * X["TTM369"] + X["NOISE304"]); book = book[book.index < "2025-06-30"]
    def dd(s):
        cc = s.cumsum(); return float((cc.cummax() - cc).max())
    yrs = 15.06
    print("book pre: net $%.0f DD $%.0f MAR %.2f" % (book.sum(), dd(book), book.sum() / yrs / dd(book)))
    spec = importlib.util.spec_from_file_location("engudq", os.path.join(CACHE, "ENGUDQ_1M_ETH_1_0.py"))   # frozen copy, sha1 d2501c2e
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    base = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    for rl in (0, 100, 200, 400, 700, 1000):
        p = dict(base); p["regime_len"] = rl
        r = run_backtest(mod, arrays=arr, params=p, cost_pts=0.783, return_trades=True)
        if not r or not r.get("trades"):
            print("regime_len", rl, "no trades"); continue
        rows = []
        for (e, x, pnl, side, px) in r["trades"]:
            fix = sum(side * j for (k, j) in st if e < k <= x)       # stitch booked inside the trade
            rows.append((pd.Timestamp(day[min(x, len(day) - 1)]), (pnl - fix) * 20, pnl * 20, idx[e].year))
        T = pd.DataFrame(rows, columns=["xday", "usd", "usd_raw", "yr"])
        by = T.groupby("yr").usd.sum()
        s = T.groupby("xday").usd.sum().reindex(book.index).fillna(0)
        comb = book + s
        w = T.usd
        print("regime_len %4d (~%3.0f ETH days): n=%4d net $%8.0f (raw $%8.0f) PF %.2f DD $%6.0f yrs+ %2d/%d | 2018 %+6.0f 2020 %+6.0f 2022 %+6.0f | corr %.3f | book+leg MAR %.2f DD $%.0f" % (
            rl, rl * 390 / 1380, len(T), w.sum(), T.usd_raw.sum(), w[w > 0].sum() / max(-w[w < 0].sum(), 1), dd(T.sort_values('xday').usd),
            int((by > 0).sum()), len(by), by.get(2018, 0), by.get(2020, 0), by.get(2022, 0), np.corrcoef(s, book)[0, 1],
            comb.sum() / yrs / dd(comb), dd(comb)))
