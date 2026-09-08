# -*- coding: utf-8 -*-
"""Does a bigger IS trial budget in Auto-Validate help? Same validate on the WIDE parent
ORB_3_6.py (crown #314's window + lockbox), n_trials varied. Usage: trials_exp.py N SEED OUT"""
import sys, os, json, time
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.validate import run_validate
N, SEED, OUT = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
t0 = time.time()
def cb(pct, msg=""):
    print("[%5.0fs] %s %s" % (time.time()-t0, pct, msg), flush=True)
r = run_validate("ORB_3_6.py", instrument="NQ", timeframe="5m", session="rth", source=None,
                 cost_pts=0.533, min_trades=30, n_trials=N, wf_folds=0, seed=SEED,
                 lockbox_months=12, date_from="2010-06-07", date_to="2026-08-13", progress_cb=cb)
v = r.get("validate") or {}
keep = {"n_trials": N, "seed": SEED, "elapsed_s": round(time.time()-t0),
        "n_evaluated": r.get("n_evaluated"), "n_valid": r.get("n_valid"),
        "best_params": r.get("best_params"), "best": r.get("best"),
        "verdict": v.get("verdict"), "n_pass": v.get("n_pass"), "wfe": v.get("wfe"),
        "folds_held": v.get("folds_held"), "n_folds": v.get("n_folds"), "dsr": v.get("dsr"),
        "pbo": v.get("pbo") or r.get("pbo"), "lockbox": v.get("lockbox"),
        "selection": r.get("selection"), "steering": r.get("steering") or v.get("steering"),
        "is_metrics": {k: (r.get("best") or {}).get(k) for k in ("total_pnl","profit_factor","num_trades","max_drawdown")}}
json.dump(keep, open(OUT, "w"), indent=1, default=str)
print("DONE", OUT, keep["verdict"], keep["lockbox"] and {k: keep["lockbox"].get(k) for k in ("pass","pf","pnl")})
