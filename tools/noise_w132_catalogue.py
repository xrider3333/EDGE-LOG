"""w132 catalogue re-runs (NOISE lane), NQ 5m RTH db_noadj_rth, data cut 2025-06-30, 1 contract, cost 0.783 pt, $20/pt.
Daily $ CSVs for owner_screen.py, in C:/EdgeLog/manager/reports/w132_noise/cat_*.csv.
- LDM: sign of (09:55 close - prior RTH close) [gap-inclusive first half-hour], enter 15:30 bar open that way, out at the close.
- MOC: long at the 15:00 bar open, out at the close (last-hour drift).
- MOC_TREND: as MOC but in the direction of the day so far (15:00 open vs session open).
PYTHONPATH=. python tools/noise_w132_catalogue.py
"""
import numpy as np
import pandas as pd

from augur_engine.data import find_master, load_master_arrays

OUT = r"C:/EdgeLog/manager/reports/w132_noise/cat_%s.csv"
COST, PV = 0.783, 20.0
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2016-05-01", date_to="2025-06-30")
ix = pd.DatetimeIndex(A["index"]).tz_convert("America/New_York").tz_localize(None)
df = pd.DataFrame({k: np.asarray(A[k], float) for k in ("open", "close")}, index=ix)
df["d"], df["t"] = ix.normalize(), ix.strftime("%H:%M")
rows = {"LDM": [], "MOC": [], "MOC_TREND": []}
prev_close = None
for d, s in df.groupby("d"):
    t = s.set_index("t")
    last = s.close.iloc[-1]
    if s.t.iloc[-1] < "15:55":           # half day: skip, keep its close as the next reference
        prev_close = last
        continue
    if prev_close is not None and "09:55" in t.index and "15:30" in t.index:
        sd = np.sign(t.loc["09:55", "close"] - prev_close)
        if sd:
            rows["LDM"].append((d, sd * (last - t.loc["15:30", "open"]) - COST))
    if "15:00" in t.index:
        e = t.loc["15:00", "open"]
        rows["MOC"].append((d, last - e - COST))
        sd = np.sign(e - s.open.iloc[0])
        if sd:
            rows["MOC_TREND"].append((d, sd * (last - e) - COST))
    prev_close = last
for k, v in rows.items():
    x = pd.DataFrame(v, columns=["date", "pts"])
    x["pnl"], x["trades"] = x.pts * PV, 1
    x[["date", "pnl", "trades"]].to_csv(OUT % k, index=False)
    print(k, len(x), "trades, net $%.0f, gross/trade %.3f pts" % (x.pnl.sum(), x.pts.mean() + COST))
