# -*- coding: utf-8 -*-
"""Parity gate for NOISE_1_8_CT304H_TP.py (docs/PREREG_noise_422_tp_validate_2026-10-14.md), run BEFORE the validate is queued.

  P1  tp = off at run #422's crown (20 / 1.15 / 1.75) reproduces NOISE_1_8_CT304H.py through the engine trade for trade:
      fill bar, exit bar, points and size, on the full window 2010-06-07 .. 2026-07-16 (run #422's), cost 0.533.
  P2  NOISE_1_10_TP.py at tp_r = 0 reproduces NOISE_1_0.py at the #304 core to the cent.
  P3  tp = 1.0 reproduces NOISE TARGET r1's T100 cell (tools/noise_target_r1_stageA.py, an in-memory patch of NOISE_1_0
      written separately): every fill bar, exit bar and unit P&L. Two independent codings of the same target rule.
The strategy files are loaded from THIS file's checkout; the engine and the master come from the shared checkout
(worktrees carry no master registry).
    python tools/noise_422_tp_parity.py
"""
import importlib.util as _ilu
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, os.path.join(SHARED, "tools"))
sys.path.insert(0, SHARED)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402

CROWN = dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75)
CORE = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both", window="all_day",
            flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75, confirm_bars=1,
            daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)


def load(path, alias):
    sp = _ilu.spec_from_file_location(alias, path)
    m = _ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def rows(r):
    t = sorted(zip(r["trades"], r.get("trade_sizes") or [1.0] * len(r["trades"])), key=lambda z: int(z[0][0]))
    return [(int(a[0]), int(a[1]), round(float(a[2]), 9), float(s)) for a, s in t]


def main():
    m = find_master("NQ", "5m", "rth", "db_noadj_rth")
    print("master %s %s .. %s" % (m.get("filename"), m.get("date_from"), m.get("date_to")))
    A = load_master_arrays(m, date_from="2010-06-07", date_to="2026-07-16")
    S = os.path.join(HERE, "augur_strategies")
    tp = load(os.path.join(S, "NOISE_1_8_CT304H_TP.py"), "_p_ct304h_tp")
    ct = load(os.path.join(SHARED, "augur_strategies", "NOISE_1_8_CT304H.py"), "_p_ct304h")
    a = rows(run_backtest(tp, arrays=A, params=dict(CROWN, tp="off"), cost_pts=0.533, return_trades=True))
    b = rows(run_backtest(ct, arrays=A, params=CROWN, cost_pts=0.533, return_trades=True))
    assert a == b, "P1 FAIL: %d vs %d trades, first difference %r" % (
        len(a), len(b), next(((x, y) for x, y in zip(a, b) if x != y), None))
    print("P1 PASS: tp off = NOISE_1_8_CT304H at run #422's crown, %d trades identical (bars, points, sizes)" % len(a))
    n10 = load(os.path.join(S, "NOISE_1_10_TP.py"), "_p_n10tp")
    n0 = load(os.path.join(SHARED, "augur_strategies", "NOISE_1_0.py"), "_p_n0")
    a = rows(run_backtest(n10, arrays=A, params=dict(CORE, tp_r=0.0), cost_pts=0.533, return_trades=True))
    b = rows(run_backtest(n0, arrays=A, params=CORE, cost_pts=0.533, return_trades=True))
    assert a == b, "P2 FAIL"
    print("P2 PASS: NOISE_1_10_TP at tp_r 0 = NOISE_1_0 at the #304 core, %d trades to the cent" % len(a))
    for d in (os.path.join(os.path.dirname(HERE), "noise-target-1012", "tools"), os.path.join(SHARED, "tools"),
              os.path.join(HERE, "tools")):                             # wherever ledger 2.151's harness is checked out
        if os.path.exists(os.path.join(d, "noise_target_r1_stageA.py")):
            sys.path.insert(0, d)
    import noise_target_r1_stageA as H                                   # noqa: E402
    ref = H.run(H.build(1.0, "full"), 0.533)                             # its own master load (R.A, to 2026-09-16)
    a = rows(run_backtest(n10, arrays=H.R.A, params=dict(CORE, tp_r=1.0), cost_pts=0.533, return_trades=True))
    b = [(int(x[0]), int(x[1]), round(float(x[2]), 9), 1.0) for x in sorted(ref, key=lambda z: int(z[0]))]
    assert a == b, "P3 FAIL: %d vs %d" % (len(a), len(b))
    print("P3 PASS: tp_r 1.0 = NOISE TARGET r1's T100 coding, %d trades identical" % len(a))


if __name__ == "__main__":
    main()
