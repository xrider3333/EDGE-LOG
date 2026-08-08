"""T3 gate: FROZEN-CONFIG walk-forward for the ENGU-Q ETH clock-scaled candidate.

Pre-registered next gate (per BACKTESTING_STACK.md 2026-08-05 round-6 entry / owner
instruction 2026-08-08): the deployable ETH candidate is the FROZEN clock-scaled #149
config (time-lookbacks x3.54: ema_len=1380, tl_len=170, atr_len=106) shipped as the
DEFAULT_PARAMS of augur_strategies/ENGUQ_1M_ETH_1_0.py. This driver runs that frozen
config AS-IS (zero tuning, no grid/discovery) through two checks:

  1. PARITY — reproduce the documented continuous full-window run (NQ 1m ETH,
     2010-06-07 -> 2026-06-30, db_noadj_eth master, 0.533 pts RT cost, x$20/pt):
     net $434,721.12 / PF 1.33 / maxDD -$50,420 (+/- 2%). Abort before the WF step
     if parity fails (would mean this driver isn't reproducing the doc's convention).

  2. FROZEN WALK-FORWARD — split the continuous window into 8 sequential equal-BAR
     folds; run the frozen config independently per fold (fresh warm-up each fold —
     each fold's own early trendline/EMA/ATR warm-up trades are dropped, same as any
     from-scratch run on that slice; accepted per the pre-registered protocol).

     Pre-registered PASS gates (stated before running):
       (a) >= 6/8 folds net-positive (dollars)
       (b) worst single fold >= -$25,000
       (c) first-half folds (1-4) sum POSITIVE IN POINTS (era-honesty: NQ's price
           level back-loads dollar PnL onto later folds even for a flat-in-points
           edge, so the point-sum check on the early half is the honest signal)

Also reports the 2025-06-30 -> 2026-06-30 slice (the candidate's lockbox-year analog)
net/PF from the CONTINUOUS run's own trades, sliced by ENTRY date (not a separate
re-run) — this is what the doc's "LB entry-sliced" number means.

No commits. No doc edits. Print-only driver; owner reviews the console output.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.strategies import load_strategy                      # noqa: E402
from augur_engine.engine import run_backtest as eng_run_backtest       # noqa: E402

STRAT_FILE = "ENGUQ_1M_ETH_1_0.py"
INSTRUMENT = "NQ"
TIMEFRAME = "1m"
SESSION = "eth"
SOURCE = "db_noadj_eth"
MULT = 20.0          # NQ $/pt (INSTRUMENTS['NQ']['multiplier'] in optimizer.py)
COST_PTS = 0.533     # standard round-trip cost (pts) used throughout BACKTESTING_STACK.md
DATE_FROM = "2010-06-07"
DATE_TO = "2026-06-30"
LB_FROM = "2025-06-30"
LB_TO = "2026-06-30"
N_FOLDS = 8

DOC_NET = 434_721.12
DOC_PF = 1.33
DOC_DD = -50_420.0
TOL = 0.02   # +/-2%


def within_tol(actual, doc, tol=TOL):
    if doc == 0:
        return actual == 0
    return abs(actual - doc) / abs(doc) <= tol


def fmt_money(x):
    return f"${x:,.2f}"


def slice_arrays(arrays, i0, i1):
    out = {}
    for k in ("open", "high", "low", "close", "volume", "day_id"):
        v = arrays.get(k)
        out[k] = v[i0:i1] if v is not None else None
    idx = arrays.get("index")
    out["index"] = idx[i0:i1] if idx is not None else None
    out["meta"] = arrays.get("meta")
    return out


def pf_of(pnls):
    p = np.asarray(pnls, float)
    gw = p[p > 0].sum()
    gl = -p[p < 0].sum()
    if gl > 1e-9:
        return float(gw / gl)
    return float("inf") if gw > 0 else 0.0


def main():
    mod = load_strategy(STRAT_FILE)
    frozen = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}

    print("=" * 78)
    print("FROZEN PARAMS (ENGUQ_1M_ETH_1_0.py DEFAULT_PARAMS, run AS-IS, zero tuning):")
    for k, v in frozen.items():
        print(f"    {k:14s} = {v}")
    print("=" * 78)

    print(f"\nPre-registered gates (stated before running):")
    print(f"  PARITY : net $ / PF / maxDD $ within +/-2% of doc "
          f"({fmt_money(DOC_NET)} / PF {DOC_PF} / {fmt_money(DOC_DD)}), cost={COST_PTS} pts, x${MULT:.0f}/pt")
    print(f"  WF PASS: (a) >=6/8 folds net-positive (b) worst fold >= -$25,000 "
          f"(c) folds 1-4 net POINTS sum > 0")

    master = find_master(INSTRUMENT, TIMEFRAME, SESSION, SOURCE)
    if master is None:
        print(f"\nABORT: no master found for {INSTRUMENT}/{TIMEFRAME}/{SESSION}/{SOURCE}")
        sys.exit(2)
    print(f"\nMaster: {master.get('name')}  file={master.get('filename')}  "
          f"source={master.get('source')}  session={master.get('session')}")

    print(f"\nLoading master arrays, window {DATE_FROM} -> {DATE_TO} (this can take a "
          f"few minutes for a multi-hundred-MB CSV)...")
    arrays = load_master_arrays(master, date_from=DATE_FROM, date_to=DATE_TO)
    n_bars = len(arrays["close"])
    idx = arrays["index"]
    print(f"Loaded {n_bars:,} bars.  first={idx[0]}  last={idx[-1]}")

    # ---------- 1. PARITY: continuous full-window run ----------
    print("\n" + "-" * 78)
    print("STEP 1 — PARITY: continuous full-window run, frozen config, cost=%.3f pts" % COST_PTS)
    res_full = eng_run_backtest(
        mod, arrays=arrays, params=frozen, cost_pts=COST_PTS,
        return_trades=True,
    )
    if res_full is None:
        print("ABORT: full-window run returned None (no trades / bad params).")
        sys.exit(2)

    net_pts_full = res_full["total_pnl"]
    net_dollars_full = net_pts_full * MULT
    pf_full = res_full["profit_factor"]
    dd_pts_full = res_full["max_drawdown"]
    dd_dollars_full = dd_pts_full * MULT
    n_trades_full = res_full["num_trades"]

    print(f"  bars={n_bars:,}  trades={n_trades_full}  "
          f"net={fmt_money(net_dollars_full)}  net_pts={net_pts_full:,.2f}  "
          f"PF={pf_full:.3f}  maxDD={fmt_money(dd_dollars_full)}")
    print(f"  doc : net={fmt_money(DOC_NET)}  PF={DOC_PF}  maxDD={fmt_money(DOC_DD)}")

    ok_net = within_tol(net_dollars_full, DOC_NET)
    ok_pf = within_tol(pf_full, DOC_PF)
    ok_dd = within_tol(dd_dollars_full, DOC_DD)
    parity_pass = ok_net and ok_pf and ok_dd
    print(f"  parity net={'PASS' if ok_net else 'FAIL'}  "
          f"PF={'PASS' if ok_pf else 'FAIL'}  "
          f"maxDD={'PASS' if ok_dd else 'FAIL'}   ==> "
          f"{'PARITY PASS' if parity_pass else 'PARITY FAIL'}")

    if not parity_pass:
        print("\nABORT — parity gate failed. Not proceeding to the walk-forward step.")
        print("Cost-convention checklist to inspect before re-running:")
        print(f"  - trades returned by engine.run_backtest are ALREADY cost-netted at "
              f"trade[2] (augur_engine.engine._apply_costs subtracts {COST_PTS} once "
              f"per trade). Do not subtract it again externally.")
        print(f"  - multiplier used here: NQ x${MULT:.0f}/pt (optimizer.py INSTRUMENTS['NQ']).")
        print(f"  - window used: {DATE_FROM} -> {DATE_TO} inclusive (load_master_arrays "
              f"date_to is inclusive of the whole day).")
        sys.exit(1)

    # ---------- 2. LOCKBOX-YEAR SLICE (entry-date sliced, from the continuous run) ----------
    print("\n" + "-" * 78)
    print(f"STEP 2 — lockbox-year analog slice {LB_FROM} -> {LB_TO} "
          f"(entry-date sliced from the continuous run's own trades):")
    lb_from_ts = pd.Timestamp(LB_FROM, tz="US/Eastern")
    lb_to_ts = pd.Timestamp(LB_TO, tz="US/Eastern") + pd.Timedelta(days=1)
    lb_pnls = []
    for t in res_full["trades"]:
        entry_idx = t[0]
        entry_ts = idx[entry_idx]
        if lb_from_ts <= entry_ts < lb_to_ts:
            lb_pnls.append(t[2])
    if lb_pnls:
        lb_net_pts = float(np.sum(lb_pnls))
        lb_net_dollars = lb_net_pts * MULT
        lb_pf = pf_of(lb_pnls)
        print(f"  n={len(lb_pnls)}  net={fmt_money(lb_net_dollars)}  "
              f"net_pts={lb_net_pts:,.2f}  PF={lb_pf:.3f}")
    else:
        print("  n=0 trades in lockbox-year slice.")

    # ---------- 3. FROZEN WALK-FORWARD: 8 sequential equal-BAR folds ----------
    print("\n" + "-" * 78)
    print(f"STEP 3 — FROZEN WF: {N_FOLDS} sequential equal-BAR folds, frozen config, "
          f"fresh warm-up per fold, cost={COST_PTS} pts:")

    bounds = [round(n_bars * i / N_FOLDS) for i in range(N_FOLDS + 1)]
    fold_rows = []
    for i in range(N_FOLDS):
        i0, i1 = bounds[i], bounds[i + 1]
        farr = slice_arrays(arrays, i0, i1)
        fbars = i1 - i0
        fres = eng_run_backtest(mod, arrays=farr, params=frozen, cost_pts=COST_PTS,
                                return_trades=False)
        if fres is None:
            fold_rows.append({
                "fold": i + 1, "bars": fbars, "trades": 0,
                "net_dollars": 0.0, "net_pts": 0.0, "pf": 0.0,
                "t0": farr["index"][0] if fbars else None,
                "t1": farr["index"][-1] if fbars else None,
            })
            continue
        net_pts = fres["total_pnl"]
        fold_rows.append({
            "fold": i + 1, "bars": fbars, "trades": fres["num_trades"],
            "net_dollars": net_pts * MULT, "net_pts": net_pts, "pf": fres["profit_factor"],
            "t0": farr["index"][0], "t1": farr["index"][-1],
        })

    print(f"\n  {'fold':>4} {'bars':>10} {'trades':>7} {'net $':>14} {'net pts':>10} "
          f"{'PF':>6}   window")
    for r in fold_rows:
        print(f"  {r['fold']:>4} {r['bars']:>10,} {r['trades']:>7} "
              f"{fmt_money(r['net_dollars']):>14} {r['net_pts']:>10,.2f} {r['pf']:>6.2f}   "
              f"{r['t0']} -> {r['t1']}")

    n_pos = sum(1 for r in fold_rows if r["net_dollars"] > 0)
    worst_fold = min(fold_rows, key=lambda r: r["net_dollars"])
    first_half_pts = sum(r["net_pts"] for r in fold_rows[:4])

    gate_a = n_pos >= 6
    gate_b = worst_fold["net_dollars"] >= -25_000
    gate_c = first_half_pts > 0
    wf_pass = gate_a and gate_b and gate_c

    print("\n" + "-" * 78)
    print("WF GATE VERDICT:")
    print(f"  (a) folds net-positive: {n_pos}/{N_FOLDS}  "
          f"{'PASS' if gate_a else 'FAIL'} (need >=6/8)")
    print(f"  (b) worst fold: fold {worst_fold['fold']} = {fmt_money(worst_fold['net_dollars'])}  "
          f"{'PASS' if gate_b else 'FAIL'} (need >= -$25,000)")
    print(f"  (c) folds 1-4 net points sum: {first_half_pts:,.2f} pts  "
          f"{'PASS' if gate_c else 'FAIL'} (need > 0)")
    print(f"\n  ==> WF {'PASS' if wf_pass else 'FAIL'}")

    print("\n" + "=" * 78)
    print("SUMMARY")
    print(f"  parity : {'PASS' if parity_pass else 'FAIL'}")
    print(f"  wf     : {'PASS' if wf_pass else 'FAIL'}")
    print("=" * 78)


if __name__ == "__main__":
    main()
