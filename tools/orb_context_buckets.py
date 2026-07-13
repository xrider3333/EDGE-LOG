"""ORB items S + T — context DIAGNOSTICS: overnight-range confluence + gap conditioning.

Diagnostic-first (quality rule): bucket the deploy config's trades by session context and see
whether any bucket is toxic or golden BEFORE building a lever. Signals (all causal, known
before the RTH open):

  S) ON-RANGE CONFLUENCE  overnight high/low from the ETH master (prior 18:00 ET -> 9:29 ET).
       For a LONG:  entry level at/above the ON high  -> "beyond ONH" (fresh air)
                    else                              -> "inside ON range" (into resistance)
       Shorts symmetric vs the ON low.
  T) OVERNIGHT GAP        today's RTH open vs yesterday's RTH close, normalized by the
       trailing 20-day average daily range. Buckets: big-up / flat / big-down (|gap| > 0.25x),
       crossed with trade side (with-gap vs against-gap).

Output: n / net$ / avg$ / WR / PF per bucket, full window + lockbox flag.
Usage: python tools/orb_context_buckets.py
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
CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
           atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)

print("running deploy config (RTH) ...", flush=True)
m = find_master("NQ", "5m", "rth")
arr = load_master_arrays(m, date_from="2010-06-07", date_to="2026-06-30")
r = ae.run_backtest("ORB_3_0_BE.py", arrays=arr, params=CFG, cost_pts=FEE, return_trades=True)
tr = r["trades"]; idx = arr["index"]
T = pd.DataFrame({
    "date": pd.to_datetime(pd.Series([idx[t[0]] for t in tr]), unit="s", utc=True).dt.tz_convert("US/Eastern").dt.date,
    "pnl": [t[2] * MULT for t in tr],
    "side": [t[3] for t in tr],
    "entry": [t[4] for t in tr],
})
print(f"  {len(T)} trades")

# ── RTH daily bars: prior close + trailing avg range (for the gap signal) ──────
bt = pd.to_datetime(pd.Series(idx), unit="s", utc=True).dt.tz_convert("US/Eastern")
rth = pd.DataFrame({"d": bt.dt.date, "o": arr["open"], "h": arr["high"], "l": arr["low"], "c": arr["close"]})
day = rth.groupby("d").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
day["rng20"] = (day["h"] - day["l"]).rolling(20).mean().shift(1)
day["gap"] = day["o"] - day["c"].shift(1)
day["gapn"] = day["gap"] / day["rng20"]

# ── overnight high/low from the ETH master (prior 18:00 -> 9:29 ET) ────────────
print("loading ETH master for the overnight range ...", flush=True)
me = find_master("NQ", "5m", "eth")
ae_arr = load_master_arrays(me, date_from="2010-06-01", date_to="2026-06-30")
ebt = pd.to_datetime(pd.Series(ae_arr["index"]), unit="s", utc=True).dt.tz_convert("US/Eastern")
ed = pd.DataFrame({"h": ae_arr["high"], "l": ae_arr["low"]})
ed["t"] = ebt.values
hh = ebt.dt.hour + ebt.dt.minute / 60.0
# assign each overnight bar to the RTH date it PRECEDES: bars >= 18:00 belong to the NEXT
# calendar day's session; bars < 9:30 belong to that day's session.
sess_date = ebt.dt.date.where(hh < 9.5, (ebt + pd.Timedelta(days=1)).dt.date)
on_mask = (hh >= 18.0) | (hh < 9.5)
on = ed[on_mask.values].copy(); on["sd"] = sess_date[on_mask.values].values
onr = on.groupby("sd").agg(onh=("h", "max"), onl=("l", "min"))
print(f"  overnight ranges for {len(onr)} sessions")

T = T.join(day[["gapn"]], on="date").join(onr, on="date")

def bucket_report(title, frame, keyfn):
    print(f"\n=== {title} ===")
    frame = frame.copy(); frame["b"] = frame.apply(keyfn, axis=1)
    print(f"{'bucket':>28} | {'n':>5} | {'net$':>10} | {'avg$':>7} | {'WR%':>5} | {'PF':>5}")
    print("-" * 78)
    for b, g in sorted(frame.groupby("b"), key=lambda kv: -kv[1]["pnl"].sum()):
        p = g["pnl"].values
        gw = p[p > 0].sum(); gl = -p[p < 0].sum()
        pf = gw / gl if gl > 0 else float("inf")
        print(f"{b:>28} | {len(p):>5} | {p.sum():>10,.0f} | {p.mean():>7,.0f} | {100*(p>0).mean():>4.0f}% | {pf:>5.2f}")

# S: ON-range confluence
s = T.dropna(subset=["onh"])
def s_key(row):
    if row["side"] > 0:
        return "LONG beyond ON high" if row["entry"] >= row["onh"] else "LONG inside ON range"
    return "SHORT beyond ON low" if row["entry"] <= row["onl"] else "SHORT inside ON range"
bucket_report(f"S — overnight-range confluence ({len(s)} trades matched)", s, s_key)

# T: gap conditioning
t = T.dropna(subset=["gapn"])
def t_key(row):
    g = row["gapn"]
    mag = "big-up gap" if g > 0.25 else ("big-down gap" if g < -0.25 else "flat open")
    if mag == "flat open":
        return "flat open (either side)"
    withg = (g > 0 and row["side"] > 0) or (g < 0 and row["side"] < 0)
    return f"{mag} · {'WITH-gap' if withg else 'AGAINST-gap'} trade"
bucket_report(f"T — overnight gap vs trade side ({len(t)} trades matched)", t, t_key)

print("\nRead: a lever is only worth building if a bucket is decisively toxic (deep negative net")
print("across many trades) or golden — small deltas are noise; remember M (filters cut the edge).")
