import os, sys, json
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
sys.path.insert(0, os.getcwd())
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from augur_engine.ml_gate import (entry_features_causal, gate_trades, _stats as gate_stats,
                                  _make_model)
from augur_engine import ml_keel

SESSION = {"db_noadj_rth": "rth", "db_noadj_eth": "eth"}

SCRATCH = r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\cf70e01e-1bab-4445-b5e2-10d6db1f8d89\scratchpad\book_legs_ml"
OUTDIR = r"C:\EdgeLog\book_legs"
os.makedirs(OUTDIR, exist_ok=True)


def load_run(rid):
    with open(os.path.join(SCRATCH, f"run_{rid}_full.json"), encoding="utf-8") as fh:
        return json.load(fh)


def get_arrays(d):
    src = d["data_source"]
    sess = SESSION[src]
    m = find_master(d["instrument"], d["timeframe"], sess, src)
    if m is None:
        raise SystemExit(f"no master for {d['instrument']} {d['timeframe']} {sess} {src}")
    arr = load_master_arrays(m, date_from=d.get("date_from"), date_to=d.get("date_to"))
    return arr, m


def raw_trades(d, arr):
    res = run_backtest(d["strategy"], arrays=arr, params=d["best_params"],
                       cost_pts=float(d.get("cost_pts") or 0.0), return_trades=True)
    T = sorted([(int(t[0]), int(t[1]), float(t[2]), float(t[3]) if len(t) > 3 else None,
                float(t[4]) if len(t) > 4 else None) for t in res["trades"]], key=lambda t: t[0])
    return T, res


def entry_ts_of(arr, T):
    idx = arr["index"]
    nb = len(idx)
    return np.array([idx[min(t[0], nb - 1)] for t in T])


def close(a, b, tol=0.01, rel=True):
    if a is None or b is None:
        return False
    if rel:
        return abs(a - b) <= max(tol * abs(b), 0.5)
    return abs(a - b) <= tol


def check_block(name, repro, stored, pnl_tol=0.01):
    """Compare num_trades EXACT, total_pnl within pnl_tol relative."""
    ok_n = int(repro.get("num_trades") or 0) == int(stored.get("num_trades") or 0)
    ok_p = close(repro.get("total_pnl"), stored.get("total_pnl"), pnl_tol)
    msg = (f"{name}: trades repro={repro.get('num_trades')} stored={stored.get('num_trades')} "
          f"({'OK' if ok_n else 'MISMATCH'}) | net repro={repro.get('total_pnl'):.2f} "
          f"stored={stored.get('total_pnl'):.2f} ({'OK' if ok_p else 'MISMATCH'})")
    return (ok_n and ok_p), msg


def _loc_ts(t, ref_tz):
    if t is None:
        return None
    ts = pd.Timestamp(t)
    if ts.tzinfo is None and ref_tz is not None:
        ts = ts.tz_localize(ref_tz)
    return ts


def slice_stats(entry_ts, pnls, t0=None, t1=None):
    ref_tz = entry_ts[0].tzinfo if len(entry_ts) else None
    t0 = _loc_ts(t0, ref_tz); t1 = _loc_ts(t1, ref_tz)
    m = np.ones(len(pnls), bool)
    if t0 is not None:
        m &= entry_ts >= t0
    if t1 is not None:
        m &= entry_ts < t1
    return gate_stats(np.asarray(pnls, float)[m]), m
