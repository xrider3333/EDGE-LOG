# -*- coding: utf-8 -*-
"""Round 60 parity gate: each new file's centre must reproduce the file it was cut from, to the dollar,
and every out-of-set cell must be refused."""
import importlib.util as ilu
import os
import sys

import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
WT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\noiser60\augur_strategies"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
os.environ["AUGUR_TRIAL_CACHE"] = "1"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays        # noqa: E402
from augur_engine.engine import run_backtest                         # noqa: E402

END = pd.Timestamp("2026-07-16").date()
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07")
IDX = pd.DatetimeIndex(A["index"])


def load(folder, name):
    sp = ilu.spec_from_file_location(name + "_" + os.path.basename(folder), os.path.join(folder, name + ".py"))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def go(mod, params):
    try:
        r = run_backtest(mod, arrays=A, params=params, cost_pts=0.533, return_trades=True)
    except Exception as e:                                            # noqa: BLE001
        return 0, 0, "raised %s" % type(e).__name__
    if not r or not r.get("trades"):
        return 0, 0, "refused"
    t = [x for x in r["trades"] if IDX[x[0]].date() < END]
    return len(t), int(round(sum(x[2] for x in t) * 20)), "ran"


HSQ = load(os.path.join(ROOT, "augur_strategies"), "NOISE_1_9_HSQ304H")
CT = load(os.path.join(ROOT, "augur_strategies"), "NOISE_1_8_CT304")
GEO = load(WT, "NOISE_1_9_GEO304")
CTH = load(WT, "NOISE_1_8_CT304H")

ok = True
ref_n, ref_d, _ = go(HSQ, dict(gate_len=20, gate_ratio=1.15))
new_n, new_d, _ = go(GEO, dict(GEO._CENTER))
same = (ref_n == new_n and abs(ref_d - new_d) <= 1)
ok &= same
print("GEO304 centre   %5d trades $%9s   vs run-398 filter on the crown %5d / $%9s   %s"
      % (new_n, format(new_d, ","), ref_n, format(ref_d, ","), "PASS" if same else "FAIL"))
nb_n, _, _ = go(GEO, dict(GEO._CENTER, lookback=44))
out_n, _, out_s = go(GEO, dict(GEO._CENTER, lookback=42))
print("GEO304 neighbour lookback 44 -> %d trades | out-of-set lookback 42 -> %s" % (nb_n, out_s))
ok &= nb_n > 0 and out_n == 0

ref2_n, ref2_d, _ = go(CT, dict(gate_tf_min=60, gate_len=20, gate_ratio=1.0, tilt_mult=1.5))
new2_n, new2_d, _ = go(CTH, dict(gate_len=20, gate_ratio=1.0, tilt_mult=1.5))
same2 = (ref2_n == new2_n and abs(ref2_d - new2_d) <= 1)
ok &= same2
print("CT304H centre   %5d trades $%9s   vs CT304 hourly 20/1.0 at 1.5x %5d / $%9s   %s"
      % (new2_n, format(new2_d, ","), ref2_n, format(ref2_d, ","), "PASS" if same2 else "FAIL"))
nb2_n, nb2_d, _ = go(CTH, dict(gate_len=24, gate_ratio=0.85, tilt_mult=1.75))
o1_n, _, o1_s = go(CTH, dict(gate_len=20, gate_ratio=1.0, tilt_mult=2.0))
o2_n, _, o2_s = go(CTH, dict(gate_len=18, gate_ratio=1.0, tilt_mult=1.5))
print("CT304H neighbour 24/0.85 at 1.75x -> %d trades $%s | tilt 2.0 -> %s | length 18 -> %s"
      % (nb2_n, format(nb2_d, ","), o1_s, o2_s))
ok &= nb2_n > 0 and o1_n == 0 and o2_n == 0

crown_n, crown_d, _ = go(CT, dict(gate_tf_min=60, gate_len=20, gate_ratio=1.0, tilt_mult=1.0))
print("reference: the live crown itself (tilt switched off) %d trades $%s" % (crown_n, format(crown_d, ",")))
print("ALL PASS" if ok else "SOMETHING FAILED")
