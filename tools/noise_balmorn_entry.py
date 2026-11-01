r"""TEST 244 FOLLOW-UP - NOISE #382 balance-morning ENTRY filter (MANAGER #155, 2026-11-01).

Prereg docs/PREREG_noise_balance_morning_entry_2026-11-01.md (locked 34c391e7f49d, pushed e09e87d9 before this ran).
One cell: skip entries filled at/after 11:00 (entry bar = 19th RTH bar or later) on mornings whose 09:30-11:00
directional efficiency is < 0.55 - computed exactly as test 244's lock2.py features() does. Entries before 11:00 are
untouched. Reuses lock2.py's bar loading (refuses a master that reaches the lockbox), MFE parity and daily_four, on the
t74 rebuild of the walk-forward chain. The lead came from this same chain, so this can only kill it.

    python tools/noise_balmorn_entry.py   -> prints the tables, writes C:\EdgeLog\_anatomy_cache\t244_balmorn\result.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

LOCK2_DIR = r"C:\EdgeLog\_anatomy_cache\t244_lock2"
sys.path.insert(0, LOCK2_DIR)
import lock2  # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t244_balmorn"
THR = 0.55


def main():
    os.makedirs(OUT, exist_ok=True)
    leg = lock2.LEGS[0]
    assert "382" in leg["name"], leg
    d, win, A, idx = lock2.load_bars(leg)
    F = lock2.features(A, idx)
    cost, mult, wf = float(d["cost_pts"]), float(d.get("multiplier") or 20.0), d["validate"]["wf_oos"]
    t = pd.read_csv(leg["csv"])
    t["at_open"] = t.at_open.astype(bool)
    mfe, ao = lock2.recompute_mfe(t, F["O"], F["H"], F["L"])
    par = float(np.mean(np.abs(mfe - t.mfe.values) <= lock2.PARITY_TOL))
    if par < 0.99:
        raise SystemExit("MFE parity %.4f below 0.99 - refusing" % par)

    e = t.e.values.astype(int)
    late = F["pos"][e] >= lock2.MORN_BARS                  # entry bar is the 19th bar or later: fills at/after 11:00
    eff = F["eff"][e]
    bal = late & np.isfinite(eff) & (eff < THR)
    trend = late & np.isfinite(eff) & (eff >= THR)

    raw0 = t.raw.values.astype(float)
    base, bf, usd0 = lock2.daily_four(t, raw0, idx, cost, mult, wf)
    keep = ~bal
    tk = t[keep].reset_index(drop=True)
    filt, ff, _ = lock2.daily_four(tk, raw0[keep], idx, cost, mult, wf)
    ff = ff.reindex(bf.index, fill_value=0.0)
    folds_won = int((ff > bf + 1e-9).sum())
    years = float(wf["years"])

    gb = np.maximum(t.mfe.values - raw0, 0.0)
    win_ = raw0 - cost > 0

    def grp(m, name):
        return dict(group=name, n=int(m.sum()), avg_usd=float(usd0[m].mean()) if m.any() else None,
                    win_rate=float(win_[m].mean()) if m.any() else None,
                    avg_mfe_pts=float(t.mfe.values[m].mean()) if m.any() else None,
                    avg_giveback_pts=float(gb[m].mean()) if m.any() else None,
                    sum_usd=float(usd0[m].sum()))

    split = [grp(bal, "after 11:00, balance morning (eff<0.55)"), grp(trend, "after 11:00, trend morning (eff>=0.55)"),
             grp(~late, "before 11:00 (untouched)")]
    keys = ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "net", "max_dd", "one_episode")
    res = dict(parity=par, n_trades=len(t), skipped=int(bal.sum()), skipped_per_yr=bal.sum() / years,
               years=years, hold={k: base[k] for k in keys}, filtered={k: filt[k] for k in keys},
               folds_won=folds_won, folds=len(bf), usd_per_yr_diff=(filt["net"] - base["net"]) / years,
               fold_hold=bf.round(0).to_dict(), fold_filtered=ff.round(0).to_dict(), split=split,
               skipped_sum_usd=float(usd0[bal].sum()))
    passes = (filt["roc30"] > base["roc30"] and filt["sortino"] > base["sortino"] and folds_won >= 5
              and not (filt["one_episode"] and not base["one_episode"]))
    res["verdict"] = "LIFT (lead only - same chain)" if passes else "NO LIFT"
    json.dump(res, open(os.path.join(OUT, "result.json"), "w"), indent=2, default=float)
    print(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()
