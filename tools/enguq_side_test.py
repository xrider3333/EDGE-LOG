"""BATTERY R -- the never-tested SHORT mirror of ENGU-Q.

Pre-registered before looking at any short result:
  PARITY (mandatory, run first): side='long' must reproduce the certified engine EXACTLY
    (n=2843, net $434,721.12, PF 1.332, DD $50,420). If parity fails, every short number
    below is meaningless and the battery is void.

  For the SHORT leg to be worth anything at all it must clear ALL of:
    S1  net > $0                       -- it must actually make money
    S2  >= 300 trades                  -- enough sample to mean anything
    S3  profit factor >= 1.15          -- clear of the cost/noise floor
    S4  >= 60% of years positive       -- not one lucky crash (2020/2022)
    S5  lockbox net > $0               -- survives the untouched final year
    S6  longest hold <= 120 days       -- the stuck-position guard that killed #198/#223

  For 'both' to be worth adopting over the long-only certified config it must ALSO clear:
    B1  net > $434,721 (the control)
    B2  net/DD > 8.62  (the control) -- shorts must improve risk-adjusted return, since the
        whole argument for adding a second direction is diversification, not more trades.

Anything less than that is a clean negative and gets written up as one.
"""
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_strategies.ENGUQ_1M_ETH_SIDE_1_0 import run_backtest        # noqa: E402

MULT, COST, LB_START = 20.0, 0.533, "2025-06-30"
CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5,
            regime_len=0)
CTRL_NET, CTRL_DD, CTRL_NETDD, CTRL_N = 434721.12, 50420.22, 8.62, 2843

OUT = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15"
       r"\scratchpad\side_results.json")

arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                         date_from=None, date_to="2026-06-30")
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v, day, idx = arr["volume"], arr["day_id"], arr["index"]


def stats(res):
    trades = res["trades"]
    d = np.array([(t[2] - COST) * MULT for t in trades])
    ent = pd.to_datetime([idx[int(t[0])] for t in trades]).tz_localize(None)
    ext = pd.to_datetime([idx[int(t[1])] for t in trades]).tz_localize(None)
    sides = np.array([t[3] for t in trades])
    cum = np.cumsum(d)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    pf = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
    lb = d[ent >= pd.Timestamp(LB_START)]
    lbpf = lb[lb > 0].sum() / max(abs(lb[lb < 0].sum()), 1e-9) if len(lb) else float("nan")
    yrs = pd.Series(d).groupby(ent.year.values).sum()
    hold = (ext - ent).total_seconds() / 86400.0
    return dict(
        n=int(len(d)), net=float(d.sum()), dd=dd,
        net_dd=float(d.sum()) / dd if dd else float("inf"),
        pf=float(pf), win_rate=float((d > 0).mean() * 100),
        lb_n=int(len(lb)), lb_net=float(lb.sum()), lb_pf=float(lbpf),
        pos_years=int((yrs > 0).sum()), tot_years=int(len(yrs)),
        longest_hold_d=float(hold.max()),
        n_long=int((sides == 1).sum()), n_short=int((sides == -1).sum()),
        net_long=float(d[sides == 1].sum()), net_short=float(d[sides == -1].sum()),
        fills=res.get("_fills"),
    )


def run(**kw):
    return stats(run_backtest(o, h, l, c, volumes=v, day_id=day, index=idx,
                              return_trades=True, **dict(CERT, **kw)))


rows = {}
print("=" * 78)
print("STEP 1 - PARITY (side='long', limit_atr=0) must match the certified engine")
p = run(side="long", limit_atr=0.0)
rows["parity_long"] = p
ok_n = p["n"] == CTRL_N
ok_net = abs(p["net"] - CTRL_NET) < 1.0
print(f"  n={p['n']} (want {CTRL_N})  net=${p['net']:,.2f} (want ${CTRL_NET:,.2f})  "
      f"PF={p['pf']:.3f}  DD=${p['dd']:,.0f}")
print(f"  PARITY: {'PASS' if (ok_n and ok_net) else 'FAIL'}")
if not (ok_n and ok_net):
    print("\n  ABORT - parity failed, every short number would be meaningless.")
    json.dump(rows, open(OUT, "w"), indent=1)
    sys.exit(1)

print("\n" + "=" * 78)
print("STEP 2 - the SHORT mirror, alone, at the certified config")
for lim in (0.0, 0.5):
    s = run(side="short", limit_atr=lim)
    rows[f"short_lim{lim}"] = s
    print(f"  limit={lim:.2f}  n={s['n']:5d}  net=${s['net']:11,.0f}  DD=${s['dd']:9,.0f}  "
          f"net/DD={s['net_dd']:6.2f}  PF={s['pf']:.3f}  win={s['win_rate']:.1f}%")
    print(f"            LB=${s['lb_net']:10,.0f} (n={s['lb_n']}, PF={s['lb_pf']:.3f})  "
          f"yrs+{s['pos_years']}/{s['tot_years']}  hold<={s['longest_hold_d']:.0f}d")
    g = dict(S1_net_pos=s["net"] > 0, S2_n300=s["n"] >= 300, S3_pf115=s["pf"] >= 1.15,
             S4_years60=s["pos_years"] / max(s["tot_years"], 1) >= 0.60,
             S5_lb_pos=s["lb_net"] > 0, S6_hold120=s["longest_hold_d"] <= 120)
    rows[f"short_lim{lim}"]["gates"] = g
    print(f"            gates: {g}")
    print(f"            SHORT VERDICT: {'PASS' if all(g.values()) else 'FAIL'}")

print("\n" + "=" * 78)
print("STEP 3 - BOTH sides sharing one position slot")
for lim in (0.0, 0.5):
    b = run(side="both", limit_atr=lim)
    rows[f"both_lim{lim}"] = b
    print(f"  limit={lim:.2f}  n={b['n']:5d} (L {b['n_long']} / S {b['n_short']})  "
          f"net=${b['net']:11,.0f}  DD=${b['dd']:9,.0f}  net/DD={b['net_dd']:6.2f}  "
          f"PF={b['pf']:.3f}")
    print(f"            split: long ${b['net_long']:,.0f} / short ${b['net_short']:,.0f}")
    print(f"            LB=${b['lb_net']:10,.0f} (n={b['lb_n']}, PF={b['lb_pf']:.3f})  "
          f"yrs+{b['pos_years']}/{b['tot_years']}  hold<={b['longest_hold_d']:.0f}d")
    g = dict(B1_beats_ctrl_net=b["net"] > CTRL_NET, B2_beats_ctrl_netdd=b["net_dd"] > CTRL_NETDD,
             S6_hold120=b["longest_hold_d"] <= 120)
    rows[f"both_lim{lim}"]["gates"] = g
    print(f"            gates: {g}")
    print(f"            BOTH VERDICT: {'PASS' if all(g.values()) else 'FAIL'}")

json.dump(rows, open(OUT, "w"), indent=1, default=float)
print("\nSAVED ->", OUT)
