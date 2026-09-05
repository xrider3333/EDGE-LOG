#!/usr/bin/env python3
"""
NOISE HUNT ROUND 6 (2026-09-04) — EV R and R / YR.

Owner ask: find a NOISE configuration that beats the family's best on BOTH
  EV R   = expectancy in R, where 1 R = the average LOSING trade (net $ after cost)
           = (net $ / trades) / |avg losing trade $|
  R / YR = EV R x trades per year   (NOISE trades most of any family, so it is the
           natural R / YR leader — the question is whether a neighbour does better).

TWO REFERENCE CONFIGS, measured first and printed in full:
  CROWN = run #243 (live paper / NT config)
  FRESH = run #305 (PASS 8/8 folds, ~3,744 trades, higher PF)

WINDOW (HARD RULE): NQ 5m RTH master, entries <= 2026-08-12 (run #243's date_to).
  IS  = entries before 2025-08-13 00:00 ET
  LB  = entries from 2025-08-13 through 2026-08-12 (12 months, SPENT: confirmatory
        only, it is a gate leg and never a ranking key)
  Costs 0.533 pts round-turn x $20/pt.  Years = first bar -> 2026-08-12 (~16.18).

PRE-REGISTERED GATE — written BEFORE any cell ran, never changed afterwards.
A cell is a FULL CANDIDATE only if, on the pinned window, ALL of:
  L1  EV R   > max(CROWN EV R,   FRESH EV R)
  L2  R / YR > max(CROWN R / YR, FRESH R / YR)
  L3  lockbox net  >= CROWN lockbox net
  L4  worst rolling-12-month net >= min(CROWN worst, FRESH worst)
        (rolling-12 = tools.orb_hunt3.robustness, monthly step, $ after cost)
SOFT tier: beats BOTH references on one of {EV R, R / YR} while within 10% of the
better reference on the other, AND passes L3 and L4.  Legs are printed per cell.
Nothing is adopted from this file; a FULL candidate goes to a pinned Auto-Validate.

Metrics the engine does NOT attach (NOISE_1_0.run_backtest returns only total_pnl,
num_trades, win_rate, profit_factor, max_drawdown, avg_pnl), so they are computed
here from the trade log: avg_win / avg_loss in $ after cost, Sharpe and Sortino
(daily-PnL, annualised x sqrt(252), trading days with a trade), trades/yr, EV R, R/YR.

Note on knobs: with daytype_mode='skip_bot_short' the engine never reads daytype_hi
(only the skip_top modes do), so the CROWN->FRESH 'daytype_hi' bridge step is a
declared NO-OP and is run only to prove it.

SWEEPS
  A  bridge    CROWN -> FRESH one knob at a time, and FRESH -> CROWN one knob back
  B  confirm   confirm_bars {1,2,3,4} x stop_k {1.0..2.0} x band_mult_short {1,1.25,1.5}
               on the CROWN base
  C  filters   vol_skip_pct {0,80,90,95,99} x daytype_mode {off, skip_bot_short,
               skip_bot_all} x (lo,hi) {(.2,.8),(.25,.6),(.3,.7)} on the FRESH base
               (mode 'off' ignores lo/hi -> one cell per vol_skip_pct)
  D  lookback  lookback {30,36,44,51,60,72,90} x band_mult_long {0.5,0.75,1.0}
               on the FRESH base

    python tools/noise_hunt6.py refs
    python tools/noise_hunt6.py bridge | confirm | filters | lookback | all
Every cell is written to  <scratch>/noise6_<sub>.json  (override with --out DIR).
No runner job is queued, nothing is pushed, no strategy file is created.
"""
import os
import sys
import json
import time
import argparse
import itertools

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, IS_END, LB_END                      # noqa: E402
from tools.orb_hunt3 import robustness                                # noqa: E402

COST, MULT = 0.533, 20.0
STRATEGY = "NOISE_1_0.py"
SOFT_TOL = 0.10

CROWN = {"band_mult_long": 0.75, "band_mult_short": 1.5, "confirm_bars": 1,
         "daytype_hi": 0.8, "daytype_lo": 0.2, "daytype_mode": "skip_bot_short",
         "exit_mode": "vwap", "flat_eod": True, "lookback": 44, "side": "Both",
         "skip_holidays": False, "stop_k": 1.75, "stop_mode": "bandwidth",
         "vol_skip_pct": 90.0, "window": "all_day"}
FRESH = {"band_mult_long": 0.75, "band_mult_short": 1.25, "confirm_bars": 4,
         "daytype_hi": 0.6, "daytype_lo": 0.25, "daytype_mode": "skip_bot_short",
         "exit_mode": "vwap", "flat_eod": True, "lookback": 51, "side": "Both",
         "skip_holidays": False, "stop_k": 1.25, "stop_mode": "bandwidth",
         "vol_skip_pct": 99.0, "window": "all_day"}

DEFAULT_OUT = (r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop"
               r"\a9e4eec9-eca2-494f-9f8f-ef843d44c8b9\scratchpad")

_UP = os.path.join(ROOT, "augur_uploads")
if not os.path.isfile(os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")):
    _UP = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads")
MASTER = os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")

_BARS = None


def bars():
    """Pinned NQ 5m RTH master, cut at LB_END so every cell covers the same span."""
    global _BARS
    if _BARS is None:
        df = pd.read_csv(MASTER, usecols=["time", "open", "high", "low", "close", "volume"])
        dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
        df = df[df["_dt"] < pd.Timestamp(LB_END, tz="US/Eastern")].reset_index(drop=True)
        _BARS = dict(
            open=df["open"].values.astype(float), high=df["high"].values.astype(float),
            low=df["low"].values.astype(float), close=df["close"].values.astype(float),
            volume=df["volume"].values.astype(float),
            day_id=pd.factorize(df["_dt"].dt.date)[0],
            index=pd.DatetimeIndex(df["_dt"]))
        first = _BARS["index"][0].tz_localize(None)
        last = pd.Timestamp(LB_END) - pd.Timedelta(days=1)
        _BARS["years"] = (last - first).days / 365.25
    return _BARS


def _sharpe_sortino(dates, pnl):
    s = pd.Series(pnl, index=pd.DatetimeIndex(dates)).groupby(level=0).sum()
    if len(s) < 2 or s.std(ddof=1) < 1e-9:
        return 0.0, 0.0
    daily = s.values
    sharpe = float(daily.mean() / daily.std(ddof=1) * np.sqrt(252))
    down = daily[daily < 0]
    dd = float(np.sqrt(np.mean(np.square(down)))) if len(down) else 0.0
    sortino = float(daily.mean() / dd * np.sqrt(252)) if dd > 1e-9 else float("inf")
    return sharpe, sortino


def measure(params):
    """One continuous run on the pinned window -> every number the gate and the
    tables need. Returns None when the config produces no trades."""
    b = bars()
    r = strat(STRATEGY).run_backtest(b["open"], b["high"], b["low"], b["close"],
                                     volumes=b["volume"], day_id=b["day_id"],
                                     return_trades=True, **params)
    tr = (r or {}).get("trades") or []
    if not tr:
        return None
    idx = b["index"]
    ie = pd.Timestamp(IS_END, tz=idx.tz)
    dts = [idx[t[0]] for t in tr]
    p = (np.asarray([t[2] for t in tr], float) - COST) * MULT
    n = len(p)
    wins, losses = p[p > 0], p[p < 0]
    gw, gl = float(wins.sum()), float(-losses.sum())
    cum = np.cumsum(p)
    dd = float(abs((cum - np.maximum.accumulate(cum)).min()))
    net = float(p.sum())
    avg_loss = float(-losses.mean()) if len(losses) else float("nan")
    avg_win = float(wins.mean()) if len(wins) else 0.0
    evr = (net / n) / avg_loss if avg_loss > 1e-9 else float("nan")
    tpy = n / b["years"]
    ryr = evr * tpy
    naive = [d.tz_localize(None) for d in dts]
    sharpe, sortino = _sharpe_sortino([d.normalize() for d in naive], p)
    rob = robustness(naive, p)
    is_mask = np.array([d <= ie for d in dts])
    return dict(n=n, net=net, is_net=float(p[is_mask].sum()),
                lb_net=float(p[~is_mask].sum()), lb_n=int((~is_mask).sum()),
                dd=dd, pf=(gw / gl if gl > 1e-9 else float("inf")),
                mar=(net / b["years"]) / dd if dd > 1e-9 else float("inf"),
                wr=100.0 * len(wins) / n, sharpe=sharpe, sortino=sortino,
                avg_win_usd=avg_win, avg_loss_usd=avg_loss, evr=evr,
                trades_per_year=tpy, window_years=b["years"], ryr=ryr,
                roll12_win=rob["win_pct"], roll12_worst=rob["worst"])


# ── the gate ─────────────────────────────────────────────────────────────────────
_REF = {}


def refs():
    """Measure both references once (cached) and derive the gate thresholds."""
    if not _REF:
        c, f = measure(CROWN), measure(FRESH)
        _REF.update(crown=c, fresh=f,
                    evr=max(c["evr"], f["evr"]), ryr=max(c["ryr"], f["ryr"]),
                    lb=c["lb_net"], worst=min(c["roll12_worst"], f["roll12_worst"]))
    return _REF


def judge(m):
    g = refs()
    legs = dict(L1_evr=m["evr"] > g["evr"], L2_ryr=m["ryr"] > g["ryr"],
                L3_lb=m["lb_net"] >= g["lb"], L4_worst=m["roll12_worst"] >= g["worst"])
    full = all(legs.values())
    near_evr = m["evr"] >= g["evr"] * (1 - SOFT_TOL)
    near_ryr = m["ryr"] >= g["ryr"] * (1 - SOFT_TOL)
    soft = (not full) and legs["L3_lb"] and legs["L4_worst"] and (
        (legs["L1_evr"] and near_ryr) or (legs["L2_ryr"] and near_evr))
    return legs, full, soft


# ── printing ─────────────────────────────────────────────────────────────────────
HDR = ("%-34s %5s %9s %8s %8s %6s %5s %6s %6s %7s %7s %6s %8s %5s %s"
       % ("cell", "n", "net", "lb_net", "dd", "pf", "wr", "sharpe", "avgL$",
          "EV R", "R/YR", "r12w%", "r12worst", "gate", "tier"))


def line(name, m, legs=None, full=False, soft=False):
    if m is None:
        return "%-34s   (no trades)" % name
    g = ""
    if legs is not None:
        g = "".join("1" if v else "." for v in legs.values())
    tier = "FULL" if full else ("SOFT" if soft else "")
    return ("%-34s %5d %9.0f %8.0f %8.0f %6.3f %5.1f %6.2f %7.0f %7.4f %7.2f %6.1f %8.0f %5s %s"
            % (name[:34], m["n"], m["net"], m["lb_net"], m["dd"], m["pf"], m["wr"],
               m["sharpe"], m["avg_loss_usd"], m["evr"], m["ryr"], m["roll12_win"],
               m["roll12_worst"], g, tier))


def print_refs():
    g = refs()
    print("REFERENCES (pinned window, entries <= 2026-08-12, cost %.3f pts x $%d, %.2f yrs)"
          % (COST, MULT, bars()["years"]))
    print(HDR)
    for k, p in (("crown", CROWN), ("fresh", FRESH)):
        m = g[k]
        print(line("REF " + k.upper() + " (#%s)" % ("243" if k == "crown" else "305"), m))
        print("    is_net=%.0f lb_n=%d sortino=%.2f avg_win=$%.0f trades/yr=%.1f mar=%.2f"
              % (m["is_net"], m["lb_n"], m["sortino"], m["avg_win_usd"],
                 m["trades_per_year"], m["mar"]))
    print("GATE: EV R > %.4f | R/YR > %.2f | lb_net >= %.0f | roll12 worst >= %.0f"
          % (g["evr"], g["ryr"], g["lb"], g["worst"]))
    print("legs column = L1 EV R, L2 R/YR, L3 lockbox, L4 roll12-worst")


def sweep(sub, cells, out_dir):
    """cells = [(name, params)] -> prints the table, writes the JSON, returns rows."""
    print_refs()
    print("\n=== %s: %d cells ===" % (sub.upper(), len(cells)))
    print(HDR)
    rows = []
    t0 = time.time()
    for i, (name, params) in enumerate(cells, 1):
        try:
            m = measure(params)
            if m is None:
                print(line(name, None), flush=True)
                rows.append(dict(name=name, params=params, error="no trades"))
                continue
            legs, full, soft = judge(m)
            print(line(name, m, legs, full, soft), flush=True)
            rows.append(dict(name=name, params=params, gate_legs=legs, passes=full,
                             soft=soft, **m))
        except Exception as e:                                   # noqa: BLE001
            print("%-34s   ERROR %s" % (name, e), flush=True)
            rows.append(dict(name=name, params=params, error=str(e)))
        if i % 10 == 0:
            print("   ... %d/%d  %.0fs" % (i, len(cells), time.time() - t0), flush=True)
    ok = [r for r in rows if "evr" in r]
    print("\n-- top 10 by R/YR --")
    for r in sorted(ok, key=lambda r: -r["ryr"])[:10]:
        print(line(r["name"], r, r["gate_legs"], r["passes"], r["soft"]))
    print("-- top 10 by EV R --")
    for r in sorted(ok, key=lambda r: -r["evr"])[:10]:
        print(line(r["name"], r, r["gate_legs"], r["passes"], r["soft"]))
    fulls = [r for r in ok if r["passes"]]
    softs = [r for r in ok if r["soft"]]
    print("\nFULL candidates: %d   SOFT: %d" % (len(fulls), len(softs)))
    for r in fulls + softs:
        print("  %s %s -> %s" % ("FULL" if r["passes"] else "SOFT", r["name"],
                                 json.dumps(r["params"], sort_keys=True)))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "noise6_%s.json" % sub)
    g = refs()
    with open(path, "w") as fh:
        json.dump(dict(sub=sub, gate=dict(evr=g["evr"], ryr=g["ryr"], lb=g["lb"],
                                          worst=g["worst"]),
                       refs=dict(crown=dict(params=CROWN, **g["crown"]),
                                 fresh=dict(params=FRESH, **g["fresh"])),
                       cells=rows), fh, indent=1, default=str)
    print("wrote", path)
    return rows


# ── the four sweeps ───────────────────────────────────────────────────────────────
BRIDGE_KNOBS = ["band_mult_short", "confirm_bars", "lookback", "stop_k",
                "vol_skip_pct", "daytype_hi", "daytype_lo"]


def cells_bridge():
    out = []
    for k in BRIDGE_KNOBS:
        vals = [FRESH[k]] if k != "confirm_bars" else [2, 3, 4]
        for v in vals:
            out.append(("C->F %s=%s" % (k, v), dict(CROWN, **{k: v})))
    for k in BRIDGE_KNOBS:
        vals = [CROWN[k]] if k != "confirm_bars" else [3, 2, 1]
        for v in vals:
            out.append(("F->C %s=%s" % (k, v), dict(FRESH, **{k: v})))
    return out


def cells_confirm():
    return [("cb%d sk%.2f bs%.2f" % (cb, sk, bs),
             dict(CROWN, confirm_bars=cb, stop_k=sk, band_mult_short=bs))
            for cb, sk, bs in itertools.product([1, 2, 3, 4],
                                                [1.0, 1.25, 1.5, 1.75, 2.0],
                                                [1.0, 1.25, 1.5])]


def cells_filters():
    out = []
    for vs in [0.0, 80.0, 90.0, 95.0, 99.0]:
        out.append(("vs%.0f off" % vs, dict(FRESH, vol_skip_pct=vs, daytype_mode="off")))
        for mode in ["skip_bot_short", "skip_bot_all"]:
            for lo, hi in [(0.2, 0.8), (0.25, 0.6), (0.3, 0.7)]:
                out.append(("vs%.0f %s lo%.2f hi%.1f" % (vs, mode.replace("skip_bot_", ""), lo, hi),
                            dict(FRESH, vol_skip_pct=vs, daytype_mode=mode,
                                 daytype_lo=lo, daytype_hi=hi)))
    return out


def cells_lookback():
    return [("lb%d bl%.2f" % (lb, bl), dict(FRESH, lookback=lb, band_mult_long=bl))
            for lb, bl in itertools.product([30, 36, 44, 51, 60, 72, 90], [0.5, 0.75, 1.0])]


SUBS = dict(bridge=cells_bridge, confirm=cells_confirm, filters=cells_filters,
            lookback=cells_lookback)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sub", choices=["refs", "all"] + list(SUBS))
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()
    if a.sub == "refs":
        print_refs()
        return
    for sub in (list(SUBS) if a.sub == "all" else [a.sub]):
        sweep(sub, SUBS[sub](), a.out)


if __name__ == "__main__":
    main()
