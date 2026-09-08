"""
ORB ROUND 10b — DIRECTION-RULE fork sweep driver.

Sweeps ORB_3_6_DIR.py's one new knob (dir_rule: which rule decides the allowed side
under trade_mode="First-candle dir") on top of the #314 crown, using the same
run-once-slice-by-date harness as tools/orb_pick.py / orb_hunt10_re.py (trades_of /
stats / sessions), so FULL/IS/OOS/5y windows all see the identical warm-up and filter
history.

    python tools/orb_hunt10_dir.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, IS_END, LB_END          # noqa: E402
from tools.orb_hunt3 import robustness                    # noqa: E402

COST, MULT = 0.533, 20.0
_UP = os.path.join(ROOT, "augur_uploads")
if not os.path.isdir(_UP):
    _UP = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads")
MASTER = os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")

FORK = "ORB_3_6_DIR.py"

# ── the #314 crown, exact params from ROUND10_SPEC.md ─────────────────────────
CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
             partial_exit_R=0, trail_bars=0, flat_eod=True, skip_holidays=True,
             breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
             atr_filter=0.75, vpace_filter=0.8)
CROWN_NET_FULL = 397150.0   # ROUND10_SPEC's crown full-window net$, for G2

IS_START = "2010-06-07"          # earliest bar; IS window is "everything <= IS_END"
OOS_START = IS_END               # "2025-08-13"
FIVE_Y_START = "2021-08-13"

# crown row first, then the 6 new rules ("either" = reference row = trade_mode "Both").
CONFIGS = [
    ("CROWN (first_candle)", "first_candle"),
    ("gap", "gap"),
    ("gap_fade", "gap_fade"),
    ("prior_day", "prior_day"),
    ("prior_day_fade", "prior_day_fade"),
    ("or_vs_prior_close", "or_vs_prior_close"),
    ("either (ref, =Both)", "either"),
]

_B = None


def bars():
    global _B
    if _B is None:
        df = pd.read_csv(MASTER)
        dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
        _B = dict(open=df["open"].values.astype(float), high=df["high"].values.astype(float),
                  low=df["low"].values.astype(float), close=df["close"].values.astype(float),
                  volume=df["volume"].values.astype(float),
                  day_id=pd.factorize(df["_dt"].dt.date)[0],
                  index=pd.DatetimeIndex(df["_dt"]))
    return _B


def trades_of(dir_rule):
    """Run the fork ONCE on the whole master; slice by date afterwards. Returns
    [(entry_datetime, net$, side)] with side in {1: long, -1: short}, entries only
    up to LB_END (the lockbox is never loaded/reported here)."""
    b = bars()
    params = dict(CROWN, dir_rule=dir_rule)
    r = strat(FORK).run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **params)
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    out = []
    for t in (r or {}).get("trades") or []:
        d = idx[t[0]]
        if d > le:
            continue
        out.append((d.tz_localize(None), (t[2] - COST) * MULT, t[3]))
    return out


def sessions():
    b = bars()
    idx = b["index"]
    return pd.Series(idx.date).drop_duplicates().values


def stats(tr, start, end, all_days):
    """tr = [(entry_datetime, net$)] already inside the window."""
    if len(tr) < 5:
        return None
    dts = [d for d, _ in tr]
    p = np.array([x for _, x in tr], float)
    yrs = (dts[-1] - dts[0]).days / 365.25
    if yrs <= 0:
        yrs = max((pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25, 1e-6)
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    wins, losses = p[p > 0], p[p < 0]
    al = abs(losses.mean()) if len(losses) else np.nan
    evr = p.mean() / al if al == al and al > 0 else np.nan
    try:
        rob = robustness(dts, list(p))
        worst12, win12 = rob["worst"], rob["win_pct"]
    except Exception:
        worst12, win12 = np.nan, np.nan
    return dict(n=len(p), net=p.sum(), dd=dd,
                pf=(wins.sum() / abs(losses.sum())) if len(losses) else np.inf,
                mar=(p.sum() / yrs) / dd if dd else np.nan,
                evr=evr, ryr=(evr * len(p) / yrs) if (yrs > 0 and evr == evr) else np.nan,
                tpy=len(p) / yrs if yrs > 0 else np.nan,
                worst12=worst12, win12=win12)


def side_split(tr, side):
    p = np.array([v for _, v, s in tr if s == side], float)
    if len(p) == 0:
        return dict(n=0, net=0.0, pf=np.nan)
    w, l = p[p > 0], p[p < 0]
    return dict(n=len(p), net=float(p.sum()),
                pf=(w.sum() / abs(l.sum())) if len(l) else np.inf)


def fmt_row(lab, s):
    if s is None:
        return "%-22s %6s %10s %9s %6s %6s %6s %6s %6s %9s %5s" % (
            lab, "-", "-", "-", "-", "-", "-", "-", "-", "-", "-")
    return "%-22s %6d %10s %9s %6.3f %6.2f %6.3f %6.1f %6.0f %9s %5.1f" % (
        lab, s["n"], f"{s['net']:,.0f}", f"{s['dd']:,.0f}", s["pf"], s["mar"],
        s["evr"], s["ryr"], s["tpy"], f"{s['worst12']:,.0f}", s["win12"])


HEADER = ("%-22s %6s %10s %9s %6s %6s %6s %6s %6s %9s %5s"
          % ("config", "n", "net$", "maxDD$", "PF", "MAR", "EV R", "R/YR", "tr/yr", "worst12", "win12%"))


def main():
    all_days = sessions()
    print("=" * 116)
    print("ORB ROUND 10b - DIRECTION-RULE sweep (ORB_3_6_DIR.py) on the #314 crown")
    print("  master NQ 5m RTH no-adj, 0.533 pts/RT, one contract, entries to %s" % LB_END)
    print("=" * 116)

    cache = {}
    for lab, dr in CONFIGS:
        cache[lab] = trades_of(dr)

    windows = [
        ("FULL  (<= %s)" % LB_END, IS_START, LB_END),
        ("IS    (<= %s)" % IS_END, IS_START, IS_END),
        ("OOS   (%s .. %s)" % (OOS_START, LB_END), OOS_START, LB_END),
        ("5-YEAR (from %s)" % FIVE_Y_START, FIVE_Y_START, LB_END),
    ]

    results = {}   # lab -> window_name -> stats
    for wname, wstart, wend in windows:
        print("\n" + "-" * 116)
        print(wname)
        print("-" * 116)
        print(HEADER)
        print("-" * 116)
        s0 = pd.Timestamp(wstart)
        e0 = pd.Timestamp(wend)
        for lab, dr in CONFIGS:
            tr = [(d, v) for d, v, _ in cache[lab] if s0 <= d <= e0]
            s = stats(tr, wstart, wend, all_days)
            results.setdefault(lab, {})[wname] = s
            print(fmt_row(lab, s))

    full_name, is_name, oos_name, five_y_name = [w[0] for w in windows]

    # ── per-side split, FULL and 5y, every rule ────────────────────────────────
    print("\n" + "=" * 116)
    print("PER-SIDE SPLIT (longs vs shorts), FULL and 5-YEAR windows")
    print("=" * 116)
    print("%-22s | %-28s | %-28s" % ("config", "FULL longs / shorts", "5y longs / shorts"))
    for lab, dr in CONFIGS:
        full_tr = cache[lab]
        y5_tr = [(d, v, s) for d, v, s in full_tr if pd.Timestamp(FIVE_Y_START) <= d]
        fl, fs = side_split(full_tr, 1), side_split(full_tr, -1)
        yl, ys = side_split(y5_tr, 1), side_split(y5_tr, -1)
        print("%-22s | L n=%4d $%9s PF%5.2f | S n=%4d $%9s PF%5.2f || 5y L n=%3d $%8s PF%5.2f | S n=%3d $%8s PF%5.2f"
              % (lab, fl["n"], f"{fl['net']:,.0f}", fl["pf"], fs["n"], f"{fs['net']:,.0f}", fs["pf"],
                 yl["n"], f"{yl['net']:,.0f}", yl["pf"], ys["n"], f"{ys['net']:,.0f}", ys["pf"]))

    # ── best-other-rule pick (by 5y MAR) for the per-year regime check ────────
    scored = [(lab, results[lab][five_y_name]["mar"]) for lab, dr in CONFIGS
              if dr != "first_candle" and results[lab][five_y_name] is not None]
    crown_mar5y = results["CROWN (first_candle)"][five_y_name]["mar"] if results["CROWN (first_candle)"][five_y_name] else None
    best_lab, best_mar5y = (max(scored, key=lambda x: x[1]) if scored else (None, None))

    # ── per-year net table: first_candle vs best other rule ────────────────────
    print("\n" + "=" * 116)
    print("PER-YEAR NET$: first_candle (crown) vs best other rule by 5y MAR (%s)"
          % (best_lab or "n/a"))
    print("=" * 116)
    crown_tr = cache["CROWN (first_candle)"]
    crown_y = pd.Series([v for _, v, _ in crown_tr],
                         index=pd.DatetimeIndex([d for d, _, _ in crown_tr])).groupby(
        pd.DatetimeIndex([d for d, _, _ in crown_tr]).year).sum()
    if best_lab:
        best_tr = cache[best_lab]
        best_y = pd.Series([v for _, v, _ in best_tr],
                            index=pd.DatetimeIndex([d for d, _, _ in best_tr])).groupby(
            pd.DatetimeIndex([d for d, _, _ in best_tr]).year).sum()
        years = sorted(set(crown_y.index) | set(best_y.index))
        print("%-6s %14s %14s %14s" % ("year", "first_candle$", best_lab[:14] + "$", "delta$"))
        for y in years:
            cv = crown_y.get(y, 0.0); bv = best_y.get(y, 0.0)
            print("%-6d %14s %14s %14s" % (y, f"{cv:,.0f}", f"{bv:,.0f}", f"{bv - cv:,.0f}"))
    else:
        print("No scored alternative rule.")

    # ── gate check table (G1/G2/G3/G5; G4 plateau discussed below — dir_rule is
    #    a single CATEGORICAL knob with no numeric neighbours, so the usual
    #    "immediate neighbour" plateau check does not apply here; instead we
    #    require the winning rule to ALSO beat the crown split by split, i.e.
    #    IS AND OOS both individually beat the crown's IS/OOS MAR — the closest
    #    honest analogue of "not a single lucky configuration"). ──────────────
    print("\n" + "=" * 116)
    print("GATE CHECK  (G1 5yMAR>%.2f & fullMAR>0.85 | G2 net>=95%%*$%.0f | G3 OOS net/PF>=crown | G5 tr/yr>=120)"
          % (crown_mar5y or 0, CROWN_NET_FULL))
    print("G4 (plateau): dir_rule is a single CATEGORICAL knob (no numeric neighbours) — substituted")
    print("  with an IS-AND-OOS-both-beat-crown consistency check (see per-rule note below).")
    print("=" * 116)
    crown_full = results["CROWN (first_candle)"][full_name]
    crown_oos = results["CROWN (first_candle)"][oos_name]
    crown_is = results["CROWN (first_candle)"][is_name]
    for lab, dr in CONFIGS:
        if dr == "first_candle":
            continue
        f = results[lab][full_name]; y5 = results[lab][five_y_name]
        o = results[lab][oos_name]; isw = results[lab][is_name]
        if not (f and y5 and o and isw):
            print("%-22s INSUFFICIENT DATA" % lab); continue
        fails = []
        if not (y5["mar"] > crown_mar5y):
            fails.append("G1(5yMAR %.2f<=%.2f)" % (y5["mar"], crown_mar5y))
        if not (f["mar"] > 0.85):
            fails.append("G1(fullMAR %.2f<=0.85)" % f["mar"])
        if not (f["net"] >= 0.95 * CROWN_NET_FULL):
            fails.append("G2(net %.0f<95%%*%.0f)" % (f["net"], CROWN_NET_FULL))
        if not (o["net"] >= crown_oos["net"]):
            fails.append("G3(OOSnet %.0f<%.0f)" % (o["net"], crown_oos["net"]))
        if not (o["pf"] >= crown_oos["pf"]):
            fails.append("G3(OOSpf %.3f<%.3f)" % (o["pf"], crown_oos["pf"]))
        if not (f["tpy"] >= 120):
            fails.append("G5(tr/yr %.0f<120)" % f["tpy"])
        g4_note = "consistent" if (isw["mar"] > crown_is["mar"] and o["mar"] > crown_oos["mar"]) else "NOT consistent (IS/OOS split)"
        print("%-22s %s   [G4: %s]" % (lab, "PASS" if not fails else "FAIL: " + "; ".join(fails), g4_note))


if __name__ == "__main__":
    main()
