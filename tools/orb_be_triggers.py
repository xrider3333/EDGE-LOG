"""ORB item K — breakeven-TRIGGER bake-off (ORB.md §6).

Item H found the R-multiple breakeven (arm at 1.0 x risk) cuts DD ~33% and holds in the
lockbox. K asks: does a DIFFERENT arming signal beat it? Each trigger family is swept in
ISOLATION on run #137's frozen base (only the breakeven trigger moves), on an in-sample
window AND a held-out lockbox, ranked by MAR / drawdown (NOT PnL — a BE lever is flat on
PnL, which is what fooled run #153).

Strategy: augur_strategies/ORB_3_0_BET.py (be_mode selector). Windows == the item-H study.
Anchors (must reproduce, else the data path is wrong):
    be_mode=off            -> plain #137            (~$567,297 full)
    be_mode=R, be_after_R=1 -> ORB_3_0_BE champion  (~$574,177 full, DD ~-$26,763)

Usage:  python tools/orb_be_triggers.py
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.engine import run_backtest, find_master, load_master_arrays, load_strategy

INST, TF, SESS, MULT, FEE = "NQ", "5m", "rth", 20.0, 0.533
FULL = ("2010-06-07", "2026-06-30")
OPT  = ("2010-06-07", "2025-06-29")
LB   = ("2025-06-30", "2026-06-30")
BASE = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
            atr_filter=0.1, breakout_buf=0.0, target_R=4.5)

# threshold sweeps per trigger family (index 0 == the "off" anchor where applicable)
SWEEPS = {
    "R":    ("be_after_R",    [0.0, 0.5, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0, 2.5]),
    "bars": ("be_after_bars", [2, 3, 4, 5, 6, 8, 10, 12, 16, 20]),
    "atr":  ("be_after_atr",  [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.25, 1.5]),
    "orw":  ("be_after_orw",  [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]),
}

print("loading master + windows ...", flush=True)
MASTER = find_master(INST, TF, SESS)
if MASTER is None:
    print("no NQ 5m rth master found"); sys.exit(1)
MOD = load_strategy("ORB_3_0_BET.py")
ARR = {w: load_master_arrays(MASTER, date_from=d0, date_to=d1) for w, (d0, d1) in
       (("full", FULL), ("opt", OPT), ("lb", LB))}


def kpi(window, **params):
    r = run_backtest(MOD, arrays=ARR[window], params=dict(BASE, **params),
                     cost_pts=FEE, return_trades=False)
    if not r:
        return dict(net=0.0, dd=0.0, pf=0.0, mar=0.0, n=0)
    net = r["total_pnl"] * MULT
    dd  = abs(r.get("max_drawdown", 0) or 0) * MULT
    return dict(net=net, dd=dd, pf=(r.get("profit_factor", 0) or 0),
                mar=(net / dd if dd else 0.0), n=int(r.get("num_trades", 0) or 0))


def line(tag, o, l):
    print(f"  {tag:>7} | IS ${o['net']:>10,.0f} DD ${o['dd']:>8,.0f} MAR {o['mar']:>5.1f} "
          f"| LB ${l['net']:>8,.0f} DD ${l['dd']:>7,.0f} MAR {l['mar']:>5.1f} PF {l['pf']:.2f} n{l['n']:>4}",
          flush=True)


# ── Anchors ───────────────────────────────────────────────────────────────────
print("\n=== ANCHORS (data-path sanity) ===")
a_off  = kpi("full", be_mode="off")
a_r1   = kpi("full", be_mode="R", be_after_R=1.0)
print(f"  #137 (be off)   full net ${a_off['net']:>10,.0f}  DD ${a_off['dd']:>8,.0f}  PF n/a   "
      f"[expect ~$567,297 / DD ~$40,233]")
print(f"  BE R=1.0        full net ${a_r1['net']:>10,.0f}  DD ${a_r1['dd']:>8,.0f}  "
      f"MAR {a_r1['mar']:.1f}  [expect ~$574,177 / DD ~$26,763]")

# ── The R control (in-sample + lockbox) every other trigger must beat ──────────
ctrl_o, ctrl_l = kpi("opt", be_mode="R", be_after_R=1.0), kpi("lb", be_mode="R", be_after_R=1.0)
print("\n=== CONTROL: be_mode=R be_after_R=1.0 (item-H champion) ===")
line("R=1.0", ctrl_o, ctrl_l)

# ── Sweep each trigger family in isolation ─────────────────────────────────────
best = {}   # mode -> (thresh, opt, lb)
for mode, (pname, vals) in SWEEPS.items():
    print(f"\n=== be_mode={mode}  (sweep {pname}) ===")
    rows = []
    for val in vals:
        o = kpi("opt", be_mode=mode, **{pname: val})
        l = kpi("lb",  be_mode=mode, **{pname: val})
        rows.append((val, o, l))
        line(f"{val}", o, l)
    # best LOCKBOX MAR among steps that actually arm (net>0), require a real trade set
    cand = [r for r in rows if r[2]["mar"] > 0 and r[2]["n"] > 0]
    bm = max(cand, key=lambda r: r[2]["mar"]) if cand else rows[0]
    best[mode] = (bm[0], bm[1], bm[2])
    print(f"  -> best LOCKBOX MAR at {pname}={bm[0]}: LB MAR {bm[2]['mar']:.1f} DD ${bm[2]['dd']:,.0f}")

# ── Structure trigger (single config, no threshold) ────────────────────────────
print("\n=== be_mode=struct  (first higher-low / lower-high; single config) ===")
s_o, s_l = kpi("opt", be_mode="struct"), kpi("lb", be_mode="struct")
line("struct", s_o, s_l)
best["struct"] = ("(structure)", s_o, s_l)

# ── SCORECARD: each family's lockbox champion vs the R=1.0 control ─────────────
print("\n" + "=" * 96)
print("SCORECARD — best-in-LOCKBOX per trigger vs the R=1.0 control  (NQ 5m rth · #137 base)")
print("=" * 96)
print(f"{'trigger':>9} | {'thresh':>10} | {'LB MAR':>6} {'LB DD$':>9} {'LB PF':>5} {'LB net$':>9} "
      f"| {'IS MAR':>6} {'IS DD$':>9} | beats R-control?")
print("-" * 96)
print(f"{'R (ctrl)':>9} | {'1.0':>10} | {ctrl_l['mar']:>6.1f} {ctrl_l['dd']:>9,.0f} {ctrl_l['pf']:>5.2f} "
      f"{ctrl_l['net']:>9,.0f} | {ctrl_o['mar']:>6.1f} {ctrl_o['dd']:>9,.0f} | —")
for mode in ("bars", "atr", "orw", "struct"):
    th, o, l = best[mode]
    win = "YES" if (l["mar"] > ctrl_l["mar"] and l["dd"] <= ctrl_l["dd"]) else \
          ("mar-only" if l["mar"] > ctrl_l["mar"] else ("dd-only" if l["dd"] < ctrl_l["dd"] else "no"))
    print(f"{mode:>9} | {str(th):>10} | {l['mar']:>6.1f} {l['dd']:>9,.0f} {l['pf']:>5.2f} "
          f"{l['net']:>9,.0f} | {o['mar']:>6.1f} {o['dd']:>9,.0f} | {win}")
print("-" * 96)
print("Read: a trigger 'wins' only if it beats the 1.0R control on BOTH lockbox MAR and lockbox DD.")
print("(In-sample MAR/DD shown too — a champion should look good in BOTH windows, not just the lockbox.)")
