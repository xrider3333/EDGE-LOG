"""Is the house book still built on the right legs?

The book the paper report tracks is ORB #234 + ENGU-Q #309, one NQ contract each, plus three ES
contracts of the TTM leg. Those two NQ legs were the crowns when the book was defined - and both
crowns have since moved:

    ORB      #234 (ORB_3_6_C2.py)          ->  #314 (ORB_3_6_R6.py), crowned 2026-09-05 on RISK
    ENGU-Q   #309 (ENGUQ_1M_ETH_ER_1_0.py) ->  #335 (ENGUQ_1M_ETH_R2_1_0.py), crowned 2026-09-08

Every BOOK run from #336 to #361 kept the old pair deliberately, so that a TTM change was the only
thing moving between them. That was right for those comparisons and it leaves this question unasked:
would the book itself be better with the current crowns in it? Note the shop's own caveat on ORB
#314 - it was crowned on risk and earns about 5 percent LESS than #234 over five years - so this is
genuinely open in both directions.

THE BAR, written before the run, is the canonical one BOOK.md section 10 made standard today:
against the book in production, (1) annualised MAR at least 1.05x, (2) LOCKBOX drawdown within 5
percent, (3) lockbox net at least as large. The whole-run drawdown is reported as a CHECK, not a
gate, because it is set by one stretch of tape and a leg that sat that stretch out cannot move it.

This is a SCAN of saved daily profits, the same construction the round 7-11 stack reads use. Nothing
is crowned here; a composition that clears goes to a BOOK run for the record.

Log: tools/data/book_crown_refresh.txt
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
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest as engine_run
from api import paper as P

LOG = os.path.join(ROOT, "tools", "data", "book_crown_refresh.txt")
CACHE = os.path.join(ROOT, "tools", "data", "book_crown_refresh_legs.npz")
DATE_FROM, DATE_TO, LB_FROM = r8.DATE_FROM, r8.DATE_TO, r8.LB_FROM

# (key, strategy file, instrument, timeframe, session, params) - the four NQ legs plus the TTM leg
LEGS = [
    ("ORB_234",   "ORB_3_6_C2.py",             "NQ", "5m",  "rth", P.ORB_234,   0.533, 20.0),
    ("ORB_314",   "ORB_3_6_R6.py",             "NQ", "5m",  "rth", P.ORB_314,   0.533, 20.0),
    ("ENGUQ_309", "ENGUQ_1M_ETH_ER_1_0.py",    "NQ", "1m",  "eth", P.ENGUQ_309, 0.533, 20.0),
    ("ENGUQ_335", "ENGUQ_1M_ETH_R2_1_0.py",    "NQ", "1m",  "eth", None,        0.533, 20.0),
    ("TTM_SS",    "TTMSQZ_3_0_ES30SS20.py",    "ES", "30m", "rth", dict(kc_mult=1.5, eod_cutoff=1), 0.363, 50.0),
]


def leg_daily():
    """Cost-inclusive dollars per calendar day for every leg, cached - the ENGU-Q legs are slow."""
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        return {k: pd.Series(z[k + "_v"], index=pd.to_datetime(z[k + "_d"])) for k in z["keys"]}
    out, store = {}, {"keys": np.array([l[0] for l in LEGS], object)}
    for key, fn, inst, tf, sess, params, cost, mult in LEGS:
        t0 = time.time()
        arrays = load_master_arrays(find_master(inst, tf, sess), date_from=DATE_FROM, date_to=DATE_TO)
        res = engine_run(fn, arrays=arrays, params=dict(params) if params else {},
                         cost_pts=cost, return_trades=True)
        tr = [(int(t[0]), int(t[1]), float(t[2])) for t in (res or {}).get("trades") or []]
        usd = np.array([t[2] for t in tr]) * mult
        dates = pd.DatetimeIndex(arrays["index"])[[t[1] for t in tr]].tz_localize(None).normalize()
        s = pd.Series(usd, index=dates).groupby(level=0).sum()
        out[key] = s
        store[key + "_v"] = s.values
        store[key + "_d"] = s.index.values.astype("datetime64[ns]")
        print("  %-10s %-26s %5d trades  $%10s  %4.0fs" % (
            key, fn, len(tr), "{:,.0f}".format(usd.sum()), time.time() - t0), flush=True)
    np.savez(CACHE, **store)
    return out


def main():
    L = ["IS THE HOUSE BOOK STILL BUILT ON THE RIGHT LEGS?   %s" % time.strftime("%Y-%m-%d %H:%M"),
         "window %s..%s, lockbox from %s; NQ 0.533 pts a round trip and 20 dollars a point, ES 0.363 and 50"
         % (DATE_FROM, DATE_TO, LB_FROM),
         "BAR (canonical, BOOK.md section 10): vs the book in production - ann. MAR >= x1.05, LOCKBOX drawdown",
         "within 5 percent, lockbox net at least as large. Whole-run drawdown is a CHECK, not a gate."]
    print("\n".join(L), flush=True)
    L.append("")
    L.append("LEGS (each on its own tape, one contract, cost-inclusive):")
    print(L[-1], flush=True)
    d = leg_daily()
    for key, fn, inst, tf, sess, params, cost, mult in LEGS:
        s = d[key]
        cum = s.cumsum().values
        dd = -float((cum - np.maximum.accumulate(cum)).min())
        L.append("  %-10s %-26s %-3s %-4s  net $%10s  DD $%9s  days %5d" % (
            key, fn, inst, tf, "{:,.0f}".format(s.sum()), "{:,.0f}".format(dd), len(s)))
        print(L[-1], flush=True)

    def book(orb, enguq, ttm_w=3.0):
        return (d[orb].add(d[enguq], fill_value=0.0)
                .add(d["TTM_SS"] * ttm_w, fill_value=0.0).sort_index())

    prod = book("ORB_234", "ENGUQ_309")
    sp = r8.book_score(prod)
    H = "  %-40s %11s %9s %6s %6s %11s %6s %9s %6s %6s  %s"
    L.append("")
    L.append(H % ("book", "net $", "DD $", "MAR", "xMAR", "lockbox $", "xLB", "LB DD $", "xLBDD", "yrs+", "verdict"))
    print(L[-1], flush=True)

    def emit(nm, daily, verdict=None):
        s = r8.book_score(daily)
        if verdict is None:
            c1 = s["mar"] >= sp["mar"] * 1.05
            c2 = s["lbdd"] <= sp["lbdd"] * 1.05
            c3 = s["lb"] >= sp["lb"]
            verdict = "CLEARS all three" if (c1 and c2 and c3) else "no (%s)" % ", ".join(
                x for x, ok in (("MAR", c1), ("LB drawdown", c2), ("LB net", c3)) if not ok)
        L.append(H % (nm, "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]), "%.3f" % s["mar"],
                      "%.3f" % (s["mar"] / sp["mar"]), "{:,.0f}".format(s["lb"]), "%.3f" % (s["lb"] / sp["lb"]),
                      "{:,.0f}".format(s["lbdd"]), "%.3f" % (s["lbdd"] / sp["lbdd"]),
                      "%d/%d" % (s["ypos"], s["ny"]), verdict))
        print(L[-1], flush=True)
        return s

    emit("IN PRODUCTION: ORB 234 + ENGU-Q 309 + 3 TTM", prod, "the thing to beat")
    emit("ORB 314 (current crown) swapped in", book("ORB_314", "ENGUQ_309"))
    emit("ENGU-Q 335 (current crown) swapped in", book("ORB_234", "ENGUQ_335"))
    emit("BOTH current crowns", book("ORB_314", "ENGUQ_335"))
    L.append("")
    L.append("AND WITHOUT THE TTM LEG, so the NQ pair can be read on its own:")
    print(L[-1], flush=True)
    for nm, o, e in (("ORB 234 + ENGU-Q 309 (the old pair)", "ORB_234", "ENGUQ_309"),
                     ("ORB 314 + ENGU-Q 335 (both crowns)", "ORB_314", "ENGUQ_335")):
        emit("  " + nm, book(o, e, ttm_w=0.0))
    # IS IT THE LEG, OR THE SIZE? ENGU-Q #335 trades 2,843 times against #309's 1,604 and carries a
    # bigger drawdown of its own, so at the book's flat 1.0 weight it may simply be too much leg
    # rather than the wrong leg. Weight is a risk decision, not a fitted knob (round 10), so this is
    # reported as a diagnostic - it does not turn a failing composition into a passing one.
    L.append("")
    L.append("IS IT THE LEG OR THE SIZE? ENGU-Q 335 at reduced weight, everything else in production.")
    L.append("READ THESE ROWS CAREFULLY: they REPLACE the 309 leg rather than adding to it, so a lower weight")
    L.append("means a SMALLER book, and the falling MAR is partly just less money. The like-for-like row is")
    L.append("weight 1.00, where 335 earns 434,721 dollars against 309 591,267 with a larger drawdown of its")
    L.append("own - less money and more risk, before any book effect. The sweep is here to show that scaling")
    L.append("the leg down does not rescue it, not to suggest a weight that would.")
    print(L[-1], flush=True)
    for w in (0.25, 0.5, 0.75, 1.0):
        daily = (d["ORB_234"].add(d["ENGUQ_335"] * w, fill_value=0.0)
                 .add(d["TTM_SS"] * 3.0, fill_value=0.0).sort_index())
        emit("  ENGU-Q 335 at weight %.2f" % w, daily)
    L.append("")
    L.append("READ IT THIS WAY: the book in production is not stale, it is correct. Both NQ legs have been")
    L.append("superseded as CROWNS since the book was defined, and putting either current crown into the book")
    L.append("makes the book worse - ORB 314 costs 7 percent of annualised MAR and 6 percent of the lockbox,")
    L.append("and ENGU-Q 335 more than doubles the whole-run drawdown, from 34,903 to 71,773 dollars, for a")
    L.append("lockbox drawdown 45 percent larger. That is not a criticism of either crown: each was crowned on")
    L.append("its own tape for its own reasons, and #335 does earn a bigger lockbox here. It is a statement")
    L.append("about BOOKS - the best leg on its own and the best leg for a book are different questions, and")
    L.append("this book's drawdown is bought by how its legs' bad stretches line up rather than by any one of")
    L.append("them. Reducing #335's weight recovers most of the damage without ever beating the incumbent,")
    L.append("which says the problem is the leg's shape in this company, not merely its size.")
    r8._lines_to(L, LOG)
    print("log ->", LOG)


if __name__ == "__main__":
    main()
