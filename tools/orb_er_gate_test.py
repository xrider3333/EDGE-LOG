"""ER gate on the ORB crown (2026-08-23, owner away: "try new things").

Does the Kaufman efficiency floor that works on ENGU-Q (run #265) and transfers to ES
(STUDIES row 345) also help the OTHER momentum leg, ORB #230/#234?

Legality: the #230 family takes at most ONE trade per day (first-candle-direction,
close-confirmed entry, no re-entry), so skipping an entry cannot enable a different trade
later that day - a trade-level filter is path-exact. Causality: the ER is computed on
closes up to the bar BEFORE the entry bar (the entry fires at the signal bar's close, so
the prior bar's ER is strictly known).

PRE-REGISTERED (written before running):
  primary cell: er_len 12 (one hour of 5m bars, the same one-hour window ENGU-Q uses),
  er_th 0.25, prior-bar. Bars: (1) gated PF > ungated PF, full window;
  (2) the PF gain holds in >= 3 of 4 eras. Secondary cells (context only, no cherry-pick):
  er_len 6 / 24, th 0.15 / 0.25 / 0.35.
Config: run #234 crown (C2 ride+BE) params, NQ 5m RTH db_noadj_rth, cost 0.533 x $20.
"""
import sys
import numpy as np
import pandas as pd
import importlib.util as ilu

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

spec = ilu.spec_from_file_location(
    "orb", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_strategies\ORB_3_4_C221.py")
m = ilu.module_from_spec(spec); spec.loader.exec_module(m)

COST, MULT = 0.533, 20.0

arr = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"),
                         date_from="2010-06-07", date_to="2026-08-13")
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v, day, idx = arr["volume"], arr["day_id"], arr["index"]

params = {k: v_["default"] for k, v_ in m.DEFAULT_PARAMS.items()}
r = m.run_backtest(o, h, l, c, volumes=v, day_id=day, return_trades=True, **params)
tr = r["trades"]
d_all = np.array([(t[2] - COST) * MULT for t in tr])
ent_i = np.array([int(t[0]) for t in tr])
ent_t = pd.to_datetime([idx[i] for i in ent_i]).tz_localize(None)
print(f"control: n={len(tr)} net=${d_all.sum():,.0f} "
      f"PF={d_all[d_all>0].sum()/abs(d_all[d_all<0].sum()):.3f}")


def er_at(L):
    chg = np.abs(c - np.concatenate([np.full(L, np.nan), c[:-L]]))
    ad = np.abs(np.diff(c, prepend=c[0])); cs = np.cumsum(ad)
    vs = cs - np.concatenate([np.zeros(L), cs[:-L]])
    er = np.where(vs > 0, chg / np.maximum(vs, 1e-9), 0.0)
    return np.nan_to_num(er)


def eras_pf(d, ent, a, b):
    mm = (ent >= pd.Timestamp(a)) & (ent < pd.Timestamp(b))
    x = d[mm]
    return x[x > 0].sum() / max(abs(x[x < 0].sum()), 1e-9) if len(x) else np.nan

ERAS = (("2010-01-01", "2014-01-01"), ("2014-01-01", "2018-01-01"),
        ("2018-01-01", "2022-01-01"), ("2022-01-01", "2027-01-01"))
u_eras = [eras_pf(d_all, ent_t, a, b) for a, b in ERAS]

for L in (6, 12, 24):
    er = er_at(L)
    for th in (0.15, 0.25, 0.35):
        keep = er[np.maximum(ent_i - 1, 0)] >= th        # PRIOR bar, strictly causal
        d = d_all[keep]; ent = ent_t[keep]
        if not len(d):
            print(f"L={L:2d} th={th:.2f}: empty"); continue
        pf = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
        g_eras = [eras_pf(d, ent, a, b) for a, b in ERAS]
        holds = sum(1 for g, u in zip(g_eras, u_eras) if np.isfinite(g) and g > u)
        tag = " <-- PRIMARY" if (L == 12 and th == 0.25) else ""
        print(f"L={L:2d} th={th:.2f}: n={len(d):4d} net=${d.sum():9,.0f} PF={pf:.3f} "
              f"eras_hold={holds}/4{tag}")

er = er_at(12)
keep = er[np.maximum(ent_i - 1, 0)] >= 0.25
d = d_all[keep]; ent = ent_t[keep]
pf_u = d_all[d_all > 0].sum() / abs(d_all[d_all < 0].sum())
pf_g = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
holds = sum(1 for gg, uu in zip([eras_pf(d, ent, a, b) for a, b in ERAS], u_eras)
            if np.isfinite(gg) and gg > uu)
ok = pf_g > pf_u and holds >= 3
print(f"\nPRIMARY BAR: PF {pf_g:.3f} vs {pf_u:.3f} ({'PASS' if pf_g>pf_u else 'FAIL'}) | "
      f"eras {holds}/4 ({'PASS' if holds>=3 else 'FAIL'})")
print("VERDICT:", "PROMISING - queue a validate before believing it" if ok else "DEAD on ORB")
