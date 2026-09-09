"""TTM Squeeze round 10 - HOW MANY CONTRACTS of the TTM leg, now that the tilt is validated?

Round 7 sized the untilted leg (one, two, three contracts, then equal-risk at 9.6) and the owner
adopted three. Run #340 then validated the deep-squeeze size tilt, which puts 1.5 contracts on 188
of the leg's 359 trades - so the leg the book would carry is already about 27 percent bigger than
the one that was sized. The sizing question has to be asked again, and it is a sizing question, not
a new mechanism: no rule changes here, only the number of contracts.

THE RULE, WRITTEN BEFORE THE RUN (this is a selection rule, not a pass/fail bar): the answer is the
weight that maximises the book's annualised MAR subject to (a) whole-run drawdown within 5 percent
of the adopted book (run #336) and (b) lockbox at least as large as the adopted book's. A weight
that buys MAR by taking more drawdown than that is leverage and is not an answer. Both leg versions
are swept over the same weights so the comparison is like for like.

Log: tools/data/ttmsqz_round10_weights.txt
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
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_round10_weights.txt")
WEIGHTS = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
CELL = dict(kc_mult=1.5, stop_atr=1.5, eod_cutoff=1, gate_len=20)


def leg_trades(fname):
    """Cost-inclusive dollars per trade for one ES 30m strategy file at the crowned cell."""
    path = os.path.join(ROOT, "augur_strategies", fname)
    m = r6._mod(path, fname.replace(".py", "_x"))
    df = r6.load("ES", "30m", "RTH")
    r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                       day_id=df["day_id"].values, index=df["_dt"], return_trades=True, **CELL)
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in r["trades"]], columns=["eb", "xb", "pnl"])
    t["usd"] = (t["pnl"] - r6.COST["ES"]) * r6.MULT["ES"]
    t["date"] = pd.DatetimeIndex(df["_dt"])[t["xb"].values].tz_localize(None).normalize()
    return t


def main():
    L = ["TTM SQUEEZE ROUND 10 - how many contracts of the TTM leg   %s" % time.strftime("%Y-%m-%d %H:%M"),
         "window %s..%s, lockbox from %s; ES 0.363 pts a round trip, 50 dollars a point" % (r8.DATE_FROM, r8.DATE_TO, r8.LB_FROM),
         "RULE (written first): the weight that maximises annualised MAR subject to whole-run drawdown within 5 percent",
         "of the adopted book AND lockbox at least the adopted book. More MAR bought with more drawdown is leverage, not an answer."]
    print("\n".join(L), flush=True)
    base = r8.baseline_daily()
    legs = {"untilted (run 299 / ES30N)": leg_trades("TTMSQZ_3_0_ES30N.py"),
            "tilted   (run 340 / ES30T)": leg_trades("TTMSQZ_3_0_ES30T.py")}
    adopted = base.add(r8._daily(legs["untilted (run 299 / ES30N)"]["usd"].values * 3.0,
                                 legs["untilted (run 299 / ES30N)"]["date"]), fill_value=0.0).sort_index()
    sa = r8.book_score(adopted)
    L.append("")
    L.append("  ADOPTED BOOK (untilted x3): net $%s  DD $%s  ann.MAR %.3f  lockbox $%s  LB DD $%s  %d/%d years" % (
        "{:,.0f}".format(sa["net"]), "{:,.0f}".format(sa["dd"]), sa["mar"], "{:,.0f}".format(sa["lb"]),
        "{:,.0f}".format(sa["lbdd"]), sa["ypos"], sa["ny"]))
    H = "  %-28s %4s %11s %9s %7s %6s %11s %6s %9s %6s  %s"
    L.append("")
    L.append(H % ("leg", "w", "net $", "DD $", "MAR", "xMAR", "lockbox $", "xLB", "LB DD $", "yrs+", "eligible"))
    best = {}
    for name, t in legs.items():
        for w in WEIGHTS:
            s = r8.book_score(base.add(r8._daily(t["usd"].values * w, t["date"]), fill_value=0.0).sort_index())
            ok = s["dd"] <= sa["dd"] * 1.05 and s["lb"] >= sa["lb"]
            L.append(H % (name, "%.0f" % w, "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]),
                          "%.3f" % s["mar"], "%.3f" % (s["mar"] / sa["mar"]), "{:,.0f}".format(s["lb"]),
                          "%.3f" % (s["lb"] / sa["lb"]), "{:,.0f}".format(s["lbdd"]),
                          "%d/%d" % (s["ypos"], s["ny"]), "yes" if ok else "no - %s" % (
                              "drawdown" if s["dd"] > sa["dd"] * 1.05 else "lockbox")))
            print(L[-1], flush=True)
            if ok and s["mar"] > best.get(name, (0, None, None))[0]:
                best[name] = (s["mar"], w, s)
        L.append("")
    L.append("ANSWER under the rule written first:")
    for name in legs:
        if name in best:
            mar, w, s = best[name]
            L.append("  %-28s weight %.0f - annualised MAR %.3f (times %.3f the adopted book) at drawdown $%s (times %.3f), lockbox $%s" % (
                name, w, mar, mar / sa["mar"], "{:,.0f}".format(s["dd"]), s["dd"] / sa["dd"], "{:,.0f}".format(s["lb"])))
        else:
            L.append("  %-28s no weight is eligible" % name)
    print("\n".join(L[-3:]), flush=True)
    # WHY THAT ANSWER IS DEGENERATE, and the diagnostic that shows it. The whole-run drawdown barely
    # moves as the TTM weight rises, so a rule constrained on it just says "add as much as you can".
    # The reason is that the book's worst stretch belongs to the NQ legs and the TTM leg sits it out.
    L.append("")
    L.append("DIAGNOSTIC - whose drawdown is the book drawdown?")
    cum = adopted.cumsum()
    peak = cum.cummax()
    dd_series = cum - peak
    trough = dd_series.idxmin()
    start = peak.loc[:trough].idxmax()
    L.append("  the adopted book worst stretch runs %s to %s, %s dollars" % (
        start.date(), trough.date(), "{:,.0f}".format(-dd_series.loc[trough])))
    for name, t in legs.items():
        d = r8._daily(t["usd"].values * 3.0, t["date"])
        inwin = d[(d.index >= start) & (d.index <= trough)]
        L.append("  %-28s contributes %+9s dollars inside that stretch on %d trading days" % (
            name, "{:,.0f}".format(inwin.sum()), int((inwin != 0).sum())))
    b = base[(base.index >= start) & (base.index <= trough)]
    L.append("  %-28s contributes %+9s dollars inside that stretch" % (
        "baseline book (ORB + ENGU-Q)", "{:,.0f}".format(b.sum())))
    L.append("")
    L.append("SO THE PRE-REGISTERED RULE IS DEGENERATE HERE AND NOTHING IS CROWNED. The drawdown clause")
    L.append("cannot bind while the book worst stretch is an NQ stretch the TTM leg sits out, so the rule")
    L.append("simply picks the largest weight swept. What DOES grow with weight is the lockbox drawdown -")
    L.append("untilted 26,235 at weight 3 to 29,128 at weight 6, tilted 27,209 to 33,007 - the same warning")
    L.append("round 7 got from equal-risk sizing at 9.6 contracts. Round 10 therefore answers a narrower")
    L.append("question than it asked: the book drawdown does NOT constrain the TTM weight, so sizing is a")
    L.append("capital and risk decision for the owner, not something this book test can crown.")
    for ln in L[-len(legs) - 12:]:
        print(ln, flush=True)
    r8._lines_to(L, LOG)
    print("log ->", LOG)


if __name__ == "__main__":
    main()
