"""NOISE #422 and #382: raw vs fixed tilts vs full KEEL on ONLY the trades after every setting was fixed
(2026-09-27, MANAGER audit item #18).

WHICH DATA SET WHAT (all read on NOISE #243 / #304 validate tapes ending 2026-08-12, walk-forward AND
lockbox - see the version notes in augur_engine/ml_keel.py CFG):
  compression 1.5x  v9  2026-09-07  TTM round-6 by-product; 2x rejected on #304's lockbox drawdown
  Friday 1.5x       v11 2026-09-08  picked from five weekdays on WF AND lockbox EV R
  FOMC 0.5x         v12 2026-09-09  a-priori hypothesis (the Fed calendar), permutation + placebo support;
                                    0.5 chosen as the middle because deeper cuts read better on the lockbox
  KEEL model        v1-v12 2026-09-02..09  members, windows, shade, trust - all tuned reading both stretches
  #382 / #422 cells validates ending 2026-07-16
CUT-OFF = 2026-08-12, the last bar any of those settings read. Clean window = entries from 2026-08-13 to
the last bar of the master. Caveat stated with the result: round 60 (09-24) and the 09-27 comparisons have
since LOOKED at data through 2026-09-16, so only 2026-09-17 onward is also unseen by any comparison.
The 2026-09-14 session carries an in-session contract splice (+~297 pts at 11:30 ET) and is dropped from
every arm.

    python tools/keel_clean_window.py        (~30 min: KEEL walks to the last bar, seed 42 + the 7-seed bag)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import keel_bag_check as B                                            # noqa: E402
import keel_422_stack_check as S                                      # noqa: E402
from augur_engine import ml_keel as K                                 # noqa: E402
from augur_engine.analytics import sortino_from_pnls                  # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

CUT, UNSEEN, SPLICE = pd.Timestamp("2026-08-12"), pd.Timestamp("2026-09-16"), pd.Timestamp("2026-09-14").date()
EVENT = dict(K.CFG["v12"]["event"])
DOW = {k: v for k, v in K.CFG["v12"]["dow"].items() if k != "cap"}
CAP = float(K.CFG["v12"]["comp"]["cap"])
LEGS = (("NOISE #422", "NOISE_1_8_CT304H.py", S.P422), ("NOISE #382", "NOISE_1_8_CT304.py", B.LEGS["382"][2]))


def read(pnl):
    q = np.asarray(pnl, float)
    if not len(q):
        return "n 0"
    cum = np.cumsum(q)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    so = sortino_from_pnls(list(q), 1.0)
    return (f"n {len(q):3d}  net ${q.sum():>9,.0f}  DD ${dd:>7,.0f}  net/DD {q.sum() / dd if dd > 0 else float('nan'):5.2f}"
            f"  win {100 * (q > 0).mean():4.0f}%  per-trade Sortino {so / np.sqrt(len(q)) if so else 0:5.2f}")


def main():
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07")
    idx = pd.DatetimeIndex(A["index"])
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    F = K.keel_features(A)
    print(f"tape to {idx[-1]}; settings cut-off {CUT.date()}; 2026-09-14 (splice) dropped")
    for name, fn, params in LEGS:
        r = run_backtest(B.mod(fn), arrays=A, params=params, cost_pts=B.COST, return_trades=True)
        T = sorted(r["trades"], key=lambda z: z[0])
        P = np.array([float(t[2]) for t in T]) * B.MULT
        ts = idx[[max(int(t[0]) - 1, 0) for t in T]]
        keep = np.array([d.date() != SPLICE for d in ts])
        clean = (ts > CUT) & keep
        unseen = (ts > UNSEEN) & keep
        arms = {"raw": np.ones(len(T)),
                "fixed tilts": K.compression_sizes(A, T, mult=1.5, dow=DOW, cap=CAP, event=EVENT),
                "KEEL seed 42": np.asarray(K.keel_walk(A, T, feats=F, version="v12", seed=42)["size"], float)}
        arms["KEEL 7-seed"] = np.mean([K.keel_walk(A, T, feats=F, version="v12", seed=s)["size"] for s in S.BAG], axis=0)
        print(f"\n{name}: clean window {ts[clean][0].date() if clean.any() else '-'} .. {ts[clean][-1].date() if clean.any() else '-'}")
        for lab, k in arms.items():
            print(f"  {lab:13s} after cut-off: {read((P * k)[clean])}")
            print(f"  {'':13s} unseen only  : {read((P * k)[unseen])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
