"""TTM r27 (log tools/data/ttmsqz_r27_is_read.txt) - shelf No. 8 'Momentum turning points' as a side-gate on TTM #459: IS-ONLY design read (power-first gate).
Draft note docs/DRAFT_TTM_r27_PHASE_GATE_2026-10-15.txt (written before any phase number).
Reuses tools/ttmsqz_r25_scalp_exits.py (load / run / make_sim / frame / four, unchanged): #459's trades with parity to the twin."""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

SHARED = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
sp = importlib.util.spec_from_file_location("r25", os.path.join(SHARED, "tools", "ttmsqz_r25_scalp_exits.py"))
R = importlib.util.module_from_spec(sp)
sp.loader.exec_module(R)


def phases(arr_all):
    """ES session closes from the master's whole history; phase per session from closes strictly BEFORE it."""
    idx = pd.DatetimeIndex(arr_all["index"])
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    c = pd.Series(np.asarray(arr_all["close"], float), index=idx)
    dc = c.groupby(idx.normalize()).last()
    prev = dc.shift(1)
    slow = np.sign(prev - dc.shift(1 + 252))
    fast = np.sign(prev - dc.shift(1 + 21))
    ph = pd.Series("none", index=dc.index)
    ok = slow.notna() & fast.notna()
    ph[ok & (slow > 0) & (fast > 0)] = "Bull"
    ph[ok & (slow > 0) & (fast <= 0)] = "Correction"
    ph[ok & (slow <= 0) & (fast <= 0)] = "Bear"
    ph[ok & (slow <= 0) & (fast > 0)] = "Rebound"
    return ph, slow


def main():
    arr, idx, cal = R.load()
    twin = R.run(arr, R.ORIG)[0]
    tr0, rec0 = R.run(arr, R.make_sim(None))
    assert len(twin) == len(tr0) and all(tuple(a) == tuple(b) for a, b in zip(twin, tr0)), "parity"
    D = R.frame(rec0, idx)
    full = R.load_master_arrays(R.find_master("ES", "30m", "rth", "db_adj_rth"))
    ph, slow = phases(full)
    d = D.entry.dt.normalize()
    D["phase"] = ph.reindex(d).fillna("none").to_numpy()
    D["slow"] = slow.reindex(d).to_numpy()
    I = D[D.entry <= pd.Timestamp(R.IS_END)].copy()
    I["usd"] = (I.pts - R.COST_REAL) * R.MULT
    yrs = (pd.Timestamp(R.IS_END) - pd.Timestamp(R.D0)).days / 365.25
    print("IS %s..%s: %d trades (%d long / %d short), phase 'none' %d; master first session %s" % (
        R.D0, R.IS_END, len(I), (I.side > 0).sum(), (I.side < 0).sum(), (I.phase == "none").sum(), str(ph.index[0].date())))
    print("\nphase x side (IS, real cost 0.613 pt, $ per contract):")
    for p_ in ("Bull", "Correction", "Bear", "Rebound", "none"):
        for sd, nm in ((1, "long"), (-1, "short")):
            S = I[(I.phase == p_) & (I.side == sd)]
            if len(S):
                print("  %-10s %-5s n %3d  mean $%+8.1f  sum $%+9.0f  win %4.0f%%" % (p_, nm, len(S), S.usd.mean(), S.usd.sum(), 100 * (S.usd > 0).mean()))
    skip = {
        "G1 AGREE": ((I.side > 0) & (I.phase == "Bear")) | ((I.side < 0) & (I.phase == "Bull")),
        "G2 SLOW": ((I.side > 0) & (I.slow < 0)) | ((I.side < 0) & (I.slow > 0)),
        "G3 BEAR-ONLY": (I.side > 0) & (I.phase == "Bear"),
    }
    base = R.four(D, R.COST_REAL, R.D0, R.IS_END, cal)
    print("\n#459 as is, IS real cost: %s" % R.fmt(base))
    for nm, sk in skip.items():
        added = -I.usd[sk].sum() / yrs
        Dg = D.drop(index=I.index[sk.to_numpy()])
        g = R.four(Dg, R.COST_REAL, R.D0, R.IS_END, cal)
        print("%-13s skips %3d trades | $ a year added %+7.0f | %s" % (nm, int(sk.sum()), added, R.fmt(g)))


if __name__ == "__main__":
    main()
