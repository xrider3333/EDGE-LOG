"""
ORB ROUND 10 — FAILED-BREAKOUT REVERSAL ("trap trade") fork sweep driver.

Sweeps ORB_3_6_REV.py's new knobs (reverse_after_stop, reverse_after_be,
rev_stop_frac, rev_target_R) on top of the #314 crown, using the same
run-once-slice-by-date harness as tools/orb_pick.py (trades_of / stats /
sessions), so FULL/IS/OOS/5y windows all see the identical warm-up and filter
history. Also prints the reversal ("trap") trades' OWN stats separately, using
the fork's native "trades_rev" output (no slot-guessing needed).

    python tools/orb_hunt10_rev.py
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

FORK = "ORB_3_6_REV.py"

# ── the #314 crown, exact params from ROUND10_SPEC.md ─────────────────────────
CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
             partial_exit_R=0, trail_bars=0, flat_eod=True, skip_holidays=True,
             breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
             atr_filter=0.75, vpace_filter=0.8)

IS_START = "2010-06-07"          # earliest bar; IS window is "everything <= IS_END"
OOS_START = IS_END               # "2025-08-13"
FIVE_Y_START = "2021-08-13"

# 12 sweep configs (2 x 3 x 2) + the crown (reverse_after_stop=False) = 13 rows.
# rev_direct is NOT implemented this round (see ORB_3_6_REV.py docstring), so no
# rev_direct=True rows are added — per spec: "skip this if it makes the code messy".
CONFIGS = [("CROWN (rev off)", dict(reverse_after_stop=False))]
for rafter_be in (False, True):
    for rsf in (0, 1.5, 2.0):
        for rtR in (0, 3.0):
            lab = "rev/be=%s/sf=%s/tR=%s" % (rafter_be, rsf, rtR)
            CONFIGS.append((lab, dict(reverse_after_stop=True, reverse_after_be=rafter_be,
                                       rev_stop_frac=rsf, rev_target_R=rtR)))

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
    """Run the fork ONCE on the whole master; slice by date afterwards. Returns
    (all_trades, rev_trades) — both lists of (entry_datetime, net$), the second
    being ONLY the reversal ("trap") trades, via the fork's native trades_rev."""
    b = bars()
    params = dict(CROWN, **over)
    r = strat(FORK).run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **params)
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    rev_keys = set()
    for t in (r or {}).get("trades_rev") or []:
        rev_keys.add((t[0], t[1], t[3], round(t[4], 6)))
    out, rev_out = [], []
    for t in (r or {}).get("trades") or []:
        d = idx[t[0]]
        if d > le:
            continue
        pnl = (t[2] - COST) * MULT
        out.append((d.tz_localize(None), pnl))
        if (t[0], t[1], t[3], round(t[4], 6)) in rev_keys:
            rev_out.append((d.tz_localize(None), pnl))
    return out, rev_out


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
                worst12=worst12, win12=win12,
                win_rate=100.0 * len(wins) / len(p))


def fmt_row(lab, s):
    if s is None:
        return "%-24s %6s %10s %9s %6s %6s %6s %6s %6s %9s %5s" % (
            lab, "-", "-", "-", "-", "-", "-", "-", "-", "-", "-")
    return "%-24s %6d %10s %9s %6.3f %6.2f %6.3f %6.1f %6.0f %9s %5.1f" % (
        lab, s["n"], f"{s['net']:,.0f}", f"{s['dd']:,.0f}", s["pf"], s["mar"],
        s["evr"], s["ryr"], s["tpy"], f"{s['worst12']:,.0f}", s["win12"])


HEADER = ("%-24s %6s %10s %9s %6s %6s %6s %6s %6s %9s %5s"
          % ("config", "n", "net$", "maxDD$", "PF", "MAR", "EV R", "R/YR", "tr/yr", "worst12", "win12%"))


def main():
    all_days = sessions()
    print("=" * 118)
    print("ORB ROUND 10 - FAILED-BREAKOUT REVERSAL sweep (ORB_3_6_REV.py) on the #314 crown")
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

    results = {}   # lab -> window_name -> stats (on the FULL trade set, first+rev combined)
    for wname, wstart, wend in windows:
        print("\n" + "-" * 118)
        print(wname)
        print("-" * 118)
        print(HEADER)
        print("-" * 118)
        s0 = pd.Timestamp(wstart)
        e0 = pd.Timestamp(wend)
        for lab, over in CONFIGS:
            tr_all, _ = cache[lab]
            tr = [(d, v) for d, v in tr_all if s0 <= d <= e0]
            s = stats(tr, wstart, wend, all_days)
            results.setdefault(lab, {})[wname] = s
            print(fmt_row(lab, s))

    # ── plateau read on the best config (by 5y MAR) ────────────────────────────
    five_y_name = windows[3][0]
    crown_mar5y = results["CROWN (rev off)"][five_y_name]["mar"] if results["CROWN (rev off)"][five_y_name] else None
    scored = [(lab, results[lab][five_y_name]["mar"]) for lab, _ in CONFIGS
              if lab != "CROWN (rev off)" and results[lab][five_y_name] is not None]
    print("\n" + "=" * 118)
    if scored:
        best_lab, best_mar5y = max(scored, key=lambda x: x[1])
        print("BEST by 5y MAR: %s  (MAR %.2f vs crown %.2f)" % (best_lab, best_mar5y, crown_mar5y))
        best_over = dict(CONFIGS)[best_lab]
        gain = best_mar5y - crown_mar5y
        rafter_be0, rsf0, rtR0 = best_over["reverse_after_be"], best_over["rev_stop_frac"], best_over["rev_target_R"]
        neigh = []
        for nv in ({False, True} - {rafter_be0}):
            neigh.append(dict(best_over, reverse_after_be=nv))
        for nv in ({0, 1.5, 2.0} - {rsf0}):
            neigh.append(dict(best_over, rev_stop_frac=nv))
        for nv in ({0, 3.0} - {rtR0}):
            neigh.append(dict(best_over, rev_target_R=nv))
        plateau_ok = True
        print("Plateau check (immediate neighbours must keep >=70%% of the 5y MAR gain over crown):")
        for nover in neigh:
            match = [l for l, o in CONFIGS if o.get("reverse_after_stop", False)
                     and o.get("reverse_after_be") == nover.get("reverse_after_be")
                     and o.get("rev_stop_frac") == nover.get("rev_stop_frac")
                     and o.get("rev_target_R") == nover.get("rev_target_R")]
            if not match:
                continue
            nl = match[0]
            nmar = results[nl][five_y_name]["mar"] if results[nl][five_y_name] else None
            if nmar is None or gain <= 0:
                keep = None
            else:
                keep = (nmar - crown_mar5y) / gain
            print("  %-24s 5y MAR %s  keep=%s" % (
                nl, ("%.2f" % nmar) if nmar is not None else "n/a",
                ("%.0f%%" % (keep * 100)) if keep is not None else "n/a"))
            if keep is None or keep < 0.70:
                plateau_ok = False
        print("PLATEAU: %s" % ("PASS" if plateau_ok else "NOT PLATEAU"))

        # ── separate reversal ("trap") trade stats for the best config ─────────
        _, best_rev = cache[best_lab]
        print("\nREVERSAL ('trap') TRADES ONLY (best config = %s, full window <= %s):" % (best_lab, LB_END))
        if best_rev:
            rp = np.array([v for _, v in best_rev], float)
            rw, rl = rp[rp > 0], rp[rp < 0]
            print("  n=%d  net=$%s  PF=%.3f  win%%=%.1f  avg=$%.0f" % (
                len(rp), f"{rp.sum():,.0f}",
                (rw.sum() / abs(rl.sum())) if len(rl) else np.inf,
                100 * len(rw) / len(rp), rp.mean()))
        else:
            print("  n=0 (no reversal trades fired in-window)")

        # ── reversal-only stats for EVERY sweep config (own-edge read) ─────────
        print("\nREVERSAL TRADES ONLY, ALL CONFIGS (full window <= %s):" % LB_END)
        print("%-24s %6s %10s %6s %6s" % ("config", "n", "net$", "PF", "win%"))
        for lab, over in CONFIGS:
            _, rev_tr = cache[lab]
            if not rev_tr:
                print("%-24s %6d %10s %6s %6s" % (lab, 0, "-", "-", "-"))
                continue
            rp = np.array([v for _, v in rev_tr], float)
            rw, rl = rp[rp > 0], rp[rp < 0]
            print("%-24s %6d %10s %6.3f %6.1f" % (
                lab, len(rp), f"{rp.sum():,.0f}",
                (rw.sum() / abs(rl.sum())) if len(rl) else np.inf,
                100 * len(rw) / len(rp)))
    else:
        print("No scored configs.")

    # ── gate check table ────────────────────────────────────────────────────────
    print("\n" + "=" * 118)
    print("GATE CHECK  (G1 5y MAR>%.2f & full MAR>0.85 | G2 net>=95%% of $397,150 | G3 OOS net/PF>=crown | G5 tr/yr>=120)"
          % (crown_mar5y or 0))
    print("=" * 118)
    full_name, oos_name = windows[0][0], windows[2][0]
    crown_full = results["CROWN (rev off)"][full_name]
    crown_oos = results["CROWN (rev off)"][oos_name]
    for lab, over in CONFIGS:
        f = results[lab][full_name]; y5 = results[lab][five_y_name]; o = results[lab][oos_name]
        if not (f and y5 and o):
            print("%-24s INSUFFICIENT DATA" % lab); continue
        fails = []
        if not (y5["mar"] > crown_mar5y):
            fails.append("G1(5yMAR %.2f<=%.2f)" % (y5["mar"], crown_mar5y))
        if not (f["mar"] > 0.85):
            fails.append("G1(fullMAR %.2f<=0.85)" % f["mar"])
        if not (f["net"] >= 0.95 * 397150):
            fails.append("G2(net %.0f<95%%*397150)" % f["net"])
        if not (o["net"] >= crown_oos["net"]):
            fails.append("G3(OOSnet %.0f<%.0f)" % (o["net"], crown_oos["net"]))
        if not (o["pf"] >= crown_oos["pf"]):
            fails.append("G3(OOSpf %.3f<%.3f)" % (o["pf"], crown_oos["pf"]))
        if not (f["tpy"] >= 120):
            fails.append("G5(tr/yr %.0f<120)" % f["tpy"])
        print("%-24s %s" % (lab, "PASS" if not fails else "FAIL: " + "; ".join(fails)))


if __name__ == "__main__":
    main()
