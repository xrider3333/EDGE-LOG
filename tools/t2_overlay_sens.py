"""T2 — reproduce the S1 sized-ORB blend result and probe the post-hoc rolling-normalization
caveat (BACKTESTING_STACK.md 2026-07-24, Round 5, S1).

S1 claim: the validated ORB sizing overlay (risk-parity cap-3x * time-of-day tilt
2.0/1.0/0.5 * side tilt long0.5/short1.5, augur_engine/sizing.py) applied to ORB #125,
with ERA-LOCAL ROLLING RISK NORMALIZATION (trailing 250-trade median of risk points,
exposure-matched to mean weight 1.0), lifts:
  ORB leg  $360,640 -> $631,805   (leg maxDD -$9.4k -> -$7.1k)
  1:1 blend (ORB + certified ENGU-Q #149) $838k -> $1,109k net, DD -$58.7k, net/DD 13.95->18.91

sizing.py (as shipped) does NOT contain the rolling-normalization piece: `sizing_weights`'s
risk_parity term is `f = 1/risk_pts; f = f/f.mean()` -- a GLOBAL mean, not a trailing/rolling
one. That rolling rule is implemented HERE in the driver (see `rolling_rp_factor` /
`sizing_weight` below), exactly per the BACKTESTING_STACK.md description, so this script is
also the reproducible record of what "the rolling rule" concretely is.

IMPLEMENTATION NOTE (found empirically, see report): the documented $ results are NOT
reproduced by routing the rolling weights through `augur_engine.sizing.sized_metrics`'s
capital-match (which risk-weights the match: sum(size*risk) == sum(baseline_risk)).
They ARE reproduced (both leg and blend within ~0.1%) by using the mean-normalized weight
directly AS the contract-size multiplier (size = weight, mean(weight) == 1.0 over the full
history) with no further risk-weighted rescale. That is the literal reading of the doc's
last clause ("weights exposure-matched so mean weight = 1.0 across the full history") and
is what this driver does.

No commits. Read-only against the repo; writes nothing.
Usage: python tools/t2_overlay_sens.py
"""
import sys, pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest, find_master, load_master_arrays
from augur_engine import sizing as SZ
import importlib.util

_s = importlib.util.spec_from_file_location("enguq", REPO / "augur_strategies" / "ENGUQ_1M_1_0.py")
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
ENG_149 = _m.NQ_DEPLOY_PARAMS_149

WIN = ("2010-06-07", "2026-06-30")          # pinned window (blend_recert.py convention)
LOCKBOX_FROM = "2025-06-30"                  # last-12-mo / lockbox slice start
COST = 0.533                                 # RT cost, points (both legs)
MULT = 20.0                                  # NQ point value
RP_CAP = 3.0
LONG_W, SHORT_W = 0.5, 1.5
TIERS = SZ.DEFAULT_TIME_TIERS

ORB_125 = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
               breakout_buf=0.0, target_R=0.0, partial_exit_R=0.0, trail_bars=5,
               flat_eod=True)
BASELINE_NET_DD = 13.94   # documented round-3 baseline blend net/DD (task-supplied threshold)

TOL = 0.015  # 1.5% parity tolerance


def pct_diff(actual, expect):
    return abs(actual - expect) / abs(expect) if expect else float("inf")


# ── Leg loaders ──────────────────────────────────────────────────────────────
def load_orb_gross():
    """ORB #125 gross (pre-cost, 1-contract) trades on the pinned window. find_master is
    ambiguous for NQ 5m rth (db_noadj_rth vs tv tie alphabetically) -- pin source='tv'
    per BACKTESTING_STACK.md 2026-07-24 note, else parity is off by 1 trade."""
    master = find_master("NQ", "5m", "rth", source="tv")
    arr = load_master_arrays(master, date_from=WIN[0], date_to=WIN[1])
    r = run_backtest("ORB_3_1.py", arrays=arr, params=ORB_125, cost_pts=0.0, return_trades=True)
    return r, arr


def load_eng_leg():
    """Certified ENGU-Q leg (#149 deploy params), 1m rth. find_master defaults to
    db_noadj_rth here (unambiguous match to the certified/expected net) -- no pin needed."""
    master = find_master("NQ", "1m", "rth", source=None)
    arr = load_master_arrays(master, date_from=WIN[0], date_to=WIN[1])
    r = run_backtest("ENGUQ_1M_1_0.py", arrays=arr, params=ENG_149, cost_pts=COST, return_trades=True)
    idx = arr["index"]
    d = {}
    for t in r["trades"]:
        day = pd.Timestamp(idx[int(t[1])]).date()
        d[day] = d.get(day, 0.0) + float(t[2]) * MULT
    s = pd.Series(d).sort_index()
    s.index = pd.to_datetime(s.index)
    return r, s


# ── The rolling-normalization sizing rule (NOT in sizing.py -- built here) ──────────────
def rolling_rp_factor(risk_pts, window, stat, min_periods=30):
    """Trailing `window`-trade {median,mean} of risk_pts, min_periods `min_periods`,
    falling back to an EXPANDING {median,mean} (min_periods=1) wherever the rolling
    window hasn't got enough history yet (first ~min_periods trades). Returns
    local_stat(risk_pts) / risk_pts, i.e. each trade's risk expressed relative to its
    own era's typical risk (era-local normalization) -- NOT capped yet."""
    s = pd.Series(np.asarray(risk_pts, float))
    if stat == "median":
        roll = s.rolling(window, min_periods=min_periods).median()
        exp = s.expanding(min_periods=1).median()
    elif stat == "mean":
        roll = s.rolling(window, min_periods=min_periods).mean()
        exp = s.expanding(min_periods=1).mean()
    else:
        raise ValueError(stat)
    local = roll.fillna(exp).to_numpy()
    return local / np.asarray(risk_pts, float)


def sizing_weight(risk_pts, entry_bar, side, window, stat, rp_cap=RP_CAP):
    """weight = tilts * (local_stat(risk)/risk) capped at rp_cap; then exposure-matched
    so mean(weight) == 1.0 across the full trade history. This normalized weight is used
    DIRECTLY as the contract-size multiplier (see module docstring)."""
    rp = np.minimum(rolling_rp_factor(risk_pts, window, stat), rp_cap)
    tilt = SZ.time_weight(entry_bar, TIERS) * np.where(np.asarray(side) > 0, LONG_W, SHORT_W)
    w = tilt * rp
    return w / w.mean()


def sized_orb_leg(orb_res, arr, window, stat):
    """Returns (daily_pnl_series[USD], leg_net, leg_maxdd, max_weight)."""
    trades = orb_res["trades"]
    pnl, risk, ebar, side = SZ.trade_features(trades, arr, ORB_125["stop_frac"], ORB_125["or_bars"])
    exit_gi = np.array([t[1] for t in trades])
    w = sizing_weight(risk, ebar, side, window, stat)
    net = w * (pnl - COST) * MULT
    idx = arr["index"]
    days = pd.to_datetime([pd.Timestamp(idx[int(g)]).date() for g in exit_gi])
    daily = pd.Series(net, index=days).groupby(level=0).sum().sort_index()
    cum = daily.cumsum()
    dd = float((cum - cum.cummax()).min())
    return daily, float(daily.sum()), dd, float(w.max())


def blend_stats(orb_daily, eng_daily):
    df = pd.DataFrame({"orb": orb_daily, "eng": eng_daily}).fillna(0.0).sort_index()
    df["combo"] = df["orb"] + df["eng"]
    cum = df["combo"].cumsum()
    dd = float((cum - cum.cummax()).min())
    net = float(df["combo"].sum())
    years = df.groupby(df.index.year)["combo"].sum()
    last12 = float(df.loc[df.index >= LOCKBOX_FROM, "combo"].sum())
    return net, dd, years, last12


def main():
    print("=" * 100)
    print("STEP 1-2: PARITY -- reproduce size-1 baseline legs/blend, then the documented S1 cell (250/median)")
    print("=" * 100)

    orb_res, orb_arr = load_orb_gross()
    eng_res, eng_daily = load_eng_leg()

    # size-1 baseline leg (no overlay) -- must match blend_recert.py's certified numbers.
    pnl0, risk0, ebar0, side0 = SZ.trade_features(orb_res["trades"], orb_arr, ORB_125["stop_frac"], ORB_125["or_bars"])
    net0 = float(((pnl0 - COST) * MULT).sum())
    exit_gi0 = np.array([t[1] for t in orb_res["trades"]])
    idx0 = orb_arr["index"]
    days0 = pd.to_datetime([pd.Timestamp(idx0[int(g)]).date() for g in exit_gi0])
    orb0_daily = pd.Series((pnl0 - COST) * MULT, index=days0).groupby(level=0).sum().sort_index()
    cum0 = orb0_daily.cumsum(); dd0 = float((cum0 - cum0.cummax()).min())
    print(f"ORB #125 size-1 leg : n={orb_res['num_trades']}  net=${net0:,.2f}  maxDD=${dd0:,.0f}"
          f"   (expect n=4064 / $360,640.26 / DD ~-$9.4k)")
    print(f"ENGU-Q #149 leg     : n={eng_res['num_trades']}  net=${eng_daily.sum():,.2f}"
          f"   (expect n=2048 / ~$474.7-477.5k)")

    base_net, base_dd, base_years, base_last12 = blend_stats(orb0_daily, eng_daily)
    print(f"BASELINE 1:1 BLEND  : net=${base_net:,.0f}  maxDD=${base_dd:,.0f}  net/DD={base_net/abs(base_dd):.2f}"
          f"   (task baseline net/DD = {BASELINE_NET_DD})")
    print(f"BASELINE last-12mo (>= {LOCKBOX_FROM}): ${base_last12:,.0f}   (doc lockbox-yr baseline ~$183k)")

    # documented S1 cell: window=250, stat=median
    orb_daily_s1, leg_net_s1, leg_dd_s1, maxw_s1 = sized_orb_leg(orb_res, orb_arr, 250, "median")
    blend_net_s1, blend_dd_s1, years_s1, last12_s1 = blend_stats(orb_daily_s1, eng_daily)
    print(f"\nS1 (window=250, stat=median):")
    print(f"  sized ORB leg  : net=${leg_net_s1:,.0f}  maxDD=${leg_dd_s1:,.0f}   "
          f"(target $631,805 / -$7.1k, diff {pct_diff(leg_net_s1,631805)*100:.2f}%)")
    print(f"  blend          : net=${blend_net_s1:,.0f}  maxDD=${blend_dd_s1:,.0f}  net/DD={blend_net_s1/abs(blend_dd_s1):.2f}   "
          f"(target $1,109k / -$58.7k / 18.91, net diff {pct_diff(blend_net_s1,1109000)*100:.2f}%, "
          f"DD diff {pct_diff(abs(blend_dd_s1),58700)*100:.2f}%)")
    print(f"  max weight     : {maxw_s1:.2f}x   (doc: p95 3.2x / max 7.9x)")

    leg_ok = pct_diff(leg_net_s1, 631805) <= TOL
    blend_ok = pct_diff(blend_net_s1, 1109000) <= TOL and pct_diff(abs(blend_dd_s1), 58700) <= TOL
    if not (leg_ok and blend_ok):
        print("\nABORT: S1 reproduction outside 1.5% tolerance on leg and/or blend. Stopping.")
        return
    print("\nPARITY OK -- both leg and blend within 1.5% of documented S1. Proceeding to sensitivity grid.")

    print("\n" + "=" * 100)
    print("STEP 3-4: SENSITIVITY GRID -- window x {125,250,500} x stat x {median,mean}, everything else frozen")
    print("=" * 100)

    rows = []
    for window in (125, 250, 500):
        for stat in ("median", "mean"):
            orb_daily, leg_net, leg_dd, maxw = sized_orb_leg(orb_res, orb_arr, window, stat)
            blend_net, blend_dd, years, last12 = blend_stats(orb_daily, eng_daily)
            net_dd = blend_net / abs(blend_dd)
            # align years index across baseline/candidate (union, 0-filled)
            all_years = sorted(set(base_years.index) | set(years.index))
            delta = pd.Series({y: years.get(y, 0.0) - base_years.get(y, 0.0) for y in all_years})
            n_worse = int((delta < 0).sum())
            n_better = int((delta > 0).sum())
            n_years = len(all_years)
            verdict_holds = (net_dd > BASELINE_NET_DD) and (n_better >= 14)
            rows.append(dict(window=window, stat=stat, leg_net=leg_net, leg_dd=leg_dd,
                              blend_net=blend_net, blend_dd=blend_dd, net_dd=net_dd,
                              last12=last12, n_years=n_years, n_worse=n_worse, n_better=n_better,
                              maxw=maxw, holds=verdict_holds))

    hdr = (f"{'window':>6} {'stat':>6} | {'leg net':>11} {'leg DD':>9} | {'blend net':>12} {'blend DD':>10} "
           f"{'net/DD':>7} | {'last12mo':>10} | {'yrs worse':>9} {'yrs better':>10} | verdict")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        v = "HOLDS" if r["holds"] else "fails"
        print(f"{r['window']:>6} {r['stat']:>6} | ${r['leg_net']:>10,.0f} ${r['leg_dd']:>8,.0f} | "
              f"${r['blend_net']:>11,.0f} ${r['blend_dd']:>9,.0f} {r['net_dd']:>7.2f} | "
              f"${r['last12']:>9,.0f} | {r['n_worse']:>9}/{r['n_years']} {r['n_better']:>7}/{r['n_years']} | {v}")

    print(f"\nBaseline blend net/DD = {base_net/abs(base_dd):.2f}  (task threshold {BASELINE_NET_DD})")
    n_hold = sum(1 for r in rows if r["holds"])
    print(f"Verdict cells holding: {n_hold}/6")


if __name__ == "__main__":
    main()
