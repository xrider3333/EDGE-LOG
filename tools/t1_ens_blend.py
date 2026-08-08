"""Re-test the "blend ORB-leg -> ENS" upgrade on the now-CERTIFIED legs (t1 driver, not committed).

Reuses tools/blend_recert.py's structure/conventions exactly: window PINNED
2010-06-07 -> 2026-06-30, both legs costed 0.533 pts RT x $20, exit-date daily PnL
(bucketed on trade[1] = exit bar index), union of dates 0-filled, ENGU-Q leg =
ENGUQ_1M_1_0.NQ_DEPLOY_PARAMS_149 on NQ 1m rth.

STEP 1 (parity gate): reruns the ORIGINAL 1:1 baseline (ORB_3_1.py #125 single-lot x
ENGU-Q) byte-for-byte as blend_recert.py does (no source pin on the 5m master --
whatever find_master('NQ','5m','rth') resolves to today) and checks it against the
recertified baseline (net $837,645 / maxDD -$60,098 / corr +0.069, +/-1%). ABORTS the
rest of the script if that gate fails.

STEP 2+ (the actual re-test): swaps the ORB leg for ORB_3_0_ENS.py (2-lot ride+trail
exit ensemble), run TWICE:
  Config A -- "gate-floor crown" (2026-08-05 transfer sweep): stop 1.75 / target_R 4.0 /
              trail_bars 12 / be_after_R 1.0.
  Config B -- the file's plain DEFAULT_PARAMS (S4 "2-lot exit ensemble" read): stop 1.75 /
              target_R 4.5 / trail_bars 5 / be_after_R 1.0.
Per the owner's IMPORTANT master pin note: find_master('NQ','5m','rth') is AMBIGUOUS
(db_noadj_rth vs tv tie) -- for the ORB/ENS leg specifically we pass source='tv'
explicitly (2026-07-24 note: alphabetical/default pick breaks #125 parity by 1 trade).
The ENGU-Q leg (1m) is left unpinned, exactly as blend_recert.py does it.

Usage: python tools/t1_ens_blend.py
"""
import sys, pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest, find_master, load_master_arrays
import importlib.util
_s = importlib.util.spec_from_file_location("enguq", REPO / "augur_strategies" / "ENGUQ_1M_1_0.py")
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
ENG_149 = _m.NQ_DEPLOY_PARAMS_149

WIN = ("2010-06-07", "2026-06-30")
LB_START = pd.Timestamp("2025-06-30").date()
COST = 0.533
MULT = 20.0

# ── leg params ──────────────────────────────────────────────────────────────
ORB_125 = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
               breakout_buf=0.0, target_R=0.0, partial_exit_R=0.0, trail_bars=5,
               flat_eod=True)

# Config A -- "gate-floor crown" (2026-08-05 transfer sweep). File-pinned knobs
# (or_bars/trade_mode/stop_frac/vol_filter/atr_filter/breakout_buf/be_after_R all have
# min==max==default in ORB_3_0_ENS.DEFAULT_PARAMS, i.e. NOT free -- only target_R and
# trail_bars are the "runner knobs" per the file's own docstring/PARAM_GRID_PRESETS).
ENS_A = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
             breakout_buf=0.0, be_after_R=1.0, target_R=4.0, trail_bars=12)

# Config B -- plain DEFAULT_PARAMS defaults (S4 "2-lot exit ensemble" read).
ENS_B = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
             breakout_buf=0.0, be_after_R=1.0, target_R=4.5, trail_bars=5)


def leg(strat, tf, params, source=None):
    """Exit-date daily PnL Series for one leg. source=None reproduces find_master's
    default resolution exactly (used for the STEP-1 parity gate); source='tv' pins
    the ORB/ENS 5m master per the owner's ambiguity note."""
    if source:
        master = find_master("NQ", tf, "rth", source=source)
    else:
        master = find_master("NQ", tf, "rth")
    arr = load_master_arrays(master, date_from=WIN[0], date_to=WIN[1])
    r = run_backtest(strat, arrays=arr, params=params, cost_pts=COST, return_trades=True)
    idx = arr["index"]
    d = {}
    for t in r["trades"]:
        day = pd.Timestamp(idx[int(t[1])]).date()
        d[day] = d.get(day, 0.0) + float(t[2]) * MULT
    return r, pd.Series(d).sort_index(), master.get("source")


def blend_stats(orb, eng, tag):
    df = pd.DataFrame({"orb": orb, "eng": eng}).fillna(0.0).sort_index()
    df["combo"] = df["orb"] + df["eng"]
    cum = df["combo"].cumsum()
    dd = float((cum - cum.cummax()).min())
    net = float(df["combo"].sum())
    corr = float(df["orb"].corr(df["eng"]))
    years = df.groupby(pd.DatetimeIndex(df.index).year)["combo"].sum()
    losing = years[years < 0]
    worst_day = float(df["combo"].min())

    lb = df[df.index >= LB_START]
    lb_cum = lb["combo"].cumsum()
    lb_net = float(lb["combo"].sum())
    lb_dd = float((lb_cum - lb_cum.cummax()).min()) if len(lb) else 0.0

    print(f"\nBLEND {tag}: net=${net:,.0f}  maxDD(daily cum)=${dd:,.0f}  "
          f"net/DD={net/abs(dd):.2f}  daily corr={corr:+.3f}  worst day=${worst_day:,.0f}")
    print(f"  years: {len(years)}  losing: {len(losing)} "
          f"{dict(losing.round(0)) if len(losing) else ''}")
    print(f"  by year: {{{', '.join(f'{int(y)}: {round(v):,}' for y, v in years.items())}}}")
    print(f"  last-12mo (from {LB_START} on): net=${lb_net:,.0f}  maxDD=${lb_dd:,.0f}  "
          f"n_days={len(lb)}")
    return dict(net=net, dd=dd, mar=net / abs(dd) if dd else 0.0, corr=corr,
                losing_years=len(losing), worst_day=worst_day, lb_net=lb_net, lb_dd=lb_dd)


def leg_report(name, r, series):
    n = r["num_trades"]
    net = float(series.sum())
    pf = r["profit_factor"]
    dd_trades = float(r["max_drawdown"]) * MULT  # trade-sequence DD (not daily-cum)
    print(f"  {name:26} n={n:5d}  net=${net:>12,.0f}  PF={pf:.3f}  "
          f"DD(trade-seq)=${dd_trades:>10,.0f}")
    return dict(n=n, net=net, pf=pf, dd=dd_trades)


# ── STEP 1: parity gate — reproduce blend_recert.py exactly (no source pin) ────
print("=" * 78)
print("STEP 1 — PARITY GATE: reproduce the 1:1 baseline exactly as blend_recert.py does")
print("=" * 78)
orb_base_r, orb_base, orb_base_src = leg("ORB_3_1.py", "5m", ORB_125, source=None)
eng_r, eng, eng_src = leg("ENGUQ_1M_1_0.py", "1m", ENG_149, source=None)
print(f"(masters resolved: ORB leg 5m source='{orb_base_src}', ENGU-Q leg 1m source='{eng_src}')")
leg_report("ORB #125 (baseline)", orb_base_r, orb_base)
leg_report("ENGU-Q #149", eng_r, eng)
base_stats = blend_stats(orb_base, eng, "BASELINE 1:1 (ORB_3_1 x ENGU-Q)")

TARGET_NET, TARGET_DD, TARGET_CORR = 837_645.0, -60_098.0, 0.069
ok_net = abs(base_stats["net"] - TARGET_NET) / abs(TARGET_NET) <= 0.01
ok_dd = abs(base_stats["dd"] - TARGET_DD) / abs(TARGET_DD) <= 0.01
ok_corr = abs(base_stats["corr"] - TARGET_CORR) <= 0.01
print(f"\nparity check vs target (net $837,645 / maxDD -$60,098 / corr +0.069, +/-1%):")
print(f"  net  : ${base_stats['net']:,.0f}  {'PASS' if ok_net else 'FAIL'}")
print(f"  maxDD: ${base_stats['dd']:,.0f}  {'PASS' if ok_dd else 'FAIL'}")
print(f"  corr : {base_stats['corr']:+.3f}  {'PASS' if ok_corr else 'FAIL'}")

if not (ok_net and ok_dd and ok_corr):
    print("\n*** PARITY GATE FAILED — ABORTING before running the ENS configs. ***")
    sys.exit(1)
print("\n*** PARITY GATE PASSED. Proceeding to ENS-leg configs. ***")

# ── STEP 2/3: ENS configs A and B, pinning source='tv' on the ORB/ENS 5m master ──
print("\n" + "=" * 78)
print("STEP 2 — ENS Config A: gate-floor crown (stop 1.75 / target_R 4.0 / trail_bars 12 / be 1.0)")
print("=" * 78)
print(f"  params run: {ENS_A}")
ensA_r, ensA, ensA_src = leg("ORB_3_0_ENS.py", "5m", ENS_A, source="tv")
print(f"  (ORB/ENS 5m master pinned source='{ensA_src}')")
leg_report("ORB_3_0_ENS (config A)", ensA_r, ensA)
leg_report("ENGU-Q #149", eng_r, eng)
blendA_stats = blend_stats(ensA, eng, "A (ENS gate-floor crown x ENGU-Q)")

print("\n" + "=" * 78)
print("STEP 3 — ENS Config B: file DEFAULT_PARAMS (stop 1.75 / target_R 4.5 / trail_bars 5 / be 1.0)")
print("=" * 78)
print(f"  params run: {ENS_B}")
ensB_r, ensB, ensB_src = leg("ORB_3_0_ENS.py", "5m", ENS_B, source="tv")
print(f"  (ORB/ENS 5m master pinned source='{ensB_src}')")
leg_report("ORB_3_0_ENS (config B)", ensB_r, ensB)
leg_report("ENGU-Q #149", eng_r, eng)
blendB_stats = blend_stats(ensB, eng, "B (ENS file-defaults x ENGU-Q)")
print(f"  (vs S4 2026-07-24 expectation ~$943k / -$58.5k)")

# ── STEP 4: final comparison table ──────────────────────────────────────────
print("\n" + "=" * 78)
print("FINAL COMPARISON — baseline vs blend-A vs blend-B")
print("=" * 78)
rows = [
    ("net", f"${base_stats['net']:,.0f}", f"${blendA_stats['net']:,.0f}", f"${blendB_stats['net']:,.0f}"),
    ("maxDD (daily cum)", f"${base_stats['dd']:,.0f}", f"${blendA_stats['dd']:,.0f}", f"${blendB_stats['dd']:,.0f}"),
    ("net/DD", f"{base_stats['mar']:.2f}", f"{blendA_stats['mar']:.2f}", f"{blendB_stats['mar']:.2f}"),
    ("daily corr", f"{base_stats['corr']:+.3f}", f"{blendA_stats['corr']:+.3f}", f"{blendB_stats['corr']:+.3f}"),
    ("losing years", str(base_stats['losing_years']), str(blendA_stats['losing_years']), str(blendB_stats['losing_years'])),
    ("worst day", f"${base_stats['worst_day']:,.0f}", f"${blendA_stats['worst_day']:,.0f}", f"${blendB_stats['worst_day']:,.0f}"),
    (f"last-12mo net (from {LB_START})", f"${base_stats['lb_net']:,.0f}", f"${blendA_stats['lb_net']:,.0f}", f"${blendB_stats['lb_net']:,.0f}"),
    ("last-12mo maxDD", f"${base_stats['lb_dd']:,.0f}", f"${blendA_stats['lb_dd']:,.0f}", f"${blendB_stats['lb_dd']:,.0f}"),
]
hdr = f"{'metric':28} {'baseline (1-lot)':>20} {'blend-A (crown)':>20} {'blend-B (defaults)':>20}"
print(hdr)
print("-" * len(hdr))
for name, b, a, c in rows:
    print(f"{name:28} {b:>20} {a:>20} {c:>20}")
