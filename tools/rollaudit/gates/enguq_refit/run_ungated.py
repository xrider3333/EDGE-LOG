"""Follow-up: separate the base-strategy effect from the gate's own effect.

Reuses the same base trade lists run_study.py already built on each master (1,355
noadj / 1,389 fadj). Computes UNGATED per-stretch stats (same WF/LB split, LB from
2025-09-25) and the GATE'S OWN effect = gated minus ungated (net $ and return/DD).
Augments results.json with per-trade pnl ($) and this new section. READ-ONLY.
"""
import os
import sys
import json

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
GATES = os.path.join(REPO, "tools", "rollaudit", "gates")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "rollaudit"))
sys.path.insert(0, GATES)

import numpy as np
import pandas as pd

from common import leg_config, load_raw_arrays, get_trades, yrs_between, stats_block, NQ_MULT
from augur_engine.data import find_master, load_master_arrays

HERE = os.path.dirname(__file__)
RESULTS_PATH = os.path.join(HERE, "results.json")

LEG_KEY = "ENGUQ_ER_H"


def rodd(net_usd, years, dd_usd):
    """(net/yrs) / |DD| -- undefined (None) when there is no drawdown to divide by."""
    if not years or dd_usd is None or dd_usd == 0:
        return None
    return (net_usd / years) / abs(dd_usd)


def ungated_stretch_stats(arrays, trades):
    T = sorted([tuple(t) for t in trades], key=lambda t: t[0])
    idx = pd.DatetimeIndex(arrays["index"])
    idx_last = arrays["index"][-1]
    lb_start = idx_last - pd.DateOffset(months=12)
    entry_ts = idx[[min(int(t[0]), len(idx) - 1) for t in T]]
    is_lb = entry_ts >= lb_start
    years_wf = yrs_between(arrays["index"][0], lb_start)
    years_lb = yrs_between(lb_start, idx_last)

    pnl_pts = np.array([float(t[2]) for t in T])
    pnl_usd = pnl_pts * NQ_MULT

    wf = stats_block(pnl_pts[~is_lb], years=years_wf)   # stats_block applies NQ_MULT itself
    lb = stats_block(pnl_pts[is_lb], years=years_lb)
    return dict(lb_start=str(lb_start), years_wf=years_wf, years_lb=years_lb,
                wf=wf, lb=lb, pnl_usd=[float(x) for x in pnl_usd],
                entry_bars=[int(t[0]) for t in T])


def main():
    leg = leg_config(LEG_KEY)

    arrays_noadj, master_noadj = load_raw_arrays(leg)
    trades_noadj, _ = get_trades(leg, arrays_noadj)

    master_fadj = find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"),
                               source="db_fadj_eth")
    arrays_fadj = load_master_arrays(master_fadj, date_from=leg.get("history_from"), date_to=None)
    trades_fadj, _ = get_trades(leg, arrays_fadj)

    ungated = dict(noadj=ungated_stretch_stats(arrays_noadj, trades_noadj),
                   fadj=ungated_stretch_stats(arrays_fadj, trades_fadj))

    with open(RESULTS_PATH) as f:
        results = json.load(f)

    # sanity: entry_bars order must line up with the already-saved gated entry_bars
    for cond in ("noadj", "fadj"):
        assert ungated[cond]["entry_bars"] == results["gated"][cond]["entry_bars"], \
            f"{cond}: entry-bar order mismatch between run_study.py and this rerun"

    # per-trade pnl ($) into results.json, aligned with the existing entry_bars/keep order
    trades_map = {"noadj": trades_noadj, "fadj": trades_fadj}
    for cond in ("noadj", "fadj"):
        T = sorted([tuple(t) for t in trades_map[cond]], key=lambda t: t[0])
        results["gated"][cond]["pnl_usd"] = [float(t[2]) * NQ_MULT for t in T]

    gate_effect = {}
    for cond in ("noadj", "fadj"):
        g = results["gated"][cond]
        u = ungated[cond]
        eff = {}
        for stretch in ("wf", "lb"):
            gs, us = g[stretch], u[stretch]
            g_rodd = rodd(gs["net_usd"], u[f"years_{stretch}"], gs["max_dd_usd"])
            u_rodd = rodd(us["net_usd"], u[f"years_{stretch}"], us["max_dd_usd"])
            eff[stretch] = dict(
                ungated_n=us["n"], gated_n=gs["n"],
                ungated_net_usd=us["net_usd"], gated_net_usd=gs["net_usd"],
                delta_net_usd=gs["net_usd"] - us["net_usd"],
                ungated_dd_usd=us["max_dd_usd"], gated_dd_usd=gs["max_dd_usd"],
                ungated_rodd=u_rodd, gated_rodd=g_rodd,
                delta_rodd=(None if (g_rodd is None or u_rodd is None) else g_rodd - u_rodd),
            )
        gate_effect[cond] = eff

    results["ungated"] = ungated
    results["gate_effect"] = gate_effect

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2, default=str)

    for cond in ("noadj", "fadj"):
        u = ungated[cond]
        print(f"[{cond}] UNGATED WF n={u['wf']['n']} net=${u['wf']['net_usd']:.0f} "
              f"dd=${u['wf']['max_dd_usd']:.0f} roc={u['wf']['roc_pct_yr']:.2f}%/yr "
              f"sortino={u['wf']['sortino']:.2f}", flush=True)
        print(f"[{cond}] UNGATED LB n={u['lb']['n']} net=${u['lb']['net_usd']:.0f} "
              f"dd=${u['lb']['max_dd_usd']:.0f} roc={u['lb']['roc_pct_yr']:.2f}%/yr "
              f"sortino={u['lb']['sortino']:.2f}", flush=True)
    for cond in ("noadj", "fadj"):
        for stretch in ("wf", "lb"):
            e = gate_effect[cond][stretch]
            print(f"[{cond}] GATE EFFECT {stretch.upper()}: delta_net=${e['delta_net_usd']:.0f} "
                  f"ungated_RoDD={e['ungated_rodd']} gated_RoDD={e['gated_rodd']} "
                  f"delta_RoDD={e['delta_rodd']}", flush=True)
    print(f"wrote {RESULTS_PATH}", flush=True)


if __name__ == "__main__":
    main()
