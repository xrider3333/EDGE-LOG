"""ORB context-tilt v2 — the ONE pre-registered follow-up from round 3 (ORB.md §4.23).

Five independent lenses (S ON-range, T gap, X15 prior-close location, X17 fresh-air,
X18 streak, X19 CLV, X5 value-area) all found the same factor: in a STRETCHED context the
RESPONSIVE (fade) side carries the cream and the CHASING side is dead weight.

PRE-REGISTERED RULE (declared before running — do not tune after seeing results):
  If the session context is UP-STRETCHED:   shorts x W_FADE, longs x W_CHASE.
  If the session context is DOWN-STRETCHED: longs  x W_FADE, shorts x W_CHASE.
  Neutral (or contradictory flags): x1.0.  Magnitudes: (1.25, 0.75) and the softer (1.1, 0.9).

STRETCH DEFINITIONS (three independent single-variable definitions + their OR-composite;
all causal — prior-day daily values / today's open only):
  D1 GAP:    overnight gap vs trailing-20d avg range  > +0.25 (up) / < -0.25 (down)
  D2 CLOSE:  prior-day close location in its range    > 0.75  (up) / < 0.25  (down)
  D3 STREAK: consecutive daily up-closes >= +2 (up) / down-closes <= -2 (down)
  COMP:      up if any Di up (and no Di down); down if any Di down (and no Di up); else neutral.

GRADUATION BAR (stricter than usual, because this is a composite follow-up): the rule must pass
MAR >= baseline in BOTH windows for the pre-registered (1.25,0.75) on the COMPOSITE **and** on at
least 2 of the 3 single definitions, with the softer (1.1,0.9) also passing (magnitude plateau).
Finally a STACK test: context-v2 + the adopted compression x1.25 applied together (both graduates
must not fight). Usage: python tools/orb_context_tilt_v2.py
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
LBD = pd.Timestamp("2025-06-30").date()
CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
           atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)

print("running deploy config once (BE 1.0R, full window) ...", flush=True)
m = find_master("NQ", "5m", "rth")
arr = load_master_arrays(m, date_from="2010-06-07", date_to="2026-06-30")
r = ae.run_backtest("ORB_3_0_BE.py", arrays=arr, params=CFG, cost_pts=FEE, return_trades=True)
tr = r["trades"]; idx = arr["index"]
net_chk, dd_chk = r["total_pnl"] * MULT, abs(r["max_drawdown"]) * MULT
print(f"  ANCHOR: net ${net_chk:,.0f} / DD ${dd_chk:,.0f} / {len(tr)} trades  [expect $574,177 / $26,763 / 3951]")
assert abs(net_chk - 574177) < 5 and len(tr) == 3951, "anchor failed"

dates = pd.to_datetime(pd.Series([idx[t[0]] for t in tr]), unit="s", utc=True).dt.tz_convert("US/Eastern").dt.date
side  = np.array([t[3] for t in tr])
pnl   = np.array([t[2] for t in tr]) * MULT

# ── daily context (causal: everything shifted to describe the PRIOR day / today's open) ──
bt = pd.to_datetime(pd.Series(idx), unit="s", utc=True).dt.tz_convert("US/Eastern")
day = (pd.DataFrame({"d": bt.dt.date, "o": arr["open"], "h": arr["high"], "l": arr["low"], "c": arr["close"]})
       .groupby("d").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")))
day["rng20"] = (day["h"] - day["l"]).rolling(20).mean().shift(1)
day["gapn"]  = (day["o"] - day["c"].shift(1)) / day["rng20"]
prng = (day["h"] - day["l"]).shift(1)
day["ploc"]  = ((day["c"] - day["l"]) / (day["h"] - day["l"])).shift(1)
chg = np.sign(day["c"].diff())
streak = chg.copy()
for i in range(1, len(streak)):
    if chg.iloc[i] != 0 and chg.iloc[i] == chg.iloc[i - 1]:
        streak.iloc[i] = streak.iloc[i - 1] + chg.iloc[i]
day["streak"] = streak.shift(1)

DEFS = {
    "D1 gap":    (day["gapn"] > 0.25,  day["gapn"] < -0.25),
    "D2 close":  (day["ploc"] > 0.75,  day["ploc"] < 0.25),
    "D3 streak": (day["streak"] >= 2,  day["streak"] <= -2),
}
up_c = pd.concat([u for u, d in DEFS.values()], axis=1).any(axis=1)
dn_c = pd.concat([d for u, d in DEFS.values()], axis=1).any(axis=1)
DEFS["COMPOSITE"] = (up_c & ~dn_c, dn_c & ~up_c)

def stats(w):
    s = pnl * w
    lbm = np.array([d >= LBD for d in dates])
    o = s[~lbm]; oc = np.cumsum(o); odd = abs(float((oc - np.maximum.accumulate(oc)).min()))
    lb = s[lbm]; lc = np.cumsum(lb); ldd = abs(float((lc - np.maximum.accumulate(lc)).min())) if len(lb) else 0
    return (float(o.sum()), odd, float(o.sum()) / odd if odd else 0,
            float(lb.sum()), ldd, float(lb.sum()) / ldd if ldd else 0)

def weights(upmask, dnmask, wf, wc):
    up = np.array([bool(upmask.get(d, False)) for d in dates])
    dn = np.array([bool(dnmask.get(d, False)) for d in dates])
    w = np.ones(len(pnl))
    w[up & (side < 0)] = wf; w[up & (side > 0)] = wc
    w[dn & (side > 0)] = wf; w[dn & (side < 0)] = wc
    return w

b = stats(np.ones(len(pnl)))
hdr = f"{'rule':>28} | {'IS net$':>10} {'DD$':>8} {'MAR':>6} | {'LB net$':>8} {'DD$':>7} {'MAR':>5} | judge"
print("\n" + "=" * len(hdr)); print(hdr); print("-" * len(hdr))
print(f"{'baseline':>28} | {b[0]:>10,.0f} {b[1]:>8,.0f} {b[2]:>6.2f} | {b[3]:>8,.0f} {b[4]:>7,.0f} {b[5]:>5.2f} |")
results = {}
for name, (u, d) in DEFS.items():
    for wf, wc in ((1.1, 0.9), (1.25, 0.75)):
        s = stats(weights(u, d, wf, wc))
        ok = s[2] >= b[2] and s[5] >= b[5]
        results[(name, wf)] = ok
        nsig = int((weights(u, d, 2, 2) != 1).sum())
        print(f"{name+f' ({wf}/{wc})':>28} | {s[0]:>10,.0f} {s[1]:>8,.0f} {s[2]:>6.2f} | {s[3]:>8,.0f} {s[4]:>7,.0f} {s[5]:>5.2f} | {'PASS' if ok else 'fail'}  ({nsig} tr)")

# ── graduation bar ─────────────────────────────────────────────────────────────
singles_pass = sum(1 for n in ("D1 gap", "D2 close", "D3 streak") if results[(n, 1.25)])
comp_main, comp_soft = results[("COMPOSITE", 1.25)], results[("COMPOSITE", 1.1)]
grad = comp_main and comp_soft and singles_pass >= 2
print("-" * len(hdr))
print(f"BAR: composite (1.25/0.75) {'PASS' if comp_main else 'FAIL'} · soft (1.1/0.9) "
      f"{'PASS' if comp_soft else 'FAIL'} · singles at 1.25: {singles_pass}/3 (need >=2)")
print(f">>> CONTEXT-TILT v2: {'GRADUATES' if grad else 'does NOT graduate'}")

# ── stack test with the adopted compression tilt ───────────────────────────────
day["rng"] = day["h"] - day["l"]
nr7 = (day["rng"] == day["rng"].rolling(7).min()).shift(1, fill_value=False)
ins = ((day["h"] < day["h"].shift(1)) & (day["l"] > day["l"].shift(1))).shift(1, fill_value=False)
compm = np.array([bool(nr7.get(d, False) or ins.get(d, False)) for d in dates])
w_comp = np.where(compm, 1.25, 1.0)
u, d = DEFS["COMPOSITE"]
w_ctx = weights(u, d, 1.25, 0.75)
print("\n=== STACK test (both graduates together vs each alone) ===")
for lbl, w in (("compression x1.25 alone", w_comp), ("context-v2 alone", w_ctx),
               ("STACKED (ctx * compression)", w_comp * w_ctx)):
    s = stats(w)
    ok = s[2] >= b[2] and s[5] >= b[5]
    print(f"{lbl:>28} | IS MAR {s[2]:>5.2f} | LB MAR {s[5]:>5.2f} | {'PASS' if ok else 'fail'}")
