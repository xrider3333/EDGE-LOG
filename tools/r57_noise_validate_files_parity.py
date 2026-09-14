# -*- coding: utf-8 -*-
"""Parity gate for the five round-57 validate files: the centre cell must reproduce the round-56 scorecard
to the dollar, defaults must equal the centre, an in-set neighbour must run, an out-of-set cell must be refused."""
import os, sys, importlib.util as ilu
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
WT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\noisevalidates\augur_strategies"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402

END = pd.Timestamp("2026-07-16").date()
EXPECT = {
    "NOISE_1_9_HSQ304": ("5m", 615, 139997, dict(gate_tf_min=90), dict(gate_tf_min=45)),
    "NOISE_1_9_HSQ243": ("5m", 586, 124443, dict(gate_len=16), dict(gate_len=18)),
    "NOISE_1_1_N304": ("15m", 3011, 376760, dict(lookback=36), dict(lookback=38)),
    "NOISE_1_1_N304C2": ("5m", 4075, 376427, dict(stop_k=2.0), dict(stop_k=2.25)),
    "NOISE_1_4_C3N": ("5m", 2112, 209517, dict(confirm_bars=4), dict(confirm_bars=5)),
}
ARR = {}
ok_all = True
for name, (tf, n_exp, net_exp, inset, outset) in EXPECT.items():
    sp = ilu.spec_from_file_location(name, os.path.join(WT, name + ".py"))
    M = ilu.module_from_spec(sp)
    sp.loader.exec_module(M)
    if tf not in ARR:
        ARR[tf] = load_master_arrays(find_master("NQ", tf, "rth", "db_noadj_rth"), date_from="2010-06-07")
    A = ARR[tf]
    idx = pd.DatetimeIndex(A["index"])
    defaults = {k: v["default"] for k, v in M.DEFAULT_PARAMS.items()}
    assert defaults == M._CENTER, (name, defaults, M._CENTER)

    def go(params):
        r = run_backtest(M, arrays=A, params=params, cost_pts=0.533, return_trades=True)
        if not r or not r.get("trades"):
            return 0, 0
        t = [x for x in r["trades"] if idx[x[0]].date() < END]
        return len(t), int(round(sum(x[2] for x in t) * 20))

    n, net = go(dict(M._CENTER))
    n_in, net_in = go(dict(M._CENTER, **inset))
    try:
        n_out, _ = go(dict(M._CENTER, **outset))
    except Exception:
        n_out = 0
    ok = n == n_exp and abs(net - net_exp) <= 1 and n_in > 0 and n_out == 0
    ok_all &= ok
    print("%-18s %-4s centre %5d trades $%9s (expect %5d / $%9s) | in-set neighbour %5d trades | out-of-set %s -> %s"
          % (name, tf, n, format(net, ","), n_exp, format(net_exp, ","), n_in,
             "refused" if n_out == 0 else "RAN (%d)" % n_out, "PASS" if ok else "FAIL"))
print("ALL PASS" if ok_all else "SOMETHING FAILED")
