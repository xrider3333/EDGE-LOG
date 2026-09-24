"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
SCAN ONLY (no belief): three flow mechanisms on NQ 5m ETH, 2010-06-07..2025-06-30 (pre-lockbox).
All conditions use prices KNOWN at the decision time; outcomes are later windows. $ at 1 NQ (x20).
A1 overnight drift window (European open) conditional on the prior RTH session return.
A2 late-day continuation (LETF rebalancing): sign(open->15:30) vs 15:30->16:00 (and ->16:15 on ETH tape).
C1 European-morning momentum: sign(02:00->04:00) vs 04:00->09:25.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays
A = load_master_arrays(find_master("NQ", "5m", "eth", "db_noadj_eth"), date_from="2010-06-01", date_to="2025-06-30")
df = pd.DataFrame({"o": A["open"], "c": A["close"]}, index=A["index"])
df.index = df.index.tz_localize(None)
t = df.index
def px_at(hhmm, col="o"):
    """price of the bar OPENING at hh:mm each calendar day (NaN if missing)."""
    h, m = hhmm
    s = df[(t.hour == h) & (t.minute == m)][col]
    s.index = s.index.normalize()
    return s
P = pd.DataFrame({
    "o0930": px_at((9, 30)), "o1530": px_at((15, 30)), "o1600": px_at((16, 0)), "o1615": px_at((16, 15)),
    "o0200": px_at((2, 0)), "o0130": px_at((1, 30)), "o0300": px_at((3, 0)), "o0400": px_at((4, 0)), "o0925": px_at((9, 25)),
    "o0000": px_at((0, 0)),
})
P = P.sort_index()
# prior RTH session return (09:30 open -> 16:00 open of the 16:00 bar ~ close), known at 16:00 the prior day
P["rth_ret_prev"] = (P["o1600"] - P["o0930"]).shift(1)
P["yr"] = P.index.year
def rep(name, sig, out, cost=0.783):
    d = pd.DataFrame({"sig": sig, "out": out, "yr": P["yr"]}).dropna()
    d = d[np.abs(d["out"]) < 400]     # drop contract stitches for a scan
    g = d["sig"] * d["out"] * 20 - cost * 20 * (d["sig"] != 0)
    n = int((d["sig"] != 0).sum())
    byy = g.groupby(d["yr"]).sum()
    cum = g.cumsum(); dd = float((cum.cummax() - cum).max())
    print("%-48s n=%5d  net $%9.0f  $/tr %7.1f  yrs+ %2d/%2d  DD $%7.0f  net2016+ $%9.0f" % (
        name, n, g.sum(), g.sum() / max(n, 1), int((byy > 0).sum()), len(byy), dd, g[d["yr"] >= 2016].sum()))
# A1: long 01:30 -> 04:00 next calendar day morning (the overnight after day d). Use same-row 'o0130'/'o0400'
# NOTE rows are calendar days; the 01:30 of calendar day d+1 belongs to the night after RTH day d.
nxt = P.shift(-1)
out_eu = nxt["o0400"] - nxt["o0130"]
for thr_name, cond in [("all nights", P["o1600"].notna()),
                       ("prior RTH down", (P["o1600"] - P["o0930"]) < 0),
                       ("prior RTH up", (P["o1600"] - P["o0930"]) > 0)]:
    rep("A1 long 01:30->04:00 | " + thr_name, cond.astype(float).where(cond, 0.0), out_eu)
out_night = nxt["o0925"] - P["o1615"]
for thr_name, cond in [("all nights", P["o1600"].notna()), ("prior RTH down", (P["o1600"] - P["o0930"]) < 0)]:
    rep("A1b long 16:15->09:25 | " + thr_name, cond.astype(float).where(cond, 0.0), out_night)
# A2: sign of open->15:30 decides 15:30->16:00 (RTH close) and 15:30->16:15
s = np.sign(P["o1530"] - P["o0930"])
big = (np.abs(P["o1530"] - P["o0930"]) > (P["o1530"] - P["o0930"]).abs().rolling(20).mean().shift(1))
rep("A2 late-day sign 15:30->16:00", s, P["o1600"] - P["o1530"], cost=0.533)
rep("A2 late-day sign 15:30->16:15", s, P["o1615"] - P["o1530"], cost=0.533)
rep("A2 late-day sign, big days only 15:30->16:15", s.where(big, 0.0), P["o1615"] - P["o1530"], cost=0.533)
# C1: European morning momentum
s2 = np.sign(P["o0400"] - P["o0200"])
rep("C1 sign(02:00->04:00) -> 04:00->09:25", s2, P["o0925"] - P["o0400"])
s3 = np.sign(P["o0400"] - P["o0000"])
rep("C1 sign(00:00->04:00) -> 04:00->09:25", s3, P["o0925"] - P["o0400"])
