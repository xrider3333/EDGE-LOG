"""BOOK ROUND 56 - mark-to-market vs closed-trade daily curve for the multi-day ENGU-Q legs (book round 56).

A BOOK curve books every trade on its EXIT day. ENGU-Q trades can stay open for weeks to months, so
the swings while they are open never reach the curve. Here every open ENGU-Q position is valued at
the last bar close of each day it is open (same UTC day-stamp the book uses), so the day-to-day
increments sum EXACTLY to the trade's closed P&L (checked per trade) - only the timing moves.
"""
import os, sys, json
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
sys.path.insert(0, os.getcwd())
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
import numpy as np, pandas as pd
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest

D = os.environ.get("EDGELOG_BOOK56_DIR", r"C:\EdgeLog\_anatomy_cache\book56")
legs = json.load(open(os.path.join(D, "legs.json"), encoding="utf-8"))


def mtm_daily(key):
    leg = legs[key]["leg"]
    m = find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"])
    arr = load_master_arrays(m, date_from="2010-06-07", date_to="2026-06-30")
    idx = arr["index"]
    day = np.asarray(idx, dtype="datetime64[D]")            # the book's own UTC day stamp
    close = np.asarray(arr["close"], dtype=float)
    r = run_backtest(leg["strategy"], arrays=arr, params=leg["params"], cost_pts=float(leg["cost_pts"]), return_trades=True)
    mult = float(leg["mult"])
    closed, mtm = {}, {}
    worst_gap = 0.0
    for t in r["trades"]:
        e, x, p, side, px = int(t[0]), min(int(t[1]), len(idx) - 1), float(t[2]), float(t[3]), float(t[4])
        closed[day[x]] = closed.get(day[x], 0.0) + p * mult
        prev = 0.0
        # value the open position at the last close of every day strictly before the exit day
        d_open = day[e:x + 1]
        c_open = close[e:x + 1]
        last_of_day = np.r_[d_open[1:] != d_open[:-1], True]
        for d, c in zip(d_open[last_of_day][:-1], c_open[last_of_day][:-1]):
            val = side * (c - px) * mult
            mtm[d] = mtm.get(d, 0.0) + (val - prev)
            prev = val
        mtm[day[x]] = mtm.get(day[x], 0.0) + (p * mult - prev)
    s_c = pd.Series(closed).sort_index(); s_m = pd.Series(mtm).sort_index()
    s_c.index = pd.to_datetime(s_c.index); s_m.index = pd.to_datetime(s_m.index)
    return s_c, s_m


def dd(v):
    c = np.cumsum(np.asarray(v, float))
    return float(-(c - np.maximum.accumulate(c)).min()) if len(c) else 0.0


def main():
    X = pd.read_csv(os.path.join(D, "leg_dailies.csv"), index_col="date", parse_dates=True).sort_index()
    out = {}
    for key in ("ENGUQ335", "ENGUQ_ES370"):
        s_c, s_m = mtm_daily(key)
        chk = abs(s_c.sum() - s_m.sum())
        par = abs(s_c.reindex(X.index).fillna(0).sum() - X[key].sum())
        print(f"{key}: closed ${s_c.sum():,.2f} | mtm ${s_m.sum():,.2f} | diff {chk:.4f} | vs book leg column diff {par:.4f}")
        idx = X.index.union(s_m.index)
        out[key] = (s_c.reindex(idx).fillna(0.0), s_m.reindex(idx).fillna(0.0))
        for nm, lo, hi in (("pre", "2010-06-07", "2025-06-30"), ("LB", "2025-06-30", "2026-07-01")):
            a = s_c[(s_c.index >= lo) & (s_c.index < hi)]; b = s_m[(s_m.index >= lo) & (s_m.index < hi)]
            print(f"   {nm:3} leg alone: net closed ${a.sum():>10,.0f} mtm ${b.sum():>10,.0f} | DD closed ${dd(a):>8,.0f}  mtm ${dd(b):>8,.0f}")
    # the #397 book with its ENGU-Q leg marked to market
    Xf = X.reindex(X.index.union(out["ENGUQ335"][1].index)).fillna(0.0)
    base = Xf["ORB297"] + Xf["ENGUQ335"] + 3 * Xf["TTM369"] + Xf["NOISE304"]
    mtm_book = Xf["ORB297"] + out["ENGUQ335"][1].reindex(Xf.index).fillna(0.0) + 3 * Xf["TTM369"] + Xf["NOISE304"]
    for nm, lo, hi in (("pre", "2010-06-07", "2025-06-30"), ("LB", "2025-06-30", "2026-07-01")):
        a = base[(base.index >= lo) & (base.index < hi)]; b = mtm_book[(mtm_book.index >= lo) & (mtm_book.index < hi)]
        c = a.cumsum(); cb = b.cumsum()
        ia = int(np.argmax(np.maximum.accumulate(c.values) - c.values)); ib = int(np.argmax(np.maximum.accumulate(cb.values) - cb.values))
        print(f"#397 {nm:3}: net closed ${a.sum():>11,.0f} mtm ${b.sum():>11,.0f} | max DD closed ${dd(a):>8,.0f} (trough {c.index[ia].date()})"
              f"  MARKED-TO-MARKET ${dd(b):>8,.0f} (trough {cb.index[ib].date()})")
    # with the ES candidate too
    es = out["ENGUQ_ES370"]
    for nm, lo, hi in (("pre", "2010-06-07", "2025-06-30"), ("LB", "2025-06-30", "2026-07-01")):
        a = (base + es[0].reindex(base.index).fillna(0.0)); b = (mtm_book + es[1].reindex(base.index).fillna(0.0))
        a = a[(a.index >= lo) & (a.index < hi)]; b = b[(b.index >= lo) & (b.index < hi)]
        print(f"#397 + ES ENGU-Q x1 {nm:3}: net ${a.sum():>11,.0f} | max DD closed ${dd(a):>8,.0f}  marked-to-market ${dd(b):>8,.0f}")
    pd.DataFrame({k + "_mtm": v[1] for k, v in out.items()}).to_csv(os.path.join(D, "enguq_mtm_daily.csv"), index_label="date")


if __name__ == "__main__":
    main()
