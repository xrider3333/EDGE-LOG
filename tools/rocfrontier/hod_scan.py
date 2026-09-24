"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
Hour-of-day drift scan, NQ 5m ETH (db_noadj_eth). SCAN ONLY - no belief until a strategy file exists.
Window: 2010-06-07 .. 2025-06-30 (pre-lockbox). Bar timestamps are OPEN times (ET).
Per 30-min slot: mean close-to-close points of the bars that OPEN inside the slot, in $ at 1 NQ (x20).
Outlier bars (|ret| > 12x rolling median abs ret) dropped = contract stitches.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays
m = find_master("NQ", "5m", "eth", "db_noadj_eth")
A = load_master_arrays(m, date_from="2010-06-07", date_to="2025-06-30")
idx = A["index"]; c = A["close"]; o = A["open"]
df = pd.DataFrame({"o": o, "c": c}, index=idx)
df["ret"] = df["c"].diff()
# gap between bars across sessions is included in the first bar's ret; flag stitches
med = df["ret"].abs().rolling(2000, min_periods=200).median()
df["bad"] = df["ret"].abs() > 12 * med
df.loc[df["bad"], "ret"] = np.nan
df["slot"] = df.index.hour * 2 + (df.index.minute >= 30).astype(int)
df["yr"] = df.index.year
print("bars", len(df), "dropped stitches", int(df["bad"].sum()))
tab = df.groupby("slot")["ret"].agg(["mean", "count"])
tab["usd_per_day"] = tab["mean"] * 6 * 20  # 6 bars per 30 min
byyr = df.pivot_table(index="slot", columns="yr", values="ret", aggfunc="sum") * 20
for s in tab.index:
    h, mm = divmod(s, 2)
    row = byyr.loc[s]
    pos = int((row > 0).sum())
    print("%02d:%02d  mean/bar %+6.3f pts  $/day-slot %+7.2f  yrs+ %2d/%d  total$ %+10.0f  last5y$ %+9.0f" % (
        h, 30 * mm, tab.loc[s, "mean"], tab.loc[s, "usd_per_day"], pos, len(row.dropna()), row.sum(),
        row[[y for y in row.index if y >= 2020]].sum()))
