"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
Build NQ and ES daily RTH OHLC (09:30-16:00 ET) from the 5m RTH no-adj masters + the house roll-seam list.
Saved once to parquet-free CSV in the scratchpad so later scans stay memory-light."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_strategies")
from augur_engine.data import find_master, load_master_arrays
from ONDRIFT_1_0 import detect_roll_seams
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
for inst in ("NQ", "ES"):
    A = load_master_arrays(find_master(inst, "5m", "rth", "db_noadj_rth"), date_from="2009-06-01", date_to="2026-09-24")
    df = pd.DataFrame({"o": A["open"], "h": A["high"], "l": A["low"], "c": A["close"], "v": A["volume"]}, index=A["index"])
    df["d"] = df.index.tz_localize(None).normalize()
    D = df.groupby("d").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"), n=("o", "size"))
    seams = detect_roll_seams(D["o"].values, D["c"].values, list(D.index))
    D["seam"] = False
    D.iloc[seams, D.columns.get_loc("seam")] = True
    D.to_csv(os.path.join(CACHE, "%s_daily_rth.csv" % inst))
    print(inst, len(D), "days", D.index[0].date(), D.index[-1].date(), "seams", len(seams))
