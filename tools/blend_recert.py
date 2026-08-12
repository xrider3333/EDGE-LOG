"""Recertify the book baseline: ORB 3.1 #125 (NQ 5m) x ENGU-Q NQ 1m deploy, 1:1,
now with the CERTIFIED ENGU-Q params (ENGUQ_1M_1_0.NQ_DEPLOY_PARAMS_149).

*** WARNING (2026-08-11) — the ORB leg here (ORB_125) reproduces a LOOK-AHEAD bug. ***
Touch-entry ORB fills the instant price touches the range edge (intrabar), but
vol_filter=1.25 gates that fill on the breakout bar's FINISHED volume, which does not
exist yet at fill time. That leak is ~91% of the ORB leg's edge, so the $835,351 book
total below is NOT live-achievable. This script "recertifying" that number only proves
the engine still reproduces the old (leaking) figure — it is not a fresh validation of
tradeable edge. See ORB.md (repo root, top banner) for the full writeup.

Round-3 documented baseline (2026-07-13): net $835,351.08 / maxDD -$60,097.59 /
net-DD 13.90 / 0 losing years in 17 / daily Pearson +0.07 / worst day -$13,797.
Window PINNED 2010-06-07 -> 2026-06-30, both legs costed 0.533 pts RT x $20,
exit-date daily PnL, union of dates 0-filled. Usage: python tools/blend_recert.py
"""
import sys, pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest, find_master, load_master_arrays
import importlib.util
_s = importlib.util.spec_from_file_location("enguq", REPO / "augur_strategies" / "ENGUQ_1M_1_0.py")
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
ENG_149 = _m.NQ_DEPLOY_PARAMS_149

# LEAKING CONFIG (see warning above): vol_filter gates on future-known volume. Historical
# reference only - not live-achievable. See ORB.md.
ORB_125 = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
               breakout_buf=0.0, target_R=0.0, partial_exit_R=0.0, trail_bars=5,
               flat_eod=True)
WIN = ("2010-06-07", "2026-06-30")

def leg(strat, tf, params):
    arr = load_master_arrays(find_master("NQ", tf, "rth"), date_from=WIN[0], date_to=WIN[1])
    r = run_backtest(strat, arrays=arr, params=params, cost_pts=0.533, return_trades=True)
    idx = arr["index"]
    d = {}
    for t in r["trades"]:
        day = pd.Timestamp(idx[int(t[1])]).date()
        d[day] = d.get(day, 0.0) + float(t[2]) * 20.0
    return r, pd.Series(d).sort_index()

orb_r, orb = leg("ORB_3_1.py", "5m", ORB_125)
eng_r, eng = leg("ENGUQ_1M_1_0.py", "1m", ENG_149)
print(f"ORB leg   : n={orb_r['num_trades']} net=${orb.sum():,.0f} PF={orb_r['profit_factor']:.3f} "
      f"(expect n=4064 / $360,640 / 1.611)")
print(f"ENGU-Q leg: n={eng_r['num_trades']} net=${eng.sum():,.0f} PF={eng_r['profit_factor']:.3f} "
      f"(expect n=2048 / ~$474.7-477.5k / ~1.41)")

df = pd.DataFrame({"orb": orb, "eng": eng}).fillna(0.0).sort_index()
df["combo"] = df["orb"] + df["eng"]
cum = df["combo"].cumsum()
dd = float((cum - cum.cummax()).min())
net = float(df["combo"].sum())
corr = float(df["orb"].corr(df["eng"]))
years = df.groupby(pd.DatetimeIndex(df.index).year)["combo"].sum()
losing = years[years < 0]
worst_day = df["combo"].min()
print(f"\nBLEND 1:1 : net=${net:,.0f}  maxDD=${dd:,.0f}  net/DD={net/abs(dd):.2f}  "
      f"corr={corr:+.3f}  worst day=${worst_day:,.0f}")
print(f"years: {len(years)}  losing: {len(losing)} {dict(losing.round(0)) if len(losing) else ''}")
print("by year:", {int(y): round(v) for y, v in years.items()})
print("\nvs round-3 baseline: $835,351 / -$60,098 / 13.90 / 0 losing / corr +0.07 / worst -$13,797")
