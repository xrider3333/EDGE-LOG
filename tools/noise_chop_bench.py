"""tools/noise_chop_bench.py -- "CHOP GATE" bench for NOISE_1_2_CHOP.py.

PRE-REGISTERED BARS (declared BEFORE running; all four must pass for a cell to
be "PROMISING"):
  1. full-window PF > parent PF (same window, same costs)
  2. the PF gain holds in >= 3 of 4 eras (2010-14, 2014-18, 2018-22, 2022+)
  3. >= 40 trades in the held-out year (anti-starvation)
  4. EV R AND R/YR both above the parent's (same window)
PRIMARY cell (declared before running): er_len=12, er_max=0.30.
Parent/control = NOISE_1_0.py's champion cell from run #305 (er_max=0.0, i.e.
the CHOP gate fully off) -- NOT the frozen defaults; run #305 is the parity
anchor and the champion this task is trying to beat.

PARITY ANCHOR: run #305 (latest full-discovery NOISE validate, NQ 5m RTH
db_noadj_rth, date_from=2010-06-07, date_to=2026-08-12, cost_pts=0.533).
IMPORTANT CORRECTION (found while building this bench, verified by scanning
every numeric field in the run-305 doc): the doc's top-level best_pnl_usd=
131091.42 / best_pf=1.4240 / best_trades=2591 are the DISCOVERY-TIME (pre-
lockbox / IS-window) selection metrics for the champion params -- NOT a
reproduction target for a plain run_backtest() over the doc's own full
date_from/date_to span. The doc ALSO stores the full-window confirmatory
re-run at `gate_validate.ungated_full` / `validate.causal` / `equity.final`:
n_trades=3744, total_pnl_pts=17366.671616964006 (net $347,333.43 at mult=20),
profit_factor=1.3858812018274325 -- and THIS is exactly what a plain
run_backtest(NOISE_1_0.py, champion best_params, date_from=2010-06-07,
date_to=2026-08-12, cost_pts=0.533) reproduces (verified by hand before
writing this driver). That full-window figure is the correct parity anchor
for a bench that operates on the FULL window (as this one does, per the
bench-grid spec below), so it is what EXPECT_NET/EXPECT_PF/EXPECT_TRADES
below target -- NOT the doc's top-level best_* fields.

Held-out year: run #305's doc has no lockbox_months field (None) -- using this
project's standard 12-month convention anchored on the run's own date_to:
2025-08-12 -> 2026-08-12 (the last 12 months of the run's window).

Bench grid (12 cells): er_len in {6,12,24} x er_max in {0.20,0.30,0.40,0.50},
all on #305's champion params/window -- 13 engine runs total (12 + control).
Budget: <=24 engine runs. Sequential.
"""
import os
import sys
import json
import datetime

import numpy as np

ROOT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\noise-chop"
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)

import augur_engine.paths as paths           # noqa: E402
paths.DB_PATH = os.path.join(SHARED, "optimizer_history.db")
paths.UPLOADS = os.path.join(SHARED, "augur_uploads")

import augur_engine.data as data_mod         # noqa: E402
data_mod.DB_PATH = paths.DB_PATH
data_mod.UPLOADS = paths.UPLOADS

from augur_engine.engine import run_backtest as eng_bt   # noqa: E402

FEE, MULT = 0.533, 20.0
INSTRUMENT, TF, SESSION, SOURCE = "NQ", "5m", "rth", "db_noadj_rth"
DATE_FROM = "2010-06-07"
DATE_TO = "2026-08-12"          # run #305's window
HELD_OUT_START = "2025-08-12"   # 12 months before date_to (no lockbox_months on #305)

# run #305's champion params (Firestore users/IO0K35JpLIcH9YK4C0pMNYUzZOM2/runs/305)
CHAMP_PARAMS = dict(
    daytype_lo=0.25, window="all_day", confirm_bars=4, daytype_mode="skip_bot_short",
    band_mult_long=0.75, vol_skip_pct=99.0, band_mult_short=1.25, skip_holidays=False,
    stop_mode="bandwidth", flat_eod=True, lookback=51, side="Both", daytype_hi=0.6,
    stop_k=1.25, exit_mode="vwap",
)
# Full-window confirmatory figures from run #305's own doc (gate_validate.
# ungated_full / validate.causal / equity.final) -- see docstring correction above.
EXPECT_NET = 347333.43233928934
EXPECT_PF = 1.3858812018274325
EXPECT_TRADES = 3744

ERAS = [
    ("2010-14", "2010-01-01", "2014-01-01"),
    ("2014-18", "2014-01-01", "2018-01-01"),
    ("2018-22", "2018-01-01", "2022-01-01"),
    ("2022+", "2022-01-01", "2027-01-01"),
]


def _trade_stats(trades, index_arr, mult=MULT):
    """Tag each ALREADY cost-adjusted (entry_idx, exit_idx, pnl_pts, side, entry_px)
    trade -- as returned by engine.run_backtest(..., return_trades=True), which runs
    every trade through _apply_costs before handing it back -- with its entry
    timestamp, for era/held-out slicing. Do NOT subtract cost_pts again here."""
    rows = []
    for t in trades:
        entry_idx, pnl_pts = t[0], t[2]
        ts = index_arr[entry_idx]
        rows.append((ts, pnl_pts * mult))
    return rows


def _summ(rows):
    if not rows:
        return dict(n=0, net=0.0, pf=0.0, wr=0.0)
    vals = np.array([r[1] for r in rows], float)
    wins = vals[vals > 0]; losses = vals[vals < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    wr = 100.0 * len(wins) / len(vals)
    return dict(n=len(vals), net=float(vals.sum()), pf=pf, wr=wr)


def _ev_r_ryr(summ, years):
    n, pf, wr = summ["n"], summ["pf"], summ["wr"]
    if n == 0 or years <= 0:
        return 0.0, 0.0
    win_rate = wr / 100.0
    ev_r = (1.0 - win_rate) * (pf - 1.0) if pf not in (0.0, float("inf")) else 0.0
    if pf == float("inf"):
        ev_r = (1.0 - win_rate) * 999.0   # degenerate no-loss case, flagged not relied on
    trades_per_year = n / years
    ryr = ev_r * trades_per_year
    return ev_r, ryr


def run_cell(er_len, er_max, label):
    params = dict(CHAMP_PARAMS, er_max=er_max, er_len=er_len)
    r = eng_bt("NOISE_1_2_CHOP.py", instrument=INSTRUMENT, timeframe=TF, session=SESSION,
               source=SOURCE, cost_pts=FEE, date_from=DATE_FROM, date_to=DATE_TO,
               params=params, return_trades=True)
    if r is None or not r.get("trades"):
        print("%-28s NO TRADES" % label)
        return None
    arrays = data_mod.load_master_arrays(
        data_mod.find_master(INSTRUMENT, TF, SESSION, SOURCE),
        date_from=DATE_FROM, date_to=DATE_TO)
    index_arr = arrays["index"]
    rows = _trade_stats(r["trades"], index_arr)

    full = _summ(rows)
    years_full = (index_arr[-1] - index_arr[0]).total_seconds() / 86400.0 / 365.25
    ev_full, ryr_full = _ev_r_ryr(full, years_full)

    import pandas as pd
    ho_start = pd.Timestamp(HELD_OUT_START, tz="US/Eastern")
    held = [row for row in rows if row[0] >= ho_start]
    held_summ = _summ(held)
    ev_ho, ryr_ho = _ev_r_ryr(held_summ, 1.0)

    era_pf = {}
    for name, lo, hi in ERAS:
        lo_ts = pd.Timestamp(lo, tz="US/Eastern"); hi_ts = pd.Timestamp(hi, tz="US/Eastern")
        era_rows = [row for row in rows if lo_ts <= row[0] < hi_ts]
        era_pf[name] = _summ(era_rows)["pf"]

    return dict(label=label, er_len=er_len, er_max=er_max, full=full,
                years_full=years_full, ev_full=ev_full, ryr_full=ryr_full,
                held=held_summ, ev_ho=ev_ho, ryr_ho=ryr_ho, era_pf=era_pf)


def main():
    print("=" * 78)
    print("PARITY CHECK: er_max=0.0, run #305 champion params, #305's window")
    print("=" * 78)
    control = run_cell(12, 0.0, "control (er_max=0.0)")
    if control is None:
        print("PARITY: FAIL (no trades)")
        sys.exit(1)
    n, net, pf = control["full"]["n"], control["full"]["net"], control["full"]["pf"]
    print("  got:      n=%d net=$%s PF=%.6f" % (n, format(net, ",.2f"), pf))
    print("  expected: n=%d net=$%s PF=%.6f" % (
        EXPECT_TRADES, format(EXPECT_NET, ",.2f"), EXPECT_PF))
    parity_ok = (n == EXPECT_TRADES and abs(net - EXPECT_NET) < 1.0 and abs(pf - EXPECT_PF) < 0.0005)
    print("  PARITY: %s" % ("PASS" if parity_ok else "FAIL"))
    print()
    if not parity_ok:
        print("PARITY FAILED -- aborting bench, not shipping.")
        sys.exit(1)

    parent = control  # er_max=0.0 IS the parent behavior on this file
    parent_pf = parent["full"]["pf"]
    parent_ev, parent_ryr = parent["ev_full"], parent["ryr_full"]

    print("=" * 78)
    print("BENCH GRID: er_len x er_max on #305 champion params/window")
    print("=" * 78)
    grid = []
    for er_len in (6, 12, 24):
        for er_max in (0.20, 0.30, 0.40, 0.50):
            label = "er_len=%d er_max=%.2f" % (er_len, er_max)
            cell = run_cell(er_len, er_max, label)
            if cell is None:
                continue
            eras_ok = sum(1 for name, _, _ in ERAS if cell["era_pf"][name] > parent["era_pf"][name])
            bar1 = cell["full"]["pf"] > parent_pf
            bar2 = eras_ok >= 3
            bar3 = cell["held"]["n"] >= 40
            bar4 = (cell["ev_full"] > parent_ev) and (cell["ryr_full"] > parent_ryr)
            passed = bar1 and bar2 and bar3 and bar4
            cell["bars"] = dict(pf_gain=bar1, eras_ok=eras_ok, held_ok=bar3,
                                 ev_ryr_ok=bar4, ALL_PASS=passed)
            grid.append(cell)
            print("%-24s n=%-5d net=$%-12s PF=%.4f  EV_R=%.4f R/YR=%.2f  "
                  "eras_held=%d/4  LB n=%-4d  BARS: pf=%s eras=%s lb>=40=%s "
                  "ev/ryr=%s  ALL=%s" % (
                      label, cell["full"]["n"], format(cell["full"]["net"], ",.0f"),
                      cell["full"]["pf"], cell["ev_full"], cell["ryr_full"], eras_ok,
                      cell["held"]["n"], bar1, bar2, bar3, bar4, passed))

    print()
    print("PARENT (control, er_max=0.0): n=%d net=$%s PF=%.4f EV_R=%.4f R/YR=%.2f" % (
        parent["full"]["n"], format(parent["full"]["net"], ",.0f"), parent_pf,
        parent_ev, parent_ryr))
    print()

    primary = next((c for c in grid if c["er_len"] == 12 and abs(c["er_max"] - 0.30) < 1e-9), None)
    print("=" * 78)
    print("PRIMARY (er_len=12, er_max=0.30) verdict: %s" %
          ("PROMISING" if (primary and primary["bars"]["ALL_PASS"]) else "DEAD"))
    print("=" * 78)

    any_pass = [c for c in grid if c["bars"]["ALL_PASS"]]
    if any_pass:
        print("Non-primary cells also passing all 4 bars: %s" %
              [c["label"] for c in any_pass if c is not primary])

    out = dict(
        parity_pass=parity_ok, parent=dict(net=parent["full"]["net"], pf=parent_pf,
                                            n=parent["full"]["n"], ev_r=parent_ev, ryr=parent_ryr),
        grid=[{k: v for k, v in c.items()} for c in grid],
        primary_pass=bool(primary and primary["bars"]["ALL_PASS"]),
        any_pass=[c["label"] for c in any_pass],
    )
    with open(os.path.join(ROOT, "tools", "_noise_chop_bench.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)

    return primary, any_pass, grid, parent


if __name__ == "__main__":
    main()
