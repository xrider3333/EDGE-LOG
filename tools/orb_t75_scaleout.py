r"""TEST 75, ORB HALF - ORB #314 SCALE-OUT EXITS (owner 10-31, MANAGER #145 / ORB #126).
Prereg: docs/PREREG_noise_orb_t75_scaleout_2026-10-31.md (28885f3c) + docs/PREREG_orb_t75_scaleout_addendum_2026-10-31.md.

    python tools/orb_t75_scaleout.py          the 30-cell grid on the #314 WF chain vs HOLD; the lockbox is never loaded

The chain (8 anchored folds, per-fold stored params, parity printed fold by fold) is test 74's rebuild
(tools/orb_t74_giveback.py chain / paths / daily_four), so both tests read the same trades.

Rule (prereg): trigger T in the trade's favour (1R / 2R, R = the entry's own stop distance; or a fixed % of entry:
QQQ 2 / 4 / 6 at the 10-30 reference 690 = 0.290 / 0.580 / 0.870%). F of the position closes AT the trigger level on the
first bar after the entry bar and before the leg's exit bar that reaches it (stop-first: no scale on the exit bar). The
remainder holds to the leg's exit; with BE on, from the bar after the scale its stop is entry (open through = open fill,
touch = entry), acting through the exit bar unless the leg's exit is at that bar's open. A scaled trade pays one extra
exit, cost / 2 x F. Per-unit result = F x T + (1 - F) x remainder - extra; the leg's round-trip cost stays on the whole.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orb_t74_giveback as t74  # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t75_scaleout_orb"
REF = 690.0                                            # QQQ at the 10-30 reference (prereg)
TRIGS = [("1R", "R", 1.0), ("2R", "R", 2.0)] + [("%gQ" % q, "pct", q / REF) for q in (2.0, 4.0, 6.0)]
FRACS = [1 / 3, 1 / 2, 2 / 3]
FLAB = {1 / 3: "1/3", 1 / 2: "1/2", 2 / 3: "2/3"}


def simulate(tr, A, kind, k, frac, be, cost):
    """(raw pts per trade, scaled flag per trade). raw is before the round-trip cost (daily_four takes it off)."""
    O, H, L = (np.asarray(A[c], float) for c in ("open", "high", "low"))
    out, sc = [], []
    for f, e, x, sd, ep, raw, s, risk in tr:
        trig = k * risk if kind == "R" else k * ep
        if trig <= 0:
            out.append(raw); sc.append(False); continue
        lvl = ep + sd * trig
        j = next((b for b in range(e + 1, x) if (H[b] >= lvl if sd > 0 else L[b] <= lvl)), None)
        if j is None:
            out.append(raw); sc.append(False); continue
        rem = raw
        if be:
            at_open = abs(ep + sd * raw - O[x]) < 1e-9
            last = x - 1 if at_open else x
            for b in range(j + 1, last + 1):
                if (O[b] <= ep) if sd > 0 else (O[b] >= ep):
                    rem = sd * (O[b] - ep); break
                if (L[b] <= ep) if sd > 0 else (H[b] >= ep):
                    rem = 0.0; break
        out.append(frac * trig + (1 - frac) * rem - cost / 2.0 * frac)
        sc.append(True)
    return np.asarray(out), np.asarray(sc)


def captured(raws, mfe):
    m = mfe > 0
    return float(np.sum(raws[m]) / np.sum(mfe[m]))


def main():
    os.makedirs(OUT, exist_ok=True)
    tr, A, idx, meta = t74.chain()
    mfe = t74.paths(tr, A).mfe.to_numpy(float)
    raw0 = np.asarray([t[5] for t in tr])
    base, bf, _ = t74.daily_four(tr, raw0, idx, meta)
    keys = ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "one_episode", "max_dd", "net")
    rows = [dict(cell="HOLD (leg as is)", t=None, f=None, be=None, **{k: base[k] for k in keys}, folds_won="-",
                 scaled=0, mfe_captured=captured(raw0, mfe))]
    for name, kind, k in TRIGS:
        for fr in FRACS:
            for be in (False, True):
                r, s = simulate(tr, A, kind, k, fr, be, meta["cost"])
                f, ff, _ = t74.daily_four(tr, r, idx, meta)
                rows.append(dict(cell="T%s F%s BE%s" % (name, FLAB[fr], "on" if be else "off"),
                                 t=name, f=round(fr, 3), be=be, **{kk: f[kk] for kk in keys},
                                 folds_won="%d/%d" % (int((ff > bf + 1e-9).sum()), len(bf)), scaled=int(s.sum()),
                                 mfe_captured=captured(r, mfe)))
    g = pd.DataFrame(rows)
    g.to_csv(os.path.join(OUT, "grid_wf.csv"), index=False)
    pd.set_option("display.width", 220)
    print(g.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
