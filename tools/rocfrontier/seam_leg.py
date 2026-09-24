"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
Stitch P&L inside a multi-day leg (generalised from seam_enguq.py). Usage: python seam_leg.py <legs.json key>"""
import os, sys, json, numpy as np, pandas as pd
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, os.getcwd())
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
if __name__ == "__main__":
    key = sys.argv[1]
    leg = json.load(open(r"C:\EdgeLog\_anatomy_cache\book56\legs.json", encoding="utf-8"))[key]["leg"]
    arr = load_master_arrays(find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"]), date_from="2010-06-07", date_to="2026-06-30")
    idx = pd.DatetimeIndex(arr["index"]).tz_localize(None); o = arr["open"]; c = arr["close"]; mult = float(leg["mult"])
    r = run_backtest(leg["strategy"], arrays=arr, params=leg["params"], cost_pts=float(leg["cost_pts"]), return_trades=True)
    T = r["trades"]; net = sum(t[2] for t in T) * mult
    Dd = pd.read_csv(os.path.join(CACHE, "%s_daily_rth.csv" % leg["instrument"]), index_col=0, parse_dates=True)
    jmp = np.r_[0.0, o[1:] - c[:-1]]
    st = []
    for sd in Dd.index[Dd.seam.values]:
        a = np.searchsorted(idx, sd - pd.Timedelta(days=4)); b = np.searchsorted(idx, sd + pd.Timedelta(days=1))
        if b > a:
            k = a + int(np.argmax(np.abs(jmp[a:b]))); st.append((k, jmp[k], idx[k]))
    rows = [(idx[e], idx[min(x, len(idx) - 1)], t, side * j * mult) for (e, x, p, side, px) in T for (k, j, t) in st if e < k <= x]
    df = pd.DataFrame(rows, columns=["entry", "exit", "stitch_ts", "usd"])
    pre = df[df.stitch_ts < "2025-06-30"]; lb = df[df.stitch_ts >= "2025-06-30"]
    tn = pd.DataFrame([(idx[e], p * mult) for (e, x, p, s, px) in T], columns=["e", "usd"])
    print("%s: %d trades, net $%.0f (pre $%.0f / LB $%.0f) | %d stitches found, median |jump| %.1f pts" % (
        key, len(T), net, tn[tn.e < "2025-06-30"].usd.sum(), tn[tn.e >= "2025-06-30"].usd.sum(), len(st), np.median([abs(j) for _, j, _ in st])))
    print("  crossings: %d trades, booked stitch $%.0f | pre-LB %d trades $%.0f | LB %d trades $%.0f" % (
        len(df), df.usd.sum(), len(pre), pre.usd.sum(), len(lb), lb.usd.sum()))
    df["yr"] = df.stitch_ts.dt.year
    print("  by year:", " ".join("%d:%d/$%.0f" % (y, g.shape[0], g.usd.sum()) for y, g in df.groupby("yr")))
    print("  stitch sizes 2022+ (pts):", " ".join("%s:%+.1f" % (t.date(), j) for (k, j, t) in st if t.year >= 2022))
