"""RUNBOARD data builder — pooled book-level stats, stage-split, for runboard.html.

Treats each config as ONE strategy (both legs' trades pooled, overlay weights applied):
  FULL = 2010-06-07 -> 2026-06-30   IS = FULL minus the LB year   LB = 2025-06-30 -> 2026-06-30
  WF   = 8 equal-day slices of the FULL daily $ series (count positive)
Per stage: net, PF (pooled trades, $-weighted), maxDD (daily curve within stage), MAR = net/|DD|.
Trades bucketed by EXIT date (uniform convention). Prints a table + a JSON block to paste
into runboard.html's DATA constant.
"""
import json, sys, pathlib
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

def leg_trades(strat, arr, params, weights=None):
    """-> list of (exit_date, pnl_usd) with cost + weight applied."""
    r = run_backtest(strat, arrays=arr, params=params, cost_pts=0.533, return_trades=True)
    idx = arr["index"]
    out = []
    for k, t in enumerate(r["trades"]):
        w = 1.0 if weights is None else float(weights[k])
        out.append((pd.Timestamp(idx[int(t[1])]).date(), float(t[2]) * 20.0 * w))
    return r, out

def stage_stats(trades, lo=None, hi=None):
    """trades: (date, $). Window [lo, hi). Returns net/pf/dd/mar/n."""
    sel = [(d, p) for d, p in trades if (lo is None or d >= lo) and (hi is None or d < hi)]
    if not sel:
        return None
    daily = {}
    gw = gl = 0.0
    for d, p in sel:
        daily[d] = daily.get(d, 0.0) + p
        if p > 0: gw += p
        else: gl -= p
    s = pd.Series(daily).sort_index()
    cum = s.cumsum(); dd = float((cum - cum.cummax()).min())
    net = float(s.sum())
    return dict(net=round(net), pf=round(gw / gl, 3) if gl > 0 else None,
                dd=round(abs(dd)), mar=round(net / abs(dd), 2) if dd < -1e-9 else None,
                n=len(sel))

def wf_slices(trades, k=8):
    daily = {}
    for d, p in trades:
        daily[d] = daily.get(d, 0.0) + p
    s = pd.Series(daily).sort_index()
    parts = np.array_split(np.arange(len(s)), k)
    sl = [round(float(s.iloc[ix].sum())) for ix in parts]
    return sum(1 for x in sl if x > 0), sl

# ── legs ─────────────────────────────────────────────────────────────────────
arr5 = load_master_arrays(tv_master("NQ", "5m"), date_from=WIN[0], date_to=WIN[1])
arr1 = load_master_arrays(find_master("NQ", "1m", "rth"), date_from=WIN[0], date_to=WIN[1])
_, orb_t = leg_trades("ORB_3_1.py", arr5, ORB_125)
_, eng_t = leg_trades("ENGUQ_1M_1_0.py", arr1, ENG_149)
_, ensA_t = leg_trades("ORB_3_0_ENS.py", arr5, ENS_A)
_, ensB_t = leg_trades("ORB_3_0_ENS.py", arr5, ENS_B)

orb_run = run_backtest("ORB_3_1.py", arrays=arr5, params=ORB_125, cost_pts=0.533, return_trades=True)
pnl, risk_a, ebar, side = SZ.trade_features(orb_run["trades"], arr5, 0.75, 1)
risk = pd.Series(risk_a)
med = risk.rolling(250, min_periods=30).median().fillna(risk.expanding(min_periods=1).median())
w = (np.minimum(3.0, med / risk).values * SZ.time_weight(ebar, SZ.DEFAULT_TIME_TIERS)
     * np.where(side > 0, 0.5, 1.5))
w = w / w.mean()
_, sized_t = leg_trades("ORB_3_1.py", arr5, ORB_125, weights=w)

arrE = load_master_arrays(find_master("NQ", "1m", "eth"), date_from=WIN[0], date_to=WIN[1])
_s2 = importlib.util.spec_from_file_location("eth", REPO / "augur_strategies" / "ENGUQ_1M_ETH_1_0.py")
_m2 = importlib.util.module_from_spec(_s2); _s2.loader.exec_module(_m2)
_, eth_t = leg_trades("ENGUQ_1M_ETH_1_0.py", arrE, {k: v["default"] for k, v in _m2.DEFAULT_PARAMS.items()})

BOOKS = [
    ("baseline", "Baseline book", "ORB #125 + ENGU-Q #149, 1:1", orb_t + eng_t),
    ("ens_crown", "ENS-crown book", "ENS leg (4.0R/trail 12) + ENGU-Q", ensA_t + eng_t),
    ("ens_def", "ENS-defaults book", "ENS leg (4.5R/trail 5) + ENGU-Q", ensB_t + eng_t),
    ("overlay", "Overlay book", "sized ORB #125 (rp×time×side) + ENGU-Q", sized_t + eng_t),
    ("eth", "ETH standalone", "ENGU-Q clock-scaled, 24h session (single leg)", eth_t),
]

rows = []
print(f"{'book':22} {'FULL net':>10} {'IS PF':>6} {'IS MAR':>7} {'WF+/8':>6} {'LB PF':>6} {'LB MAR':>7} {'LB net':>9}")
for bid, name, legs, tr in BOOKS:
    full = stage_stats(tr)
    is_ = stage_stats(tr, hi=LB_FROM)
    lb = stage_stats(tr, lo=LB_FROM)
    wfp, sl = wf_slices(tr)
    rows.append(dict(id=bid, name=name, legs=legs,
                     full=full, is_=is_, lb=lb, wf=dict(pos=wfp, of=8, slices=sl)))
    print(f"{name:22} {full['net']:>10,} {is_['pf']:>6} {is_['mar']:>7} {wfp:>4}/8 "
          f"{lb['pf']:>6} {lb['mar']:>7} {lb['net']:>9,}")

print("\n=== JSON for runboard.html DATA ===")
print(json.dumps(rows, indent=1))
