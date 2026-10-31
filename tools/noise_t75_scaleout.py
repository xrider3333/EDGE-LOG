r"""TEST 75 - SCALE-OUT exits, NOISE #382 half (owner 10-31 via MANAGER #145). Prereg: docs/PREREG_noise_orb_t75_scaleout_2026-10-31.md.

At trigger T close fraction F at the trigger level, hold the rest to the leg's normal exit; optional breakeven on the rest.
Reuses test 74's WF-chain rebuild of #382 (tools/noise_t74_giveback.py: same trades, same rebuild caveat, lockbox never
loaded). 30 cells = T {1R, 2R, 3/5/8 QQQ $ as % of entry at QQQ 690} x F {1/3, 1/2, 2/3} x BE {off, on}.

    python tools/noise_t75_scaleout.py          writes C:\EdgeLog\_anatomy_cache\t75_scaleout\grid_wf.csv and prints it
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_t74_giveback as t74  # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t75_scaleout"
QQQ_REF = 690.0
TRIGGERS = [("1R", "R", 1.0), ("2R", "R", 2.0), ("3pt", "pct", 3 / QQQ_REF), ("5pt", "pct", 5 / QQQ_REF),
            ("8pt", "pct", 8 / QQQ_REF)]
FRACS = [(1 / 3, "1/3"), (1 / 2, "1/2"), (2 / 3, "2/3")]


def simulate(tr, A, kind, tv, frac, be, cost):
    """(per-unit raw pts after the extra scale commission, scaled?) per trade. Prereg rules: the trigger may fill on bars
    e+1 .. x-1 only (never the entry bar, never the leg's exit bar - stop first), at the trigger level exactly; with BE on
    the remainder's stop sits at entry from the bar after the scale."""
    O, H, L = (np.asarray(A[k], float) for k in ("open", "high", "low"))
    out, scaled = [], []
    for f, e, x, sd, ep, raw, s, risk in tr:
        T = tv * risk if kind == "R" else tv * ep
        xp = ep + sd * raw
        at_open = abs(xp - O[x]) < 1e-9
        res, hit = raw, False
        if T > 0:
            for j in range(e + 1, x):
                fav = (H[j] - ep) if sd > 0 else (ep - L[j])
                if fav >= T:
                    rem = raw
                    if be:
                        last = x - 1 if at_open else x
                        for k in range(j + 1, last + 1):
                            if sd > 0:
                                if O[k] < ep:
                                    rem = O[k] - ep
                                    break
                                if L[k] <= ep:
                                    rem = 0.0
                                    break
                            else:
                                if O[k] > ep:
                                    rem = ep - O[k]
                                    break
                                if H[k] >= ep:
                                    rem = 0.0
                                    break
                    res = frac * T + (1 - frac) * rem - frac * cost / 2.0
                    hit = True
                    break
        out.append(res)
        scaled.append(hit)
    return np.asarray(out), np.asarray(scaled)


def captured(raws, mfe):
    m = mfe > 0
    return float(np.sum(raws[m]) / np.sum(mfe[m]))


def main():
    os.makedirs(OUT, exist_ok=True)
    tr, A, idx, meta = t74.chain()
    mfe = t74.paths(tr, A).mfe.to_numpy()
    raw0 = np.asarray([t[5] for t in tr])
    base, bf, _ = t74.daily_four(tr, raw0, idx, meta)
    keys = ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "one_episode", "max_dd", "net")
    rows = [dict(cell="HOLD (leg as is)", T=None, F=None, BE=None, **{k: base[k] for k in keys}, folds_won="-",
                 scaled=0, mfe_captured=captured(raw0, mfe))]
    for tl, kind, tv in TRIGGERS:
        for fr, fl in FRACS:
            for be in (False, True):
                r, sc = simulate(tr, A, kind, tv, fr, be, meta["cost"])
                f, ff, _ = t74.daily_four(tr, r, idx, meta)
                rows.append(dict(cell="T%s F%s BE%s" % (tl, fl, "on" if be else "off"), T=tl, F=fl, BE=be,
                                 **{k: f[k] for k in keys}, folds_won="%d/%d" % (int((ff > bf + 1e-9).sum()), len(bf)),
                                 scaled=int(sc.sum()), mfe_captured=captured(r, mfe)))
    g = pd.DataFrame(rows)
    g.to_csv(os.path.join(OUT, "grid_wf.csv"), index=False)
    pd.set_option("display.width", 220)
    print(g.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
