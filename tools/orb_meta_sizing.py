"""ORB items N + O — meta-sizing on the strategy's OWN equity (owner brainstorm 2026-07-12).

The B/M lesson: market-state filters that DELETE sessions amputate the short edge and fail.
These two levers keep taking every trade and only change SIZE, keyed off the strategy's own
equity — aimed square at the real DD driver (multi-month chop episodes, §4.17):

  N) DD-THROTTLE   trade at fraction f while the SIZED book is more than $X underwater from
                   its peak; restore full size on a new sized-equity high. (Causal: the weight
                   for trade i uses equity through trade i-1.)
  O) EQUITY GATE   trade at fraction f while the 1-lot reference equity is below its own
                   rolling k-trade average (equity-curve-momentum meta-filter).

Deploy config (BE 1.0R), full window + lockbox slice (2025-06-30 →). MAR is the judge:
a throttle only wins if it cuts DD proportionally MORE than net, in BOTH windows.
f=0 rows (full stop while underwater) included for contrast — those ARE filters, expect worse.

Usage: python tools/orb_meta_sizing.py
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import numpy as np
import pandas as pd
import augur_engine as ae
from augur_engine.engine import find_master, load_master_arrays

FEE, MULT = 0.533, 20.0
LB_FROM = pd.Timestamp("2025-06-30").date()
CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
           atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)

print("running deploy config once (BE 1.0R, full window) ...", flush=True)
m = find_master("NQ", "5m", "rth")
arr = load_master_arrays(m, date_from="2010-06-07", date_to="2026-06-30")
r = ae.run_backtest("ORB_3_0_BE.py", arrays=arr, params=CFG, cost_pts=FEE, return_trades=True)
tr = r["trades"]; idx = arr["index"]
t_date = pd.to_datetime(pd.Series([idx[t[0]] for t in tr]), unit="s", utc=True).dt.tz_convert("US/Eastern").dt.date.values
pnl = np.array([t[2] for t in tr]) * MULT              # net $ per trade, 1-lot reference
is_lb = t_date >= LB_FROM

def stats(sized):
    cum = np.cumsum(sized); dd = float((cum - np.maximum.accumulate(cum)).min()) if len(cum) else 0.0
    net = float(sized.sum()); mar = net / abs(dd) if dd else 0.0
    lb = sized[is_lb]; lcum = np.cumsum(lb)
    ldd = float((lcum - np.maximum.accumulate(lcum)).min()) if len(lcum) else 0.0
    lnet = float(lb.sum()); lmar = lnet / abs(ldd) if ldd else 0.0
    return net, abs(dd), mar, lnet, abs(ldd), lmar

def dd_throttle(x_usd, f):
    """weight_i from the SIZED book's drawdown through trade i-1 (causal)."""
    w = np.ones(len(pnl)); eq = 0.0; peak = 0.0
    for i in range(len(pnl)):
        w[i] = f if (peak - eq) > x_usd else 1.0
        eq += pnl[i] * w[i]
        peak = max(peak, eq)
    return w

def eq_gate(k, f):
    """weight_i: f while 1-lot reference equity < its rolling k-trade mean (causal)."""
    ref = np.cumsum(pnl)
    w = np.ones(len(pnl))
    for i in range(k, len(pnl)):
        sma = ref[i - k:i].mean()
        if ref[i - 1] < sma:
            w[i] = f
    return w

hdr = (f"{'lever':>26} | {'FULL net$':>10} {'DD$':>8} {'MAR':>6} | {'LB net$':>8} {'DD$':>7} {'MAR':>5} | {'%half':>5}")
print("\n" + "=" * len(hdr)); print(hdr); print("-" * len(hdr))
def row(label, w):
    sized = pnl * w
    net, dd, mar, lnet, ldd, lmar = stats(sized)
    pct = 100.0 * (w < 1.0).mean()
    print(f"{label:>26} | {net:>10,.0f} {dd:>8,.0f} {mar:>6.1f} | {lnet:>8,.0f} {ldd:>7,.0f} {lmar:>5.1f} | {pct:>4.0f}%")
    return mar, lmar

row("baseline (always 1.0)", np.ones(len(pnl)))
print("-- N: DD-throttle (sized book underwater > $X -> size f) --")
for x in (5000, 8000, 10000, 15000):
    for f in (0.5, 0.25, 0.0):
        row(f"N: X=${x/1000:.0f}k f={f}", dd_throttle(x, f))
print("-- O: equity gate (1-lot equity < rolling k-trade mean -> size f) --")
for k in (10, 20, 50):
    for f in (0.5, 0.0):
        row(f"O: k={k} f={f}", eq_gate(k, f))
print("-" * len(hdr))
print("Judge: MAR must improve in BOTH windows vs baseline. %half = share of trades taken reduced.")
