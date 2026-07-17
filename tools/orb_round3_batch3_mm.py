"""ORB round-3 batch-3 — X4 measured-move targets (target_orw sweep).

X4 asks: does quoting the profit target in OPENING-RANGE WIDTHS (the classic chart-trader
"measured move" — project the range itself beyond the breakout) beat the deploy R-multiple
target? Strategy: augur_strategies/ORB_3_0_MM.py = ORB_3_0_BE.py with target_R swapped for
target_orw (tgt = entry +/- target_orw x OR width; 0 = ride to EOD). Because the deploy
risk is stop_frac x rng = 1.75 x rng, target_R 4.5 == 4.5 x 1.75 = 7.875 OR-widths — so
target_orw=7.875 is a geometry-identity anchor that must reproduce the BE deploy run
EXACTLY before the sweep means anything. Shorter measured-move targets should trade win
rate UP against per-trade expectancy; the judge is MAR in BOTH windows, not WR.

Anchors (must reproduce, else STOP — the data path or the port is wrong):
    ORB_3_0_BE  deploy (target_R=4.5)      FULL -> $574,177 / DD $26,763 / 3951 trades
    ORB_3_0_MM  target_orw=7.875           FULL -> same numbers (identical geometry)

Sweep: target_orw in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.875] on the OPT (in-sample)
and LB (lockbox) windows. JUDGE: a variant graduates only if MAR >= the 7.875 baseline
in BOTH windows.

Usage:  python tools/orb_round3_batch3_mm.py
"""
import os, sys
try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception: pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.engine import run_backtest, find_master, load_master_arrays

INST, TF, SESS, MULT, FEE = "NQ", "5m", "rth", 20.0, 0.533
FULL = ("2010-06-07", "2026-06-30")
OPT  = ("2010-06-07", "2025-06-29")
LB   = ("2025-06-30", "2026-06-30")

# Deploy baseline (BE strategy) and the same config expressed for the MM strategy.
BASE_BE = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
               atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)
BASE_MM = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
               atr_filter=0.1, breakout_buf=0.0, be_after_R=1.0)   # + target_orw per run

ANCHOR = dict(net=574_177.0, dd=26_763.0, n=3951, tol=5.0)
SWEEP  = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.875]

print("loading master + windows ...", flush=True)
MASTER = find_master(INST, TF, SESS)
if MASTER is None:
    print("no NQ 5m rth master found"); sys.exit(1)
ARR = {w: load_master_arrays(MASTER, date_from=d0, date_to=d1) for w, (d0, d1) in
       (("full", FULL), ("opt", OPT), ("lb", LB))}


def kpi(strategy, window, params):
    r = run_backtest(strategy, arrays=ARR[window], params=params,
                     cost_pts=FEE, return_trades=False)
    if not r:
        return dict(net=0.0, dd=0.0, pf=0.0, mar=0.0, wr=0.0, n=0)
    net = r["total_pnl"] * MULT
    dd  = abs(r.get("max_drawdown", 0) or 0) * MULT
    return dict(net=net, dd=dd, pf=(r.get("profit_factor", 0) or 0),
                mar=(net / dd if dd else 0.0), wr=float(r.get("win_rate", 0) or 0),
                n=int(r.get("num_trades", 0) or 0))


def check(tag, k):
    ok = (abs(k["net"] - ANCHOR["net"]) <= ANCHOR["tol"]
          and abs(k["dd"] - ANCHOR["dd"]) <= ANCHOR["tol"]
          and k["n"] == ANCHOR["n"])
    print(f"  {tag:<28} net ${k['net']:>10,.0f}  DD ${k['dd']:>8,.0f}  n {k['n']:>4}  "
          f"[expect ${ANCHOR['net']:,.0f} / ${ANCHOR['dd']:,.0f} / {ANCHOR['n']}]  "
          f"-> {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


# ── Anchors (deploy identity, then the MM 7.875 geometry-identity) ─────────────
print("\n=== ANCHORS (FULL window, deploy config) ===")
a_be = check("ORB_3_0_BE target_R=4.5",  kpi("ORB_3_0_BE.py", "full", BASE_BE))
a_mm = check("ORB_3_0_MM target_orw=7.875",
             kpi("ORB_3_0_MM.py", "full", dict(BASE_MM, target_orw=7.875)))
if not (a_be and a_mm):
    print("\nANCHOR FAILED — stopping. Do not trust anything below."); sys.exit(1)
print("  both anchors PASS — MM target geometry == deploy geometry. Proceeding.")

# ── Sweep target_orw on OPT + LB ───────────────────────────────────────────────
rows = []
for orw in SWEEP:
    p = dict(BASE_MM, target_orw=orw)
    rows.append((orw, kpi("ORB_3_0_MM.py", "opt", p), kpi("ORB_3_0_MM.py", "lb", p)))

base_o = next(o for orw, o, l in rows if orw == 7.875)
base_l = next(l for orw, o, l in rows if orw == 7.875)

W = 118
print("\n" + "=" * W)
print("MEASURED-MOVE TARGET SWEEP — target_orw x OR-width  (NQ 5m rth · 137+BE base · 7.875 == deploy 4.5R)")
print("=" * W)
print(f"{'orw':>6} | {'OPT net$':>10} {'OPT DD$':>8} {'OPT MAR':>7} {'OPT PF':>6} {'OPT WR%':>7} {'OPT n':>5} "
      f"| {'LB net$':>9} {'LB DD$':>8} {'LB MAR':>6} {'LB PF':>5} {'LB WR%':>6} {'LB n':>4} | note")
print("-" * W)
for orw, o, l in rows:
    grad = (o["mar"] >= base_o["mar"]) and (l["mar"] >= base_l["mar"])
    note = "<- deploy-equivalent baseline" if orw == 7.875 else \
           (f"GRADUATES (MAR>=base both)" if grad else
            f"WR {o['wr'] - base_o['wr']:+.1f}pp IS / {l['wr'] - base_l['wr']:+.1f}pp LB vs base")
    print(f"{orw:>6.3f} | {o['net']:>10,.0f} {o['dd']:>8,.0f} {o['mar']:>7.1f} {o['pf']:>6.2f} "
          f"{o['wr']:>7.1f} {o['n']:>5} | {l['net']:>9,.0f} {l['dd']:>8,.0f} {l['mar']:>6.1f} "
          f"{l['pf']:>5.2f} {l['wr']:>6.1f} {l['n']:>4} | {note}", flush=True)
print("-" * W)
print("WR SHIFT read: measured-move should trade WR UP as target_orw shrinks (more targets hit) "
      "against per-trade expectancy;")
print("the judge is MAR, not WR.")

# ── JUDGE ──────────────────────────────────────────────────────────────────────
winners = [(orw, o, l) for orw, o, l in rows
           if orw != 7.875 and o["mar"] >= base_o["mar"] and l["mar"] >= base_l["mar"]]
print(f"\nJUDGE — baseline target_orw=7.875 (deploy 4.5R): "
      f"OPT MAR {base_o['mar']:.1f} / LB MAR {base_l['mar']:.1f}")
if winners:
    for orw, o, l in winners:
        print(f"  GRADUATE: target_orw={orw} -> OPT MAR {o['mar']:.1f} (base {base_o['mar']:.1f}), "
              f"LB MAR {l['mar']:.1f} (base {base_l['mar']:.1f})")
else:
    print("  NO measured-move target beats the 7.875 deploy baseline on MAR in BOTH windows -> X4 FAILS.")
