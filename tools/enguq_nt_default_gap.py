"""How far off was the NinjaTrader ENGU-Q strategy's SHIPPED DEFAULTS? (2026-08-26)

The deployed EdgeLogENGUQ1m.cs defaulted to the RTH-scaled lookbacks with the efficiency
gate switched OFF (TlLen 48 / EmaLen 390 / AtrLen 30 / ErTh 0.0). The paper leg it is mapped
to (ENGUQ_ER) is the run #265 ETH config (tl 170 / ema 1380 / atr 106 / er_th 0.25).

Nobody ever attached the strategy, so this never cost real money - but if it HAD been
attached, this is what it would have traded. Same tape, same costs, same window for both.
"""
import sys
import importlib.util as ilu
import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

spec = ilu.spec_from_file_location(
    "er", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_strategies\ENGUQ_1M_ETH_ER_1_0.py")
m = ilu.module_from_spec(spec); spec.loader.exec_module(m)

COST, MULT, LB = 0.533, 20.0, "2025-06-30"
BASE = dict(buf_atr=0.9, vol_mult=0.8, stop_mult=1.0, trail_frac=2.5, min_brk=1.3,
            act_R=2.5, breakeven_R=1.5, regime_len=0, limit_atr=0.0, er_len=60)

WANT = dict(BASE, tl_len=170, ema_len=1380, atr_len=106, er_th=0.25)   # run #265
SHIPPED = dict(BASE, tl_len=48, ema_len=390, atr_len=30, er_th=0.0)    # NT defaults

arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                         date_from=None, date_to="2026-06-30")
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v, day, idx = arr["volume"], arr["day_id"], arr["index"]


def run(p):
    r = m.run_backtest(o, h, l, c, volumes=v, day_id=day, return_trades=True, **p)
    tr = r["trades"]
    d = np.array([(t[2] - COST) * MULT for t in tr])
    ent = pd.to_datetime([idx[int(t[0])] for t in tr]).tz_localize(None)
    lb = d[ent >= pd.Timestamp(LB)]
    eq = np.cumsum(d)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    pf = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
    lbpf = lb[lb > 0].sum() / max(abs(lb[lb < 0].sum()), 1e-9) if len(lb) else float("nan")
    return dict(n=len(d), net=float(d.sum()), pf=float(pf), dd=dd,
                lb_n=int(len(lb)), lb_net=float(lb.sum()), lb_pf=float(lbpf))


for nm, p in (("run #265 (what it SHOULD trade)", WANT),
              ("NT shipped defaults (what it WOULD have traded)", SHIPPED)):
    s = run(p)
    print(f"{nm}\n  trades {s['n']:5d}  net ${s['net']:11,.0f}  PF {s['pf']:.3f}  "
          f"maxDD ${s['dd']:9,.0f}\n  held-out year: {s['lb_n']:3d} trades  "
          f"${s['lb_net']:9,.0f}  PF {s['lb_pf']:.3f}\n")
