"""RUNBOARD apples-to-apples: same WF and LB yardsticks for all 5 configs.
WF = 8 equal-day slices of each config's daily $ PnL (continuous, no re-fit): count positive.
LB = 2025-06-30->2026-06-30 slice: net, maxDD within slice, net/DD.
Full = 2010-06-07->2026-06-30: net, maxDD, net/DD.
Configs: baseline blend / ENS-crown blend / ENS-defaults blend / overlay blend / ETH standalone.
"""
import sys, pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest, find_master, load_master_arrays
from augur_engine.data import list_masters
from augur_engine import sizing as SZ
import importlib.util
_s = importlib.util.spec_from_file_location("enguq", REPO / "augur_strategies" / "ENGUQ_1M_1_0.py")
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
ENG_149 = _m.NQ_DEPLOY_PARAMS_149

WIN = ("2010-06-07", "2026-06-30")
LB_FROM = pd.Timestamp("2025-06-30").date()
ORB_125 = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
               breakout_buf=0.0, target_R=0.0, partial_exit_R=0.0, trail_bars=5, flat_eod=True)
ENS_A = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
             breakout_buf=0.0, be_after_R=1.0, target_R=4.0, trail_bars=12)
ENS_B = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
             breakout_buf=0.0, be_after_R=1.0, target_R=4.5, trail_bars=5)

def tv_master(inst, tf):
    cands = [m for m in list_masters() if m.get("instrument") == inst and m.get("timeframe") == tf
             and (m.get("session") or "").lower() == "rth"]
    tv = [m for m in cands if (m.get("source") or "") == "tv"]
    return (tv or cands)[0]

def daily(strat, arr, params, weights=None):
    r = run_backtest(strat, arrays=arr, params=params, cost_pts=0.533, return_trades=True)
    idx = arr["index"]; d = {}
    for k, t in enumerate(r["trades"]):
        w = 1.0 if weights is None else weights[k]
        day = pd.Timestamp(idx[int(t[1])]).date()
        d[day] = d.get(day, 0.0) + float(t[2]) * 20.0 * w
    return r, pd.Series(d).sort_index()

def stats(s):
    cum = s.cumsum(); dd = float((cum - cum.cummax()).min()); net = float(s.sum())
    lb = s[pd.Index(s.index) >= LB_FROM]
    lbc = lb.cumsum(); lbdd = float((lbc - lbc.cummax()).min()) if len(lb) else float("nan")
    ei = np.array_split(np.arange(len(s)), 8)
    slices = [float(s.iloc[ix].sum()) for ix in ei]
    return dict(net=net, dd=dd, mar=net/abs(dd), lb_net=float(lb.sum()), lb_dd=lbdd,
                lb_mar=float(lb.sum())/abs(lbdd) if lbdd < -1e-9 else float("inf"),
                wf_pos=sum(1 for x in slices if x > 0), slices=[round(x) for x in slices])

arr5 = load_master_arrays(tv_master("NQ", "5m"), date_from=WIN[0], date_to=WIN[1])
arr1 = load_master_arrays(find_master("NQ", "1m", "rth"), date_from=WIN[0], date_to=WIN[1])
orb_r, orb_d = daily("ORB_3_1.py", arr5, ORB_125)
eng_r, eng_d = daily("ENGUQ_1M_1_0.py", arr1, ENG_149)
ensA_r, ensA_d = daily("ORB_3_0_ENS.py", arr5, ENS_A)
ensB_r, ensB_d = daily("ORB_3_0_ENS.py", arr5, ENS_B)

# overlay weights on ORB #125 trades (t2 recipe: tilts x min(cap3, rolling250med/risk), mean-normed)
orb_run = run_backtest("ORB_3_1.py", arrays=arr5, params=ORB_125, cost_pts=0.533, return_trades=True)
pnl, risk_a, ebar, side = SZ.trade_features(orb_run["trades"], arr5, 0.75, 1)
risk = pd.Series(risk_a)
med = risk.rolling(250, min_periods=30).median()
med = med.fillna(risk.expanding(min_periods=1).median())
rp = np.minimum(3.0, med / risk)
tw = SZ.time_weight(ebar, SZ.DEFAULT_TIME_TIERS)
sw = np.where(side > 0, 0.5, 1.5)
w = rp.values * tw * sw
w = w / w.mean()
_, sized_d = daily("ORB_3_1.py", arr5, ORB_125, weights=w)

arrE = load_master_arrays(find_master("NQ", "1m", "eth"), date_from=WIN[0], date_to=WIN[1])
_s2 = importlib.util.spec_from_file_location("eth", REPO / "augur_strategies" / "ENGUQ_1M_ETH_1_0.py")
_m2 = importlib.util.module_from_spec(_s2); _s2.loader.exec_module(_m2)
ETH_P = {k: v["default"] for k, v in _m2.DEFAULT_PARAMS.items()}
eth_r, eth_d = daily("ENGUQ_1M_ETH_1_0.py", arrE, ETH_P)

rows = {
    "baseline blend (ORB#125 + ENGUQ)": stats(pd.DataFrame({"a": orb_d, "b": eng_d}).fillna(0).sum(axis=1)),
    "ENS-crown blend": stats(pd.DataFrame({"a": ensA_d, "b": eng_d}).fillna(0).sum(axis=1)),
    "ENS-defaults blend": stats(pd.DataFrame({"a": ensB_d, "b": eng_d}).fillna(0).sum(axis=1)),
    "overlay blend (sized ORB + ENGUQ)": stats(pd.DataFrame({"a": sized_d, "b": eng_d}).fillna(0).sum(axis=1)),
    "ETH standalone (ENGUQ clock-scaled)": stats(eth_d),
}
print(f"{'config':38} {'net':>11} {'maxDD':>9} {'MAR':>6} {'WF+/8':>6} {'LB net':>9} {'LB DD':>9} {'LB MAR':>7}")
for k, v in rows.items():
    print(f"{k:38} {v['net']:>11,.0f} {abs(v['dd']):>9,.0f} {v['mar']:>6.2f} {v['wf_pos']:>4}/8 "
          f"{v['lb_net']:>9,.0f} {abs(v['lb_dd']):>9,.0f} {v['lb_mar']:>7.2f}")
    print(f"{'':38} slices: {v['slices']}")
print("\nsanity: baseline net expect ~838k; overlay ~1,110k; ENS-B ~943k; ETH ~435k")
