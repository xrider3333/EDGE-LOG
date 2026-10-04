# -*- coding: utf-8 -*-
"""NOISE round 69b - leave-one-out ablation of Custom ML's 09-27 'fixed' NOISE #422 package, WALK-FORWARD ONLY.

MANAGER #29 (reported, not judged; no lockbox): which part carried the package's walk-forward read (about 109 vs 85
ROC at a $30k drawdown)? The package (augur_engine.ml_keel.compression_sizes with v12's fixed values) multiplies each
#422 trade by: 1.5x when KEEL's 60-minute squeeze is on at entry; 1.5x on Fridays; product capped at 3; then 0.5x
before an FOMC statement (entry before 14:00 ET on statement day). The cap cannot bind (1.5 x 1.5 = 2.25 < 3).
Nothing here reads entries on or after 2025-07-16.

  python tools/r69b_noise_fixed_ablation.py  -> tools/r37_results/r69b_fixed_ablation.txt
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402
from augur_engine import ml_keel as K                                 # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

DOW = {k: v for k, v in K.CFG["v12"]["dow"].items() if k != "cap"}
EVENT = dict(K.CFG["v12"]["event"])
CAP = float(K.CFG["v12"]["comp"]["cap"])

if __name__ == "__main__":
    ct = R.load("NOISE_1_8_CT304H.py")
    tr = sorted(run_backtest(ct, arrays=R.A, params=dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75),
                             cost_pts=R.COST, return_trades=True)["trades"], key=lambda t: int(t[0]))
    k = [int(t[0]) for t in tr]
    net = np.array([float(t[2]) for t in tr])

    def arm(comp, fri, fomc):
        return K.compression_sizes(R.A, tr, mult=1.5 if comp else 1.0, dow=DOW if fri else None, cap=CAP,
                                   event=EVENT if fomc else None)

    arms = [("NOISE #422 (no package)", None), ("full package", (1, 1, 1)),
            ("package minus compression", (0, 1, 1)), ("package minus Friday", (1, 0, 1)),
            ("package minus FOMC", (1, 1, 0)), ("compression 1.5x only", (1, 0, 0)),
            ("Friday 1.5x only", (0, 1, 0)), ("FOMC 0.5x only", (0, 0, 1))]
    print("NOISE round 69b - fixed-package ablation on #422, WALK-FORWARD ONLY %s .. %s (reported, not judged)"
          % (R.WF0, R.LB0))
    wfm = np.array([R.WF0 <= R.DATE[x - 1] < R.LB0 for x in k])
    for name, a in arms:
        m = np.ones(len(tr)) if a is None else arm(*a)
        s = R.stats(list(zip(k, net * m)), R.WF0, R.LB0)
        print("  %-27s ROC@30k %5.1f%%  Sortino %4.2f  (%5.1f%%/yr, DD $%s)  mean size %.2f, max %.2f" % (
            name, s["r30"], s["so"], s["roc"], format(int(s["dd"]), ","), m[wfm].mean(), m[wfm].max()))
