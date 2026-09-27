"""Round 18b - the BEFORE / AFTER numbers for the staged TTM switch (MANAGER, owner 2026-09-27).

Two changes are staged, neither flipped:
  1. the book leg moves from run #369 (raw ES 30m) to the ROLL-GUARDED file TTMSQZ_3_0_ES30SSOF2R.py -
     at #369's own cell (entry cutoff 1) or at run #428's crowned cell (entry cutoff 5);
  2. the book sizes it 3 / 4 / 7 whole ES contracts (base / one tilt / both tilts) instead of a flat
     3 x the 1.0 / 1.5 / 2.25 ladder (ideal 3 / 4.5 / 6.75), per round 18a.

Leg-level: every variant on the pinned window, cost 0.363 per contract, $50 a point. Book-level: the
PAPER BOOK FIGURE's own composition (ORB 234 + ENGU-Q 309 at one NQ contract each, cached daily P&L
from tools/ttmsqz_round8_crown.py) with only the TTM leg varied, so the difference is the TTM change
alone. The NQ legs are on the raw masters too (the roll audit puts ENGU-Q about 17 percent lower on
back-adjusted data); holding them fixed isolates the TTM change and says nothing about them.

Per-trade size is recovered from the trade itself: the file returns points NET of the engine's single
cost subtraction, and a trade sized s is worth s*(raw - cost), so s = pnl / (raw - cost), snapped to
1.0 / 1.5 / 2.25. The same recovery is what the staged book switch in api/paper.py does.

Log: tools/data/ttmsqz_r18b_stage_numbers.txt
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"   # masters and the run registry live here
sys.path.insert(0, SHARED)
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest

r8 = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("r8", os.path.join(SHARED, "tools", "ttmsqz_round8_crown.py")))
r8.__spec__.loader.exec_module(r8)

COST, MULT, YRS, LB_FROM = 0.363, 50.0, 16.06, "2025-07-01"
LADDER = {1.0: 3, 1.5: 4, 2.25: 7}
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r18b_stage_numbers.txt")


def snap(s):
    return min(LADDER, key=lambda k: abs(k - s))


def leg_trades(fn, eod):
    arr = load_master_arrays(find_master("ES", "30m", "rth"), date_from="2010-06-07", date_to="2026-06-30")
    r = run_backtest(fn, arrays=arr, params=dict(kc_mult=1.5, eod_cutoff=eod), cost_pts=COST, return_trades=True)
    ix = pd.DatetimeIndex(arr["index"])
    rows = []
    for t in r["trades"]:
        eb, xb, pts, side, epx, xpx = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4]), float(t[5])
        raw = side * (xpx - epx)
        s = snap(pts / (raw - COST)) if abs(raw - COST) > 1e-9 else 1.0
        rows.append((ix[xb].tz_localize(None).normalize() if ix.tz is not None else ix[xb].normalize(),
                     pts, raw, s))
    return pd.DataFrame(rows, columns=["date", "pts", "raw", "s"])


def usd(df, mode):
    if mode == "x3":
        return df["pts"].to_numpy() * MULT * 3.0
    c = df["s"].map(LADDER).to_numpy()
    return c * (df["raw"].to_numpy() - COST) * MULT


def stats(dates, u):
    cum = np.concatenate([[0.0], np.cumsum(u)]); dd = -float((cum - np.maximum.accumulate(cum)).min())
    lbm = (dates >= pd.Timestamp(LB_FROM)).to_numpy()
    lb = u[lbm]; lcum = np.concatenate([[0.0], np.cumsum(lb)])
    ldd = -float((lcum - np.maximum.accumulate(lcum)).min())
    gw, gl = u[u > 0].sum(), -u[u < 0].sum()
    return dict(n=len(u), net=u.sum(), pf=gw / gl, dd=dd, mar=u.sum() / YRS / dd,
                roc=u.sum() / YRS / 1000.0, lbn=int(lbm.sum()), lb=lb.sum(), lbdd=ldd, lbroc=lb.sum() / 1000.0)


def main():
    L = ["TTM round 18b - BEFORE / AFTER for the staged book-leg switch and the 3 / 4 / 7 schedule   %s" % time.strftime("%Y-%m-%d %H:%M"),
         "window 2010-06-07..2026-06-30, lockbox from 2025-07-01, ES 30m RTH db_noadj_rth, 0.363 pts / contract, $50 a point",
         "ROC = net per year on $100,000; lockbox ROC = lockbox net on $100,000 (one year).", ""]
    variants = [
        ("BEFORE  #369 raw, flat 3x ladder (in the book now)", "TTMSQZ_3_0_ES30SSOF2.py", 1, "x3"),
        ("#369 raw, 3 / 4 / 7", "TTMSQZ_3_0_ES30SSOF2.py", 1, "347"),
        ("roll guard at #369 cell, flat 3x", "TTMSQZ_3_0_ES30SSOF2R.py", 1, "x3"),
        ("AFTER-A roll guard at #369 cell, 3 / 4 / 7", "TTMSQZ_3_0_ES30SSOF2R.py", 1, "347"),
        ("roll guard at #428 cell (cutoff 5), flat 3x", "TTMSQZ_3_0_ES30SSOF2R.py", 5, "x3"),
        ("AFTER-B roll guard at #428 cell, 3 / 4 / 7", "TTMSQZ_3_0_ES30SSOF2R.py", 5, "347"),
    ]
    H = "  %-50s %4s %10s %5s %8s %5s %6s   %3s %9s %8s %6s"
    L.append("LEG (book weight applied)")
    L.append(H % ("variant", "n", "net $", "PF", "DD $", "MAR", "ROC%", "LBn", "LB $", "LB DD $", "LBROC%"))
    cache, legdaily = {}, {}
    for name, fn, eod, mode in variants:
        k = (fn, eod)
        if k not in cache:
            cache[k] = leg_trades(fn, eod)
        df = cache[k]
        u = usd(df, mode)
        s = stats(df["date"], u)
        legdaily[name] = pd.Series(u, index=df["date"]).groupby(level=0).sum()
        L.append(H % (name, s["n"], "{:,.0f}".format(s["net"]), "%.2f" % s["pf"], "{:,.0f}".format(s["dd"]),
                      "%.2f" % s["mar"], "%.1f" % s["roc"], s["lbn"], "{:,.0f}".format(s["lb"]),
                      "{:,.0f}".format(s["lbdd"]), "%.1f" % s["lbroc"]))
        print(L[-1], flush=True)
    L.append("")
    L.append("PAPER BOOK FIGURE (ORB 234 + ENGU-Q 309, one NQ contract each, + the TTM leg above); only TTM varies")
    B = "  %-50s %11s %9s %6s %11s %9s"
    L.append(B % ("book", "net $", "DD $", "MAR", "LB $", "LB DD $"))
    base = r8.baseline_daily()
    for name, *_ in variants:
        daily = base.add(legdaily[name], fill_value=0.0).sort_index()
        b = r8.book_score(daily)
        L.append(B % (name, "{:,.0f}".format(b["net"]), "{:,.0f}".format(b["dd"]), "%.3f" % b["mar"],
                      "{:,.0f}".format(b["lb"]), "{:,.0f}".format(b["lbdd"])))
        print(L[-1], flush=True)
    L.append("")
    L.append("Size census (trades by recovered size, #369 cell guarded): " +
             ", ".join("%.2f=%d" % (k, int((cache[("TTMSQZ_3_0_ES30SSOF2R.py", 1)]["s"] == k).sum())) for k in LADDER))
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    open(LOG, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[-1:]), "\nlog ->", LOG)


if __name__ == "__main__":
    main()
