"""ORB round-3 wave-2 — TIME-SCALE tilts X13 + X14 (session-clock exit/stop shaping).

Two intraday-time variants of the champion book, swept OPT (in-sample) vs LB (lockbox):
    X13 lunch-hour trail tightening (ORB_3_0_ENSL.py): the 2-lot ensemble's lot-B trail
        lookback drops from trail_bars=5 to lunch_trail bars for bars stamped 12:00-13:59
        ET, reverting after — does giving back less over the lunch chop improve the book?
        Baseline = ORB_3_0_ENS at target_R 4.5 / trail_bars 5 (== ENSL lunch_trail=0).
    X14 session-age-scaled stop (ORB_3_0_LATE.py): entries at session-bar index >= late_bar
        switch to late_stop_frac (target/BE rescale off that trade's own risk) — P2 found
        late breaks = 63% of trades at PF 1.30, so maybe the 1.75x stop is mis-sized late.
        Baseline = the ORB_3_0_BE deploy champion (== LATE late_bar=0).

JUDGE: a cell graduates ONLY if MAR >= baseline in BOTH windows AND its neighboring
magnitudes also pass or nearly pass (plateau) — a single knife-edge pass does NOT graduate.

Anchors (must reproduce within $5, else the data path is wrong — STOP):
    ENSL lunch_trail=0 (tR 4.5 / trail 5) full -> $465,109 / DD $17,439 / 3951 trades
    LATE late_bar=0                       full -> $574,177 / DD $26,763 / 3951 trades

Usage:  python tools/orb_round3_wave2_timescale.py
"""
import os, sys
try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception: pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.engine import run_backtest, find_master, load_master_arrays, load_strategy

INST, TF, SESS, MULT, FEE = "NQ", "5m", "rth", 20.0, 0.533
FULL = ("2010-06-07", "2026-06-30")
OPT  = ("2010-06-07", "2025-06-29")
LB   = ("2025-06-30", "2026-06-30")
BASE = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
            atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)
ENS_P  = dict(BASE, trail_bars=5)                 # ensemble family (X13)

ANCHOR_ENSL = dict(net=465109.0, dd=17439.0, n=3951)
ANCHOR_LATE = dict(net=574177.0, dd=26763.0, n=3951)
TOL = 5.0
NEAR = 0.95      # "nearly passes" = MAR >= 95% of baseline in both windows

print("loading master + windows ...", flush=True)
MASTER = find_master(INST, TF, SESS)
if MASTER is None:
    print("no NQ 5m rth master found"); sys.exit(1)
ENSL = load_strategy("ORB_3_0_ENSL.py")
LATE = load_strategy("ORB_3_0_LATE.py")
ARR = {w: load_master_arrays(MASTER, date_from=d0, date_to=d1) for w, (d0, d1) in
       (("full", FULL), ("opt", OPT), ("lb", LB))}


def kpi(mod, window, **params):
    r = run_backtest(mod, arrays=ARR[window], params=params,
                     cost_pts=FEE, return_trades=False)
    if not r:
        return dict(net=0.0, dd=0.0, pf=0.0, mar=0.0, n=0)
    net = r["total_pnl"] * MULT
    dd  = abs(r.get("max_drawdown", 0) or 0) * MULT
    return dict(net=net, dd=dd, pf=(r.get("profit_factor", 0) or 0),
                mar=(net / dd if dd else 0.0), n=int(r.get("num_trades", 0) or 0))


def line(tag, o, l, flag=""):
    print(f"  {tag:>22} | OPT ${o['net']:>10,.0f} DD ${o['dd']:>8,.0f} MAR {o['mar']:>5.1f} PF {o['pf']:.2f} "
          f"| LB ${l['net']:>8,.0f} DD ${l['dd']:>7,.0f} MAR {l['mar']:>5.1f} PF {l['pf']:.2f} n{l['n']:>4}"
          f"{('  ' + flag) if flag else ''}", flush=True)


def check_anchor(name, got, want):
    ok = (abs(got["net"] - want["net"]) <= TOL and abs(got["dd"] - want["dd"]) <= TOL
          and got["n"] == want["n"])
    print(f"  {name:<28} net ${got['net']:>10,.2f}  DD ${got['dd']:>9,.2f}  n {got['n']}   "
          f"[expect ${want['net']:,.0f} / ${want['dd']:,.0f} / {want['n']}]  -> {'OK' if ok else 'FAIL'}",
          flush=True)
    return ok


def status(row, bo, bl):
    """PASS / near / FAIL vs the family baseline MARs (both windows)."""
    if row["o"]["mar"] >= bo["mar"] - 1e-9 and row["l"]["mar"] >= bl["mar"] - 1e-9:
        return "PASS"
    if row["o"]["mar"] >= NEAR * bo["mar"] and row["l"]["mar"] >= NEAR * bl["mar"]:
        return "near"
    return "FAIL"


# ── Anchors (data-path sanity — STOP on failure) ──────────────────────────────
print("\n=== ANCHORS ===")
a1 = kpi(ENSL, "full", **ENS_P, lunch_trail=0)
a2 = kpi(LATE, "full", **BASE, late_bar=0)
ok1 = check_anchor("ENSL lt=0 (== ENS 4.5/5)", a1, ANCHOR_ENSL)
ok2 = check_anchor("LATE lb=0 (== deploy)", a2, ANCHOR_LATE)
if not (ok1 and ok2):
    print("\nANCHOR FAILURE — stopping (engine variant does not reproduce its parent)."); sys.exit(1)

# ── X13: lunch-hour trail tightening ──────────────────────────────────────────
print("\n=== X13 lunch_trail sweep (ENSL; trail_bars=5, target_R=4.5, be 1.0) ===")
x13_bo = kpi(ENSL, "opt", **ENS_P, lunch_trail=0)
x13_bl = kpi(ENSL, "lb",  **ENS_P, lunch_trail=0)
line("BASE ENS 4.5/5 (lt=0)", x13_bo, x13_bl)
X13_VALS = [2, 3, 4]
x13 = {}
for lt in X13_VALS:
    row = {"o": kpi(ENSL, "opt", **ENS_P, lunch_trail=lt),
           "l": kpi(ENSL, "lb",  **ENS_P, lunch_trail=lt)}
    x13[lt] = row
    line(f"lunch_trail={lt}", row["o"], row["l"], status(row, x13_bo, x13_bl))

print("\n--- JUDGE X13 (graduate = MAR >= baseline BOTH windows + plateau) ---")
x13_grads = []
for lt in X13_VALS:
    st = status(x13[lt], x13_bo, x13_bl)
    nbrs = [v for v in X13_VALS if abs(v - lt) == 1]
    nst  = [status(x13[v], x13_bo, x13_bl) for v in nbrs]
    plateau = all(s in ("PASS", "near") for s in nst) if nbrs else False
    grad = (st == "PASS") and plateau
    if grad: x13_grads.append(lt)
    print(f"  lunch_trail={lt}: {st}"
          f" | neighbors {dict(zip(nbrs, nst))} | plateau={'yes' if plateau else 'NO'}"
          f" -> {'GRADUATES' if grad else 'does not graduate'}", flush=True)
print(f"  X13 verdict: {('GRADUATES at ' + str(x13_grads)) if x13_grads else 'no cell graduates'}",
      flush=True)

# ── X14: session-age-scaled stop ──────────────────────────────────────────────
print("\n=== X14 late_bar x late_stop_frac sweep (LATE; deploy base) ===")
x14_bo = kpi(LATE, "opt", **BASE, late_bar=0)
x14_bl = kpi(LATE, "lb",  **BASE, late_bar=0)
line("BASE deploy (lb=0)", x14_bo, x14_bl)
X14_BARS, X14_FRACS = [16, 24], [1.0, 1.25, 1.5]
x14 = {}
for b in X14_BARS:
    for f in X14_FRACS:
        row = {"o": kpi(LATE, "opt", **BASE, late_bar=b, late_stop_frac=f),
               "l": kpi(LATE, "lb",  **BASE, late_bar=b, late_stop_frac=f)}
        x14[(b, f)] = row
        line(f"late_bar={b} lsf={f}", row["o"], row["l"], status(row, x14_bo, x14_bl))

print("\n--- JUDGE X14 (graduate = MAR >= baseline BOTH windows + plateau) ---")
x14_grads = []
for b in X14_BARS:
    for f in X14_FRACS:
        st = status(x14[(b, f)], x14_bo, x14_bl)
        fi = X14_FRACS.index(f)
        nbr_keys = [(b, X14_FRACS[fi + d]) for d in (-1, 1) if 0 <= fi + d < len(X14_FRACS)]
        nbr_keys += [(b2, f) for b2 in X14_BARS if b2 != b]
        nst = {k: status(x14[k], x14_bo, x14_bl) for k in nbr_keys}
        plateau = all(s in ("PASS", "near") for s in nst.values())
        grad = (st == "PASS") and plateau
        if grad: x14_grads.append((b, f))
        print(f"  late_bar={b} lsf={f}: {st}"
              f" | neighbors { {f'{k[0]}/{k[1]}': v for k, v in nst.items()} } | plateau={'yes' if plateau else 'NO'}"
              f" -> {'GRADUATES' if grad else 'does not graduate'}", flush=True)
print(f"  X14 verdict: {('GRADUATES at ' + str(x14_grads)) if x14_grads else 'no cell graduates'}",
      flush=True)

print("\ndone.", flush=True)
