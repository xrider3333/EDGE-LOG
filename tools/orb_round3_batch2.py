"""ORB round-3 batch 2 — X3 (relative volume) + X6 (VWAP-side), as overlays on the deploy config.

Method (same quality rules as batch 1):
  1. Run the DEPLOY config ONCE on FULL with return_trades; every signal below is computed
     CAUSALLY from the bar arrays at/before each trade's ENTRY bar — nothing peeks forward.
  2. X3 RVOL: cumulative session volume at the entry bar's depth vs the mean of the SAME-depth
     cumulative volume over the PRIOR 14 sessions (a prior session shorter than the depth
     contributes its full-session volume). <14 priors -> rvol = NaN (excluded from buckets and
     tilt signal, weight 1.0). Diagnostic buckets, then TILT tests (1.25x / 1.5x on rvol>=1.0
     and separately rvol>=1.2).
  3. X6 VWAP-side: session VWAP (volume x hlc3, cumulative through the entry bar); a trade is
     "aligned" when it fires in the direction of price-vs-VWAP (long above / short below).
     Diagnostic buckets, then TILT tests (1.25x / 1.5x on aligned).
  4. Tilts multiply size on signal trades (1.0 otherwise) — never delete trades. OPT/LB are
     sliced from the FULL trade list by ENTRY date (valid: the strategy is EOD-flat, so a
     window only matters via dates). JUDGE: a tilt graduates ONLY if MAR >= baseline in BOTH
     the OPT window AND the LB window.

Anchor (must reproduce, else the data path is wrong):
    deploy config, FULL -> net $574,177 / max DD $26,763 / 3951 trades.

Usage: python tools/orb_round3_batch2.py
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
from augur_engine.engine import run_backtest, find_master, load_master_arrays

FEE, MULT = 0.533, 20.0
FULL = ("2010-06-07", "2026-06-30")
LB_FROM = pd.Timestamp("2025-06-30").date()
CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
           atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)
ANCHOR_NET, ANCHOR_DD, ANCHOR_N, TOL = 574_177.0, 26_763.0, 3951, 5.0
RVOL_LOOKBACK = 14

# ── run the deploy config ONCE on FULL, then hard-anchor ──────────────────────
print("running deploy config once (BE 1.0R, full window) ...", flush=True)
m = find_master("NQ", "5m", "rth")
if m is None:
    print("ANCHOR FAILED: no NQ 5m rth master found"); sys.exit(1)
arr = load_master_arrays(m, date_from=FULL[0], date_to=FULL[1])
r = run_backtest("ORB_3_0_BE.py", arrays=arr, params=CFG, cost_pts=FEE, return_trades=True)
net = r["total_pnl"] * MULT
dd = abs(r["max_drawdown"]) * MULT
n = int(r["num_trades"])
print(f"  FULL net ${net:,.2f} / DD ${dd:,.2f} / {n} trades "
      f"[expect ${ANCHOR_NET:,.0f} / ${ANCHOR_DD:,.0f} / {ANCHOR_N}]")
if abs(net - ANCHOR_NET) > TOL or abs(dd - ANCHOR_DD) > TOL or n != ANCHOR_N:
    print("ANCHOR FAILED — stopping (do not trust anything below)."); sys.exit(1)
print("  ANCHOR OK", flush=True)

trades = sorted(r["trades"], key=lambda t: t[0])  # chronological by entry bar
vol = np.asarray(arr["volume"], dtype=float)
hi, lo, cl = (np.asarray(arr[k], dtype=float) for k in ("high", "low", "close"))
day_id = np.asarray(arr["day_id"])
nbar = len(vol)

# session runs: start index, length, and per-bar session ordinal / session start
new_sess = np.empty(nbar, dtype=bool)
new_sess[0] = True
new_sess[1:] = day_id[1:] != day_id[:-1]
sess_ord = np.cumsum(new_sess) - 1            # per-bar session ordinal 0..S-1
starts = np.flatnonzero(new_sess)             # per-session first bar index
lens = np.diff(np.append(starts, nbar))       # per-session bar count

# prefix sums for O(1) in-session cumulative volume / volume*hlc3
cs_v = np.concatenate(([0.0], np.cumsum(vol)))
cs_pv = np.concatenate(([0.0], np.cumsum(vol * (hi + lo + cl) / 3.0)))

entry_dates = pd.to_datetime(pd.Series([arr["index"][t[0]] for t in trades]),
                             unit="s", utc=True).dt.tz_convert("US/Eastern").dt.date.values
pnl = np.array([t[2] * MULT for t in trades])          # trade $, already net of fees
side = np.array([t[3] for t in trades])
entry_px = np.array([t[4] for t in trades], dtype=float)

rvol = np.full(len(trades), np.nan)
aligned = np.zeros(len(trades), dtype=bool)
for i, t in enumerate(trades):
    e = t[0]
    k = sess_ord[e]
    s = starts[k]
    # X3 — relative cumulative volume vs prior 14 sessions at the same depth.
    # STRICTLY CAUSAL (verification 2026-07-16): volume through the bar BEFORE entry only.
    # The first cut included the entry bar's full volume (cs_v[e+1]) and "graduated" —
    # but the breakout bar's volume spike IS the break (circular); with strictly-prior
    # volume the rvol>=1.0 tilts FAIL the lockbox (6.52/5.91 vs 7.06). Keep strict.
    depth = e - s                     # bars strictly before the entry bar
    if k >= RVOL_LOOKBACK and depth >= 1:
        cum_today = cs_v[e] - cs_v[s]
        priors = np.empty(RVOL_LOOKBACK)
        for j in range(k - RVOL_LOOKBACK, k):
            b = starts[j] + min(depth, lens[j])       # same strict depth, capped
            priors[j - (k - RVOL_LOOKBACK)] = cs_v[b] - cs_v[starts[j]]
        mp = priors.mean()
        if mp > 0:
            rvol[i] = cum_today / mp
    # X6 — session VWAP through the entry bar (inclusive)
    cv = cs_v[e + 1] - cs_v[s]
    vwap = (cs_pv[e + 1] - cs_pv[s]) / cv if cv > 0 else np.nan
    aligned[i] = (not np.isnan(vwap)) and ((side[i] > 0 and entry_px[i] > vwap) or
                                           (side[i] < 0 and entry_px[i] < vwap))

# ── diagnostic buckets (FULL window) ──────────────────────────────────────────
def bucket_row(label, mask):
    p = pnl[mask]
    if len(p) == 0:
        print(f"{label:>26} | {0:>5} | {'-':>10} | {'-':>7} | {'-':>4} | {'-':>5}")
        return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    pf = gw / gl if gl > 0 else 99.0
    print(f"{label:>26} | {len(p):>5} | {p.sum():>10,.0f} | {p.mean():>7,.0f} "
          f"| {100 * (p > 0).mean():>3.0f}% | {pf:>5.2f}")

print("\n=== X3 — RVOL buckets (cum session vol at entry depth vs prior 14 mean, FULL) ===")
print(f"{'bucket':>26} | {'n':>5} | {'net$':>10} | {'avg$':>7} | {'WR%':>4} | {'PF':>5}")
has = ~np.isnan(rvol)
bucket_row("rvol < 0.8", has & (rvol < 0.8))
bucket_row("0.8 <= rvol < 1.2", has & (rvol >= 0.8) & (rvol < 1.2))
bucket_row("1.2 <= rvol < 1.5", has & (rvol >= 1.2) & (rvol < 1.5))
bucket_row("rvol >= 1.5", has & (rvol >= 1.5))
bucket_row("no history (<14 priors)", ~has)

print("\n=== X6 — VWAP-side buckets (entry vs session VWAP incl. entry bar, FULL) ===")
print(f"{'bucket':>26} | {'n':>5} | {'net$':>10} | {'avg$':>7} | {'WR%':>4} | {'PF':>5}")
bucket_row("aligned (with VWAP side)", aligned)
bucket_row("opposed (against VWAP)", ~aligned)

# ── tilt tests: size w on signal trades, 1.0 otherwise; MAR in FULL/OPT/LB ────
opt_m = np.array([d < LB_FROM for d in entry_dates])
lb_m = ~opt_m

def window_stats(w, mask):
    s = (pnl * w)[mask]
    if len(s) == 0:
        return 0.0, 0.0, 0.0
    cum = np.cumsum(s)
    ddw = abs(float((cum - np.maximum.accumulate(cum)).min()))
    netw = float(s.sum())
    return netw, ddw, (netw / ddw if ddw > 0 else 0.0)

def tilt_row(label, w):
    f = window_stats(w, np.ones(len(pnl), dtype=bool))
    o = window_stats(w, opt_m)
    l = window_stats(w, lb_m)
    print(f"{label:>30} | {f[0]:>10,.0f} {f[1]:>8,.0f} {f[2]:>6.1f} "
          f"| {o[0]:>10,.0f} {o[1]:>8,.0f} {o[2]:>6.1f} "
          f"| {l[0]:>8,.0f} {l[1]:>7,.0f} {l[2]:>5.1f}")
    return f, o, l

print(f"\n(OPT = entry date < {LB_FROM}: {int(opt_m.sum())} trades; LB: {int(lb_m.sum())} trades)")
print("\n=== TILT tests — size w on signal trades (1.0 otherwise), MAR judged OPT AND LB ===")
print(f"{'tilt':>30} | {'FULL net$':>10} {'DD$':>8} {'MAR':>6} "
      f"| {'OPT net$':>10} {'DD$':>8} {'MAR':>6} | {'LB net$':>8} {'DD$':>7} {'MAR':>5}")
base_f, base_o, base_l = tilt_row("baseline (1.0x)", np.ones(len(pnl)))

tilts = []
for thresh in (1.0, 1.2):
    sig = has & (rvol >= thresh)
    for w in (1.25, 1.5):
        wt = np.where(sig, w, 1.0)
        label = f"X3 rvol>={thresh} x{w} ({int(sig.sum())} tr)"
        tilts.append((f"X3 rvol>={thresh} x{w}", tilt_row(label, wt)))
for w in (1.25, 1.5):
    wt = np.where(aligned, w, 1.0)
    label = f"X6 aligned x{w} ({int(aligned.sum())} tr)"
    tilts.append((f"X6 aligned x{w}", tilt_row(label, wt)))

# ── judge ─────────────────────────────────────────────────────────────────────
print("\n=== JUDGE (graduates only if MAR >= baseline in BOTH OPT and LB) ===")
for name, (f, o, l) in tilts:
    ok_o, ok_l = o[2] >= base_o[2], l[2] >= base_l[2]
    verdict = "GRADUATES" if (ok_o and ok_l) else "does NOT graduate"
    print(f"JUDGE {name:>18}: {verdict}  "
          f"(OPT MAR {o[2]:.2f} vs {base_o[2]:.2f} {'PASS' if ok_o else 'FAIL'}; "
          f"LB MAR {l[2]:.2f} vs {base_l[2]:.2f} {'PASS' if ok_l else 'FAIL'})")
