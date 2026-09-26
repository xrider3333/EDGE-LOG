"""Step 2/3: run the gate's own walk-forward evaluator (gate_trades) three ways
per leg: (i) raw, (ii) roll-corrected, (iii) seed spread (raw, seeds 43-62).
Split WF vs LB at gate_validate's own default boundary: last 12 months of the
series (idx[-1] - 12 months), since no leg-specific wf_from/wf_to could be
found registered in optimizer_history.db for run #231 / #265 (family run
numbers, not db ids).
"""
import json
import time
import numpy as np
import pandas as pd

from common import (leg_config, load_raw_arrays, get_trades, corrected_trades_and_features,
                    yrs_between, stats_block, splice_bar_indices, mask_splice_trades)
from augur_engine.ml_gate import gate_trades, entry_features_causal

SEEDS = list(range(43, 63))   # 20 seeds, same range ROLL_AUDIT already used


def split_wf_lb(trades_sorted, keep, index, lb_start):
    idx = pd.DatetimeIndex(index)
    entry_ts = idx[[min(int(t[0]), len(idx) - 1) for t in trades_sorted]]
    is_lb = entry_ts >= lb_start
    return is_lb


def run_condition(label, leg, arrays, trades, lb_start, seed=42, feats=None):
    g = leg["gate"]
    t0 = time.time()
    out = gate_trades(arrays, trades, model=g["model"], threshold=g["threshold"],
                      min_history=30, refit_every=25, seed=seed, feats=feats)
    dt = time.time() - t0
    T = sorted([tuple(t) for t in trades], key=lambda t: t[0])
    keep = out["keep"]
    is_lb = split_wf_lb(T, keep, arrays["index"], lb_start)
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
    n_skipped = n_total - n_taken

    result = {
        "label": label, "seed": seed, "n_total": n_total,
        "n_taken": n_taken, "n_skipped": n_skipped,
        "wf": wf_taken, "lb": lb_taken, "full": full_taken,
        "dt_s": round(dt, 1),
        "entry_bars": [int(t[0]) for t in T],
        "keep": keep.tolist(),
    }
    return result


def flip_share(raw_result, corr_result):
    """Share of decisions that flip between raw and corrected, over trades
    common to both (identified by entry_bar -- unchanged by the correction)."""
    raw_map = dict(zip(raw_result["entry_bars"], raw_result["keep"]))
    corr_map = dict(zip(corr_result["entry_bars"], corr_result["keep"]))
    common = sorted(set(raw_map) & set(corr_map))
    flips = sum(1 for e in common if raw_map[e] != corr_map[e])
    return flips, len(common), (flips / len(common) if common else None)


def main():
    all_out = {}
    for key in ("NOISE_H_RF", "ENGUQ_ER_H"):
        print(f"=== {key} ===", flush=True)
        leg = leg_config(key)
        arrays, master = load_raw_arrays(leg)
        trades, res = get_trades(leg, arrays)
        idx_last = arrays["index"][-1]
        lb_start = idx_last - pd.DateOffset(months=12)
        print(f"{key}: {len(trades)} raw trades, lb_start={lb_start}", flush=True)

        # (i) raw
        r_raw = run_condition("raw", leg, arrays, trades, lb_start, seed=42)
        print(f"{key} raw: taken {r_raw['n_taken']}/{r_raw['n_total']} dt={r_raw['dt_s']}s", flush=True)

        # (ii) roll-corrected
        adj_arrays, corr_trades, masked, stitch = corrected_trades_and_features(leg, arrays, trades)
        print(f"{key} corrected: masked {len(masked)} 2026-splice trades, "
              f"{int((stitch != 0).sum())} trades had stitch points removed "
              f"(sum |stitch| = {float(np.abs(stitch).sum()):.2f} pts)", flush=True)
        feats_adj = entry_features_causal(adj_arrays)[0]
        r_corr = run_condition("corrected", leg, adj_arrays, corr_trades, lb_start, seed=42, feats=feats_adj)
        print(f"{key} corrected: taken {r_corr['n_taken']}/{r_corr['n_total']} dt={r_corr['dt_s']}s", flush=True)

        flips, n_common, frac = flip_share(r_raw, r_corr)
        print(f"{key} flip share raw vs corrected: {flips}/{n_common} = {frac}", flush=True)

        # (iii) seed spread, raw features/trades
        seed_results = []
        for s in SEEDS:
            rs = run_condition(f"seed{s}", leg, arrays, trades, lb_start, seed=s)
            seed_results.append(rs)
            print(f"{key} seed {s}: taken {rs['n_taken']}/{rs['n_total']} "
                  f"net_full=${rs['full']['net_usd']:.0f}", flush=True)

        all_out[key] = {
            "raw": r_raw, "corrected": r_corr, "masked_n": len(masked),
            "stitch_nonzero": int((stitch != 0).sum()),
            "flip_flips": flips, "flip_common": n_common, "flip_frac": frac,
            "seeds": seed_results,
        }

        # strip the heavy per-trade arrays before dumping to json
        for cond in ("raw", "corrected"):
            all_out[key][cond] = {k: v for k, v in all_out[key][cond].items()
                                   if k not in ("entry_bars", "keep")}
        for rs in all_out[key]["seeds"]:
            rs.pop("entry_bars", None); rs.pop("keep", None)

    with open("results.json", "w") as f:
        json.dump(all_out, f, indent=2, default=str)
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
