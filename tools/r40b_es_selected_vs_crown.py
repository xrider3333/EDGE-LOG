"""
ROUND 40b — a NOISE configuration selected ENTIRELY ON ES, graded on NQ against the crown (2026-09-09).

Why this is interesting: the round-39 search only ever saw the ES 5-minute tape. It never read an NQ
bar. So running its leader on NQ is an out-of-sample test in the INSTRUMENT dimension - the usual
walk-forward tests a config on unseen TIME; this tests it on an unseen MARKET. Round 40 found it clears
the house bar on NQ at 5m/15m/30m/60m. This file grades it head-to-head against the paper crown
(NOISE_1_1_SBS_V90 = run #243's configuration) on the CROWN'S OWN window and lockbox split, so the two
are comparable, with the concentration test on both.

Window: run #243's (2010-06-07..2026-08-12), lockbox = the last 12 months. NQ 5m RTH, 0.533/RT, $20/pt.
The crown's lockbox has been read before, so treat the lockbox column as a comparison, not a fresh test.
"""
import os, sys, csv
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

ES_SELECTED = {"lookback": 62, "band_mult_long": 1.0, "band_mult_short": 1.75, "exit_mode": "vwap",
               "side": "Both", "window": "all_day", "flat_eod": False, "skip_holidays": False,
               "stop_mode": "fixed", "confirm_bars": 1, "daytype_mode": "skip_bot_all",
               "daytype_lo": 0.05, "daytype_hi": 0.95, "vol_skip_pct": 95.0, "stop_k": 3.75}
WIN = dict(date_from="2010-06-07", date_to="2026-08-12")
LB0 = "2025-08-12"


def crown_params():
    sp = ilu.spec_from_file_location("m", "augur_strategies/NOISE_1_1_SBS_V90.py")
    m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
idx = pd.DatetimeIndex(A["index"]); cut = pd.Timestamp(LB0, tz=idx.tz)
ROWS = []


def stats(label, stage, p):
    p = np.asarray(p, float)
    if len(p) == 0:
        print(f"{label:26} {stage:10} no trades"); return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl else 99
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min()); net = float(p.sum())
    w = float((p > 0).mean()); k = len(p) // 8
    f8 = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0) if k else 0
    srt = sorted(p, reverse=True); top = sum(srt[:10]); ex = np.array(srt[10:])
    exnet = float(ex.sum()) if len(ex) else 0.0
    row = dict(config=label, stage=stage, n=len(p), net=round(net), pf=round(pf, 3), dd=round(-dd),
               mar=round(net / -dd, 2) if dd < 0 else 99, win=round(100 * w, 1),
               evr=round((1 - w) * (pf - 1), 3), f8=f8,
               top10=round(100 * top / net) if net > 0 else 999, exnet=round(exnet))
    ROWS.append(row)
    print(f"{label:26} {stage:10} n={len(p):5} net=${net:>9,.0f} PF={pf:.3f} DD=${-dd:>8,.0f} "
          f"n/DD={row['mar']:6.2f} win={100*w:4.1f} f8={f8} top10={row['top10']:>3}% ex=${exnet:>9,.0f}", flush=True)


for label, params in (("ES-SELECTED on NQ", ES_SELECTED), ("NQ CROWN #243 card", crown_params())):
    r = run_backtest("augur_strategies/NOISE_1_0.py" if label.startswith("ES") else "augur_strategies/NOISE_1_1_SBS_V90.py",
                     arrays=A, params=params, cost_pts=0.533, return_trades=True)
    df = pd.DataFrame({"t": [idx[t[0]] for t in r["trades"]], "pnl": [t[2] * 20 for t in r["trades"]]})
    stats(label, "selection", df[df.t < cut].pnl.values)
    stats(label, "lockbox", df[df.t >= cut].pnl.values)
    stats(label, "whole", df.pnl.values)
with open("tools/r16_results/r40b_es_selected_vs_crown.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r40b_es_selected_vs_crown.csv")
