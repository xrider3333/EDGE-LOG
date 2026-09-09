"""TTM Squeeze round 11 - can the tilted leg actually be TRADED, and does it survive worse fills?

The owner swapped the paper book onto the tilted TTM leg on 2026-09-09. The tilt is 1.5 contracts on
a deep-squeeze entry, and the book carries the leg at weight 3 - which means 4.5 contracts on a deep
entry. THERE IS NO HALF ES CONTRACT. Nobody has yet asked what a person actually types into the
order ticket, and a validated edge that cannot be expressed in whole contracts is not an edge you
own. That is part A.

Part B is the other question a freshly adopted leg should have to answer: what happens when the
fills are worse than the house 0.363 points a round trip.

NOTHING IS CROWNED HERE. Part A is a feasibility read - which whole-contract schedule reproduces the
validated leg most closely, measured against the IDEAL (fractional) tilt, not against a bar. Part B
is a robustness read at four cost levels. Both were specified before the run.

Schedules tested (base contracts -> contracts on a deep-squeeze entry):
  3 -> 4.5   the ideal the validate measured, unattainable in ES
  2 -> 3     exactly 1.5x in whole contracts, at two thirds the size
  4 -> 6     exactly 1.5x in whole contracts, at four thirds the size
  3 -> 4     1.33x, the nearest whole schedule below the ideal
  3 -> 5     1.67x, the nearest whole schedule above it
  30 -> 45   MES micros (one tenth of an ES), which CAN express 1.5x at book size
  3 -> 3     the untilted control

Log: tools/data/ttmsqz_round11_execution.txt
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
r8 = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("r8", os.path.join(ROOT, "tools", "ttmsqz_round8_crown.py")))
r8.__spec__.loader.exec_module(r8)
r6 = r8.r6
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_round11_execution.txt")
CELL = dict(kc_mult=1.5, stop_atr=1.5, eod_cutoff=1, gate_len=20)
DEEP_THR = 0.85
ES_MULT, ES_COST = 50.0, 0.363
MES_MULT, MES_COST = 5.0, 0.50      # micro ES: a tenth the point value, a wider round trip

# (label, base contracts, deep contracts, dollars per point, cost points per round trip)
SCHEDULES = [
    ("ideal 3 -> 4.5 (what the validate measured)", 3.0, 4.5, ES_MULT, ES_COST),
    ("whole 2 -> 3   (exactly 1.5x, smaller)", 2.0, 3.0, ES_MULT, ES_COST),
    ("whole 4 -> 6   (exactly 1.5x, bigger)", 4.0, 6.0, ES_MULT, ES_COST),
    ("whole 3 -> 4   (1.33x, nearest below)", 3.0, 4.0, ES_MULT, ES_COST),
    ("whole 3 -> 5   (1.67x, nearest above)", 3.0, 5.0, ES_MULT, ES_COST),
    ("micros 30 -> 45 MES (1.5x at book size)", 30.0, 45.0, MES_MULT, MES_COST),
    ("untilted 3 -> 3 (the control)", 3.0, 3.0, ES_MULT, ES_COST),
]
COSTS = [0.363, 0.50, 0.75, 1.00]


def crown_trades():
    """Raw (pre-cost) points per trade for the crown cell, plus the deep-squeeze flag at the
    decision bar. Everything below is priced from these, so no schedule re-runs the backtest."""
    m = r6._mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30N.py"), "es30n_r11")
    df = r6.load("ES", "30m", "RTH")
    r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                       day_id=df["day_id"].values, index=df["_dt"], return_trades=True, **CELL)
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in r["trades"]], columns=["eb", "xb", "pts"])
    ratio = r8.compression_ratio(df, 60)
    rr = ratio[np.clip(t["eb"].values - 1, 0, len(ratio) - 1)]
    t["deep"] = np.isfinite(rr) & (rr <= DEEP_THR)
    t["date"] = pd.DatetimeIndex(df["_dt"])[t["xb"].values].tz_localize(None).normalize()
    return t


def priced(t, base, deep, mult, cost):
    """Dollars per trade for a contract schedule: each contract pays its own round trip."""
    n = np.where(t["deep"].values, deep, base)
    return (t["pts"].values - cost) * n * mult


def main():
    L = ["TTM SQUEEZE ROUND 11 - can the tilted leg be traded in whole contracts, and does it survive worse fills?   %s"
         % time.strftime("%Y-%m-%d %H:%M"),
         "window %s..%s, lockbox from %s. NOTHING IS CROWNED: part A is a feasibility read against the IDEAL tilt,"
         % (r8.DATE_FROM, r8.DATE_TO, r8.LB_FROM),
         "part B a robustness read at four cost levels. Both specified before the run."]
    print("\n".join(L), flush=True)
    t = crown_trades()
    L.append("")
    L.append("  %d trades, %d of them deep-squeeze entries (%.0f percent)" % (
        len(t), int(t["deep"].sum()), 100 * t["deep"].mean()))
    base_book = r8.baseline_daily()
    adopted = base_book.add(r8._daily(priced(t, 3.0, 3.0, ES_MULT, ES_COST), t["date"]), fill_value=0.0).sort_index()
    sa = r8.book_score(adopted)
    ideal = base_book.add(r8._daily(priced(t, 3.0, 4.5, ES_MULT, ES_COST), t["date"]), fill_value=0.0).sort_index()
    si = r8.book_score(ideal)

    L.append("")
    L.append("PART A - whole-contract schedules, the leg alone and then inside the book")
    H = "  %-42s %11s %8s %6s %9s | %11s %8s %6s %10s %7s %7s"
    L.append(H % ("schedule", "leg net $", "leg DD", "leg PF", "leg LB $", "BOOK net $", "BOOK DD", "MAR",
                  "BOOK LB $", "xMAR", "xIDEAL"))
    for label, b, d, mult, cost in SCHEDULES:
        usd = priced(t, b, d, mult, cost)
        cum = np.concatenate([[0.0], np.cumsum(usd)])
        dd = -float((cum - np.maximum.accumulate(cum)).min())
        gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
        lbm = t["date"].values >= np.datetime64(r8.LB_FROM)
        s = r8.book_score(base_book.add(r8._daily(usd, t["date"]), fill_value=0.0).sort_index())
        L.append(H % (label, "{:,.0f}".format(usd.sum()), "{:,.0f}".format(dd), "%.2f" % (gw / gl),
                      "{:,.0f}".format(usd[lbm].sum()), "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]),
                      "%.3f" % s["mar"], "{:,.0f}".format(s["lb"]), "%.3f" % (s["mar"] / sa["mar"]),
                      "%.3f" % (s["mar"] / si["mar"])))
        print(L[-1], flush=True)

    L.append("")
    L.append("PART B - what worse fills do to the leg (whole run, one contract, tilt on and off)")
    L.append("  %-30s %11s %8s %6s %9s %8s" % ("cost per round trip", "net $", "DD $", "PF", "lockbox $", "LB PF"))
    for c in COSTS:
        for label, b, d in (("untilted", 1.0, 1.0), ("tilted 1.5x on deep", 1.0, 1.5)):
            usd = priced(t, b, d, ES_MULT, c)
            cum = np.concatenate([[0.0], np.cumsum(usd)])
            dd = -float((cum - np.maximum.accumulate(cum)).min())
            gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
            lbm = t["date"].values >= np.datetime64(r8.LB_FROM)
            lu = usd[lbm]
            lpf = (lu[lu > 0].sum() / -lu[lu < 0].sum()) if (lu < 0).any() else float("inf")
            L.append("  %-30s %11s %8s %6.2f %9s %8s" % (
                "%.3f pts (%s%.0f a trade) %s" % (c, "$", c * ES_MULT, label),
                "{:,.0f}".format(usd.sum()), "{:,.0f}".format(dd), gw / gl,
                "{:,.0f}".format(lu.sum()), "%.2f" % min(lpf, 99)))
            print(L[-1], flush=True)
    r8._lines_to(L, LOG)
    print("log ->", LOG)


if __name__ == "__main__":
    main()
