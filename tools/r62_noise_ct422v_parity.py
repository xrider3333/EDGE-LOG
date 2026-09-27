import os, sys, importlib.util as ilu
import numpy as np, pandas as pd
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"; WT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\noiseearn\augur_strategies"
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
A = load_master_arrays(find_master("NQ","5m","rth","db_noadj_rth"), date_from="2010-06-07", date_to="2026-07-15")
def load(d, n):
    sp = ilu.spec_from_file_location(n + "_p62", os.path.join(d, n + ".py")); m = ilu.module_from_spec(sp); sp.loader.exec_module(m); return m
V = load(WT, "NOISE_1_8_CT422V"); H = load(os.path.join(ROOT, "augur_strategies"), "NOISE_1_8_CT304H")
def go(m, p):
    r = run_backtest(m, arrays=A, params=p, cost_pts=0.533, return_trades=True)
    if not r or not r.get("trades"): return 0, 0.0
    return len(r["trades"]), round(sum(x[2] for x in r["trades"]) * 20, 2)
ref = go(H, dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75)); c = go(V, dict(V._CENTER))
print("CT422V centre", c, "| NOISE #422 cell via CT304H", ref, "->", "PASS" if c == ref else "FAIL")
print("memory 68 at skip 95:", go(V, dict(vol_skip_pct=95.0, vol_ref_sessions=68)))
print("memory 160 at skip 97.5:", go(V, dict(vol_skip_pct=97.5, vol_ref_sessions=160)))
print("out-of-set memory 126:", go(V, dict(vol_skip_pct=95.0, vol_ref_sessions=126)))
