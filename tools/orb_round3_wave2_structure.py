"""ORB round-3 wave 2 — X8 (first-bar character) + X15-X19 (prior-day structure), deploy config.

Hypothesis family: the OR bar's own character (body, close direction, close location) and
the PRIOR day's structure (close location, gap-fill state, prior-extreme air, streak) are
all fully known at the entry touch, so any of them may legally tilt SIZE on the deploy book.

Method (quality rules from B/M/N/O and batches 1-4):
  1. Run the deploy config ONCE on FULL with trades; HARD ANCHOR must reproduce
     ($574,177 net / $26,763 DD / 3951 trades) or the data path is wrong — abort.
  2. Per-trade CAUSAL signals only: prior-day daily values (completed sessions), the OR
     bar itself (completes before any entry), bars strictly BEFORE the entry bar, and the
     entry touch price/side. The entry bar's own close/high/low/volume are never read.
  3. DIAGNOSTIC buckets first (n / net$ / avg$ / WR% / PF on FULL), then TILT tests ONLY
     on the two pre-registered signals (declared below BEFORE any diagnostic was viewed).
     Tilts multiply size on signal trades (1.0 otherwise) — never delete trades. Judged on
     MAR vs the 1.0x baseline in OPT (< 2025-06-30 ET entry date) AND LB (>=), sliced from
     the single FULL run (valid — strategy is EOD-flat), with a plateau read.

Usage: python tools/orb_round3_wave2_structure.py
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

# ── PRE-REGISTRATION (declared BEFORE any diagnostic bucket was computed or viewed) ──
# Exactly two tilts are MAR-judged this wave, chosen a-priori on economic sense:
#   T1  X8b with-OR-close: a break whose side agrees with the OR bar's close direction is
#       riding the day's initial impulse rather than fighting it -> size x1.25.
#   T2  X17 fresh-air: an entry already beyond the FULL prior-day extreme has no
#       overhead supply / support shelf left to chew through -> size x1.25.
# Each is run at x1.1 / x1.25 / x1.5 for the plateau read. Graduation rule: the x1.25
# center must have MAR >= baseline in BOTH OPT and LB, AND both neighbors (x1.1, x1.5)
# must pass or nearly pass (MAR >= 0.98x baseline in both windows). A single knife-edge
# pass does NOT graduate. All other buckets below are DIAGNOSTIC ONLY this wave.


def epoch_s(ix):
    """arr['index'] as int64 epoch SECONDS — handles both raw epoch arrays and the
    tz-aware DatetimeIndex that load_master_arrays returns (asi8 is UTC ns)."""
    a = np.asarray(ix)
    if np.issubdtype(a.dtype, np.number):
        return a.astype(np.int64)
    return pd.DatetimeIndex(ix).asi8 // 1_000_000_000


def sgn(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


# ── 1. Deploy run + HARD ANCHOR ───────────────────────────────────────────────
print("running deploy config once (NQ 5m RTH, FULL window) ...", flush=True)
m_nq = find_master("NQ", "5m", "rth")
arr = load_master_arrays(m_nq, date_from=FULL[0], date_to=FULL[1])
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

# ── 2. Session table (per ET date): OR bar + daily aggregates ─────────────────
O, H, L, C = arr["open"], arr["high"], arr["low"], arr["close"]
ep = epoch_s(arr["index"])
et = pd.to_datetime(pd.Series(ep), unit="s", utc=True).dt.tz_convert("US/Eastern")
bar_date = et.dt.date.values
starts = np.flatnonzero(np.r_[True, bar_date[1:] != bar_date[:-1]])
bounds = np.r_[starts, len(bar_date)]
sess_dates = bar_date[starts]
n_sess = len(starts)
d_open = O[starts]
d_close = C[bounds[1:] - 1]
d_high = np.array([H[a:b].max() for a, b in zip(bounds[:-1], bounds[1:])])
d_low = np.array([L[a:b].min() for a, b in zip(bounds[:-1], bounds[1:])])
or_o, or_h, or_l, or_c = O[starts], H[starts], L[starts], C[starts]
date2sess = {d: i for i, d in enumerate(sess_dates)}
print(f"  sessions: {n_sess:,}", flush=True)


def streak_before(si):
    """Signed consecutive prior-daily-close streak known at session si's open, cap +-4.
    Pair (si-1, si-2) sets the direction; equal closes anywhere break the run."""
    if si < 2:
        return None
    s, d0, j = 0, None, si - 1
    while j >= 1:
        d = sgn(d_close[j] - d_close[j - 1])
        if d == 0 or (d0 is not None and d != d0):
            break
        d0 = d
        s += d
        if abs(s) >= 4:
            break
        j -= 1
    return int(max(-4, min(4, s)))


# ── 3. Per-trade CAUSAL signals ───────────────────────────────────────────────
trades = r["trades"]
pnl = np.array([t[2] * MULT for t in trades])          # ALREADY net of fees
side = np.array([int(t[3]) for t in trades])
eprice = np.array([float(t[4]) for t in trades])
ebar = np.array([int(t[0]) for t in trades])
edate = np.array([bar_date[i] for i in ebar])
is_lb = np.array([d >= LB_FROM for d in edate])

x8a, x8b, x15, x16, x17, x18, x19 = [], [], [], [], [], [], []
w_orclose = np.zeros(len(trades), bool)                # T1 signal mask
w_freshair = np.zeros(len(trades), bool)               # T2 signal mask
sd_lab = np.where(side == 1, "L", "S")

for k, t in enumerate(trades):
    si = date2sess[edate[k]]
    a = starts[si]
    rng_or = or_h[si] - or_l[si]

    # X8a — OR-bar body% of range
    if rng_or <= 0:
        x8a.append("flat-OR")
    else:
        bp = abs(or_c[si] - or_o[si]) / rng_or
        x8a.append("body<0.3" if bp < 0.3 else ("body>0.7" if bp > 0.7 else "body 0.3-0.7"))

    # X8b — side vs OR-bar close direction
    dc = sgn(or_c[si] - or_o[si])
    if dc == 0:
        x8b.append("doji")
    elif dc == side[k]:
        x8b.append("WITH or-close")
        w_orclose[k] = True
    else:
        x8b.append("AGAINST or-close")

    # X19 — OR-bar CLV x side
    if rng_or <= 0:
        x19.append("flat-OR")
    else:
        clv = (or_c[si] - or_l[si]) / rng_or
        cb = "clv<0.3" if clv < 0.3 else ("clv>0.7" if clv > 0.7 else "clv 0.3-0.7")
        x19.append(f"{cb} {sd_lab[k]}")

    # prior-day block (X15-X18)
    if si < 1:
        x15.append("no-data"); x16.append("no-data"); x17.append("no-data"); x18.append("no-data")
        continue
    p_h, p_l, p_c = d_high[si - 1], d_low[si - 1], d_close[si - 1]
    p_rng = p_h - p_l

    # X15 — prior-day close location x side
    if p_rng <= 0:
        x15.append("no-data")
    else:
        loc = (p_c - p_l) / p_rng
        lb_ = "loc<0.25" if loc < 0.25 else ("loc>0.75" if loc > 0.75 else "loc 0.25-0.75")
        x15.append(f"{lb_} {sd_lab[k]}")

    # X16 — gap-fill state pre-entry x side-vs-gap
    if p_rng <= 0:
        x16.append("no-data")
    else:
        gap = d_open[si] - p_c
        if abs(gap) < 0.1 * p_rng:
            x16.append("no-gap")
        else:
            j0, j1 = a, ebar[k]                       # bars strictly BEFORE the entry bar
            filled = bool(np.any((L[j0:j1] <= p_c) & (H[j0:j1] >= p_c))) if j1 > j0 else False
            gtag = "with-gap" if side[k] == sgn(gap) else "against-gap"
            x16.append(f"{'filled' if filled else 'unfilled'}/{gtag}")

    # X17 — fresh air vs into-yesterday (entry touch price vs prior-day extreme)
    fresh = (eprice[k] >= p_h) if side[k] == 1 else (eprice[k] <= p_l)
    x17.append(f"{'fresh-air' if fresh else 'into-range'} {sd_lab[k]}")
    if fresh:
        w_freshair[k] = True

    # X18 — prior-close streak x side
    s = streak_before(si)
    x18.append("no-data" if s is None else f"streak{s:+d} {sd_lab[k]}")

for name, lab in (("x8a", x8a), ("x8b", x8b), ("x15", x15), ("x16", x16),
                  ("x17", x17), ("x18", x18), ("x19", x19)):
    assert len(lab) == len(trades), name


# ── 4. DIAGNOSTIC bucket tables (FULL window) ─────────────────────────────────
def table(title, labels, order):
    print(f"\n=== {title}  (FULL) ===")
    print(f"{'bucket':>24} | {'n':>5} | {'net$':>10} | {'avg$':>6} | {'WR%':>4} | {'PF':>5}")
    labels = np.array(labels)
    for b in order:
        p = pnl[labels == b]
        if len(p) == 0:
            print(f"{b:>24} | {0:>5} | {'-':>10} | {'-':>6} | {'-':>4} | {'-':>5}")
            continue
        gw, gl = p[p > 0].sum(), -p[p < 0].sum()
        pf = gw / gl if gl > 0 else 99.0
        print(f"{b:>24} | {len(p):>5} | {p.sum():>10,.0f} | {p.mean():>6,.0f} | "
              f"{100 * (p > 0).mean():>3.0f}% | {pf:>5.2f}")


table("X8a — OR-bar body% of its range", x8a,
      ["body<0.3", "body 0.3-0.7", "body>0.7", "flat-OR"])
table("X8b — trade side vs OR-bar close direction", x8b,
      ["WITH or-close", "AGAINST or-close", "doji"])
table("X15 — prior-day close location x side", x15,
      [f"{b} {s}" for b in ("loc<0.25", "loc 0.25-0.75", "loc>0.75") for s in ("L", "S")]
      + ["no-data"])
table("X16 — gap state pre-entry x side-vs-gap", x16,
      ["no-gap", "filled/with-gap", "filled/against-gap",
       "unfilled/with-gap", "unfilled/against-gap", "no-data"])
table("X17 — fresh air vs into-yesterday", x17,
      ["fresh-air L", "fresh-air S", "into-range L", "into-range S", "no-data"])
table("X18 — prior-close streak x side (cap +-4)", x18,
      [f"streak{s:+d} {sd}" for s in range(-4, 5) for sd in ("L", "S")] + ["no-data"])
table("X19 — OR-bar CLV x side", x19,
      [f"{b} {s}" for b in ("clv<0.3", "clv 0.3-0.7", "clv>0.7") for s in ("L", "S")]
      + ["flat-OR"])

# ── 5. TILT tests (pre-registered only; weight w on signal trades, 1.0 otherwise) ──
masks = {"FULL": np.ones(len(trades), bool), "OPT": ~is_lb, "LB": is_lb}


def wstats(w, mask):
    s = (pnl * w)[mask]
    if len(s) == 0:
        return 0.0, 0.0, 0.0
    cum = np.cumsum(s)
    ddv = abs(float((cum - np.maximum.accumulate(cum)).min()))
    netv = float(s.sum())
    return netv, ddv, (netv / ddv if ddv else 0.0)


def tilt_line(tag, w):
    parts = [f"{tag:>30} |"]
    out = {}
    for win in ("FULL", "OPT", "LB"):
        n_, d_, m_ = wstats(w, masks[win])
        out[win] = (n_, d_, m_)
        parts.append(f" {win} ${n_:>9,.0f} DD ${d_:>7,.0f} MAR {m_:>5.1f} |")
    print("".join(parts))
    return out


print("\n=== TILT tests (pre-registered T1/T2 only; size w on signal trades, 1.0 otherwise) ===")
base = tilt_line("baseline (1.0x)", np.ones(len(trades)))
FACT = (1.1, 1.25, 1.5)
fam = {}
for tag, msk in (("T1 X8b with-OR-close", w_orclose), ("T2 X17 fresh-air", w_freshair)):
    print(f"  -- {tag}: {int(msk.sum())} signal trades "
          f"({100 * msk.mean():.0f}% of book) --")
    fam[tag] = {f: tilt_line(f"{tag} x{f}", np.where(msk, f, 1.0)) for f in FACT}

# ── 6. JUDGE + plateau read ───────────────────────────────────────────────────
print("\n=== JUDGE (MAR >= baseline in BOTH OPT and LB; plateau = x1.1 and x1.5 also")
print("    pass or nearly pass [>= 0.98x baseline MAR]; knife-edge pass does NOT graduate) ===")


def ok_win(s, win, frac=1.0):
    return s[win][2] >= frac * base[win][2]


for tag, rows in fam.items():
    for f in FACT:
        s = rows[f]
        go, gl = ok_win(s, "OPT"), ok_win(s, "LB")
        print(f"  JUDGE {tag} x{f}: {'PASS' if (go and gl) else 'FAIL'}  "
              f"(OPT MAR {s['OPT'][2]:.2f} vs {base['OPT'][2]:.2f} {'PASS' if go else 'fail'}; "
              f"LB MAR {s['LB'][2]:.2f} vs {base['LB'][2]:.2f} {'PASS' if gl else 'fail'})")
    c = rows[1.25]
    center = ok_win(c, "OPT") and ok_win(c, "LB")
    nbrs = all(ok_win(rows[f], w, 0.98) for f in (1.1, 1.5) for w in ("OPT", "LB"))
    verdict = "GRADUATES" if (center and nbrs) else \
        ("FAILS (no plateau — knife-edge)" if center else "FAILS")
    print(f"  >> {tag} x1.25 (pre-registered): {verdict}")

print("\nNote: tilts are SIZE multipliers on signal trades — every trade stays in the book.")
print("All X-buckets other than T1/T2 are diagnostic-only this wave (no post-hoc tilting).")
