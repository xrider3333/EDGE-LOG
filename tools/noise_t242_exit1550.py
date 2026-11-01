r"""TEST 242 (b) - NOISE #382 exits at the 15:50 bar close instead of riding into the last bar (MANAGER #152, owner 10-31).

Prereg docs/PREREG_noise_t242_exit1550_2026-10-31.md (locked d6df542d9e67, pushed 49cdcad1 before this ran). One cell, no
grid. The lead came from MANAGER-AGENT's permutation test on these SAME chain trades, so this check can only kill it.

#382 has no exit-time knob (flat_eod is on/off: STEP E flattens at the session's LAST bar close). So the check runs on the
t74 rebuild of the walk-forward chain (tools/noise_t74_giveback.py chain(), same caveat: ~0.5% off the stored trades, both
arms use the same trades). A trade is affected when its exit bar is the session's last bar and it was already open at the
close of the bar before (entry bar <= last - 1): it exits at that bar's close instead. Every earlier exit - VWAP exit,
protective stop, a stop inside the 15:50 bar - is untouched; a stop inside the last bar stays counted for hold. Same cost,
same single round trip. Walk-forward stretch only; the lockbox is never loaded.

    python tools/noise_t242_exit1550.py      -> prints the table, writes C:\EdgeLog\_anatomy_cache\t242\exit1550.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_t74_giveback as t74  # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t242"


def early_exit(tr, A):
    """(raw pts per trade with the 15:50 exit, mask of affected trades)."""
    C = np.asarray(A["close"], float)
    did = np.asarray(A["day_id"])
    raws, hit = [], []
    for f, e, x, sd, ep, raw, s, risk in tr:
        last = x + 1 >= len(did) or did[x + 1] != did[x]        # x is the session's last bar
        if last and e <= x - 1 and did[x - 1] == did[x]:
            raws.append(sd * (C[x - 1] - ep))
            hit.append(True)
        else:
            raws.append(raw)
            hit.append(False)
    return np.asarray(raws), np.asarray(hit)


def episode(f):
    return f.get("one_episode")


def main():
    os.makedirs(OUT, exist_ok=True)
    tr, A, idx, meta = t74.chain()
    hold = np.asarray([t[5] for t in tr])
    alt, hit = early_exit(tr, A)
    fh, foldh, usdh = t74.daily_four(tr, hold, idx, meta)
    fa, folda, usda = t74.daily_four(tr, alt, idx, meta)
    yrs = float(meta["wf"]["years"])
    d = (usda - usdh)[hit]
    won = int((folda > foldh).sum())
    rows = {}
    for name, f in (("hold", fh), ("exit_1550", fa)):
        rows[name] = {k: (float(f[k]) if isinstance(f[k], (int, float, np.floating)) else f[k])
                      for k in ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "net", "max_dd", "one_episode")}
    res = dict(rows=rows, folds_won=won, folds=len(foldh), fold_hold=foldh.round(0).to_dict(),
               fold_alt=folda.round(0).to_dict(), affected=int(hit.sum()), trades=len(tr),
               affected_helped=int((d > 0).sum()), affected_hurt=int((d < 0).sum()),
               usd_per_year=float((usda.sum() - usdh.sum()) / yrs), years=yrs)
    ok = (fa["roc30"] > fh["roc30"] and fa["sortino"] > fh["sortino"] and won >= 5
          and (not fa["one_episode"] or fa["one_episode"] == fh["one_episode"]))
    res["verdict"] = "LIFT (watch forward only)" if ok else "NO LIFT"
    print(json.dumps(res, indent=1, default=str))
    with open(os.path.join(OUT, "exit1550.json"), "w", encoding="utf-8") as fh_:
        json.dump(res, fh_, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
