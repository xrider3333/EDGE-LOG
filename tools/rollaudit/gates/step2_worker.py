"""Worker: run a subset of conditions for one leg, dump to its own json file.
Usage: python -u step2_worker.py <LEG_KEY> <out.json> <cond1> [cond2 ...]
  cond in {"raw", "corrected", "seed<N>"}
"""
import sys
import json
import time
import numpy as np
import pandas as pd

from common import leg_config, load_raw_arrays, get_trades, corrected_trades_and_features, yrs_between, stats_block
from augur_engine.ml_gate import gate_trades, entry_features_causal


def split_wf_lb(trades_sorted, index, lb_start):
    idx = pd.DatetimeIndex(index)
    entry_ts = idx[[min(int(t[0]), len(idx) - 1) for t in trades_sorted]]
    return entry_ts >= lb_start


def run_condition(label, leg, arrays, trades, lb_start, seed=42, feats=None):
    g = leg["gate"]
    t0 = time.time()
    out = gate_trades(arrays, trades, model=g["model"], threshold=g["threshold"],
                      min_history=30, refit_every=25, seed=seed, feats=feats)
    dt = time.time() - t0
    T = sorted([tuple(t) for t in trades], key=lambda t: t[0])
    keep = out["keep"]
    is_lb = split_wf_lb(T, arrays["index"], lb_start)
    years_wf = yrs_between(arrays["index"][0], lb_start)
    idx_last = arrays["index"][-1]
    years_lb = yrs_between(lb_start, idx_last)

    taken_pnls = np.array([t[2] for t, k in zip(T, keep) if k])
    taken_is_lb = is_lb[keep]

    wf_taken = stats_block(taken_pnls[~taken_is_lb], years=years_wf)
    lb_taken = stats_block(taken_pnls[taken_is_lb], years=years_lb)
    full_taken = stats_block(taken_pnls, years=yrs_between(arrays["index"][0], idx_last))

    n_total = len(T)
    n_taken = int(keep.sum())
    print(f"{label}: taken {n_taken}/{n_total}  net_full=${full_taken['net_usd']:.0f} "
          f"dd_full=${full_taken['max_dd_usd']:.0f}  dt={dt:.1f}s", flush=True)

    return {
        "label": label, "seed": seed, "n_total": n_total,
        "n_taken": n_taken, "n_skipped": n_total - n_taken,
        "wf": wf_taken, "lb": lb_taken, "full": full_taken,
        "dt_s": round(dt, 1),
        "entry_bars": [int(t[0]) for t in T],
        "keep": [bool(x) for x in keep],
    }


def main():
    leg_key, out_path = sys.argv[1], sys.argv[2]
    conds = sys.argv[3:]
    leg = leg_config(leg_key)
    arrays, master = load_raw_arrays(leg)
    trades, res = get_trades(leg, arrays)
    idx_last = arrays["index"][-1]
    lb_start = idx_last - pd.DateOffset(months=12)
    print(f"{leg_key}: {len(trades)} raw trades, lb_start={lb_start}, conds={conds}", flush=True)

    adj_arrays = corr_trades = masked = stitch = feats_adj = None
    need_corrected = "corrected" in conds
    if need_corrected:
        adj_arrays, corr_trades, masked, stitch = corrected_trades_and_features(leg, arrays, trades)
        feats_adj = entry_features_causal(adj_arrays)[0]
        print(f"{leg_key} corrected: masked {len(masked)} 2026-splice trades, "
              f"{int((stitch != 0).sum())} trades stitch-corrected "
              f"(sum|stitch|={float(np.abs(stitch).sum()):.2f} pts)", flush=True)

    out = {}
    for c in conds:
        if c == "raw":
            out["raw"] = run_condition("raw", leg, arrays, trades, lb_start, seed=42)
        elif c == "corrected":
            r = run_condition("corrected", leg, adj_arrays, corr_trades, lb_start, seed=42, feats=feats_adj)
            r["masked_n"] = len(masked)
            r["stitch_nonzero"] = int((stitch != 0).sum())
            r["stitch_abs_sum"] = float(np.abs(stitch).sum())
            out["corrected"] = r
        elif c.startswith("seed"):
            s = int(c[4:])
            out[c] = run_condition(c, leg, arrays, trades, lb_start, seed=s)
        else:
            raise ValueError(c)

    with open(out_path, "w") as f:
        json.dump(out, f, default=str)
    print(f"wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
