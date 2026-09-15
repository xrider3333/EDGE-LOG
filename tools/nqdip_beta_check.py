"""
NQDIP BETA CHECK (2026-09-14) - how much of the dip book's big dollar number is simply being long a rising Nasdaq?

NQDIP is long-only, holds for days, has no stop, and sizes every mechanism to a CONSTANT $100,000 of
notional in whole micro contracts, with up to four mechanisms on at once. Over 2010-2026 the Nasdaq
100 rose roughly tenfold. So its $388,627 at run #307 could be timing skill, or it could be exposure.

This compares it against a control that has NO dip-timing at all: be long the same constant notional
on every day the daily close is above the same trend average, scaled so the control carries the SAME
AVERAGE EXPOSURE (unit-days in the market) as the dip book. Same roll-seam exclusion, same next-open
fills. The control is charged NO costs, which flatters it - so if the dip book still wins, the win is
understated, not overstated.

Also reported: dollars per unit-day held, the held-back year, and year by year.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2026-08-24")        # run #307's own window
LB0 = pd.Timestamp("2025-08-24")                                  # run #307's own held-back split
NQDIP_CROWN = {"rsi_len": 5, "pb_hold": 14, "cap_mult": 1.0, "pb_ema": 5, "cost_pts_rt": 0.783,
               "trend_len": 100, "rsi_exit": 9, "cost_bps": 2.0, "notional": 100000, "use_pb": True,
               "cap_hold": 5, "use_rsi": True, "cap_q": 0.3, "rsi_thr": 30, "dbl_n": 10,
               "use_cap": True, "use_dbl": True}                  # run #307's champion, from the run doc

sp = ilu.spec_from_file_location("nqdip", "augur_strategies/NQDIP_1_0.py")
M = ilu.module_from_spec(sp); sp.loader.exec_module(M)

A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
idx = pd.DatetimeIndex(A["index"])
r = run_backtest("augur_strategies/NQDIP_1_0.py", arrays=A, params=NQDIP_CROWN, cost_pts=0.0, return_trades=True)
T = pd.DataFrame({"ent": [t[0] for t in r["trades"]], "ex": [t[1] for t in r["trades"]],
                  "pnl": [t[2] for t in r["trades"]]})
T["eday"] = [idx[i].tz_localize(None).normalize() for i in T.ent]
T["xday"] = [idx[i].tz_localize(None).normalize() for i in T.ex]
print(f"dip book reproduced: {len(T)} trades, net ${T.pnl.sum():,.0f}  (run #307 app score: 654 trades, $388,627)")

# daily bars exactly as the plugin builds them
bounds = M._session_bounds(np.asarray(A["day_id"]), len(A["close"]))
o, c = np.asarray(A["open"], float), np.asarray(A["close"], float)
do = np.array([o[a] for a, b in bounds]); dc = np.array([c[b - 1] for a, b in bounds])
days = pd.DatetimeIndex([idx[a].tz_localize(None).normalize() for a, b in bounds])
seams = set(M.detect_roll_seams(do, dc, [idx[a] for a, b in bounds]))
trend = M._sma(dc, NQDIP_CROWN["trend_len"])

# exposure of the dip book in unit-days (a trade held from day de open to day dx open = dx-de unit-days)
pos = {d: i for i, d in enumerate(days)}
unit_days = sum(pos[x] - pos[e] for e, x in zip(T.eday, T.xday))
first = NQDIP_CROWN["trend_len"] + 1
span = len(days) - first
avg_units = unit_days / span
print(f"dip book exposure: {unit_days:,} unit-days over {span:,} trading days = {avg_units:.2f} units on average"
      f"  (maximum possible 4)")

# control: long avg_units x constant $100k notional from day d open to d+1 open, whenever close[d-1] > trend[d-1]
ctl = np.zeros(len(days)); inmkt = np.zeros(len(days), bool)
for d in range(first, len(days) - 1):
    if not (dc[d - 1] > trend[d - 1]):
        continue
    if (d + 1) in seams:                      # the stitch night is not market movement
        pts = dc[d] - do[d]
    else:
        pts = do[d + 1] - do[d]
    k = max(1, int(round(100000.0 / (do[d] * 2.0))))
    ctl[d] = pts * 2.0 * k
    inmkt[d] = True
trend_days = int(inmkt.sum())
scale = unit_days / trend_days
ctl_s = pd.Series(ctl * scale, index=days)
dip_s = pd.Series(T.pnl.values, index=T.xday.values).groupby(level=0).sum().reindex(days, fill_value=0.0)


def dd(s):
    cum = s.sort_index().cumsum(); return float(-(cum - cum.cummax()).min())


def line(nm, s):
    pre, lb = s[s.index < LB0], s[s.index >= LB0]
    print(f"  {nm:52} net ${s.sum():>9,.0f}  DD ${dd(s):>7,.0f}  net/DD {s.sum()/dd(s):5.2f}"
          f" | held-back ${lb.sum():>8,.0f}")


print(f"\ncontrol is in the market on {trend_days:,} days and is scaled x{scale:.3f} to the SAME unit-days as the dip book\n")
line("DIP BOOK (run #307 champion, costs charged)", dip_s)
line("CONTROL: trend-filtered long, same exposure, NO costs", ctl_s)
line("CONTROL unscaled: always long above trend, 1 unit", pd.Series(ctl, index=days))
print(f"\n  dollars per unit-day held: dip book ${T.pnl.sum()/unit_days:,.1f}   control ${ctl_s.sum()/unit_days:,.1f}")

print("\n  year by year (net $):")
print(f"    {'year':5} {'dip book':>10} {'control':>10}  dip minus control")
wins = 0; yrs = 0
for y in range(2011, 2026):
    a = dip_s[(dip_s.index.year == y)].sum(); b = ctl_s[(ctl_s.index.year == y)].sum()
    wins += a > b; yrs += 1
    print(f"    {y:5} {a:>10,.0f} {b:>10,.0f}  {a-b:>+10,.0f}")
print(f"    dip book beats the same-exposure control in {wins} of {yrs} full years")
