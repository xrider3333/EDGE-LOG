# orb_fragility.py — how much does ORB's outcome depend on DATA-FEED precision?
#
# Two vendors (Databento vs TV) occasionally disagree on a 5-min bar's high/low.
# This quantifies how exposed ORB is to that, over the full RTH history:
#   1. BOTH-BROKE %    — sessions where price breached BOTH the OR high AND the
#                        OR low. On these days WHICH side you trade is decided by
#                        whichever boundary your feed prints first -> direction is
#                        feed-fragile. Of those, how often the two sides have
#                        OPPOSITE P&L sign (i.e. the flip actually flips win<->loss).
#   2. +-1 TICK MC     — jitter every bar's high/low by +-1 tick (0.25), re-run,
#                        and report how the aggregate P&L and the per-trade side
#                        decisions move. Models small uniform feed noise (the large
#                        30-70pt single-print disagreements are rarer + unmodeled).
#
# Run:  python tools/orb_fragility.py            (NQ)
#       set XC_INST=ES & python tools/orb_fragility.py
import os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTERS = {"NQ": ("master_00c66966.csv", 20), "ES": ("master_a85a0438.csv", 50)}
INST = os.environ.get("XC_INST", "NQ").upper()
fname, MULT = MASTERS[INST]
TICK = 0.25
COST = 5.66 / MULT
OR_BARS, STOP_FRAC = 3, 0.75
VOL_FILTER = float(os.environ.get("FRAG_VOL", "0"))   # 0=off; 1.5=deployable config
N_MC = int(os.environ.get("FRAG_MC", "100"))

df = pd.read_csv(os.path.join(ROOT, "augur_uploads", fname))
dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
df.index = dt
O, H, L, C = (df[c].values.astype(float) for c in ["open", "high", "low", "close"])
V = df["volume"].values.astype(float)
DAY = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")
n = len(C)
bounds = []; i = 0
while i < n:
    j = i
    while j < n and DAY[j] == DAY[i]: j += 1
    bounds.append((i, j)); i = j


def run(Hx, Lx, want_both=False):
    """Replay ORB (vol filter off). Returns (pnls, sides, both_stats).
    both_stats only filled when want_both: per both-broke session, the actual P&L
    and the opposite-side P&L (to see if the flip changes the sign)."""
    pnls, sides, both = [], [], []
    for (a, b) in bounds:
        m = b - a
        if m <= OR_BARS + 1: continue
        sh, sl, so, sc = Hx[a:b], Lx[a:b], O[a:b], C[a:b]
        sv = V[a:b]
        or_hi, or_lo = sh[:OR_BARS].max(), sl[:OR_BARS].min()
        rng = or_hi - or_lo
        if rng <= 0: continue
        # did each boundary ever break post-OR?
        post_hi = sh[OR_BARS:] >= or_hi
        post_lo = sl[OR_BARS:] <= or_lo
        broke_up, broke_dn = post_hi.any(), post_lo.any()
        # actual trade: long-first tie-break, scan in time
        pos = 0; entry = stop = 0.0; pnl = None
        for k in range(OR_BARS, m):
            if pos == 0:
                up, dn = sh[k] >= or_hi, sl[k] <= or_lo
                if not (up or dn): continue
                if VOL_FILTER > 0 and k > 0:
                    mv = sv[:k].mean()
                    if mv > 0 and sv[k] < VOL_FILTER * mv: continue
                if up:
                    entry = max(or_hi, so[k]) if so[k] > or_hi else or_hi
                    stop = entry - STOP_FRAC*rng; pos = 1
                else:
                    entry = min(or_lo, so[k]) if so[k] < or_lo else or_lo
                    stop = entry + STOP_FRAC*rng; pos = -1
                continue
            if pos > 0 and sl[k] <= stop:
                ex = so[k] if so[k] < stop else stop; pnl = ex-entry; break
            if pos < 0 and sh[k] >= stop:
                ex = so[k] if so[k] > stop else stop; pnl = entry-ex; break
        if pos == 0: continue
        if pnl is None: pnl = (sc[-1]-entry) if pos > 0 else (entry-sc[-1])
        pnls.append((pnl-COST)*MULT); sides.append(pos)
        if want_both and broke_up and broke_dn:
            # counterfactual: the OTHER side, entered at its boundary, same rules
            oside = -pos
            o_entry = or_hi if oside > 0 else or_lo
            o_stop = o_entry - STOP_FRAC*rng if oside > 0 else o_entry + STOP_FRAC*rng
            # find first opposite-side breach AFTER OR, then run it
            opnl = None; started = False
            for k in range(OR_BARS, m):
                if not started:
                    if oside > 0 and sh[k] >= or_hi: started = True
                    elif oside < 0 and sl[k] <= or_lo: started = True
                    else: continue
                    continue
                if oside > 0 and sl[k] <= o_stop: opnl = o_stop-o_entry; break
                if oside < 0 and sh[k] >= o_stop: opnl = o_entry-o_stop; break
            if started and opnl is None: opnl = (sc[-1]-o_entry) if oside > 0 else (o_entry-sc[-1])
            if opnl is not None:
                both.append(((pnl-COST)*MULT, (opnl-COST)*MULT))
    return np.array(pnls), np.array(sides), both


base_pnl, base_sides, both = run(H, L, want_both=True)
nt = len(base_pnl)
print(f"{INST} ORB fragility | {fname} | vol_filter={VOL_FILTER} | {len(bounds)} sessions, {nt} trades | net of ${COST*MULT:.2f}/RT")
print(f"  baseline: total ${base_pnl.sum():,.0f}  PF {base_pnl[base_pnl>0].sum()/-base_pnl[base_pnl<0].sum():.2f}  "
      f"WR {100*(base_pnl>0).mean():.0f}%")

# 1. both-broke exposure
nb = len(both)
both = np.array(both) if both else np.zeros((0,2))
sign_flips = int(np.sum(np.sign(both[:,0]) != np.sign(both[:,1]))) if nb else 0
print(f"\n  [1] BOTH-BROKE (direction is feed-fragile):")
print(f"      {nb}/{nt} trades = {100*nb/nt:.0f}% of sessions breached BOTH OR boundaries")
print(f"      of those, {sign_flips} ({100*sign_flips/nb:.0f}%) have OPPOSITE P&L sign for the two sides")
print(f"      => ~{100*sign_flips/nt:.0f}% of ALL trades are win<->loss coin-flips between feeds")
if nb:
    actual_sum = both[:,0].sum(); opp_sum = both[:,1].sum()
    print(f"      actual-side total on both-broke days ${actual_sum:,.0f}  vs opposite-side ${opp_sum:,.0f} "
          f"(swing ${abs(actual_sum-opp_sum):,.0f})")

# 2. +-1 tick Monte-Carlo
rng = np.random.default_rng(42)
mc_tot, mc_flips = [], []
for _ in range(N_MC):
    jh = H + rng.choice([-TICK, 0, TICK], size=n)
    jl = L + rng.choice([-TICK, 0, TICK], size=n)
    jh = np.maximum(jh, np.maximum(O, C)); jl = np.minimum(jl, np.minimum(O, C))
    p, s, _ = run(jh, jl)
    mc_tot.append(p.sum())
    mlen = min(len(s), len(base_sides))
    mc_flips.append(int(np.sum(s[:mlen] != base_sides[:mlen])))
mc_tot = np.array(mc_tot); mc_flips = np.array(mc_flips)
print(f"\n  [2] +-1 TICK NOISE MONTE-CARLO ({N_MC} trials):")
print(f"      total P&L: baseline ${base_pnl.sum():,.0f} | MC mean ${mc_tot.mean():,.0f} "
      f"+- ${mc_tot.std():,.0f}  (range ${mc_tot.min():,.0f}..${mc_tot.max():,.0f})")
print(f"      P&L swing from just +-1 tick of feed noise: +-{100*mc_tot.std()/abs(base_pnl.sum()):.1f}% of baseline")
print(f"      avg trades that flip side per trial: {mc_flips.mean():.1f} of {nt} ({100*mc_flips.mean()/nt:.1f}%)")
