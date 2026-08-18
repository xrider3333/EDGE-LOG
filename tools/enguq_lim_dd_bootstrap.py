"""BATTERY S -- is the net/DD peak at limit 0.65-0.70 real, or a drawdown-path artifact?

WHY THIS TEST EXISTS
The fine sweep (lim_plateau.py) showed something the coarse battery-O grid missed: net/DD
peaks at limit 0.65 (9.87) and 0.70 (10.24), and BOTH clear the pre-registered net/DD >=
9.50 bar that every previously-tested limit cell failed. Taken at face value that would
re-crown the adopted 0.50.

But max drawdown is a SINGLE-PATH statistic -- one unlucky sequence sets it -- and the
sweep shows it swinging violently between adjacent cells that should behave almost
identically: 0.60 -> $65,064, 0.65 -> $53,130, 0.70 -> $51,614, 0.80 -> $59,189. A $13k
move between neighbours is a strong hint the DD ordering is noise, not signal. Net and PF
move smoothly over the same cells; only DD lurches. So net/DD inherits the noise.

METHOD: block bootstrap on the DAILY pnl series (block = 20 trading days, preserves
autocorrelation and drawdown clustering), 5,000 resamples, seed fixed, PAIRED by calendar
day so both limit levels see the identical resampled day order. Then ask:
  Q1  How often does 0.70's DD actually beat 0.50's?
  Q2  Is the net/DD difference (0.70 - 0.50) distinguishable from zero?
  Q3  How often does 0.70 clear net/DD >= 9.50? (i.e. is clearing the bar reproducible,
      or did the observed path just happen to land above it?)
A peak that only exists on the one realised path will show ~50% win rates and a CI
straddling zero. A real improvement will show a consistent margin.
"""
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_strategies.ENGUQ_1M_ETH_LIM_1_0 import run_backtest         # noqa: E402

MULT, COST = 20.0, 0.533
CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5,
            regime_len=0)
LEVELS = [0.00, 0.50, 0.65, 0.70]
BLOCK, N_BOOT, SEED = 20, 5000, 42
BAR = 9.50

OUT = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15"
       r"\scratchpad\lim_dd_bootstrap.json")

arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                         date_from=None, date_to="2026-06-30")
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v, day, idx = arr["volume"], arr["day_id"], arr["index"]


def daily_series(limit_atr):
    """Dollar PnL aggregated to the trade's EXIT date -- one row per calendar day."""
    res = run_backtest(o, h, l, c, volumes=v, day_id=day, index=idx,
                       return_trades=True, limit_atr=limit_atr, **CERT)
    tr = res["trades"]
    d = np.array([(t[2] - COST) * MULT for t in tr])
    ext = pd.to_datetime([idx[int(t[1])] for t in tr]).tz_localize(None).normalize()
    return pd.Series(d, index=ext).groupby(level=0).sum()


print("building daily series ...", flush=True)
series = {L: daily_series(L) for L in LEVELS}
all_days = sorted(set().union(*[set(s.index) for s in series.values()]))
frame = pd.DataFrame({L: series[L].reindex(all_days).fillna(0.0) for L in LEVELS})
print(f"  {len(frame)} trading days with activity\n", flush=True)


def net_dd(x):
    net = float(x.sum())
    cum = np.cumsum(x)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    return net, dd, (net / dd if dd else float("inf"))


obs = {}
for L in LEVELS:
    n_, d_, r_ = net_dd(frame[L].values)
    obs[L] = dict(net=n_, dd=d_, net_dd=r_)
    print(f"observed  limit {L:.2f}:  net=${n_:11,.0f}  DD=${d_:9,.0f}  net/DD={r_:6.2f}")

rng = np.random.default_rng(SEED)
n_days = len(frame)
n_blocks = int(np.ceil(n_days / BLOCK))
mat = {L: frame[L].values for L in LEVELS}

boot = {L: {"net": [], "dd": [], "net_dd": []} for L in LEVELS}
for _ in range(N_BOOT):
    starts = rng.integers(0, max(n_days - BLOCK, 1), size=n_blocks)
    order = np.concatenate([np.arange(s, s + BLOCK) for s in starts])[:n_days]
    order = order[order < n_days]
    for L in LEVELS:                      # SAME order for every level -> paired
        n_, d_, r_ = net_dd(mat[L][order])
        boot[L]["net"].append(n_)
        boot[L]["dd"].append(d_)
        boot[L]["net_dd"].append(r_)

for L in LEVELS:
    for k in boot[L]:
        boot[L][k] = np.array(boot[L][k])

print("\n" + "=" * 76)
print("Q1/Q2 -- 0.70 vs 0.50 (paired, 5,000 block bootstraps)")
dd_diff = boot[0.50]["dd"] - boot[0.70]["dd"]          # positive = 0.70 has SMALLER DD
nd_diff = boot[0.70]["net_dd"] - boot[0.50]["net_dd"]  # positive = 0.70 better
net_diff = boot[0.70]["net"] - boot[0.50]["net"]
res = {}
for name, arr_ in [("DD advantage of 0.70 ($)", dd_diff),
                   ("net/DD advantage of 0.70", nd_diff),
                   ("net advantage of 0.70 ($)", net_diff)]:
    lo, hi = np.percentile(arr_, [2.5, 97.5])
    frac = float((arr_ > 0).mean())
    straddles = lo < 0 < hi
    res[name] = dict(mean=float(arr_.mean()), ci=[float(lo), float(hi)],
                     frac_positive=frac, straddles_zero=bool(straddles))
    print(f"  {name:28s} mean={arr_.mean():10,.2f}  95% CI [{lo:10,.2f}, {hi:10,.2f}]  "
          f"wins {frac*100:5.1f}%  {'STRADDLES ZERO' if straddles else 'distinguishable'}")

print("\n" + "=" * 76)
print(f"Q3 -- how often does each level clear net/DD >= {BAR}?")
clear = {}
for L in LEVELS:
    f = float((boot[L]["net_dd"] >= BAR).mean())
    clear[L] = f
    print(f"  limit {L:.2f}: clears the bar in {f*100:5.1f}% of resamples "
          f"(observed {obs[L]['net_dd']:.2f})")

print("\n" + "=" * 76)
print("DD stability -- bootstrap spread of max drawdown per level")
for L in LEVELS:
    a = boot[L]["dd"]
    lo, hi = np.percentile(a, [2.5, 97.5])
    print(f"  limit {L:.2f}: DD 95% CI [${lo:,.0f}, ${hi:,.0f}]  width ${hi-lo:,.0f}  "
          f"(observed ${obs[L]['dd']:,.0f})")

json.dump({"observed": {str(k): v for k, v in obs.items()},
           "comparisons": res,
           "clear_bar_frac": {str(k): v for k, v in clear.items()},
           "dd_ci": {str(L): [float(x) for x in np.percentile(boot[L]["dd"], [2.5, 97.5])]
                     for L in LEVELS},
           "params": dict(block=BLOCK, n_boot=N_BOOT, seed=SEED, bar=BAR)},
          open(OUT, "w"), indent=1)
print("\nSAVED ->", OUT)
