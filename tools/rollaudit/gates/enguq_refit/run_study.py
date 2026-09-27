"""ENGUQ_ER_H gate refit on FADJ_NQ_1m_ETH -- READ-ONLY research driver.

Reuses tools/rollaudit/gates/common.py (already proved it reproduces the served
ENGUQ_ER_H artifact exactly). This script:
  1. Rebuilds the NOADJ control exactly as gate_live does and confirms max
     predict_proba diff vs the served .pkl is 0.0.
  2. Reruns the BASE STRATEGY BACKTEST *and* the gate features on
     find_master('NQ','1m','eth','db_fadj_eth') -- so the trade list itself is
     recomputed on corrected prices, not just re-priced after the fact.
  3. Evaluates both with augur_engine.ml_gate.gate_trades, same threshold /
     refit cadence / WF-LB split (last 12 months) as REPORT_2026-09-26.txt.
  4. Diffs the two base trade lists (appear/vanish by entry bar) and the
     take/skip flip share on trades common to both.
  5. Flags trades touching the two undocumented 2026 splice bars / estimated
     roll offsets.

Writes results.json next to this file. OMP_NUM_THREADS=1 set by common.py.
"""
import os
import sys
import json
import time

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
GATES = os.path.join(REPO, "tools", "rollaudit", "gates")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "rollaudit"))
sys.path.insert(0, GATES)

import numpy as np
import pandas as pd
import joblib

from common import (leg_config, load_raw_arrays, get_trades, fit_artifact_model,
                     ARTIFACT_DIR, yrs_between, stats_block,
                     SPLICE_TIMES_ET, SPLICE_DAYS_ET, mask_splice_trades)
from augur_engine.data import find_master, load_master_arrays
from augur_engine.ml_gate import gate_trades

LEG_KEY = "ENGUQ_ER_H"
OUT = os.path.join(os.path.dirname(__file__), "results.json")


def split_wf_lb(entry_ts, lb_start):
    return entry_ts >= lb_start


def evaluate(label, leg, arrays, trades, seed=42):
    g = leg["gate"]
    t0 = time.time()
    T = sorted([tuple(t) for t in trades], key=lambda t: t[0])
    out = gate_trades(arrays, T, model=g["model"], threshold=g["threshold"],
                       min_history=30, refit_every=25, seed=seed)
    dt = time.time() - t0
    keep = out["keep"]

    idx = pd.DatetimeIndex(arrays["index"])
    idx_last = arrays["index"][-1]
    lb_start = idx_last - pd.DateOffset(months=12)
    entry_ts = idx[[min(int(t[0]), len(idx) - 1) for t in T]]
    is_lb = split_wf_lb(entry_ts, lb_start)

    years_wf = yrs_between(arrays["index"][0], lb_start)
    years_lb = yrs_between(lb_start, idx_last)
    years_full = yrs_between(arrays["index"][0], idx_last)

    taken = [t for t, k in zip(T, keep) if k]
    taken_pnls = np.array([t[2] for t in taken])
    taken_is_lb = is_lb[keep]

    wf = stats_block(taken_pnls[~taken_is_lb], years=years_wf)
    lb = stats_block(taken_pnls[taken_is_lb], years=years_lb)
    full = stats_block(taken_pnls, years=years_full)

    # splice / estimated-offset touch check -- on ALL base trades (taken or not)
    kept_ns, masked_ns = mask_splice_trades(T, arrays["index"])
    kept_taken, masked_taken = mask_splice_trades(taken, arrays["index"])

    print(f"[{label}] base={len(T)} taken={int(keep.sum())} "
          f"WF net=${wf['net_usd']:.0f} dd=${wf['max_dd_usd']:.0f} "
          f"LB net=${lb['net_usd']:.0f} dd=${lb['max_dd_usd']:.0f} "
          f"splice-touch base={len(masked_ns)} taken={len(masked_taken)} (dt={dt:.1f}s)",
          flush=True)

    return dict(label=label, n_total=len(T), n_taken=int(keep.sum()),
                lb_start=str(lb_start), years_wf=years_wf, years_lb=years_lb,
                wf=wf, lb=lb, full=full,
                entry_bars=[int(t[0]) for t in T],
                exit_bars=[int(t[1]) for t in T],
                keep=[bool(x) for x in keep],
                splice_touch_base=len(masked_ns), splice_touch_taken=len(masked_taken))


def main():
    leg = leg_config(LEG_KEY)
    print(f"leg={LEG_KEY} strategy={leg['strategy']} params={leg['params']} "
          f"gate={leg['gate']} history_from={leg.get('history_from')}", flush=True)

    # ---------- 1. CONTROL: db_noadj_eth, must reproduce served artifact ----------
    t0 = time.time()
    arrays_noadj, master_noadj = load_raw_arrays(leg)
    print(f"noadj master={master_noadj['filename']} source={master_noadj.get('source')} "
          f"bars={len(arrays_noadj['index'])} span={arrays_noadj['index'][0]}.."
          f"{arrays_noadj['index'][-1]} (dt={time.time()-t0:.1f}s)", flush=True)
    trades_noadj, res_noadj = get_trades(leg, arrays_noadj)
    print(f"noadj n_trades={len(trades_noadj)} (dt={time.time()-t0:.1f}s)", flush=True)

    art = joblib.load(os.path.join(ARTIFACT_DIR, f"{LEG_KEY}.pkl"))
    reproduces_count = (len(trades_noadj) == art["n_trades_trained"])
    mdl_ctrl, X_ctrl, y_ctrl, P_ctrl, names_ctrl = fit_artifact_model(
        leg, arrays_noadj, trades_noadj, seed=leg["gate"].get("seed", 42))
    my_proba = mdl_ctrl.predict_proba(X_ctrl)[:, 1]
    served_proba = art["pipe"].predict_proba(X_ctrl)[:, 1]
    maxdiff_control = float(np.max(np.abs(my_proba - served_proba)))
    print(f"CONTROL reproduction: n_trades_trained served={art['n_trades_trained']} "
          f"local={len(trades_noadj)} match={reproduces_count} "
          f"max_proba_diff={maxdiff_control:.10f}", flush=True)

    # ---------- 2. FADJ: base backtest AND features on db_fadj_eth ----------
    t1 = time.time()
    master_fadj = find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"),
                               source="db_fadj_eth")
    assert master_fadj is not None, "no FADJ master found"
    arrays_fadj = load_master_arrays(master_fadj, date_from=leg.get("history_from"), date_to=None)
    print(f"fadj master={master_fadj['filename']} source={master_fadj.get('source')} "
          f"bars={len(arrays_fadj['index'])} span={arrays_fadj['index'][0]}.."
          f"{arrays_fadj['index'][-1]} (dt={time.time()-t1:.1f}s)", flush=True)
    trades_fadj, res_fadj = get_trades(leg, arrays_fadj)
    print(f"fadj n_trades={len(trades_fadj)} (dt={time.time()-t1:.1f}s)", flush=True)

    mdl_fadj, X_fadj, y_fadj, P_fadj, names_fadj = fit_artifact_model(
        leg, arrays_fadj, trades_fadj, seed=leg["gate"].get("seed", 42))
    print(f"fadj model fit ok, X.shape={X_fadj.shape}", flush=True)

    # ---------- 3. gate_trades evaluation, same method as REPORT_2026-09-26.txt ----------
    res_noadj_gated = evaluate("noadj", leg, arrays_noadj, trades_noadj)
    res_fadj_gated = evaluate("fadj", leg, arrays_fadj, trades_fadj)

    # ---------- 4. trade-list diff (base, pre-gate) ----------
    # Same 1-minute time grid (verified: NOADJ_NQ_1m_ETH and FADJ_NQ_1m_ETH share identical
    # `time` column), so entry-bar POSITION is comparable directly between the two masters
    # after both are sliced from the same history_from.
    assert len(arrays_noadj["index"]) == len(arrays_fadj["index"]), "index length mismatch"
    same_index = bool((pd.DatetimeIndex(arrays_noadj["index"]) ==
                        pd.DatetimeIndex(arrays_fadj["index"])).all())

    e_noadj = {int(t[0]): t for t in trades_noadj}
    e_fadj = {int(t[0]): t for t in trades_fadj}
    common_entries = set(e_noadj) & set(e_fadj)
    vanish = set(e_noadj) - set(e_fadj)     # entries only in noadj (vanish on fadj)
    appear = set(e_fadj) - set(e_noadj)     # entries only in fadj (appear vs noadj)

    diff_exit = sum(1 for e in common_entries if int(e_noadj[e][1]) != int(e_fadj[e][1]))
    diff_pnl_pts = [abs(float(e_noadj[e][2]) - float(e_fadj[e][2])) for e in common_entries]
    diff_pnl_nonzero = sum(1 for d in diff_pnl_pts if d > 1e-9)

    # take/skip flip share on common entries (post-gate)
    keep_noadj_by_entry = {int(t[0]): k for t, k in
                            zip(sorted(trades_noadj, key=lambda t: t[0]), res_noadj_gated["keep"])}
    keep_fadj_by_entry = {int(t[0]): k for t, k in
                           zip(sorted(trades_fadj, key=lambda t: t[0]), res_fadj_gated["keep"])}
    flips = sum(1 for e in common_entries
                if keep_noadj_by_entry.get(e) != keep_fadj_by_entry.get(e))

    print(f"BASE TRADE DIFF: same_time_index={same_index} "
          f"noadj_n={len(trades_noadj)} fadj_n={len(trades_fadj)} "
          f"common_entries={len(common_entries)} vanish={len(vanish)} appear={len(appear)} "
          f"common_diff_exit_bar={diff_exit} common_diff_pnl_pts_nonzero={diff_pnl_nonzero} "
          f"gate_flip_share={flips}/{len(common_entries)}="
          f"{(flips/len(common_entries) if common_entries else 0):.4f}", flush=True)

    # ---------- 5. estimated-offset / splice bar summary ----------
    rolls_tbl = pd.read_csv(os.path.join(REPO, "tools", "data", "rolls_NQ.csv"))
    est_rows = rolls_tbl[rolls_tbl["status"] != "exact"][
        ["old", "new", "switch_et", "offset_pts", "status"]].to_dict("records")

    out = dict(
        leg=LEG_KEY,
        strategy=leg["strategy"], params=leg["params"], gate=leg["gate"],
        history_from=leg.get("history_from"),
        control=dict(master=master_noadj["filename"], source=master_noadj.get("source"),
                     n_trades=len(trades_noadj), served_n_trades_trained=art["n_trades_trained"],
                     reproduces_count=reproduces_count, max_proba_diff=maxdiff_control,
                     trained_through_served=str(art["trained_through"])),
        fadj=dict(master=master_fadj["filename"], source=master_fadj.get("source"),
                  n_trades=len(trades_fadj)),
        same_time_index=same_index,
        gated=dict(noadj=res_noadj_gated, fadj=res_fadj_gated),
        trade_diff=dict(common_entries=len(common_entries), vanish=len(vanish),
                        appear=len(appear), common_diff_exit_bar=diff_exit,
                        common_diff_pnl_pts_nonzero=diff_pnl_nonzero,
                        gate_flip_count=flips,
                        gate_flip_share=(flips/len(common_entries) if common_entries else None)),
        estimated_offset_rows=est_rows,
        splice_times_et=[str(t) for t in SPLICE_TIMES_ET],
    )
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
