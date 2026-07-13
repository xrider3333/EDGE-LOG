"""ORB item M — black-swan / regime filters on the deploy config (owner idea 2026-07-12).

Premise check first: the deploy config's (BE 1.0R) max DD is NOT COVID —
    #1  2025-04-09 -> 2025-07-11  -$27.4k   (post-tariff-spike chop; the window still NETS +$26.6k)
    #2  2021-09-10 -> 2021-12-02  -$18.0k   (distribution/topping chop)
    #3  2023-02-15 -> 2023-07-10  -$18.0k   (low-vol grind)
    #4  2020-03-02 -> 2020-05-11  -$16.2k   (COVID -- and Feb15-Apr30 2020 NETS +$4.1k)
ORB feeds on vol expansion (2022 = best year, shorts carry the edge), so crisis filters may
cut winners. This tool tests the owner's two ideas anyway — the data decides:

  A) DAILY-TREND STRUCTURE: skip a session when the prior day(s) made lower lows / closed
     below a moving average (variants below). All signals use PRIOR days only (causal).
  B) VIX LEVEL: skip a session when YESTERDAY's VIX close is above a threshold (^VIX daily
     from yfinance; prior close -> today's decision, causal).

Method: run the deploy config ONCE with return_trades, then apply each filter as a session
OVERLAY on the trade list (ORB = 1 trade/session, filters only remove whole sessions, so the
overlay is exact and instant). Metrics per variant: full-window net/DD/MAR + the held-out
lockbox (2025-06-30 -> 2026-06-30), plus what the filter removed (long vs short PnL).

Usage: python tools/orb_regime_filters.py
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
LB_FROM = "2025-06-30"
CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
           atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)

print("running deploy config once (BE 1.0R, full window) ...", flush=True)
m = find_master("NQ", "5m", "rth")
arr = load_master_arrays(m, date_from="2010-06-07", date_to="2026-06-30")
r = ae.run_backtest("ORB_3_0_BE.py", arrays=arr, params=CFG, cost_pts=FEE, return_trades=True)
tr = r["trades"]; idx = arr["index"]

t_date = pd.to_datetime(pd.Series([idx[t[0]] for t in tr]), unit="s", utc=True).dt.tz_convert("US/Eastern").dt.date.values
t_pnl  = np.array([t[2] for t in tr]) * MULT   # engine _apply_costs already netted the trades
t_dir  = np.array([t[3] for t in tr])                        # +1 long / -1 short
lb_cut = pd.Timestamp(LB_FROM).date()

# ── daily bars (RTH) from the same master — high/low/close per session date ────
bt = pd.to_datetime(pd.Series(idx), unit="s", utc=True).dt.tz_convert("US/Eastern")
df = pd.DataFrame({"d": bt.dt.date, "h": arr["high"], "l": arr["low"], "c": arr["close"]})
day = df.groupby("d").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
day["ll1"]  = day["l"] < day["l"].shift(1)                                  # made a lower low
day["ll2"]  = day["ll1"] & day["ll1"].shift(1, fill_value=False)            # 2 consecutive LLs
day["lhll"] = day["ll1"] & (day["h"] < day["h"].shift(1))                   # lower high AND lower low
day["sma20"] = day["c"] < day["c"].rolling(20).mean()
day["sma50"] = day["c"] < day["c"].rolling(50).mean()
# shift(1): YESTERDAY's structure decides TODAY's session (causal)
sig = {k: day[k].shift(1, fill_value=False) for k in ("ll1", "ll2", "lhll", "sma20", "sma50")}

# ── VIX daily closes (prior close -> today's decision) ─────────────────────────
vix_prev = None
try:
    import yfinance as yf
    v = yf.download("^VIX", start="2010-01-01", end="2026-07-01", progress=False, auto_adjust=False)
    vc = v["Close"] if "Close" in v else v.iloc[:, 0]
    if hasattr(vc, "columns"):                                # yf>=1.x returns a frame
        vc = vc.iloc[:, 0]
    vix_prev = vc.shift(1)                                    # yesterday's close
    vix_prev.index = pd.to_datetime(vix_prev.index).date
    print(f"  VIX daily loaded: {len(vix_prev)} rows ({vc.index.min().date()} -> {vc.index.max().date()})")
except Exception as e:
    print(f"  !! VIX unavailable ({type(e).__name__}: {e}) — skipping VIX variants")

def skipset_trend(key):
    s = sig[key]
    return set(s.index[s.values])

def skipset_vix(th):
    s = vix_prev[vix_prev > th]
    return set(s.index)

def overlay(skip_dates, label):
    keep = ~np.isin(t_date, list(skip_dates)) if skip_dates else np.ones(len(t_pnl), bool)
    kept, cut = t_pnl[keep], t_pnl[~keep]
    cum = np.cumsum(kept); dd = float((cum - np.maximum.accumulate(cum)).min()) if len(cum) else 0.0
    net = float(kept.sum()); mar = (net / abs(dd)) if dd else 0.0
    lbm = keep & (t_date >= lb_cut)
    lb = t_pnl[lbm]; lcum = np.cumsum(lb)
    ldd = float((lcum - np.maximum.accumulate(lcum)).min()) if len(lcum) else 0.0
    lnet = float(lb.sum()); lmar = (lnet / abs(ldd)) if ldd else 0.0
    cutL = float(t_pnl[(~keep) & (t_dir > 0)].sum()); cutS = float(t_pnl[(~keep) & (t_dir < 0)].sum())
    print(f"{label:>22} | n {keep.sum():>4} | full ${net:>9,.0f} DD ${abs(dd):>7,.0f} MAR {mar:>5.1f} "
          f"| LB ${lnet:>7,.0f} DD ${abs(ldd):>6,.0f} MAR {lmar:>4.1f} "
          f"| removed: long ${cutL:>8,.0f} short ${cutS:>8,.0f}")
    return dict(net=net, dd=abs(dd), mar=mar, lnet=lnet, ldd=abs(ldd), lmar=lmar)

hdr = f"{'filter':>22} | {'n':>6} | {'FULL net / DD / MAR':^34} | {'LOCKBOX net / DD / MAR':^28} | removed PnL by side"
print("\n" + "=" * len(hdr)); print(hdr); print("-" * len(hdr))
base = overlay(set(), "baseline (no filter)")
for key, lbl in (("ll1", "skip lower-low day"), ("ll2", "skip 2x lower-lows"),
                 ("lhll", "skip LH+LL day"), ("sma20", "skip close<SMA20"), ("sma50", "skip close<SMA50")):
    overlay(skipset_trend(key), lbl)
if vix_prev is not None:
    for th in (20, 25, 30, 40):
        overlay(skipset_vix(th), f"skip VIX>{th}")
print("-" * len(hdr))
print("Read: a filter helps ONLY if MAR improves in BOTH windows. 'removed short $' is the cost of")
print("cutting down-regime sessions — shorts carry ORB's edge (PF 2.74 vs 1.03, ORB.md 4.11).")
