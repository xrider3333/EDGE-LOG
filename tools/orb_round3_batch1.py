"""ORB round-3 batch 1 — compression (X1 NR7 / X2 inside-day) + calendar (X9 weekday /
X10 OPEX·roll·month-end / X12 pre-holiday eve), as overlays on the deploy config.

Method (quality rules from B/M/N/O):
  1. DIAGNOSTIC buckets first — n / net / avg / PF per signal state. A signal only graduates
     if its buckets differ decisively.
  2. TILT test (not filter) only for the A-PRIORI hypothesis — Crabel compression: size
     1.5x on sessions whose PRIOR day was NR7 / inside / ID+NR4 (causal by construction).
     Judged on MAR, in-sample AND lockbox (2025-06-30 →), vs the 1.0x baseline.
  3. Calendar signals are DIAGNOSTIC-ONLY this round (fitting weekday weights = snooping);
     anything extreme gets a follow-up with a pre-registered rule.
X11 (FOMC days) needs a verified meeting-dates file — PENDING, not approximated.

Usage: python tools/orb_round3_batch1.py
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
T = pd.DataFrame({
    "date": pd.to_datetime(pd.Series([idx[t[0]] for t in tr]), unit="s", utc=True).dt.tz_convert("US/Eastern").dt.date,
    "pnl": [t[2] * MULT for t in tr],
})
print(f"  {len(T)} trades, net ${T['pnl'].sum():,.0f}  [expect $574,177]")

# ── daily bars (RTH) → compression flags for the PRIOR day (causal shift) ──────
bt = pd.to_datetime(pd.Series(idx), unit="s", utc=True).dt.tz_convert("US/Eastern")
day = (pd.DataFrame({"d": bt.dt.date, "h": arr["high"], "l": arr["low"]})
       .groupby("d").agg(h=("h", "max"), l=("l", "min")))
day["rng"] = day["h"] - day["l"]
day["nr7"] = day["rng"] == day["rng"].rolling(7).min()
day["nr4"] = day["rng"] == day["rng"].rolling(4).min()
day["inside"] = (day["h"] < day["h"].shift(1)) & (day["l"] > day["l"].shift(1))
day["idnr4"] = day["inside"] & day["nr4"]
sig = pd.DataFrame({k: day[k].shift(1, fill_value=False) for k in ("nr7", "nr4", "inside", "idnr4")})

# ── calendar flags ─────────────────────────────────────────────────────────────
dts = pd.to_datetime(pd.Series(sorted(day.index)))
cal = pd.DataFrame(index=dts.dt.date)
cal["wd"] = dts.dt.day_name().values
def third_friday(y, mth):
    d = pd.Timestamp(year=y, month=mth, day=15)
    while d.dayofweek != 4: d += pd.Timedelta(days=1)
    return d.date()
opex = {third_friday(y, mth) for y in range(2010, 2027) for mth in range(1, 13)}
cal["opex"] = [d in opex for d in cal.index]
qexp = {third_friday(y, mth) for y in range(2010, 2027) for mth in (3, 6, 9, 12)}
qexp_ts = sorted(pd.Timestamp(d) for d in qexp)
def in_roll_week(d):
    ts = pd.Timestamp(d)
    return any(0 <= (q - ts).days <= 7 for q in qexp_ts)
cal["rollwk"] = [in_roll_week(d) for d in cal.index]
mo = dts.dt.to_period("M")
last2 = dts.groupby(mo.values).apply(lambda s: s.iloc[-2:] if len(s) >= 2 else s)
last2_set = set(pd.to_datetime(last2.values).date)
cal["moend"] = [d in last2_set for d in cal.index]
# pre-holiday eve: a session followed by a >3-calendar-day gap to the next session
nxt = dts.shift(-1)
gap_days = (nxt - dts).dt.days
cal["preholiday"] = [(g is not pd.NaT and g > 3) for g in gap_days]

T = T.join(sig, on="date").join(cal, on="date")
for c in ("nr7", "nr4", "inside", "idnr4", "opex", "rollwk", "moend", "preholiday"):
    T[c] = T[c].fillna(False)

def buckets(title, key, order=None):
    print(f"\n=== {title} ===")
    print(f"{'bucket':>22} | {'n':>5} | {'net$':>10} | {'avg$':>6} | {'WR%':>4} | {'PF':>5}")
    groups = T.groupby(T[key].astype(str))
    keys = order or sorted(groups.groups.keys())
    for b in keys:
        if b not in groups.groups: continue
        p = groups.get_group(b)["pnl"].values
        gw = p[p > 0].sum(); gl = -p[p < 0].sum()
        print(f"{b:>22} | {len(p):>5} | {p.sum():>10,.0f} | {p.mean():>6,.0f} | {100*(p>0).mean():>3.0f}% | {gw/gl if gl>0 else 99:>5.2f}")

buckets("X1 — prior day NR7?", "nr7", ["False", "True"])
buckets("X2a — prior day inside?", "inside", ["False", "True"])
buckets("X2b — prior day ID+NR4?", "idnr4", ["False", "True"])
buckets("X9 — weekday", "wd", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
buckets("X10a — OPEX (3rd Friday)?", "opex", ["False", "True"])
buckets("X10b — quarterly roll week?", "rollwk", ["False", "True"])
buckets("X10c — month-end (last 2)?", "moend", ["False", "True"])
buckets("X12 — pre-holiday eve?", "preholiday", ["False", "True"])

# ── TILT test: 1.5x (and 1.25x) size on compression days, MAR judged IS+LB ─────
def tilt_stats(w):
    s = T["pnl"].values * w
    cum = np.cumsum(s); dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    net = float(s.sum()); mar = net / dd if dd else 0
    lbm = np.array([d >= LB_FROM for d in T["date"]])
    lb = s[lbm]; lc = np.cumsum(lb); ldd = abs(float((lc - np.maximum.accumulate(lc)).min())) if len(lb) else 0
    lnet = float(lb.sum()); lmar = lnet / ldd if ldd else 0
    return net, dd, mar, lnet, ldd, lmar

print("\n=== TILT test (size w on signal days, 1.0 otherwise) — MAR both windows ===")
print(f"{'tilt':>26} | {'FULL net':>10} {'DD':>8} {'MAR':>6} | {'LB net':>8} {'DD':>7} {'MAR':>5}")
base = tilt_stats(np.ones(len(T)))
print(f"{'baseline (1.0x)':>26} | {base[0]:>10,.0f} {base[1]:>8,.0f} {base[2]:>6.1f} | {base[3]:>8,.0f} {base[4]:>7,.0f} {base[5]:>5.1f}")
for key in ("nr7", "inside", "idnr4"):
    for f in (1.25, 1.5):
        w = np.where(T[key].values, f, 1.0)
        s = tilt_stats(w)
        n_sig = int(T[key].sum())
        print(f"{key+' x'+str(f)+' ('+str(n_sig)+' tr)':>26} | {s[0]:>10,.0f} {s[1]:>8,.0f} {s[2]:>6.1f} | {s[3]:>8,.0f} {s[4]:>7,.0f} {s[5]:>5.1f}")
print("\nX11 (FOMC days): PENDING — needs a verified 2010-2026 meeting-dates file (not approximated).")
print("Judge: a tilt graduates only if MAR >= baseline in BOTH windows (it adds size, so DD may rise;")
print("the question is whether the signal days' edge is rich enough to pay for it).")
