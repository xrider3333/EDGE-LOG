"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
SCAN - where inside the day does the month-end rebalancing flow land? For each of the last 5 trading days of
each month, signal = -sign(SPY MTD - TLT MTD) measured at the PRIOR day's close (known before the session),
|spread| >= 2%. Window returns on the 5m RTH master (bar OPEN timestamps; a window a->b = open of the bar at a
to open of the bar at b, 16:00 = last bar's close). $ at 1 contract, cost 0.533 per window. Pre-lockbox only."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays
def yahoo(sym):
    A = load_master_arrays(find_master(sym, "1d", "rth", "yahoo_adj"))
    return pd.Series(A["close"], index=pd.DatetimeIndex(A["index"]).tz_localize(None).normalize())
SPY, TLT = yahoo("SPY"), yahoo("TLT")
for inst, mult in (("NQ", 20), ("ES", 50)):
    A = load_master_arrays(find_master(inst, "5m", "rth", "db_noadj_rth"), date_from="2010-06-01", date_to="2025-06-29")
    ts = pd.DatetimeIndex(A["index"]).tz_localize(None); o = A["open"]; c = A["close"]
    df = pd.DataFrame({"o": o, "c": c}, index=ts); df["d"] = ts.normalize(); df["hm"] = ts.hour * 100 + ts.minute
    days = df["d"].unique()
    def px(hm):
        s = df[df.hm == hm].set_index("d")["o"]; return s
    P = pd.DataFrame({"o0930": px(930), "o1100": px(1100), "o1400": px(1400), "o1500": px(1500), "o1530": px(1530)})
    P["c1600"] = df.groupby("d")["c"].last()
    P = P.sort_index(); P["prev_c"] = P["c1600"].shift(1)
    dates = P.index; ym = dates.to_period("M")
    rank_from_end = pd.Series(np.arange(len(dates)), index=dates).groupby(ym).transform(lambda s: s.max() - s)
    prev_me = {}
    last_by_m = pd.Series(dates, index=dates).groupby(ym).max()
    rows = []
    for i, d in enumerate(dates):
        r = rank_from_end.iloc[i]
        if r > 4 or i == 0: continue
        per = ym[i]
        if (per - 1) not in last_by_m.index: continue
        pme = last_by_m[per - 1]; sig_day = dates[i - 1]
        s0, s1, t0, t1 = SPY.asof(pme), SPY.asof(sig_day), TLT.asof(pme), TLT.asof(sig_day)
        if any(pd.isna(x) for x in (s0, s1, t0, t1)): continue
        spread = (s1 / s0 - 1) - (t1 / t0 - 1)
        if abs(spread) < 0.02: continue
        side = -np.sign(spread)
        row = P.loc[d]
        rows.append(dict(d=d, r=r, side=side,
                         on=row.o0930 - row.prev_c, am=row.o1100 - row.o0930, mid=row.o1400 - row.o1100,
                         h14=row.o1500 - row.o1400, h15=row.c1600 - row.o1500, h1530=row.c1600 - row.o1530, day=row.c1600 - row.o0930))
    R = pd.DataFrame(rows)
    print("\n%s: %d signal-days (last 5 trading days of months with |spread|>=2%%), $ per window at 1 contract after 0.533 cost" % (inst, len(R)))
    for w in ("on", "am", "mid", "h14", "h15", "h1530", "day"):
        g = (R.side * R[w] - (0 if w == "on" else 0.533)) * mult
        by = g.groupby(R.d.dt.year).sum()
        print("  %-6s $/trade %+7.1f  total %+9.0f  win %2.0f%%  yrs+ %2d/%d  by days-to-end: %s" % (
            w, g.mean(), g.sum(), 100 * (g > 0).mean(), int((by > 0).sum()), len(by),
            " ".join("%d:%+.0f" % (k, v) for k, v in g.groupby(R.r).mean().items())))
