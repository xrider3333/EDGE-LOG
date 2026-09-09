"""
ORB ROUND 11 - SCL (adaptive stop/target scaling) fork sweep driver.

Sweeps ORB_3_6_SCL.py's four new knobs (scl_mode, scl_strength, scl_ref_days, scl_clip)
on top of the #314 crown, using the same run-once-slice-by-date harness as
tools/orb_pick.py (trades_of / stats / sessions), so FULL/IS/OOS/5y windows all
see the identical warm-up and filter history.

    python tools/orb_hunt11_scl.py
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

FORK = "ORB_3_6_SCL.py"

# ── the #314 crown, exact params from ROUND11_SPEC.md ─────────────────────────
CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
             partial_exit_R=0, trail_bars=0, flat_eod=True, skip_holidays=True,
             breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
             atr_filter=0.75, vpace_filter=0.8)

IS_START = "2010-06-07"          # earliest bar; IS window is "everything <= IS_END"
OOS_START = IS_END               # "2025-08-13"
FIVE_Y_START = "2021-08-13"

CROWN_NET_REF = 397150.0         # spec G2 reference (crown's full-window net$)

# ── grid: scl_mode x scl_strength x scl_ref_days (scl_clip held at default 0.5) ──
CONFIGS = [("CROWN (scl=off)", dict(scl_mode="off"))]
for mode in ("stop", "target", "both"):
    for strength in (-1.0, -0.5, -0.25, 0.25, 0.5, 1.0):
        for ref_days in (10, 20, 40):
            lab = "scl=%s/%+.2f/rd%d" % (mode, strength, ref_days)
            CONFIGS.append((lab, dict(scl_mode=mode, scl_strength=strength, scl_ref_days=ref_days)))

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


def trades_of(over):
    """Run the fork ONCE on the whole master; slice by date afterwards."""
    b = bars()
    params = dict(CROWN, **over)
    r = strat(FORK).run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **params)
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    out = []
    for t in (r or {}).get("trades") or []:
        d = idx[t[0]]
        if d <= le:
            out.append((d.tz_localize(None), (t[2] - COST) * MULT))
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


def fmt_row(lab, s):
    if s is None:
        return "%-24s %6s %10s %9s %6s %6s %6s %6s %6s %9s %5s" % (
            lab, "-", "-", "-", "-", "-", "-", "-", "-", "-", "-")
    return "%-24s %6d %10s %9s %6.3f %6.2f %6.3f %6.1f %6.0f %9s %5.1f" % (
        lab, s["n"], f"{s['net']:,.0f}", f"{s['dd']:,.0f}", s["pf"], s["mar"],
        s["evr"], s["ryr"], s["tpy"], f"{s['worst12']:,.0f}", s["win12"])


HEADER = ("%-24s %6s %10s %9s %6s %6s %6s %6s %6s %9s %5s"
          % ("config", "n", "net$", "maxDD$", "PF", "MAR", "EV R", "R/YR", "tr/yr", "worst12", "win12%"))


def parse_lab(lab):
    """CROWN or 'scl=<mode>/<+strength>/rd<days>' -> (mode, strength, ref_days) or None."""
    if lab.startswith("CROWN"):
        return None
    body = lab[len("scl="):]
    mode, strength_s, rd_s = body.split("/")
    return mode, float(strength_s), int(rd_s.replace("rd", ""))


def diagnostic_decile_table(all_days):
    """Bucket the crown's own trades by ratio decile (today's OR width vs its trailing
    20-day median reference) on the 5-year window. Not required by the spec - shows
    whether the flex has anything to bite on regardless of what the sweep finds."""
    b = bars()
    idx = b["index"]
    day_id = b["day_id"]
    sess_bounds = []
    a = 0
    n = len(day_id)
    while a < n:
        bb = a
        while bb < n and day_id[bb] == day_id[a]:
            bb += 1
        sess_bounds.append((a, bb)); a = bb

    or_bars = CROWN["or_bars"]
    h, l = b["high"], b["low"]
    or_w = np.full(len(sess_bounds), np.nan)
    for si, (a2, b2) in enumerate(sess_bounds):
        if (b2 - a2) > or_bars and or_bars >= 1:
            or_w[si] = h[a2:a2 + or_bars].max() - l[a2:a2 + or_bars].min()

    ratio_by_a = {}
    ref_days = 20
    for si, (a2, b2) in enumerate(sess_bounds):
        if si < 1 or not (or_w[si] == or_w[si]) or or_w[si] <= 0:
            continue
        lookback = or_w[max(0, si - ref_days):si]
        lookback = lookback[lookback == lookback]
        if len(lookback) < 3:
            continue
        ref = np.median(lookback)
        if ref > 0:
            ratio_by_a[a2] = or_w[si] / ref

    crown_trades = trades_of({})       # [(entry_dt, net$)] full window <= LB_END
    fy_start = pd.Timestamp(FIVE_Y_START)
    lb_end = pd.Timestamp(LB_END)

    # map each trade's entry datetime back to its session-start index a to fetch ratio
    idx_naive = idx.tz_localize(None)
    a_of_dt = {}
    for si, (a2, b2) in enumerate(sess_bounds):
        a_of_dt[idx_naive[a2].normalize()] = a2

    rows = []
    for d, v in crown_trades:
        if not (fy_start <= d <= lb_end):
            continue
        a2 = a_of_dt.get(d.normalize())
        ratio = ratio_by_a.get(a2) if a2 is not None else None
        rows.append((ratio, v))

    have_ratio = [(r, v) for r, v in rows if r is not None]
    print("\n" + "=" * 118)
    print("DIAGNOSTIC (not required by spec): crown trades bucketed by OR-width ratio decile")
    print("  (today's opening-range width / trailing 20-session median), 5-year window (%s..%s)"
          % (FIVE_Y_START, LB_END))
    print("=" * 118)
    if len(have_ratio) < 20:
        print("  too few trades with a computable ratio (%d) - skipping" % len(have_ratio))
        return
    ratios = np.array([r for r, _ in have_ratio], float)
    vals = np.array([v for _, v in have_ratio], float)
    edges = np.quantile(ratios, np.linspace(0, 1, 11))
    edges[0] -= 1e-9; edges[-1] += 1e-9
    print("%-8s %6s %10s %10s %6s %6s %8s %8s" % ("decile", "n", "net$", "avg$", "PF", "EV R", "ratio_lo", "ratio_hi"))
    print("-" * 78)
    for dnum in range(10):
        lo, hi = edges[dnum], edges[dnum + 1]
        m = (ratios >= lo) & (ratios <= hi) if dnum == 9 else (ratios >= lo) & (ratios < hi)
        pv = vals[m]
        if len(pv) == 0:
            print("%-8s %6d %10s %10s %6s %6s %8.3f %8.3f" % ("D%d" % (dnum + 1), 0, "-", "-", "-", "-", lo, hi))
            continue
        w, ls = pv[pv > 0], pv[pv < 0]
        pf = (w.sum() / abs(ls.sum())) if len(ls) else float("inf")
        al = abs(ls.mean()) if len(ls) else np.nan
        evr = pv.mean() / al if al == al and al > 0 else np.nan
        print("%-8s %6d %10s %10s %6.3f %6.3f %8.3f %8.3f" % (
            "D%d" % (dnum + 1), len(pv), f"{pv.sum():,.0f}", f"{pv.mean():,.0f}", pf, evr, lo, hi))
    print("D1 = narrowest opening range relative to its 20-day norm, D10 = widest.")


def main():
    all_days = sessions()
    print("=" * 118)
    print("ORB ROUND 11 - SCL (adaptive stop/target scaling) sweep (ORB_3_6_SCL.py) on the #314 crown")
    print("  master NQ 5m RTH no-adj, 0.533 pts/RT, one contract, entries to %s" % LB_END)
    print("=" * 118)

    cache = {}
    for lab, over in CONFIGS:
        cache[lab] = trades_of(over)

    windows = [
        ("FULL  (<= %s)" % LB_END, IS_START, LB_END),
        ("IS    (<= %s)" % IS_END, IS_START, IS_END),
        ("OOS   (%s .. %s)" % (OOS_START, LB_END), OOS_START, LB_END),
        ("5-YEAR (from %s)" % FIVE_Y_START, FIVE_Y_START, LB_END),
    ]

    results = {}   # lab -> window_name -> stats
    for wname, wstart, wend in windows:
        print("\n" + "-" * 118)
        print(wname)
        print("-" * 118)
        print(HEADER)
        print("-" * 118)
        s0 = pd.Timestamp(wstart)
        e0 = pd.Timestamp(wend)
        for lab, over in CONFIGS:
            tr = [(d, v) for d, v in cache[lab] if s0 <= d <= e0]
            s = stats(tr, wstart, wend, all_days)
            results.setdefault(lab, {})[wname] = s
            print(fmt_row(lab, s))

    # ── plateau read on the best config (by 5y MAR) ────────────────────────────
    five_y_name = windows[3][0]
    crown_lab = "CROWN (scl=off)"
    crown_mar5y = results[crown_lab][five_y_name]["mar"] if results[crown_lab][five_y_name] else None
    scored = [(lab, results[lab][five_y_name]["mar"]) for lab, _ in CONFIGS
              if lab != crown_lab and results[lab][five_y_name] is not None]
    print("\n" + "=" * 118)
    if scored:
        best_lab, best_mar5y = max(scored, key=lambda x: x[1])
        print("BEST by 5y MAR: %s  (MAR %.2f vs crown %.2f)" % (best_lab, best_mar5y, crown_mar5y))
        best_mode, best_strength, best_rd = parse_lab(best_lab)
        gain = best_mar5y - crown_mar5y
        # immediate neighbours: +/- one step on strength grid, +/- one step on ref_days grid
        strength_grid = [-1.0, -0.5, -0.25, 0.25, 0.5, 1.0]
        rd_grid = [10, 20, 40]
        s_i = strength_grid.index(best_strength)
        rd_i = rd_grid.index(best_rd)
        neigh_keys = set()
        if s_i > 0:
            neigh_keys.add((best_mode, strength_grid[s_i - 1], best_rd))
        if s_i < len(strength_grid) - 1:
            neigh_keys.add((best_mode, strength_grid[s_i + 1], best_rd))
        if rd_i > 0:
            neigh_keys.add((best_mode, best_strength, rd_grid[rd_i - 1]))
        if rd_i < len(rd_grid) - 1:
            neigh_keys.add((best_mode, best_strength, rd_grid[rd_i + 1]))
        plateau_ok = True
        print("Plateau check (immediate neighbours must keep >=70%% of the 5y MAR gain over crown):")
        if not neigh_keys:
            print("  (best config sits at a grid edge on every knob - no interior neighbour to check)")
            plateau_ok = False
        for nmode, nstrength, nrd in neigh_keys:
            nlab = "scl=%s/%+.2f/rd%d" % (nmode, nstrength, nrd)
            nmar = results.get(nlab, {}).get(five_y_name, {})
            nmar = nmar["mar"] if nmar else None
            if nmar is None or gain <= 0:
                keep = None
            else:
                keep = (nmar - crown_mar5y) / gain
            print("  %-24s 5y MAR %s  keep=%s" % (
                nlab, ("%.2f" % nmar) if nmar is not None else "n/a",
                ("%.0f%%" % (keep * 100)) if keep is not None else "n/a"))
            if keep is None or keep < 0.70:
                plateau_ok = False
        print("PLATEAU: %s" % ("PASS" if plateau_ok else "NOT PLATEAU"))
    else:
        print("No scored configs.")
        best_lab = None

    # ── gate check table ────────────────────────────────────────────────────────
    print("\n" + "=" * 118)
    print("GATE CHECK  (G1 5yMAR>%.2f & fullMAR>0.85 | G2 net>=95%% of $%.0f | G3 OOS net/PF>=crown | G5 tr/yr>=120)"
          % (crown_mar5y or 0, CROWN_NET_REF))
    print("=" * 118)
    full_name, oos_name = windows[0][0], windows[2][0]
    crown_full = results[crown_lab][full_name]
    crown_oos = results[crown_lab][oos_name]
    for lab, over in CONFIGS:
        f = results[lab][full_name]; y5 = results[lab][five_y_name]; o = results[lab][oos_name]
        if not (f and y5 and o):
            print("%-24s INSUFFICIENT DATA" % lab); continue
        fails = []
        if lab != crown_lab:
            if not (y5["mar"] > crown_mar5y):
                fails.append("G1(5yMAR %.2f<=%.2f)" % (y5["mar"], crown_mar5y))
        if not (f["mar"] > 0.85):
            fails.append("G1(fullMAR %.2f<=0.85)" % f["mar"])
        if not (f["net"] >= 0.95 * CROWN_NET_REF):
            fails.append("G2(net %.0f<95%%*%.0f)" % (f["net"], CROWN_NET_REF))
        if lab != crown_lab:
            if not (o["net"] >= crown_oos["net"]):
                fails.append("G3(OOSnet %.0f<%.0f)" % (o["net"], crown_oos["net"]))
            if not (o["pf"] >= crown_oos["pf"]):
                fails.append("G3(OOSpf %.3f<%.3f)" % (o["pf"], crown_oos["pf"]))
        if not (f["tpy"] >= 120):
            fails.append("G5(tr/yr %.0f<120)" % f["tpy"])
        g4 = ""
        if best_lab is not None and lab == best_lab:
            g4 = " | G4:%s" % ("PASS" if plateau_ok else "NOT PLATEAU")
            if not plateau_ok:
                fails.append("G4(not plateau)")
        print("%-24s %s%s" % (lab, "PASS" if not fails else "FAIL: " + "; ".join(fails), g4))

    diagnostic_decile_table(all_days)


if __name__ == "__main__":
    main()
