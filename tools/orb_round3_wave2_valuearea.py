"""ORB round-3 wave 2 — X5 prior-day VALUE AREA context, as overlays on the deploy config.

Prior-session volume profile (strictly causal — built ONLY from the PRIOR session's 5m
bars, all of which completed before today's open): each bar's volume is spread uniformly
across 1.0-point bins between its low and high (bin p covers [p, p+1)); POC = the
max-volume bin; VALUE AREA = expand from the POC one bin at a time toward whichever
adjacent side holds more volume (tie -> up) until >= 70% of session volume is covered.
VAH = upper edge of the top VA bin, VAL = lower edge of the bottom VA bin, so the value
area is the closed price band [VAL, VAH].

Method (quality rules from B/M/N/O):
  1. Run the deploy config ONCE on FULL with trades; HARD ANCHOR must reproduce
     ($574,177 net / $26,763 DD / 3951 trades) or the data path is wrong — abort.
  2. DIAGNOSTIC buckets first (n / net / avg / WR / PF, FULL window):
       A) today's RTH OPEN vs the prior VA (above VAH / inside / below VAL) x trade side.
       B) ENTRY price vs the prior VA edges: long entry beyond VAH / short entry beyond
          VAL = "out of value" (the breakout leaves the prior day's accepted-value zone)
          vs "inside VA" (entry within the band) vs "counter-side" (long from below VAL /
          short from above VAH).
       C) 80%-rule context (DIAGNOSTIC ONLY, no new strategy): sessions that OPENED
          outside the prior VA and then CLOSED a bar back inside it BEFORE the ORB entry
          bar (the classic 80%-rule setup: price re-accepted into value) vs the rest.
  3. PRE-REGISTERED TILT: "out of value" (B) x1.25 — size UP entries that break beyond
     the prior value area in the trade's direction.  x1.1 / x1.5 run as plateau
     neighbors.  Judged on MAR vs the 1.0x baseline in OPT AND LB (trades sliced by ET
     entry date: < 2025-06-30 = OPT, >= = LB; fresh cumsum per window); a single
     knife-edge pass does NOT graduate.  Tilts multiply size (1.0 otherwise) — no trades
     are deleted.

Causality note: the VA/POC come from the prior session only; today's RTH open (A) and the
bars strictly BEFORE the entry bar (C) are all known at the entry touch; the entry price
(B) is the touch itself.  Nothing uses the entry bar's own close/high/low/volume.

Usage: python tools/orb_round3_wave2_valuearea.py
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
ANCHOR = dict(net=574_177.0, dd=26_763.0, n=3951, tol=5.0)
VA_COVER = 0.70


def epoch_s(ix):
    """arr['index'] as int64 epoch SECONDS — handles both raw epoch arrays and the
    tz-aware DatetimeIndex that load_master_arrays returns (asi8 is UTC ns)."""
    a = np.asarray(ix)
    if np.issubdtype(a.dtype, np.number):
        return a.astype(np.int64)
    return pd.DatetimeIndex(ix).asi8 // 1_000_000_000

# ── 1. deploy run + HARD ANCHOR ───────────────────────────────────────────────
print("running deploy config once (NQ 5m RTH, FULL window) ...", flush=True)
m = find_master("NQ", "5m", "rth")
arr = load_master_arrays(m, date_from=FULL[0], date_to=FULL[1])
r = run_backtest("ORB_3_0_BE.py", arrays=arr, params=CFG, cost_pts=FEE, return_trades=True)
net = r["total_pnl"] * MULT
dd = abs(r["max_drawdown"]) * MULT
ntr = int(r["num_trades"])
ok = (abs(net - ANCHOR["net"]) <= ANCHOR["tol"] and abs(dd - ANCHOR["dd"]) <= ANCHOR["tol"]
      and ntr == ANCHOR["n"])
print(f"  ANCHOR: net ${net:,.0f} (expect ${ANCHOR['net']:,.0f})  DD ${dd:,.0f} "
      f"(expect ${ANCHOR['dd']:,.0f})  trades {ntr} (expect {ANCHOR['n']})  -> "
      f"{'PASS' if ok else 'FAIL'}")
if not ok:
    print("ANCHOR FAILED — data path is wrong, aborting before any overlay work.")
    sys.exit(1)

trades = r["trades"]
ep = epoch_s(arr["index"])
bar_et = pd.to_datetime(pd.Series(ep), unit="s", utc=True).dt.tz_convert("US/Eastern")
bar_date = bar_et.dt.date.values
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
vol = np.nan_to_num(np.asarray(arr["volume"], dtype=np.float64), nan=0.0)

# ── 2. per-session volume profile -> POC / VAH / VAL (vectorized binning) ─────
starts = np.flatnonzero(np.r_[True, bar_date[1:] != bar_date[:-1]])
bounds = np.r_[starts, len(bar_date)]
n_sess = len(starts)
sess_of_date = {bar_date[starts[k]]: k for k in range(n_sess)}

def session_profile(a, b):
    """1.0-pt volume profile of bars [a:b) -> (base_bin, prof) or None."""
    hh, ll, vv = h[a:b], l[a:b], vol[a:b]
    good = np.isfinite(hh) & np.isfinite(ll) & (hh >= ll) & (vv > 0)
    if not good.any():
        return None
    hh, ll, vv = hh[good], ll[good], vv[good]
    lo = np.floor(ll).astype(np.int64)
    hi = np.floor(hh).astype(np.int64)
    nb = hi - lo + 1                       # bins each bar spans
    w = np.repeat(vv / nb, nb)             # uniform split of the bar's volume
    tot = int(nb.sum())
    bins = np.repeat(lo, nb) + (np.arange(tot) - np.repeat(np.cumsum(nb) - nb, nb))
    base = int(lo.min())
    prof = np.zeros(int(hi.max()) - base + 1)
    np.add.at(prof, bins - base, w)
    return base, prof

def value_area(base, prof):
    """Expand from POC to the higher-volume adjacent bin until >= 70% covered."""
    tot = prof.sum()
    if tot <= 0:
        return None
    poc = int(np.argmax(prof))
    i = j = poc
    cov = prof[poc]
    target = VA_COVER * tot
    while cov < target and (i > 0 or j < len(prof) - 1):
        vd = prof[i - 1] if i > 0 else -1.0
        vu = prof[j + 1] if j < len(prof) - 1 else -1.0
        if vu >= vd:                       # tie -> expand up
            j += 1; cov += vu
        else:
            i -= 1; cov += vd
    return float(base + i), float(base + j + 1), float(base + poc + 0.5)  # VAL, VAH, POC

print("building prior-session value areas (1.0-pt bins, 70% cover) ...", flush=True)
VAL_s = np.full(n_sess, np.nan)   # per-session PRIOR-day VAL/VAH/POC
VAH_s = np.full(n_sess, np.nan)
POC_s = np.full(n_sess, np.nan)
for k in range(1, n_sess):        # session k uses session k-1's profile — causal
    sp = session_profile(bounds[k - 1], bounds[k])
    if sp is None:
        continue
    va = value_area(*sp)
    if va is None:
        continue
    VAL_s[k], VAH_s[k], POC_s[k] = va
n_valid = int(np.isfinite(VAL_s).sum())
width = VAH_s[np.isfinite(VAH_s)] - VAL_s[np.isfinite(VAL_s)]
print(f"  sessions: {n_sess:,}  with a prior-day VA: {n_valid:,}  "
      f"(median VA width {np.median(width):,.0f} pts)")

# ── 3. per-trade context ──────────────────────────────────────────────────────
entry_bar = np.array([t[0] for t in trades], dtype=np.int64)
T = pd.DataFrame({
    "date": [bar_date[i] for i in entry_bar],
    "side": [int(t[3]) for t in trades],
    "entry": [float(t[4]) for t in trades],
    "pnl": [t[2] * MULT for t in trades],       # ALREADY net of fees
})
T["sess"] = [sess_of_date[d] for d in T["date"]]
sk = T["sess"].values
T["val"], T["vah"] = VAL_s[sk], VAH_s[sk]
T["open0"] = o[starts[sk]]                       # today's RTH open (first bar's open)
has_va = np.isfinite(T["val"].values) & np.isfinite(T["vah"].values)

# A) today's open vs prior VA
op, va_lo, va_hi = T["open0"].values, T["val"].values, T["vah"].values
open_loc = np.where(~has_va, "no-data",
           np.where(op > va_hi, "above VAH", np.where(op < va_lo, "below VAL", "inside")))
T["open_loc"] = open_loc

# B) entry price vs prior VA edges (in the trade's direction)
ent, sd = T["entry"].values, T["side"].values
beyond = np.where(sd > 0, ent > va_hi, ent < va_lo)       # broke out of value, with-trade
counter = np.where(sd > 0, ent < va_lo, ent > va_hi)      # entered from the far side
T["b_loc"] = np.where(~has_va, "no-data",
             np.where(beyond, "out of value", np.where(counter, "counter-side", "inside VA")))

# C) 80%-rule context: opened outside prior VA, then a bar CLOSE back inside VA
#    strictly BEFORE the entry bar (OR bar included — it completes pre-entry)
s0 = starts[sk]
reent = np.zeros(len(T), dtype=bool)
opened_out = has_va & (open_loc != "inside") & (open_loc != "no-data")
for t_i in np.flatnonzero(opened_out):
    cs = c[s0[t_i]:entry_bar[t_i]]
    reent[t_i] = bool(np.any((cs >= va_lo[t_i]) & (cs <= va_hi[t_i])))
T["c_loc"] = np.where(~has_va, "no-data",
             np.where(opened_out & reent, "80R: opened-out + re-entered",
             np.where(opened_out, "opened-out, no re-entry", "opened inside")))

# ── 4. DIAGNOSTIC tables (FULL window) ────────────────────────────────────────
def bucket_table(title, labels_rows):
    print(f"\n=== {title} ===")
    print(f"{'bucket':>32} | {'n':>5} | {'net$':>10} | {'avg$':>6} | {'WR%':>4} | {'PF':>5}")
    for lab, mask in labels_rows:
        p = T.loc[mask, "pnl"].values
        if len(p) == 0:
            print(f"{lab:>32} | {0:>5} | {'—':>10} | {'—':>6} | {'—':>4} | {'—':>5}")
            continue
        gw = p[p > 0].sum(); gl = -p[p < 0].sum()
        pf = gw / gl if gl > 0 else 99.0
        print(f"{lab:>32} | {len(p):>5} | {p.sum():>10,.0f} | {p.mean():>6,.0f} | "
              f"{100 * (p > 0).mean():>3.0f}% | {pf:>5.2f}")

rows_a = []
for loc in ("above VAH", "inside", "below VAL", "no-data"):
    rows_a.append((loc + " (all)", T["open_loc"].values == loc))
    if loc != "no-data":
        rows_a.append((loc + " · longs", (T["open_loc"].values == loc) & (sd > 0)))
        rows_a.append((loc + " · shorts", (T["open_loc"].values == loc) & (sd < 0)))
bucket_table("A — today's RTH OPEN vs prior value area, x side (FULL)", rows_a)

rows_b = [(loc, T["b_loc"].values == loc)
          for loc in ("out of value", "inside VA", "counter-side", "no-data")]
bucket_table("B — ENTRY price vs prior VA edges (with-trade breakout) (FULL)", rows_b)

rows_c = [(loc, T["c_loc"].values == loc)
          for loc in ("80R: opened-out + re-entered", "opened-out, no re-entry",
                      "opened inside", "no-data")]
bucket_table("C — 80%-rule context (DIAGNOSTIC ONLY — no new strategy)", rows_c)

# ── 5. PRE-REGISTERED TILT: "out of value" x1.25, neighbors x1.1 / x1.5 ───────
pnl = T["pnl"].values
is_lb = np.array([d >= LB_FROM for d in T["date"]])
masks = {"FULL": np.ones(len(T), bool), "OPT": ~is_lb, "LB": is_lb}

def wstats(w, mask):
    s = (pnl * w)[mask]
    if len(s) == 0:
        return 0.0, 0.0, 0.0
    cum = np.cumsum(s)
    ddv = abs(float((cum - np.maximum.accumulate(cum)).min()))
    netv = float(s.sum())
    return netv, ddv, (netv / ddv if ddv else 0.0)

def tilt_line(tag, w):
    parts = [f"{tag:>26} |"]
    out = {}
    for win in ("FULL", "OPT", "LB"):
        n_, d_, m_ = wstats(w, masks[win])
        out[win] = (n_, d_, m_)
        parts.append(f" {win} ${n_:>9,.0f} DD ${d_:>7,.0f} MAR {m_:>5.1f} |")
    print("".join(parts))
    return out

print("\n=== TILT tests (weight w on 'out of value' trades, 1.0 otherwise) ===")
base = tilt_line("baseline (1.0x)", np.ones(len(T)))
oov = T["b_loc"].values == "out of value"
n_oov = int(oov.sum())
results = {}
for f in (1.1, 1.25, 1.5):
    results[f] = tilt_line(f"out-of-value x{f} ({n_oov} tr)", np.where(oov, f, 1.0))

print("\n=== JUDGE (graduates only if MAR >= baseline in BOTH OPT and LB, ON A PLATEAU) ===")
passes = {}
for f in (1.1, 1.25, 1.5):
    s = results[f]
    go = s["OPT"][2] >= base["OPT"][2]
    gl = s["LB"][2] >= base["LB"][2]
    near = (s["OPT"][2] >= 0.98 * base["OPT"][2]) and (s["LB"][2] >= 0.98 * base["LB"][2])
    passes[f] = (go and gl, near)
    print(f"  JUDGE out-of-value x{f}: {'PASS' if (go and gl) else 'fail'}  "
          f"(OPT MAR {s['OPT'][2]:.2f} vs {base['OPT'][2]:.2f} {'PASS' if go else 'fail'}; "
          f"LB MAR {s['LB'][2]:.2f} vs {base['LB'][2]:.2f} {'PASS' if gl else 'fail'})")
p11, p25, p50 = passes[1.1], passes[1.25], passes[1.5]
plateau = p25[0] and (p11[0] or p11[1]) and (p50[0] or p50[1])
if p25[0] and plateau:
    verdict = "GRADUATES (x1.25 passes and its neighbors pass or nearly pass)"
elif p25[0]:
    verdict = "does NOT graduate — knife-edge (x1.25 passes but a neighbor is well off)"
else:
    verdict = "does NOT graduate — the pre-registered x1.25 fails the MAR rule"
print(f"\n  VERDICT — pre-registered 'out of value' x1.25: {verdict}")
print("  (plateau read: neighbors x1.1 / x1.5 must pass, or come within 2% of baseline")
print("   MAR in both windows; C is diagnostic-only this round — no 80%-rule tilt is run.)")
