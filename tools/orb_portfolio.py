"""Item W — portfolio blend: ORB (NQ 5m, deploy config) × ENGU-Q (ES 1m, validated defaults).

The §4.16 ensemble result generalized: two books whose bad days don't line up should have a
portfolio MAR above either book. ORB is two-sided/short-carried intraday breakout on NQ;
ENGU-Q is long-only trendline-break on ES — different signal, different instrument, different
timeframe. This tool runs both books once, merges DAILY P&L (union of dates, 0 on no-trade
days), and reports each book + the 1u+1u sum + a DD-parity weighted blend, full window and
lockbox (2025-06-30 →), plus the daily-PnL correlation.

Costs: NQ 0.533 pts/RT ($5.66 comm + 0.25pt slip @ $20/pt); ES 0.363 pts/RT (same @ $50/pt).
Usage: python tools/orb_portfolio.py
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
from augur_engine.engine import load_master_arrays
from augur_engine.data import list_masters

LB_FROM = pd.Timestamp("2025-06-30").date()
ORB_CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
               atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)
ENG_CFG = dict(tl_len=34, vol_mult=1.2, stop_mult=1.7, act_R=1.0, trail_frac=2.5,
               buf_atr=0.35, min_brk=0.7, ema_len=30, atr_len=47, regime_len=0, breakeven_R=0.0)

def master_named(name):
    for m in list_masters():
        if m.get("name") == name:
            return m
    raise SystemExit(f"master not found: {name}")

def daily_pnl(strategy, master_name, mult, fee, params):
    m = master_named(master_name)
    arr = load_master_arrays(m, date_from="2010-06-07", date_to="2026-06-30")
    r = ae.run_backtest(strategy, arrays=arr, params=params, cost_pts=fee, return_trades=True)
    tr = r["trades"]; idx = arr["index"]
    d = pd.to_datetime(pd.Series([idx[t[0]] for t in tr]), unit="s", utc=True).dt.tz_convert("US/Eastern").dt.date
    p = pd.Series([t[2] * mult for t in tr], index=d.values)
    return p.groupby(level=0).sum(), r

print("running ORB deploy (NQ 5m) ...", flush=True)
orb, orb_r = daily_pnl("ORB_3_0_BE.py", "NQ 5m RTH - no-adj", 20.0, 0.533, ORB_CFG)
print(f"  ORB: {orb_r['num_trades']} trades, net ${orb.sum():,.0f}")
print("running ENGU-Q 1m validated defaults (ES 1m) ...", flush=True)
eng, eng_r = daily_pnl("ENGUQ_1M_1_0.py", "ES 1m RTH - no-adj", 50.0, 0.363, ENG_CFG)
print(f"  ENGU-Q: {eng_r['num_trades']} trades, net ${eng.sum():,.0f}, PF {eng_r['profit_factor']:.2f}, WR {eng_r['win_rate']:.0f}%")

# union daily frame, 0-fill (a book that doesn't trade that day contributes $0)
df = pd.DataFrame({"orb": orb, "eng": eng}).fillna(0.0).sort_index()
corr = df["orb"].corr(df["eng"])
print(f"\ndaily-PnL correlation (union, 0-filled): {corr:+.3f}   ({len(df)} trading days)")

def stats(s, label):
    cum = s.cumsum(); dd = float((cum - cum.cummax()).min())
    net = float(s.sum()); mar = net / abs(dd) if dd else 0.0
    lb = s[np.array([d >= LB_FROM for d in s.index])]
    lcum = lb.cumsum(); ldd = float((lcum - lcum.cummax()).min()) if len(lb) else 0.0
    lnet = float(lb.sum()); lmar = lnet / abs(ldd) if ldd else 0.0
    print(f"{label:>28} | full ${net:>10,.0f} DD ${abs(dd):>8,.0f} MAR {mar:>5.1f} | LB ${lnet:>8,.0f} DD ${abs(ldd):>7,.0f} MAR {lmar:>4.1f}")
    return net, abs(dd), mar, lnet, abs(ldd), lmar

hdr = f"{'book':>28} | {'FULL net / DD / MAR':^36} | {'LOCKBOX net / DD / MAR':^30}"
print("\n" + "=" * len(hdr)); print(hdr); print("-" * len(hdr))
o = stats(df["orb"], "ORB deploy (1u NQ)")
e = stats(df["eng"], "ENGU-Q 1m (1u ES)")
stats(df["orb"] + df["eng"], "SUM (1u + 1u)")
# DD-parity: weight ENGU so its standalone full-window DD matches ORB's
w = o[1] / e[1] if e[1] else 1.0
stats(df["orb"] + w * df["eng"], f"DD-parity (1u + {w:.2f}u)")
print("-" * len(hdr))
print("Judge: the blend wins if portfolio MAR > max(single-book MAR) in BOTH windows.")
print("Low/negative correlation is the mechanism — the books' bad days must not line up.")
