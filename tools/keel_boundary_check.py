"""KEEL vs raw, read so that no stretch boundary can decide it (2026-09-24).

tools/keel_family_shootout.py (2026-09-11) read #304's walk-forward at return-per-drawdown 3.46 for KEEL
against 2.13 raw. NOISE round 60 (tools/r60_noise_keel_base_shootout.py) read the same leg at 2.20 against
2.16. Both are arithmetically right: the raw legs agree to the dollar, and the whole gap is ONE KEEL
drawdown that peaks before 2025-02-11 and bottoms on 2025-06-23. The shoot-out's walk-forward ends at
2025-02-11 and cuts that drawdown in half; round 60's ends at 2025-07-16 and holds all of it.

A verdict that moves with a boundary is not a verdict, so this reads each leg over one CONTINUOUS stretch
from the start of the walk-forward to the end of the tape, plus both boundary conventions for reference.
"flat-leverage DD" = KEEL's drawdown divided by what flat leverage at KEEL's mean size would give; below
1.00 means the overlay's extra size is placed better than uniform leverage.

    python tools/keel_boundary_check.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import c4_rejudge as R                                            # noqa: E402
from augur_engine import ml_keel                                  # noqa: E402

SPANS = (("continuous 2016-05 .. end", "2016-05-02", None),
         ("shoot-out WF (to 2025-02-11)", "2016-05-02", "2025-02-11"),
         ("round-60 WF (to 2025-07-16)", "2016-06-30", "2025-07-16"),
         ("after 2025-02-11", "2025-02-11", None),
         ("after 2025-07-16", "2025-07-16", None))


def read(pnl, size, m, yrs):
    q = (pnl * size)[m]
    cum = np.cumsum(q)
    under = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum
    dd = float(under.max())
    return float(q.sum()), dd, (q.sum() / yrs) / dd if dd > 0 else float("nan"), int(np.argmax(under))


def main():
    for rid, fn, P in (("243", "NOISE_1_1_SBS_V90.py", R.P243), ("304", "NOISE_1_1_NBHD.py", R.P304)):
        arr, trades, E, ts, pnl = R.load_leg(fn, P)
        k = np.asarray(ml_keel.keel_walk(arr, trades, version="v12")["size"], float)
        print(f"\n#{rid}")
        for lab, a, b in SPANS:
            m = ts >= pd.Timestamp(a)
            if b:
                m &= ts < pd.Timestamp(b)
            yrs = ((pd.Timestamp(b) if b else ts[-1]) - pd.Timestamp(a)).days / 365.25
            rn, rd, rm, _ = read(pnl, np.ones(len(pnl)), m, yrs)
            kn, kd, km, ki = read(pnl, k, m, yrs)
            print(f"  {lab:30s} raw ${rn:>9,.0f} DD ${rd:>7,.0f} MAR {rm:.2f} | KEEL ${kn:>9,.0f} DD ${kd:>7,.0f}"
                  f" MAR {km:.2f} (trough {ts[m][ki].date()}) | x{km / rm:.2f}"
                  f" | flat-leverage DD x{kd / rd / k[m].mean():.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
