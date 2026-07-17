"""ORB round-3 batch 4 — X7 ES<->NQ cross-market breadth overlay, on the deploy config.

Hypothesis: an NQ opening-range break that ES has ALREADY confirmed in the same direction
(ES broke its own opening range the same way, BEFORE the NQ entry moment) is a
broader-tape move and should be richer than one ES opposes or hasn't joined yet.

Method (quality rules from B/M/N/O):
  1. Run the deploy config ONCE on FULL with trades; HARD ANCHOR must reproduce
     ($574,177 net / $26,763 DD / 3951 trades) or the data path is wrong — abort.
  2. For each NQ trade, look at ES 5m RTH bars of the SAME ET session date with
     epoch <= the NQ entry epoch (strictly causal — only what ES had done by then).
     ES opening range = first ES bar of the session (or_bars=1 convention). First bar
     whose high >= OR-high is an up-break, low <= OR-low a down-break (OR bar itself
     skipped; a bar piercing both sides is resolved by where its CLOSE is, else AMBIG).
     Buckets: CONFIRMED (ES first-break == NQ side) / OPPOSED / NONE (no ES break yet)
     / AMBIG / no-data (session missing from the ES master).
  3. DIAGNOSTIC buckets first (n / net / avg / WR / PF), then TILT tests — size 1.25x
     and 1.5x on CONFIRMED, plus a 0.5x size-tilt on OPPOSED (a size cut, NOT a filter;
     no trades are deleted). Judged on MAR vs the 1.0x baseline in the OPT window AND
     the lockbox (trades sliced by ET entry date: < 2025-06-30 = OPT, >= = LB).

Usage: python tools/orb_round3_batch4_breadth.py
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


def epoch_s(ix):
    """arr['index'] as int64 epoch SECONDS — handles both raw epoch arrays and the
    tz-aware DatetimeIndex that load_master_arrays returns (asi8 is UTC ns)."""
    a = np.asarray(ix)
    if np.issubdtype(a.dtype, np.number):
        return a.astype(np.int64)
    return pd.DatetimeIndex(ix).asi8 // 1_000_000_000

# ── 1. NQ deploy run + HARD ANCHOR ────────────────────────────────────────────
print("running deploy config once (NQ 5m RTH, FULL window) ...", flush=True)
m_nq = find_master("NQ", "5m", "rth")
arr_nq = load_master_arrays(m_nq, date_from=FULL[0], date_to=FULL[1])
r = run_backtest("ORB_3_0_BE.py", arrays=arr_nq, params=CFG, cost_pts=FEE, return_trades=True)
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
ep_nq = epoch_s(arr_nq["index"])
entry_ep = np.array([ep_nq[t[0]] for t in trades], dtype=np.int64)
entry_et = pd.to_datetime(pd.Series(entry_ep), unit="s", utc=True).dt.tz_convert("US/Eastern")
T = pd.DataFrame({
    "date": entry_et.dt.date,
    "epoch": entry_ep,
    "side": [int(t[3]) for t in trades],
    "pnl": [t[2] * MULT for t in trades],      # ALREADY net of fees
})

# ── 2. ES side: per-session opening range + first range break ─────────────────
print("loading ES 5m RTH master (same FULL window) ...", flush=True)
m_es = find_master("ES", "5m", "rth")
if m_es is None:
    print("no ES 5m rth master found"); sys.exit(1)
arr_es = load_master_arrays(m_es, date_from=FULL[0], date_to=FULL[1])
es_ep = epoch_s(arr_es["index"])
es_et = pd.to_datetime(pd.Series(es_ep), unit="s", utc=True).dt.tz_convert("US/Eastern")
es_date = es_et.dt.date.values
es_h, es_l, es_c = arr_es["high"], arr_es["low"], arr_es["close"]

# first-break per ES session: date -> (break_epoch, dir) with dir +1 up / -1 down / 0 ambig,
# or (None, None) if the session never broke its OR. Sessions absent -> 'no-data'.
first_break = {}
starts = np.flatnonzero(np.r_[True, es_date[1:] != es_date[:-1]])
bounds = np.r_[starts, len(es_date)]
for k in range(len(starts)):
    a, b = bounds[k], bounds[k + 1]
    d = es_date[a]
    or_hi, or_lo = es_h[a], es_l[a]
    if b - a < 2:
        first_break[d] = (None, None)
        continue
    up = es_h[a + 1:b] >= or_hi
    dn = es_l[a + 1:b] <= or_lo
    brk = up | dn
    if not brk.any():
        first_break[d] = (None, None)
        continue
    j = int(np.argmax(brk))
    bi = a + 1 + j
    if up[j] and dn[j]:                      # one bar pierced both sides
        if es_c[bi] >= or_hi:   di = 1
        elif es_c[bi] <= or_lo: di = -1
        else:                   di = 0       # both/ambiguous
    else:
        di = 1 if up[j] else -1
    first_break[d] = (int(es_ep[bi]), di)
print(f"  ES sessions: {len(first_break):,}  (NQ sessions traded: {T['date'].nunique():,})")

def classify(row):
    fb = first_break.get(row["date"])
    if fb is None:
        return "no-data"
    b_ep, b_dir = fb
    if b_ep is None or b_ep > row["epoch"]:   # ES hadn't broken by the NQ entry moment
        return "NONE"
    if b_dir == 0:
        return "AMBIG"
    return "CONFIRMED" if b_dir == row["side"] else "OPPOSED"

T["bucket"] = T.apply(classify, axis=1)

# ── 3. DIAGNOSTIC buckets (FULL window) ────────────────────────────────────────
print("\n=== X7 — ES breadth state at NQ entry (FULL 2010-06-07 -> 2026-06-30) ===")
print(f"{'bucket':>12} | {'n':>5} | {'net$':>10} | {'avg$':>6} | {'WR%':>4} | {'PF':>5}")
for b in ("CONFIRMED", "OPPOSED", "NONE", "AMBIG", "no-data"):
    p = T.loc[T["bucket"] == b, "pnl"].values
    if len(p) == 0:
        print(f"{b:>12} | {0:>5} | {'—':>10} | {'—':>6} | {'—':>4} | {'—':>5}")
        continue
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    pf = gw / gl if gl > 0 else 99.0
    print(f"{b:>12} | {len(p):>5} | {p.sum():>10,.0f} | {p.mean():>6,.0f} | "
          f"{100 * (p > 0).mean():>3.0f}% | {pf:>5.2f}")

# ── 4. TILT tests (size on signal trades, 1.0 otherwise — never delete trades) ─
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

print("\n=== TILT tests (weight w on signal trades, 1.0 otherwise) ===")
base = tilt_line("baseline (1.0x)", np.ones(len(T)))
tilts = []
for f in (1.25, 1.5):
    w = np.where(T["bucket"].values == "CONFIRMED", f, 1.0)
    n_sig = int((T["bucket"] == "CONFIRMED").sum())
    tilts.append((f"CONFIRMED x{f} ({n_sig} tr)", tilt_line(f"CONFIRMED x{f} ({n_sig} tr)", w)))
w_half = np.where(T["bucket"].values == "OPPOSED", 0.5, 1.0)
n_opp = int((T["bucket"] == "OPPOSED").sum())
tilts.append((f"OPPOSED x0.5 ({n_opp} tr) [size-tilt, NOT a filter]",
              tilt_line(f"OPPOSED x0.5 ({n_opp} tr)", w_half)))

print("\n=== JUDGE (graduates only if MAR >= baseline in BOTH OPT and LB) ===")
for tag, s in tilts:
    go = s["OPT"][2] >= base["OPT"][2]
    gl = s["LB"][2] >= base["LB"][2]
    verdict = "GRADUATES" if (go and gl) else "FAILS"
    print(f"  JUDGE {tag}: {verdict}  "
          f"(OPT MAR {s['OPT'][2]:.2f} vs {base['OPT'][2]:.2f} {'PASS' if go else 'fail'}; "
          f"LB MAR {s['LB'][2]:.2f} vs {base['LB'][2]:.2f} {'PASS' if gl else 'fail'})")
print("\nNote: OPPOSED x0.5 is a half-SIZE tilt on ES-opposed trades, not a filter — every")
print("trade stays in the book; only its size changes. Judged on the same MAR rule.")
