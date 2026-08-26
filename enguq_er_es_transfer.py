"""ER-gate ES TRANSFER test (2026-08-23, owner away: "try new things").

Question: is the Kaufman efficiency-ratio gate (er_len 60, er_th 0.25 - run #265's only
addition to the #226 config) STRUCTURE or an NQ artifact? ES 1m ETH was never touched by
any ENGU-Q optimization, so it is a clean transfer instrument.

PRE-REGISTERED BAR (written before running):
  1. gated PF > ungated PF on the ES full window (2010-06-07..2026-06-30), and
  2. the PF gain holds in at least 3 of 4 eras.
Config is FROZEN at the NQ values (no ES re-tuning of any knob, ER included).
ES costs: 0.79 pts x $50 (the project's standing ES figures: ~$1.25 comm + 0.5 tick slip
per side -> 0.79 ES pts round-trip, mult 50).
"""
import sys
import numpy as np
import pandas as pd
import importlib.util as ilu

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

spec = ilu.spec_from_file_location(
    "erf", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_strategies\ENGUQ_1M_ETH_ER_1_0.py")
m = ilu.module_from_spec(spec); spec.loader.exec_module(m)

CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5,
            regime_len=0, limit_atr=0.0)
LB = "2025-06-30"

def run_instrument(ins, cost, mult):
    arr = load_master_arrays(find_master(ins, "1m", "eth", "db_noadj_eth"),
                             date_from=None, date_to="2026-06-30")
    o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
    v, day, idx = arr["volume"], arr["day_id"], arr["index"]

    def one(er_th):
        r = m.run_backtest(o, h, l, c, volumes=v, day_id=day, return_trades=True,
                           **{**CERT, "er_len": 60, "er_th": er_th})
        tr = r["trades"]
        d = np.array([(t[2] - cost) * mult for t in tr])
        ent = pd.to_datetime([idx[int(t[0])] for t in tr]).tz_localize(None)
        return d, ent

    out = {}
    for nm, th in (("ungated", 0.0), ("gated", 0.25)):
        d, ent = one(th)
        pf = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
        lbm = ent >= pd.Timestamp(LB)
        lb = d[lbm]
        lbpf = lb[lb > 0].sum() / max(abs(lb[lb < 0].sum()), 1e-9) if len(lb) else float("nan")
        eras = []
        for a, b in (("2010-01-01", "2014-01-01"), ("2014-01-01", "2018-01-01"),
                     ("2018-01-01", "2022-01-01"), ("2022-01-01", "2027-01-01")):
            mm = (ent >= pd.Timestamp(a)) & (ent < pd.Timestamp(b))
            dd_ = d[mm]
            eras.append(dd_[dd_ > 0].sum() / max(abs(dd_[dd_ < 0].sum()), 1e-9) if len(dd_) else float("nan"))
        out[nm] = dict(n=len(d), net=round(float(d.sum()), 2), pf=round(float(pf), 3),
                       lb_n=int(lbm.sum()), lb_net=round(float(lb.sum()), 2),
                       lb_pf=round(float(lbpf), 3), eras=[round(float(x), 3) for x in eras])
    return out

if __name__ == "__main__":
    res = run_instrument("ES", 0.79, 50.0)
    for nm, s in res.items():
        print(f"ES {nm:8s}: n={s['n']:5d} net=${s['net']:11,.0f} PF={s['pf']:.3f} "
              f"LB n={s['lb_n']:3d} ${s['lb_net']:9,.0f} PF={s['lb_pf']:.3f} eras={s['eras']}")
    g, u = res["gated"], res["ungated"]
    holds = sum(1 for a, b in zip(g["eras"], u["eras"]) if np.isfinite(a) and np.isfinite(b) and a > b)
    bar1 = g["pf"] > u["pf"]
    print(f"\nBAR: full-window PF gated>ungated: {'PASS' if bar1 else 'FAIL'} "
          f"({g['pf']} vs {u['pf']}) | eras held {holds}/4 (need >=3): "
          f"{'PASS' if holds >= 3 else 'FAIL'}")
    print("VERDICT:", "TRANSFERS" if (bar1 and holds >= 3) else "DOES NOT TRANSFER")
