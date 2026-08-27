"""BATTERY U -- the regime filter on the #226 ETH config (ENGUQ.md 1.4, sanctioned).

PRE-REGISTERED 2026-08-20, before any result was read.

SUPERSEDED 2026-08-26: the engine constant was FIXED (390 -> 1091 ETH bars/day) in
augur_strategies/ENGUQ_1M_ETH_1_0.py, so regime_len now means days directly and this
script passes the intended days unscaled. Re-running it reproduces the same windows as
the original battery U -- the compensation moved from the caller into the engine, it did
not change what was tested. The original note is kept below for the record.

ORIGINAL: the engine computed the regime window as
regime_len * 390 bars ("390 RTH bars/day"), but the ETH tape has ~1091 one-minute bars
per day. To test a filter of D CALENDAR-ish trading days, we pass
regime_len = round(D * 1091 / 390), and we say so. Grid of intended days: 10/20/30/50/75.

Bar (judge on PF + lockbox, NOT net/DD, per ENGUQ.md and edgelog-netdd-unreliable):
  W1  PF >= 1.332            (the control's)
  W2  lockbox PF >= 1.493    (the control's)
  W3  lockbox net >= $80,000 (house bar)
  W4  drawdown falls by a LARGER fraction than net does (the stated interesting outcome)
  W5  stuck guard: longest hold <= 120d AND >= 40 lockbox trades
Window pinned to the certified basis: 2010-06-07 .. 2026-06-30, NQ 1m ETH, 0.533 x $20.
Control = regime off (must reproduce n=2843 / $434,721.12 exactly, else abort).
"""
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_strategies.ENGUQ_1M_ETH_1_0 import run_backtest             # noqa: E402

MULT, COST, LB_START = 20.0, 0.533, "2025-06-30"
CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5)
CTRL = dict(pf=1.332, lb_pf=1.493, net=434721.12, dd=50420.22, n=2843)
DAYS = [10, 20, 30, 50, 75]

OUT = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15"
       r"\scratchpad\regime_results.json")

arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                         date_from=None, date_to="2026-06-30")
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v, day, idx = arr["volume"], arr["day_id"], arr["index"]


def stats(res):
    tr = res["trades"]
    d = np.array([(t[2] - COST) * MULT for t in tr])
    ent = pd.to_datetime([idx[int(t[0])] for t in tr]).tz_localize(None)
    ext = pd.to_datetime([idx[int(t[1])] for t in tr]).tz_localize(None)
    cum = np.cumsum(d)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    pf = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
    lb = d[ent >= pd.Timestamp(LB_START)]
    lbpf = lb[lb > 0].sum() / max(abs(lb[lb < 0].sum()), 1e-9) if len(lb) else float("nan")
    hold = (ext - ent).total_seconds() / 86400.0
    # 2018+ concentration echo, since section 1 is about exactly this
    d18 = d[ent >= pd.Timestamp("2018-01-01")]
    top10 = float(np.sort(d18)[::-1][:10].sum() / d18.sum()) if len(d18) and d18.sum() > 0 else float("nan")
    return dict(n=len(d), net=float(d.sum()), dd=dd, pf=float(pf),
                lb_n=int(len(lb)), lb_net=float(lb.sum()), lb_pf=float(lbpf),
                hold=float(hold.max()), top10_2018=round(top10, 3))


def run(**kw):
    return stats(run_backtest(o, h, l, c, volumes=v, day_id=day, index=idx,
                              return_trades=True, **{**CERT, 'regime_len': 0, **kw}))


print("CONTROL (regime off) -- parity gate")
ctl = run()
print(" ", ctl)
ok = ctl["n"] == CTRL["n"] and abs(ctl["net"] - CTRL["net"]) < 1.0
print("  PARITY:", "PASS" if ok else "FAIL")
if not ok:
    sys.exit(1)

rows = {"control": ctl}
print("\nREGIME SWEEP (intended days -> passed regime_len after ETH rescale)")
for D in DAYS:
    rl = D          # engine is ETH-aware since 2026-08-26; days are days
    s = run(regime_len=rl)
    rows["d%d" % D] = dict(s, regime_len_passed=rl)
    dd_cut = 1 - s["dd"] / ctl["dd"]
    net_cut = 1 - s["net"] / ctl["net"]
    g = dict(W1_pf=s["pf"] >= CTRL["pf"], W2_lbpf=s["lb_pf"] >= CTRL["lb_pf"],
             W3_lbnet=s["lb_net"] >= 80000, W4_ddcut=dd_cut > net_cut,
             W5_guard=s["hold"] <= 120 and s["lb_n"] >= 40)
    rows["d%d" % D]["gates"] = g
    print(f"  {D:3d}d (rl={rl:3d}): n={s['n']:5d} net=${s['net']:10,.0f} ({-net_cut*100:+.1f}%) "
          f"DD=${s['dd']:8,.0f} ({-dd_cut*100:+.1f}%) PF={s['pf']:.3f} "
          f"LB=${s['lb_net']:8,.0f} (n={s['lb_n']}, PF={s['lb_pf']:.3f}) "
          f"top10share18={s['top10_2018']} hold<={s['hold']:.0f}d")
    print(f"        gates {g}  ->  {'WIN' if all(g.values()) else 'fail'}", flush=True)

json.dump(rows, open(OUT, "w"), indent=1, default=float)
print("\nSAVED ->", OUT)
