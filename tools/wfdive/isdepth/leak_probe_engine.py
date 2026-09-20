r"""Engine probe: does a strategy's WARM full-window replay leak future information into an
early sub-window? For each run, replay the champion COLD on bars [0, B) (the engine's own
fold-1 training slice, which starts at date_from so cold == warm if and only if the strategy
uses trailing information only) and compare trade-by-trade with the matrix's warm trades whose
entry_bar < B. Any difference = the strategy computes something from the WHOLE array it is
handed (a global statistic), which would make warm-matrix training windows leaky.

Usage: python tools/wfdive/isdepth/leak_probe_engine.py 307 314 304 299
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORKTREE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, WORKTREE_ROOT)
sys.path.insert(0, os.path.join(WORKTREE_ROOT, "tools"))
from tools.wfdive import common  # noqa: E402
from tools.wfdive.isdepth.build_matrix import find_run, build_plan, load_space  # noqa: E402

DATA_DIR = os.path.join(common.DATA_DIR, "isdepth")


def main():
    common.low_priority()
    common.setup_data_env()
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.auto import make_slice_evaluator
    out = {}
    for rid in [int(x) for x in sys.argv[1:]]:
        doc = find_run(rid)
        plan = build_plan(doc)
        mod, dp, space, pkeys = load_space(plan)
        z = np.load(os.path.join(DATA_DIR, f"matrix_{rid}.npz"))
        side = json.load(open(os.path.join(DATA_DIR, f"matrix_{rid}.json"), encoding="utf-8"))
        ci = side["champion_index"]
        off = z["offsets"]
        a, b = int(off[ci]), int(off[ci + 1])
        w_eb, w_xb, w_net = z["entry_bar"][a:b], z["exit_bar"][a:b], z["net"][a:b]
        champ = side["configs"][ci]["params"]
        B = side["fold_bounds"][0]["te_s"]          # fold-1 test start = fold-1 train end (anchored) or window end
        master = find_master(plan["instrument"], plan["timeframe"], plan["session"], plan["source"])
        with common.cpu_lock(f"isdepth leak_probe #{rid}"):
            t0 = time.time()
            arrays = load_master_arrays(master, date_from=plan["date_from"], date_to=plan["date_to"])
            n_bars = len(arrays["close"])
            ev = make_slice_evaluator(mod, arrays, plan["cost_pts"])
            om = ev(0, B, champ, keep_trades=True)
            # also: full-window warm replay again (matrix reproducibility) and a MID-window cold slice
            om_full = ev(0, n_bars, champ, keep_trades=True)
            mid0 = B
            mid1 = side["fold_bounds"][-1]["te_e"]
            om_mid = ev(mid0, mid1, champ, keep_trades=True)
            dt = time.time() - t0
        cold = [(int(t[0]), int(t[1]), float(t[2])) for t in (om or {}).get("trades") or []]
        warm = [(int(e), int(x), float(n)) for e, x, n in zip(w_eb, w_xb, w_net) if e < B]
        full = [(int(t[0]), int(t[1]), float(t[2])) for t in (om_full or {}).get("trades") or []]
        warm_all = [(int(e), int(x), float(n)) for e, x, n in zip(w_eb, w_xb, w_net)]
        same_prefix = (len(cold) == len(warm) and all(abs(c[2] - w[2]) < 1e-6 and c[0] == w[0] and c[1] == w[1] for c, w in zip(cold, warm)))
        # mid-window cold vs warm (entry_bar in [mid0, mid1)): quantifies cold-start loss and offset
        mid_cold = [(int(t[0]) + mid0, int(t[1]) + mid0, float(t[2])) for t in (om_mid or {}).get("trades") or []]
        warm_mid = [(e, x, n) for e, x, n in warm_all if mid0 <= e < mid1]
        cold_set = {(e, x) for e, x, _ in mid_cold}
        warm_set = {(e, x) for e, x, _ in warm_mid}
        out[str(rid)] = {
            "strategy": side["strategy"], "B_fold1_train_end": B, "n_bars": n_bars,
            "cold_prefix_trades": len(cold), "warm_prefix_trades": len(warm),
            "cold_prefix_net": sum(t[2] for t in cold), "warm_prefix_net": sum(t[2] for t in warm),
            "prefix_identical": bool(same_prefix),
            "first_diff": next(({"cold": c, "warm": w} for c, w in zip(cold, warm) if not (c[0] == w[0] and c[1] == w[1] and abs(c[2] - w[2]) < 1e-6)), None),
            "full_replay_identical_to_matrix": bool(len(full) == len(warm_all) and all(abs(f[2] - w[2]) < 1e-6 and f[0] == w[0] for f, w in zip(full, warm_all))),
            "mid_window": {"bars": [mid0, mid1], "cold_trades": len(mid_cold), "warm_trades": len(warm_mid),
                           "cold_net": sum(t[2] for t in mid_cold), "warm_net": sum(t[2] for t in warm_mid),
                           "trades_in_both": len(cold_set & warm_set), "only_cold": len(cold_set - warm_set),
                           "only_warm": len(warm_set - cold_set),
                           "first_cold_trade_bar_offset_from_start": (min(e for e, _, _ in mid_cold) - mid0) if mid_cold else None,
                           "first_warm_trade_bar_offset_from_start": (min(e for e, _, _ in warm_mid) - mid0) if warm_mid else None},
            "engine_seconds": round(dt, 1),
        }
        print(json.dumps(out[str(rid)], indent=1), flush=True)
    with open(os.path.join(DATA_DIR, "leak_probe_engine.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
