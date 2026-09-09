"""
ROUND 40 — does the NOISE ES leader travel across BAR SIZES, and is it ES-specific? (2026-09-08/09)

Round 39 searched NOISE_1_0's own ranges on ES 5m RTH and the leader was
  lookback 62 / band_mult_long 1.0 / band_mult_short 1.75 / vwap exit / both sides / all day.
Re-searching per bar size (the house rule: never carry a bar-counted knob) put the SAME cell at
rank 2 on ES 15m and rank 5 on ES 30m. That is the opposite of the round-37 lesson on NQ, so it
gets measured properly here: the one configuration, unchanged, on ES 5m / 15m / 30m / 60m, and on
NQ at the same four bar sizes as the control (is it an ES config or a NOISE config?).

Costs: ES 0.30 pts/RT at $50/pt; NQ 0.533 at $20/pt. Window 2010-06-07..2025-06-29 (the ES 15m/30m/60m
masters end 2026-06-30, so date_to is clamped per master). Lockbox never loaded. Full house read plus
the concentration test on every cell.
"""
import os, sys, csv
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

LEADER = {"lookback": 62, "band_mult_long": 1.0, "band_mult_short": 1.75, "exit_mode": "vwap",
          "side": "Both", "window": "all_day", "flat_eod": False, "skip_holidays": False,
          "stop_mode": "fixed", "confirm_bars": 1, "daytype_mode": "skip_bot_all",
          "daytype_lo": 0.05, "daytype_hi": 0.95, "vol_skip_pct": 95.0, "stop_k": 3.75}
# read verbatim from tools/r16_results/ryr_search_noise_es5m.csv (rank 1 by R/YR among gate-passing
# rows) - NOT retyped from the truncated console line; the ES 15m search returned this SAME dict.

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
ROWS = []


def read(inst, tf, cost, mult):
    try:
        A = load_master_arrays(find_master(inst, tf, "rth", "db_noadj_rth"), **WIN)
    except Exception as e:
        print(f"{inst} {tf:4} master error {e}"); return
    r = run_backtest("augur_strategies/NOISE_1_0.py", arrays=A, params=dict(LEADER), cost_pts=cost, return_trades=True)
    if not r or not r.get("trades"):
        print(f"{inst} {tf:4} no trades"); return
    p = np.array([t[2] * mult for t in r["trades"]]); n = len(p)
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl else 99
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min()); net = float(p.sum())
    w = float((p > 0).mean()); evr = (1 - w) * (pf - 1)
    k = n // 8; f8 = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else n].sum() > 0) if k else 0
    srt = sorted(p, reverse=True); top = sum(srt[:10]); ex = np.array(srt[10:])
    exnet = float(ex.sum()); exgw = ex[ex > 0].sum(); exgl = -ex[ex < 0].sum()
    hold = np.median([t[1] - t[0] for t in r["trades"]]) * int(tf.rstrip("m"))
    row = dict(inst=inst, tf=tf, n=n, net=round(net), pf=round(pf, 3), dd=round(-dd),
               mar=round(net / -dd, 2) if dd < 0 else 99, win=round(100 * w, 1), evr=round(evr, 3),
               f8=f8, top10=round(100 * top / net) if net > 0 else 999, exnet=round(exnet),
               expf=round(exgw / exgl, 3) if exgl else 99, hold_min=round(hold))
    ROWS.append(row)
    g = "PASS" if (pf >= 1.25 and row["mar"] >= 8 and n >= 300 and row["top10"] < 90 and exnet > 0) else "fail"
    print(f"{inst} {tf:4} n={n:5} net=${net:>9,.0f} PF={pf:.3f} DD=${-dd:>8,.0f} n/DD={row['mar']:5.2f} win={100*w:4.1f} "
          f"EVR={evr:.3f} f8={f8} top10={row['top10']:>3}% ex=${exnet:>9,.0f} exPF={row['expf']:.2f} hold={row['hold_min']:>4}min  {g}", flush=True)


print("THE ES 5m SEARCH LEADER, UNCHANGED, ACROSS BAR SIZES:")
for tf in ("5m", "15m", "30m", "60m"):
    read("ES", tf, 0.30, 50.0)
print("\nCONTROL - the same configuration on NQ (is it an ES config or a NOISE config?):")
for tf in ("5m", "15m", "30m", "60m"):
    read("NQ", tf, 0.533, 20.0)
with open("tools/r16_results/r40_noise_bar_travel.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r40_noise_bar_travel.csv")
