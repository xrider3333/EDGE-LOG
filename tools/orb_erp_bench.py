"""
orb_erp_bench.py -- SELF-ADJUSTING (PERCENTILE) EFFICIENCY FLOOR on the ORB crown.

PRE-REGISTERED BARS (written before running; all four must pass for PROMISING):
  1. full-window PF > parent PF (#234 C2, same window NQ 5m RTH db_noadj_rth
     2010-06-07..2026-08-13, cost 0.533 pts x $20, 1 contract)
  2. the PF gain holds in >= 3 of 4 eras (2010-14, 2014-18, 2018-22, 2022+)
  3. >= 40 trades in the held-out year (entries >= 2025-06-30) -- anti-starvation,
     the exact failure mode #278 (fixed floor) had (0 held-out trades)
  4. EV R AND R/YR both above the parent's
       EV R  = (1 - win_rate) x (PF - 1)
       R/YR  = EV R x trades_per_year
     Parent (#234 C2) reference: PF 1.307, WR ~41%, 2607 trades / ~16.2y
       -> EV R ~0.18, R/YR ~29

PRIMARY cell (declared before running): er_len=12, er_keep=0.60.
Grid: er_len in {6,12} x er_keep in {0.40,0.50,0.60,0.70} = 8 cells, + control (er_keep=0).
Parity check: er_keep=0.0 must reproduce #234 C2 EXACTLY:
    net $389,874 / PF 1.307 / DD $29,142 / 2607 trades

Cost: 9 engine runs total (1 parity + 8 grid cells), well under the <=24 budget.
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
import importlib.util as ilu  # noqa: E402

STRAT_PATH = os.path.join(ROOT, "augur_strategies", "ORB_3_6_ERP.py")
spec = ilu.spec_from_file_location("orb_3_6_erp", STRAT_PATH)
strat = ilu.module_from_spec(spec)
spec.loader.exec_module(strat)

# ── Parity anchor: run #234 (ORB_3_6_C2.py) ──────────────────────────────────
DATE_FROM = "2010-06-07"
DATE_TO = "2026-08-13"
SOURCE = "db_noadj_rth"
SESSION = "rth"
INSTRUMENT = "NQ"
TIMEFRAME = "5m"
COST_PTS = 0.533
MULT = 20.0
HELD_OUT_FROM = "2025-06-30"

BEST_PARAMS = dict(
    skip_holidays=True, breakout_buf=0.25, vpace_filter=0.7, close_confirm=True,
    flat_eod=True, or_bars=2, be_after_R=1.0, stop_frac=2.0, trail_bars=0,
    target_R=5.5, partial_exit_R=0.0, trade_mode="First-candle dir", atr_filter=0.7,
)

REF_NET = 389874.0
REF_PF = 1.307
REF_DD = 29142.0
REF_N = 2607

ERAS = [("2010-01-01", "2014-01-01"), ("2014-01-01", "2018-01-01"),
        ("2018-01-01", "2022-01-01"), ("2022-01-01", "2027-01-01")]


def load_data():
    m = find_master(INSTRUMENT, TIMEFRAME, session=SESSION, source=SOURCE)
    if m is None:
        raise SystemExit(f"master not found: {INSTRUMENT} {TIMEFRAME} {SESSION} {SOURCE}")
    arr = load_master_arrays(m, date_from=DATE_FROM, date_to=DATE_TO)
    return arr


def run(arr, er_keep, er_len, er_win=20000):
    res = strat.run_backtest(
        arr["open"], arr["high"], arr["low"], arr["close"],
        volumes=arr.get("volume"), day_id=arr["day_id"],
        er_keep=er_keep, er_len=er_len, er_win=er_win,
        return_trades=True, **BEST_PARAMS,
    )
    return res


def apply_costs(trades):
    """trades: list of (entry_idx, exit_idx, pnl_pts, side, entry_px) -> net $ list."""
    return [(t[2] - COST_PTS) * MULT for t in trades]


def entry_dates(arr, trades):
    idx = arr.get("index")
    if idx is None:
        return [None] * len(trades)
    out = []
    for t in trades:
        i = int(t[0])
        try:
            out.append(str(idx[i])[:10])
        except Exception:
            out.append(None)
    return out


def stats(net_list):
    a = np.array(net_list, float)
    if len(a) == 0:
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, wr=0.0)
    wins = a[a > 0]; losses = a[a < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    cum = np.cumsum(a); peak = np.maximum.accumulate(cum)
    dd = float((cum - peak).min())
    wr = 100.0 * len(wins) / len(a)
    return dict(n=int(len(a)), net=float(a.sum()), pf=float(pf), dd=dd, wr=wr)


def ev_r_ryr(pf, wr_pct, n, years):
    wr = wr_pct / 100.0
    ev_r = (1 - wr) * (pf - 1)
    tpy = n / years if years > 0 else 0.0
    return ev_r, ev_r * tpy


def era_pf(arr, trades, dates):
    out = []
    for lo, hi in ERAS:
        net = [t for t, d in zip(trades, dates) if d is not None and lo <= d < hi]
        s = stats(net)
        out.append(s["pf"])
    return out


def main():
    arr = load_data()
    idx = arr.get("index")
    n_bars = len(arr["close"])
    if idx is not None and len(idx) == n_bars:
        span_days = (np.datetime64(str(idx[-1])[:10]) - np.datetime64(str(idx[0])[:10])).astype(int)
        years = span_days / 365.25
    else:
        years = (np.datetime64(DATE_TO) - np.datetime64(DATE_FROM)).astype(int) / 365.25

    print(f"window {DATE_FROM}..{DATE_TO}  years~{years:.2f}  bars={n_bars}")

    # ── Parity: er_keep=0.0 ───────────────────────────────────────────────
    r0 = run(arr, er_keep=0.0, er_len=12, er_win=20000)
    n0 = r0["num_trades"]
    r0_usd_stats = stats(apply_costs(r0["trades"]))
    net0_usd, pf0, dd0_usd = r0_usd_stats["net"], r0_usd_stats["pf"], r0_usd_stats["dd"]
    parity_ok = (n0 == REF_N and abs(net0_usd - REF_NET) < 1.0 and abs(pf0 - REF_PF) < 0.001)
    print(f"PARITY (er_keep=0.0): n={n0} (ref {REF_N})  net=${net0_usd:,.0f} (ref ${REF_NET:,.0f})  "
          f"PF={pf0:.3f} (ref {REF_PF})  DD=${dd0_usd:,.0f} (ref -${REF_DD:,.0f})  "
          f"-> {'PASS' if parity_ok else 'FAIL'}")

    control_trades = apply_costs(r0["trades"])
    control_dates = entry_dates(arr, r0["trades"])
    control_stats = stats(control_trades)
    control_eras = era_pf(arr, control_trades, control_dates)
    ctl_ev, ctl_ryr = ev_r_ryr(control_stats["pf"], control_stats["wr"], control_stats["n"], years)
    print(f"CONTROL (parent, er_keep=0): PF={control_stats['pf']:.3f}  EV_R={ctl_ev:.3f}  R/YR={ctl_ryr:.2f}  "
          f"eras_PF={[round(x,3) for x in control_eras]}")

    grid = []
    for er_len in (6, 12):
        for er_keep in (0.40, 0.50, 0.60, 0.70):
            r = run(arr, er_keep=er_keep, er_len=er_len, er_win=20000)
            trades_usd = apply_costs(r["trades"]) if r else []
            dates = entry_dates(arr, r["trades"]) if r else []
            s = stats(trades_usd)
            eras = era_pf(arr, trades_usd, dates)
            eras_win = sum(1 for e, c in zip(eras, control_eras) if e > c)
            lb_trades = sum(1 for d in dates if d is not None and d >= HELD_OUT_FROM)
            ev_r, ryr = ev_r_ryr(s["pf"], s["wr"], s["n"], years)
            row = dict(er_len=er_len, er_keep=er_keep, n=s["n"], net=s["net"], pf=s["pf"],
                       dd=s["dd"], wr=s["wr"], ev_r=ev_r, ryr=ryr, eras=eras, eras_win=eras_win,
                       lb_trades=lb_trades)
            grid.append(row)
            print(f"er_len={er_len:2d} er_keep={er_keep:.2f}  n={s['n']:5d}  net=${s['net']:>10,.0f}  "
                  f"PF={s['pf']:.3f}  DD=${s['dd']:>9,.0f}  WR={s['wr']:.1f}%  EV_R={ev_r:.3f}  "
                  f"R/YR={ryr:.2f}  eras_win={eras_win}/4  LB_trades={lb_trades}")

    primary = next(r for r in grid if r["er_len"] == 12 and abs(r["er_keep"] - 0.60) < 1e-9)
    bar1 = primary["pf"] > control_stats["pf"]
    bar2 = primary["eras_win"] >= 3
    bar3 = primary["lb_trades"] >= 40
    bar4 = (primary["ev_r"] > ctl_ev) and (primary["ryr"] > ctl_ryr)
    verdict = "PROMISING" if (parity_ok and bar1 and bar2 and bar3 and bar4) else "DEAD"

    print("\nPRIMARY (er_len=12, er_keep=0.60):")
    print(f"  bar1 PF>{control_stats['pf']:.3f}: {primary['pf']:.3f} -> {'PASS' if bar1 else 'FAIL'}")
    print(f"  bar2 eras>=3/4: {primary['eras_win']} -> {'PASS' if bar2 else 'FAIL'}")
    print(f"  bar3 LB trades>=40: {primary['lb_trades']} -> {'PASS' if bar3 else 'FAIL'}")
    print(f"  bar4 EV_R&R/YR > parent ({ctl_ev:.3f}, {ctl_ryr:.2f}): "
          f"({primary['ev_r']:.3f}, {primary['ryr']:.2f}) -> {'PASS' if bar4 else 'FAIL'}")
    print(f"  VERDICT: {verdict}")

    out = dict(parity_ok=parity_ok, parity=dict(n=n0, net=net0_usd, pf=pf0, dd=dd0_usd),
               control=dict(stats=control_stats, ev_r=ctl_ev, ryr=ctl_ryr, eras=control_eras),
               grid=grid, primary=primary, verdict=verdict, years=years)
    out_path = os.path.join(ROOT, "tools", "_orb_erp_bench.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
